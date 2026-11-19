#!/usr/bin/env python3
"""R95: joint evidence prioritization and source representation under tight budgets.

On original SHA-locked SciFact, BOTH ordinary source-readable FTS5 and
contentless FTS5+SHA/zlib6 source archives must discard some documents
under 6/8 MiB SQLite file budgets. Fit priorities on train-fit only;
choose architecture-specific policy using claim-disjoint train-validation;
evaluate dev without using dev labels/text for policy choice.
No model answers generated, all ranking/source integrity checks intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sqlite3
import statistics
import sys
import tempfile
import time
import zlib
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-83","round-84","round-86","round-90","round-92","round-93"):
    sys.path.insert(0,str(HERE.parent/r))
from scifact_data_probe import fetch,parse,digests
from retrieval_ablation import train_claims_from_verified_archive
from contentless_cas import make_fts,document_bytes,EXPECTED_RELEASE_SHA
from old_source_incremental import create_legacy_contentless
from storage_budget_eval import annotated_gold,recall,rankings,bootstrap_diff
from train_budget_selection import (
    split_train_claims,train_gold_sources,train_query_relevance,
    title_rarity_scores,source_disjoint_dev,tie_hash
)

BUDGETS=(6*1024*1024,8*1024*1024)
SEEDS=(11,37,71)
POLICIES=("hash","fit_rrf","fit_rrf_per_stored_byte",
          "fit_evidence_per_stored_byte","unsupervised_title_rarity")
ARCHITECTURES=("conventional","compressed")
TOKEN_SALT="CDG-R95-v1-train-only-priority"
MAX_K=10


def doc_cost_proxy(row,architecture):
    """Proxy is used ONLY for order, never to claim exact per-doc SQLite size."""
    data=document_bytes(row)
    tokens=len(data.split())
    source_bytes=len(data) if architecture=="conventional" else len(zlib.compress(data,6))+32
    # Constant 256 approximates per-row SQLite and FTS metadata.
    # 2*words is a rough posting cost; actual byte limit checks full database.
    return 256+2*tokens+source_bytes


def ranked_corpus(corpus,policy,architecture,seed,signals):
    if policy not in POLICIES or architecture not in ARCHITECTURES:
        raise ValueError("unrecognized fixed policy or architecture")
    rrf=signals["fit_rrf"]
    freq=signals["fit_gold_frequency"]
    rarity=signals["title_rarity"]
    def sort_key(row):
        did=str(row["doc_id"])
        t=tie_hash(did,seed)
        if policy=="hash":
            return (t,)
        if policy=="fit_rrf":
            return (-rrf.get(did,0.0),t)
        if policy=="fit_rrf_per_stored_byte":
            score=(rrf.get(did,0.0)/doc_cost_proxy(row,architecture)
                   if rrf.get(did,0.0)>0 else 0.0)
            return (-score,t)
        if policy=="fit_evidence_per_stored_byte":
            score=(freq.get(did,0)/doc_cost_proxy(row,architecture)
                   if freq.get(did,0)>0 else 0.0)
            return (-score,t)
        return (-rarity[did],t)
    ranked=sorted(corpus,key=sort_key)
    if len({str(x["doc_id"]) for x in ranked})!=len(corpus):
        raise AssertionError("ordered source ids were not unique")
    return ranked


def build_source_index(path,corpus,architecture):
    """Build the *entire* retained source+FTS database with matched policy."""
    if architecture=="conventional":
        conn,_=make_fts(path,corpus,False)
    elif architecture=="compressed":
        conn=create_legacy_contentless(path,corpus)
    else:
        raise ValueError("invalid architecture")
    return conn


def prefix_bytes(folder,ordered,architecture,n,cache):
    key=(architecture,n)
    if key in cache:
        return cache[key]
    if not 1<=n<=len(ordered):
        raise ValueError("invalid prefix length")
    filename=folder/f"prefix-{architecture}-{n}.sqlite"
    conn=build_source_index(filename,ordered[:n],architecture)
    try:
        count=conn.execute("PRAGMA page_count").fetchone()[0]
        value=filename.stat().st_size
        if count*conn.execute("PRAGMA page_size").fetchone()[0]!=value:
            raise AssertionError("unexpected non-main SQLite page accounting")
    finally:
        conn.close()
        filename.unlink(missing_ok=True)
    cache[key]=value
    return value


def max_prefix_under_budget(folder,ordered,architecture,budget,cache):
    """Find largest observed fitting prefix, check its successor explicitly.

    SQLite size can exhibit page-size steps and non-monotone FTS merge effects,
    so this is *not* guaranteed global optimum. Fail on immediate violation.
    """
    low,high=0,len(ordered)
    while low<high:
        middle=(low+high+1)//2
        observed=prefix_bytes(folder,ordered,architecture,middle,cache)
        if observed<=budget:
            low=middle
        else:
            high=middle-1
    if low<1:
        raise AssertionError("budget cannot store one document")
    taken=prefix_bytes(folder,ordered,architecture,low,cache)
    if taken>budget:
        raise AssertionError("accepted over-budget database")
    if low<len(ordered):
        next_size=prefix_bytes(folder,ordered,architecture,low+1,cache)
        if next_size<=budget:
            raise AssertionError("next prefix fits, binary search wrong")
    return low,taken


def metric_view(metrics):
    return {
        "annotated_claims":metrics["eligible_claims"],
        "source_available":metrics["annotated_source_present_in_retained_corpus"],
        "r1_hits":metrics["recall"]["r1"]["hits"],
        "r5_hits":metrics["recall"]["r5"]["hits"],
        "r10_hits":metrics["recall"]["r10"]["hits"],
    }


def one_policy(corpus,fit_validation,dev,validation_gold,dev_gold,disjoint,
               signals,policy,seed,budgets=BUDGETS):
    """One ordering per architecture and two prefix limits, not tuned on dev."""
    out=[]
    for arch in ARCHITECTURES:
        order=ranked_corpus(corpus,policy,arch,seed,signals)
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            cache={}
            for budget in budgets:
                n,actual_bytes=max_prefix_under_budget(
                    folder,order,arch,budget,cache)
                chosen=order[:n]
                if n==len(corpus):
                    raise AssertionError(
                        "R95 required budget to bind both architecture choices")
                db_path=folder/"source.sqlite"
                db=build_source_index(db_path,chosen,arch)
                try:
                    read_bytes=db_path.stat().st_size
                    if read_bytes!=actual_bytes or read_bytes>budget:
                        raise AssertionError("actual persisted database bytes drifted")
                    validation_rank,val_latency=rankings(db,chosen,fit_validation,arch=="compressed")
                    dev_rank,dev_latency=rankings(db,chosen,dev,arch=="compressed")
                    chosen_ids={str(row["doc_id"]) for row in chosen}
                    val_metrics=recall(validation_gold,validation_rank,chosen_ids)
                    dev_metrics=recall(dev_gold,dev_rank,chosen_ids)
                    dis_metrics=recall(disjoint,dev_rank,chosen_ids)
                    out.append({
                        "policy":policy, "architecture":arch, "seed":seed,
                        "budget":budget, "corpus_docs":len(corpus),
                        "docs_retained":n, "db_bytes":actual_bytes,
                        "total_source_utf8_bytes_retained":sum(
                            len(document_bytes(r)) for r in chosen),
                        "validation":metric_view(val_metrics),
                        "development":metric_view(dev_metrics),
                        "dev_disjoint":metric_view(dis_metrics),
                        "dev_binary_r1":dev_metrics["binary_hits"]["1"],
                        "dev_binary_r10":dev_metrics["binary_hits"]["10"],
                        "dev_source_reads_verified":dev_latency["top_one_verified_reads"],
                        "warm_dev_source_query_wall_sec":dev_latency[
                            "warm_query_and_receipt_wall_seconds"],
                    })
                finally:
                    db.close()
                    db_path.unlink(missing_ok=True)
    return out


def select_validation_policy(rows,architecture,budget,seeds=SEEDS):
    """Policies selected *only* on claim-disjoint TRAIN validation evidence."""
    trial=[]
    for p in POLICIES:
        sub=[x for x in rows if x["architecture"]==architecture
             and x["budget"]==budget and x["policy"]==p]
        if sorted(x["seed"] for x in sub)!=sorted(seeds):
            raise AssertionError("missing predeclared validation seed")
        r10=statistics.mean(x["validation"]["r10_hits"] for x in sub)
        r1=statistics.mean(x["validation"]["r1_hits"] for x in sub)
        trial.append((r10,r1,p))
    best=sorted(trial,key=lambda x:(-x[0],-x[1],x[2]))[0]
    return {
        "architecture":architecture, "budget":budget,
        "winner":best[2],
        "validation_r10_mean_hits":round(best[0],4),
        "validation_r1_mean_hits":round(best[1],4),
        "uses_development_outcomes":False,
    }


def within_seed_pair(rows,selected,budget,seeds=SEEDS):
    out=[]
    for seed in seeds:
        matched={}
        for arch in ARCHITECTURES:
            policy=selected[(arch,budget)]["winner"]
            match=[r for r in rows if r["architecture"]==arch
                   and r["budget"]==budget and r["seed"]==seed
                   and r["policy"]==policy]
            if len(match)!=1:
                raise AssertionError("expected one selected arm")
            matched[arch]=match[0]
        compact=matched["compressed"]
        full=matched["conventional"]
        out.append({
            "budget":budget,"seed":seed,
            "compressed_policy":compact["policy"],
            "conventional_policy":full["policy"],
            "compressed_docs":compact["docs_retained"],
            "conventional_docs":full["docs_retained"],
            "compressed_bytes":compact["db_bytes"],
            "conventional_bytes":full["db_bytes"],
            "compressed_r1":compact["development"]["r1_hits"],
            "conventional_r1":full["development"]["r1_hits"],
            "compressed_r10":compact["development"]["r10_hits"],
            "conventional_r10":full["development"]["r10_hits"],
            "compressed_source_disjoint_r10":compact["dev_disjoint"]["r10_hits"],
            "conventional_source_disjoint_r10":full["dev_disjoint"]["r10_hits"],
            "r1_delta":bootstrap_diff(
                compact["dev_binary_r1"],full["dev_binary_r1"],
                seed=95000+seed+budget//1024),
            "r10_delta":bootstrap_diff(
                compact["dev_binary_r10"],full["dev_binary_r10"],
                seed=96000+seed+budget//1024),
        })
    return out


def cross_architecture_matched_subset(corpus,dev):
    """Matched-identity check: source compression cannot affect BM25 ranking."""
    # Use arbitrary fixed nontrivial subset and shuffled identity order.
    ranked=sorted(corpus,key=lambda row:tie_hash(row["doc_id"],91))
    subset=ranked[:min(400,len(ranked))]
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        full=build_source_index(root/"full.sqlite",subset,"conventional")
        compact=build_source_index(root/"compact.sqlite",subset,"compressed")
        try:
            a,_=rankings(full,subset,dev,False)
            b,_=rankings(compact,subset,dev,True)
            if a!=b:
                raise AssertionError("architecture changed matched-subset BM25 rankings")
            return {"matched_documents":len(subset),
                    "queries_equal_top10":len(dev),
                    "full_source_receipts_sha_verified":True}
        finally:
            full.close()
            compact.close()


def evaluate(corpus,train,dev,seeds=SEEDS,budgets=BUDGETS):
    fit,validation=split_train_claims(train)
    if {str(x["id"]) for x in fit}&{str(x["id"]) for x in validation}:
        raise AssertionError("fit overlaps internal validation claims")
    if {str(x["id"]) for x in train}&{str(x["id"]) for x in dev}:
        raise AssertionError("train overlaps dev claims")
    ids={str(row["doc_id"]) for row in corpus}
    validation_gold=annotated_gold(validation,corpus)
    dev_gold=annotated_gold(dev,corpus)
    source_disjoint=source_disjoint_dev(
        dev_gold,set(train_gold_sources(train,ids)))
    rrf,_,query_meta=train_query_relevance(corpus,fit)
    signal={"fit_rrf":rrf,
            "fit_gold_frequency":train_gold_sources(fit,ids),
            "title_rarity":title_rarity_scores(corpus)}
    # Precommit all model choices, seeds, budgets before any dev metric drives winner.
    out=[]
    for policy in POLICIES:
        for seed in seeds:
            out.extend(one_policy(
                corpus,validation,dev,validation_gold,dev_gold,source_disjoint,
                signal,policy,seed,budgets))
    selected={(a,b):select_validation_policy(out,a,b,seeds)
              for a in ARCHITECTURES for b in budgets}
    pairs=[v for budget in budgets
           for v in within_seed_pair(out,selected,budget,seeds)]
    aggregate=[]
    for budget in budgets:
        for arch in ARCHITECTURES:
            for policy in POLICIES:
                subset=[r for r in out if r["budget"]==budget
                        and r["architecture"]==arch and r["policy"]==policy]
                aggregate.append({
                    "budget":budget, "architecture":arch, "policy":policy,
                    "mean_docs":round(statistics.mean(
                        x["docs_retained"] for x in subset),2),
                    "mean_bytes":round(statistics.mean(
                        x["db_bytes"] for x in subset),2),
                    "mean_validation_r10":round(statistics.mean(
                        x["validation"]["r10_hits"] for x in subset),4),
                    "mean_dev_r1_hits":round(statistics.mean(
                        x["development"]["r1_hits"] for x in subset),4),
                    "mean_dev_r10_hits":round(statistics.mean(
                        x["development"]["r10_hits"] for x in subset),4),
                    "mean_disjoint_r10_hits":round(statistics.mean(
                        x["dev_disjoint"]["r10_hits"] for x in subset),4),
                })
    baseline_meta={}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for arch in ARCHITECTURES:
            c=build_source_index(root/(arch+".sqlite"),corpus,arch)
            try:baseline_meta[arch]={
                "complete_corpus_source_plus_index_bytes":
                (root/(arch+".sqlite")).stat().st_size}
            finally:c.close()
    if not all(base["complete_corpus_source_plus_index_bytes"]>max(budgets)
               for base in baseline_meta.values()):
        raise AssertionError("both arms must be storage limited")
    return {
        "round":95, "cohort":{
            "docs":len(corpus), "all_training_claims":len(train),
            "fit_claims":len(fit),
            "internal_validation_claims":len(validation),
            "validation_gold_claims":len(validation_gold),
            "dev_claims":len(dev),
            "dev_gold_claims":len(dev_gold),
            "dev_source_disjoint_claims":len(source_disjoint),
            "budgets":list(budgets),"seeds":list(seeds),
            "policies":list(POLICIES),
            "architectures":list(ARCHITECTURES),
            "no_dev_used_for_selection":True,
            "train_query_signals":query_meta,
        },
        "complete_source_index_sizes":baseline_meta,
        "matched_subset":cross_architecture_matched_subset(corpus,dev),
        "validation_selected_policies":[selected[(a,b)]
                                        for b in budgets for a in ARCHITECTURES],
        "selected_dev_paired_outcomes":pairs,
        "all_policy_aggregate_outcomes":aggregate,
        "all_dev_exploratory_runs":[
            {k:v for k,v in x.items() if not k.startswith("dev_binary_")}
            for x in out],
        "limits":[
            "SQLite persistent source+index bytes only, no model weights, RAM, WAL active history or SSD cold reads",
            "Full corpus cannot fit either budget in either architecture, but binary search only checks nearest successor",
            "Document priority is heuristic, not exact byte-optimal subset selection",
            "Fit/internal-validation claim IDs disjoint; source abstracts/topics can still overlap",
            "Source-disjoint dev only excludes train labelled source IDs, not topic or unsupervised pretraining exposure",
            "All dev outcomes exploratory public SciFact claims; not out-of-distribution generalization",
            "Same fixed FTS5 BM25 ranking policy; no model answers, hallucination, entity or entailment accuracy",
            "Source cost proxy under weighting differs from true SQLite cost; budgets use actual file sizes",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=parser.parse_args()
    tar,raw=fetch()
    source_sha=digests(tar)["sha256"]
    if source_sha!=EXPECTED_RELEASE_SHA:
        raise AssertionError("upstream SciFact source SHA changed")
    corpus,dev,_=parse(raw)
    train,train_meta=train_claims_from_verified_archive(tar)
    result=evaluate(corpus,train,dev)
    result["upstream_sha256"]=source_sha
    result["train_source"]=train_meta
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND95",json.dumps({
        "sha":source_sha,"cohort":result["cohort"],
        "sizes":result["complete_source_index_sizes"],
        "matched_subset":result["matched_subset"],
        "choices":result["validation_selected_policies"],
        "selected":result["selected_dev_paired_outcomes"],
        "aggregate":result["all_policy_aggregate_outcomes"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
