#!/usr/bin/env python3
"""R92: evidence coverage at fixed persistent source+index storage budgets.

Uses original SHA-locked SciFact and standard FTS5/BM25. Compare:
  (A) full-content source-readable SQLite FTS5,
  (B) SHA-verified compressed-source + ordinary contentless FTS5,
  (C) matched full-content and compressed SOURCE SUBSETS,
  (D) compact full corpus vs budget-fitting conventional subset.

No gold evidence IDs enter document selection; no generated answers are scored.
Human labels are used ONLY to evaluate retrieved gold evidence sources.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-83"))
sys.path.insert(0,str(HERE.parent/"round-86"))
sys.path.insert(0,str(HERE.parent/"round-87"))
sys.path.insert(0,str(HERE.parent/"round-90"))
from scifact_data_probe import fetch,parse,digests
from contentless_cas import (
    make_fts, query_fts, document_bytes,EXPECTED_RELEASE_SHA
)
from old_source_incremental import create_legacy_contentless
from atomic_source_db import read
from snapshot_kill_probe import retrieve_snapshot

SEEDS=(11,23,37,53,71)
BUDGETS_BYTES=(10*1024**2,12*1024**2)
K=(1,3,5,10)
BOOTSTRAPS=1500
SELECTION_SALT="CDG-R92-v1-UNLABELLED-ROW-PRIORITY"
ELIGIBLE_LABELS={"SUPPORT","CONTRADICT"}


def deterministic_order(corpus,seed):
    """A doc-id-only fixed hash permutation, independent of any gold labels."""
    if len({str(r["doc_id"]) for r in corpus})!=len(corpus):
        raise AssertionError("duplicate corpus document id")
    return sorted(corpus,key=lambda row:(
        hashlib.sha256((SELECTION_SALT+"|"+str(seed)+"|"
                        +str(row["doc_id"])).encode()).digest(),
        str(row["doc_id"])))


def annotated_gold(claims,corpus):
    corpus_ids={str(row["doc_id"]) for row in corpus}
    cases=[]
    for row in claims:
        label_by_doc={}
        for doc_id,rationales in (row.get("evidence") or {}).items():
            if str(doc_id) not in corpus_ids or not rationales:
                continue
            label_set={str(p["label"]) for p in rationales}
            if len(label_set)!=1 or not label_set<=ELIGIBLE_LABELS:
                raise AssertionError("unexpected ambiguous SciFact label")
            label_by_doc[str(doc_id)]=next(iter(label_set))
        if label_by_doc:
            cases.append({
                "id":str(row["id"]),
                "claim":str(row["claim"]),
                "gold":set(label_by_doc),
                "labels":label_by_doc,
            })
    if len({x["id"] for x in cases})!=len(cases):
        raise AssertionError("claim id repeated")
    return cases


def rankings(db,corpus,claims,compressed):
    """Same BM25 policy; return *doc IDs*, not rowids, and SHA-verify sources."""
    ids={rid+1:str(row["doc_id"]) for rid,row in enumerate(corpus)}
    out={}
    receipt=0
    start=time.perf_counter()
    for case in claims:
        if compressed:
            rows=retrieve_snapshot(db,case["claim"],10)
            rowids=[rid for rid,_ in rows]
            # Reading the same transaction's results is already SHA verified.
            for rid,source in rows[:1]:
                if source["source_bytes"]!=document_bytes(corpus[rid-1]):
                    raise AssertionError("compressed source changed original bytes")
                if source["doc_id"]!=ids[rid]:
                    raise AssertionError("compressed source identity changed")
                receipt+=1
        else:
            rowids=query_fts(db,case["claim"],10)
            for rid in rowids[:1]:
                title,abstract=db.execute(
                    "SELECT title,abstract FROM sources WHERE rowid=?",
                    (rid,)).fetchone()
                if title!=corpus[rid-1]["title"] or abstract!=" ".join(
                        corpus[rid-1]["abstract"]):
                    raise AssertionError("full FTS indexed source changed")
                receipt+=1
        out[str(case["id"])]=[ids[rid] for rid in rowids]
    return out,{"queries":len(claims),"top_one_verified_reads":receipt,
                "warm_query_and_receipt_wall_seconds":round(
                    time.perf_counter()-start,5)}


def recall(cases,ranking,retained_doc_ids):
    if not cases:raise ValueError("no gold-labelled evidence claims")
    relevant=0
    per_k={k:[] for k in K}
    splits={}
    for row in cases:
        available=bool(row["gold"] & retained_doc_ids)
        relevant+=int(available)
        res=ranking.get(row["id"],[])
        for k in K:
            per_k[k].append(int(bool(row["gold"].intersection(res[:k]))))
    for label in ("SUPPORT","CONTRADICT"):
        subset=[row for row in cases if label in row["labels"].values()]
        splits[label]={
            "eligible_claims":len(subset),
            "r1_hits":sum(bool(row["gold"]&set(ranking.get(row["id"],[])[:1]))
                          for row in subset),
            "r10_hits":sum(bool(row["gold"]&set(ranking.get(row["id"],[])[:10]))
                           for row in subset),
        }
    return {
        "eligible_claims":len(cases),
        "annotated_source_present_in_retained_corpus":relevant,
        "recall":{f"r{k}":{"hits":sum(per_k[k]),
                            "denominator":len(cases),
                            "rate":round(sum(per_k[k])/len(cases),6)}
                  for k in K},
        "by_gold_source_label":splits,
        "binary_hits":{str(k):per_k[k] for k in K},
    }


def bootstrap_diff(reference,alternative,reps=BOOTSTRAPS,seed=9201):
    """Paired per-claim difference. No independence across corpus seeds claim."""
    if len(reference)!=len(alternative) or not reference:
        raise ValueError("paired arrays mismatch")
    delta=[int(x)-int(y) for x,y in zip(reference,alternative)]
    rng=random.Random(seed)
    samples=[]
    for _ in range(reps):
        samples.append(sum(delta[rng.randrange(len(delta))]
                           for _ in delta)/len(delta))
    samples.sort()
    return {
        "percentage_point_gain":round(100*sum(delta)/len(delta),4),
        "claim_bootstrap_95pct_point_interval":[
            round(100*samples[int(.025*(reps-1))],4),
            round(100*samples[int(.975*(reps-1))],4)],
        "paired_claims":len(delta),
        "wins":sum(x>0 for x in delta),
        "losses":sum(x<0 for x in delta),
        "ties":sum(x==0 for x in delta),
        "caveat":"Fixed corpus selection, public dev claims, overlapping topics "
                 "and reused queries across seeds; descriptive not generalization CI",
    }


def conventional_prefix_size(directory,ordered,n,cache):
    if n in cache:return cache[n]
    if not 0<n<=len(ordered):raise ValueError("invalid subset count")
    path=directory/("prefix_"+str(n)+".sqlite")
    db,meta=make_fts(path,ordered[:n],False)
    db.close()
    value=path.stat().st_size
    path.unlink()
    cache[n]=value
    return value


def budget_prefix_count(directory,ordered,budget):
    """Find largest fitting *observed* nested hash prefix via binary search.

    This relies on practical near-monotonic SQLite database size as docs
    are added. Check chosen n+1 too. Not an optimal corpus selection proof.
    """
    cache={}
    lo,hi=0,len(ordered)
    while lo<hi:
        mid=(lo+hi+1)//2
        size=conventional_prefix_size(directory,ordered,mid,cache)
        if size<=budget:lo=mid
        else:hi=mid-1
    if lo<=0:raise AssertionError("no useful documents in budget")
    chosen_size=conventional_prefix_size(directory,ordered,lo,cache)
    if chosen_size>budget:raise AssertionError("selected corpus over budget")
    if lo<len(ordered):
        next_size=conventional_prefix_size(directory,ordered,lo+1,cache)
        if next_size<=budget:
            raise AssertionError("binary-search prefix capacity not maximal")
    return lo,chosen_size,{"sizes_measured":len(cache),
                           "selection_rule":"largest tested hash-ordered prefix",
                           "not_knapsack_optimal":True}


def one_seed(corpus,claims,cases,budgets,seed,full_comp_rank,full_comp_metrics):
    ordered=deterministic_order(corpus,seed)
    outcomes=[]
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        for budget in budgets:
            n,fit_size,search=budget_prefix_count(folder,ordered,budget)
            subset=ordered[:n]
            ids={str(row["doc_id"]) for row in subset}
            fp=folder/"full_subset.sqlite"
            cp=folder/"compressed_subset.sqlite"
            full,meta=make_fts(fp,subset,False)
            compressed=create_legacy_contentless(cp,subset)
            try:
                compressed_bytes=cp.stat().st_size
                if compressed_bytes>fit_size:
                    raise AssertionError("compressed matched subset bigger than full")
                if fit_size>budget:
                    raise AssertionError("contentful budget violated")
                f_rank,f_cost=rankings(full,subset,claims,False)
                c_rank,c_cost=rankings(compressed,subset,claims,True)
                if f_rank!=c_rank:
                    mismatch=[key for key in f_rank if f_rank[key]!=c_rank[key]]
                    raise AssertionError("matched-count compressed/full BM25 changed for "
                                         +repr(mismatch[:3]))
                observed=recall(cases,f_rank,ids)
                from_full=full_comp_metrics
                comparisons={
                    str(k):bootstrap_diff(
                        from_full["binary_hits"][str(k)],
                        observed["binary_hits"][str(k)],
                        seed=seed*100+k)
                    for k in (1,5,10)
                }
                outcomes.append({
                    "budget_bytes":budget,
                    "seed":seed,
                    "conventional_documents_fitting_budget":n,
                    "corpus_documents":len(corpus),
                    "conventional_source_index_bytes":fit_size,
                    "compressed_matched_subset_bytes":compressed_bytes,
                    "full_compressed_corpus_fits_budget":True,
                    "matched_subset_exact_top10_rankings":len(claims),
                    "source_checks":{"full":f_cost,"compressed":c_cost},
                    "observed_evidence_recall":{
                        k:v for k,v in observed.items() if k!="binary_hits"},
                    "full_compressed_vs_budget_conventional_paired":comparisons,
                    "search":search,
                })
            finally:
                full.close()
                compressed.close()
                fp.unlink(missing_ok=True)
                cp.unlink(missing_ok=True)
    return outcomes


def run(corpus,claims,budgets=BUDGETS_BYTES,seeds=SEEDS):
    if not corpus or not claims:raise ValueError("missing corpus or claims")
    if len({str(c["id"]) for c in claims})!=len(claims):
        raise ValueError("duplicate claim id")
    cases=annotated_gold(claims,corpus)
    with tempfile.TemporaryDirectory() as root:
        folder=Path(root)
        fp=folder/"full.sqlite"
        cp=folder/"compressed.sqlite"
        full,meta=make_fts(fp,corpus,False)
        compressed=create_legacy_contentless(cp,corpus)
        try:
            full_bytes=fp.stat().st_size
            compressed_bytes=cp.stat().st_size
            if compressed_bytes>=full_bytes:
                raise AssertionError("compression has no corpus-level storage savings")
            f_rank,f_cost=rankings(full,corpus,claims,False)
            c_rank,c_cost=rankings(compressed,corpus,claims,True)
            if f_rank!=c_rank:raise AssertionError("same full corpus changed rankings")
            full_metrics=recall(cases,c_rank,{str(row["doc_id"]) for row in corpus})
            for budget in budgets:
                if not compressed_bytes<=budget<full_bytes:
                    raise ValueError("requested budget is not discriminating: "+str(budget))
            outcomes=[]
            for seed in seeds:
                outcomes.extend(one_seed(corpus,claims,cases,budgets,seed,
                                         c_rank,full_metrics))
            return {
                "round":92,
                "config":{
                    "budgets_bytes":list(budgets),
                    "seeds":list(seeds),
                    "docs":len(corpus),
                    "queries":len(claims),
                    "annotated_claims":len(cases),
                    "document_selection":"SHA-256 hash of fixed salt, seed, doc_id only",
                    "selection_uses_gold_labels":False,
                    "retriever":"FTS5 unicode61 BM25 title5/body1, query OR up to 28 terms",
                    "full_source_bytes_retained":"SQLite FTS contentful source vs zlib6/SHA compressed docs",
                },
                "full_corpus":{
                    "conventional_FTS5_bytes":full_bytes,
                    "compressed_contentless_source_index_bytes":compressed_bytes,
                    "compressed_space_saving_pct":round(
                        100*(full_bytes-compressed_bytes)/full_bytes,4),
                    "equal_300_query_top10":True,
                    "full_source_readbacks":{"conventional":f_cost,
                                             "compressed":c_cost},
                    "human_gold_evidence_recall":{
                        k:v for k,v in full_metrics.items() if k!="binary_hits"},
                },
                "budget_experiments":outcomes,
                "scientific_limits":[
                    "No generated model answers, therefore no factuality or hallucination reduction claim",
                    "SciFact human gold applies to claim and explicitly annotated evidence doc, not other retrieved docs",
                    "Uniform hash-ordered subset is independent of gold but not a trained optimal document prioritization",
                    "Binary search assumes observed prefix database footprint near-monotonic; not optimal knapsack capacity",
                    "SQLite VACUUM static bytes only, no write journal peaks, history or cold SSD I/O",
                    "Original SciFact public dev data and reuse of common corpus across five seeds limit independence",
                    "Corpus compression alone changes index capacity under budget, not semantic ranking at matched doc count",
                    "No linked human-annotated generated response, no model inference time or token cost",
                ],
            }
        finally:
            full.close()
            compressed.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    p.add_argument("--synthetic",action="store_true")
    args=p.parse_args()
    if args.synthetic:
        corpus=[{"doc_id":i+1,"title":"alpha "+str(i),
                 "abstract":["some experiment notes repeated "*5+str(i)]}
                for i in range(25)]
        claims=[
            {"id":i,"claim":"alpha "+str(i),
             "evidence":{str(i+1):[{"label":"SUPPORT","sentences":[0]}]}}
            for i in range(10)]
        with tempfile.TemporaryDirectory() as root:
            f,meta=make_fts(Path(root)/"full.sqlite",corpus,False)
            c=create_legacy_contentless(Path(root)/"compressed.sqlite",corpus)
            f.close();c.close()
            compressed=(Path(root)/"compressed.sqlite").stat().st_size
            conventional=(Path(root)/"full.sqlite").stat().st_size
        # Small tests cannot necessarily discriminate source layouts on 4KiB pages;
        # use test functions directly instead of misleading tiny-capacity runs.
        print("SYNTHETIC_SIZE",json.dumps({
            "compressed":compressed,"conventional":conventional}))
        return
    tar,raw=fetch()
    if digests(tar)["sha256"]!=EXPECTED_RELEASE_SHA:
        raise AssertionError("immutable SciFact upstream changed")
    corpus,claims,_=parse(raw)
    result=run(corpus,claims)
    result["data_sha256"]=digests(tar)["sha256"]
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    summary={
        "sha":result["data_sha256"],
        "full_corpus":result["full_corpus"],
        "cases":[{
            "budget":row["budget_bytes"],
            "seed":row["seed"],
            "docs_fit":row["conventional_documents_fitting_budget"],
            "full_r1":result["full_corpus"]["human_gold_evidence_recall"]["recall"]["r1"]["hits"],
            "subset_r1":row["observed_evidence_recall"]["recall"]["r1"]["hits"],
            "full_r10":result["full_corpus"]["human_gold_evidence_recall"]["recall"]["r10"]["hits"],
            "subset_r10":row["observed_evidence_recall"]["recall"]["r10"]["hits"],
            "matched_source_rankings":row["matched_subset_exact_top10_rankings"],
            "delta":row["full_compressed_vs_budget_conventional_paired"],
        } for row in result["budget_experiments"]],
    }
    print("ROUND92",json.dumps(summary,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
