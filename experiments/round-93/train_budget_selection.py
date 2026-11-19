#!/usr/bin/env python3
"""R93: adversarial conventional FTS source retention at the R92 fixed budgets.

Challenge the compact full-corpus baseline with stronger conventional document
selection strategies learned from SciFact TRAIN labels or TRAIN claim queries
only. Select the proposed conventional policy by TRAIN Recall@10, report DEV
only afterwards, and include DEV evidence from sources never gold-labelled
in train. No dev label/text is used in ordering or policy selection.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-83"))
sys.path.insert(0,str(HERE.parent/"round-84"))
sys.path.insert(0,str(HERE.parent/"round-86"))
sys.path.insert(0,str(HERE.parent/"round-92"))
from scifact_data_probe import fetch,parse,digests
from retrieval_ablation import train_claims_from_verified_archive
from contentless_cas import make_fts,query_fts,document_bytes,EXPECTED_RELEASE_SHA
from storage_budget_eval import (
    annotated_gold,recall,rankings,bootstrap_diff,conventional_prefix_size,
    SELECTION_SALT,BUDGETS_BYTES
)

SEEDS=(11,37,71)
POLICIES=(
    "hash",
    "train_evidence_frequency",
    "train_query_reciprocal_rank",
    "train_query_greedy_coverage",
    "shortest_source_first",
    "unsupervised_title_rarity",
)
TOKEN=re.compile(r"[^\W_]+",re.UNICODE)
K_RETRIEVE_TRAIN=10
GREEDY_STEPS=400
SELECT_METRIC="r10"
PRIORITY_SALT="CDG-R93-TRAIN-ONLY-DOC-PRIORITIZATION-v1"
SPLIT_SALT="CDG-R93-CLAIM-FIT-SELECT-DISJOINT-v1"


def tie_hash(doc_id,seed):
    return hashlib.sha256((PRIORITY_SALT+"|"+str(seed)+"|"+str(doc_id))
                           .encode()).digest()


def split_train_claims(train):
    """Frozen 70/30 CLAIM-ID split before any source priorities or tuning.

    The fit split builds candidate policy scores. The selection split
    chooses the strongest predeclared policy, without sharing claim IDs.
    The corpus and some source documents may overlap between splits.
    """
    ordered=sorted(train,key=lambda row:(
        hashlib.sha256((SPLIT_SALT+"|"+str(row["id"])).encode()).digest(),
        str(row["id"])))
    n_selection=max(1,int(round(.30*len(ordered))))
    fit=ordered[:-n_selection]
    selection=ordered[-n_selection:]
    if not fit or not selection:
        raise AssertionError("not enough claims for fit/selection split")
    if set(str(x["id"]) for x in fit)&set(str(x["id"]) for x in selection):
        raise AssertionError("fit and selection claim ID overlap")
    return fit,selection


def train_gold_sources(train,corpus_ids):
    counts=Counter()
    for claim in train:
        for doc_id,items in (claim.get("evidence") or {}).items():
            if items and str(doc_id) in corpus_ids:
                counts[str(doc_id)]+=1
    return counts


def title_rarity_scores(corpus):
    token_sets=[set(TOKEN.findall(str(d["title"]).lower())) for d in corpus]
    df=Counter(w for words in token_sets for w in words)
    n=len(corpus)
    output={}
    for row,words in zip(corpus,token_sets):
        # This favors rare, diverse title terms. Never examines query/labels.
        output[str(row["doc_id"])]=sum(
            math.log((n+1)/(df[w]+1)) for w in words
        )/math.sqrt(max(1,len(words)))
    return output


def train_query_relevance(corpus,train):
    """Full corpus FTS5 ranks all TRAIN queries without evidence annotations."""
    with tempfile.TemporaryDirectory() as root:
        db,_=make_fts(Path(root)/"training_search.sqlite",corpus,False)
        try:
            rid_doc={i+1:str(row["doc_id"]) for i,row in enumerate(corpus)}
            weights=defaultdict(float)
            doc_to_queries=defaultdict(dict)
            for qi,claim in enumerate(train):
                ranked=query_fts(db,claim["claim"],K_RETRIEVE_TRAIN)
                for r,source_rid in enumerate(ranked):
                    doc_id=rid_doc[source_rid]
                    weight=1.0/(r+1)
                    weights[doc_id]+=weight
                    doc_to_queries[doc_id][qi]=weight
            return dict(weights),dict(doc_to_queries),{
                "train_claims_queried":len(train),
                "topk_per_claim":K_RETRIEVE_TRAIN,
                "topk_observed_documents":len(weights),
                "query_uses_gold_labels":False,
            }
        finally:db.close()


def greedy_coverage_priority(corpus,query_weights,seed=11):
    """Approximate per-byte maximal coverage of ranked TRAIN query top hits.

    Select up to 400 documents greedily to maximize gain of one best
    high-ranked doc for each training query. No development information.
    Cost is only a heuristic in this prioritizer. Actual SQLite bytes enforce
    the final storage budget, so it is not an optimal knapsack claim.
    """
    docs={str(x["doc_id"]):x for x in corpus}
    remaining=set(query_weights)
    best=defaultdict(float)
    selected=[]
    for _ in range(min(GREEDY_STEPS,len(remaining))):
        ranked=[]
        for doc_id in remaining:
            gain=sum(max(0.,w-best[q]) for q,w in
                     query_weights[doc_id].items())
            if gain<=0:continue
            denom=512+len(document_bytes(docs[doc_id]))
            ranked.append((gain/denom, gain, doc_id))
        if not ranked:break
        # Fixed seed-independent tie breaker to make the greedy ranking
        # fully train-only. Seeds affect only remainder ordering.
        best_choice=max(ranked,key=lambda item:(
            item[0],item[1],tie_hash(item[2],0)))
        did=best_choice[2]
        selected.append(did)
        remaining.remove(did)
        for q,w in query_weights[did].items():
            best[q]=max(best[q],w)
    return selected


def source_order(corpus,policy,seed,signals):
    gold=signals["train_gold"]
    rrf=signals["train_rrf"]
    rarity=signals["title_rarity"]
    greedy=signals["greedy"]
    greedy_rank={doc_id:len(greedy)-i for i,doc_id in enumerate(greedy)}
    def key(row):
        did=str(row["doc_id"])
        h=tie_hash(did,seed)
        if policy=="hash":return (h,)
        if policy=="train_evidence_frequency":
            return (-gold.get(did,0),h)
        if policy=="train_query_reciprocal_rank":
            return (-rrf.get(did,0),h)
        if policy=="train_query_greedy_coverage":
            # Greedy seed prefix is fixed by TRAIN queries, tail uses train RRF.
            return (0 if did in greedy_rank else 1,
                    -greedy_rank.get(did,0),-rrf.get(did,0),h)
        if policy=="shortest_source_first":
            return (len(document_bytes(row)),h)
        if policy=="unsupervised_title_rarity":
            return (-rarity[did],h)
        raise ValueError("unknown prioritizer "+policy)
    result=sorted(corpus,key=key)
    if len(result)!=len(corpus) or len(set(id(x) for x in result))!=len(corpus):
        raise AssertionError("source permutation dropped or duplicated rows")
    return result


def fit_budget(folder,ordered,budget,cache):
    """R92 binary-search convention, shared prefix-size cache across budgets."""
    lo,hi=0,len(ordered)
    while lo<hi:
        mid=(lo+hi+1)//2
        value=conventional_prefix_size(folder,ordered,mid,cache)
        if value<=budget:lo=mid
        else:hi=mid-1
    if lo<1:raise AssertionError("budget too small")
    size=conventional_prefix_size(folder,ordered,lo,cache)
    if size>budget:raise AssertionError("overbudget conventional FTS5")
    if lo<len(ordered) and conventional_prefix_size(
            folder,ordered,lo+1,cache)<=budget:
        raise AssertionError("prefix is not maximal by first-neighbor check")
    return lo,size


def source_disjoint_dev(dev_gold,train_evidence_ids):
    """Claim evidence only on sources never labelled by train claims."""
    return [x for x in dev_gold
            if not any(sid in train_evidence_ids for sid in x["gold"])]


def one_priority(corpus,train,dev,train_gold,dev_gold,disjoint,
                 policy,seed,signals,budgets=BUDGETS_BYTES):
    ordered=source_order(corpus,policy,seed,signals)
    results=[]
    with tempfile.TemporaryDirectory() as root:
        d=Path(root)
        cache={}
        for budget in budgets:
            fit_n,bytes_used=fit_budget(d,ordered,budget,cache)
            kept=ordered[:fit_n]
            kept_ids={str(x["doc_id"]) for x in kept}
            name=d/"selected.sqlite"
            db,_=make_fts(name,kept,False)
            try:
                tr_rank,_=rankings(db,kept,train,False)
                dv_rank,_=rankings(db,kept,dev,False)
                tr_metrics=recall(train_gold,tr_rank,kept_ids)
                dv_metrics=recall(dev_gold,dv_rank,kept_ids)
                ss_metrics=recall(disjoint,dv_rank,kept_ids) if disjoint else None
                results.append({
                    "policy":policy,"seed":seed,"budget_bytes":budget,
                    "documents_retained":fit_n,
                    "source_plus_fts_bytes":bytes_used,
                    "train_r1":tr_metrics["recall"]["r1"]["hits"],
                    "train_r10":tr_metrics["recall"]["r10"]["hits"],
                    "train_gold_claims":len(train_gold),
                    "dev_r1":dv_metrics["recall"]["r1"]["hits"],
                    "dev_r10":dv_metrics["recall"]["r10"]["hits"],
                    "dev_gold_claims":len(dev_gold),
                    "dev_disjoint_r1":ss_metrics["recall"]["r1"]["hits"] if ss_metrics else None,
                    "dev_disjoint_r10":ss_metrics["recall"]["r10"]["hits"] if ss_metrics else None,
                    "dev_disjoint_gold_claims":len(disjoint),
                    "dev_source_availability":dv_metrics[
                        "annotated_source_present_in_retained_corpus"],
                    "disjoint_source_availability":ss_metrics[
                        "annotated_source_present_in_retained_corpus"] if ss_metrics else None,
                })
            finally:
                db.close()
                name.unlink(missing_ok=True)
    return results


def choose_train_policy(rows,budget):
    pool=[]
    for method in POLICIES:
        matches=[r for r in rows if r["policy"]==method
                 and r["budget_bytes"]==budget]
        if len(matches)!=len(SEEDS):
            raise AssertionError("predeclared seed count changed")
        mean_r10=statistics.mean(x["train_r10"] for x in matches)
        mean_r1=statistics.mean(x["train_r1"] for x in matches)
        pool.append((mean_r10,mean_r1,method))
    top=sorted(pool,key=lambda x:(-x[0],-x[1],x[2]))[0]
    return {
        "selected_policy":top[2],
        "train_mean_hits_r10":round(top[0],4),
        "train_mean_hits_r1":round(top[1],4),
        "selection_only_train_metrics":True,
        "dev_results_not_used_in_selection":True,
    }


def evaluate(corpus,train,dev,seeds=SEEDS,budgets=BUDGETS_BYTES):
    if len({str(x["id"]) for x in train})!=len(train):
        raise AssertionError("duplicate train claim")
    if set(str(x["id"]) for x in train)&set(str(x["id"]) for x in dev):
        raise AssertionError("train/dev claim ID overlap")
    ids={str(x["doc_id"]) for x in corpus}
    fit_claims,select_claims=split_train_claims(train)
    train_gold=annotated_gold(select_claims,corpus)
    dev_gold=annotated_gold(dev,corpus)
    fit_counts=train_gold_sources(fit_claims,ids)
    all_train_counts=train_gold_sources(train,ids)
    disjoint=source_disjoint_dev(dev_gold,set(all_train_counts))
    rrf,qlinks,query_meta=train_query_relevance(corpus,fit_claims)
    greedy=greedy_coverage_priority(corpus,qlinks)
    signals={"train_gold":fit_counts,"train_rrf":rrf,
             "title_rarity":title_rarity_scores(corpus),"greedy":greedy}
    rows=[]
    for policy in POLICIES:
        for seed in seeds:
            rows.extend(one_priority(corpus,select_claims,dev,train_gold,dev_gold,
                                    disjoint,policy,seed,signals,budgets))
    selections={str(budget):choose_train_policy(rows,budget)
                for budget in budgets}
    selected_rows={}
    summary=[]
    for budget in budgets:
        selected=selections[str(budget)]["selected_policy"]
        sample=[r for r in rows if r["budget_bytes"]==budget
                and r["policy"]==selected]
        selected_rows[str(budget)]=sample
        for method in POLICIES:
            rs=[r for r in rows if r["budget_bytes"]==budget
                and r["policy"]==method]
            summary.append({
                "budget_bytes":budget,"policy":method,
                "mean_docs_retained":round(
                    statistics.mean(x["documents_retained"] for x in rs),2),
                "mean_train_recall_at10":round(
                    statistics.mean(x["train_r10"] for x in rs)/len(train_gold),6),
                "mean_dev_recall_at1":round(
                    statistics.mean(x["dev_r1"] for x in rs)/len(dev_gold),6),
                "mean_dev_recall_at10":round(
                    statistics.mean(x["dev_r10"] for x in rs)/len(dev_gold),6),
                "mean_dev_disjoint_recall_at10":(
                    round(statistics.mean(x["dev_disjoint_r10"] for x in rs)
                          /len(disjoint),6) if disjoint else None),
                "min_dev_r10_hits":min(x["dev_r10"] for x in rs),
                "max_dev_r10_hits":max(x["dev_r10"] for x in rs),
            })
    # Full compressed has 179/188 dev gold source Recall@10 from original R92.
    # Compute independent full source-recall to fail closed if control drifts.
    with tempfile.TemporaryDirectory() as root:
        db,_=make_fts(Path(root)/"full.sqlite",corpus,False)
        try:
            r,_=rankings(db,corpus,dev,False)
            full=recall(dev_gold,r,ids)
            full_disjoint=recall(disjoint,r,ids) if disjoint else None
        finally:db.close()
    return {
        "round":93,
        "cohort":{
            "docs":len(corpus),"original_train_claims":len(train),
            "fit_claims":len(fit_claims),
            "internal_selection_claims":len(select_claims),
            "internal_selection_annotated_claims":len(train_gold),
            "claim_fit_selection_overlap":0,
            "dev_claims":len(dev),"dev_annotated_claims":len(dev_gold),
            "fit_labelled_source_count":len(fit_counts),
            "all_train_labelled_source_count":len(all_train_counts),
            "dev_annotated_source_disjoint_claims":len(disjoint),
            "seeds":list(seeds),"budgets":list(budgets),
            "all_policy_names":list(POLICIES),
            "priority_training_uses_fit_claims_only":True,
            "policy_selection_uses_separate_claim_disjoint_validation":True,
            "ranker":"same full-content FTS5 BM25 title5/body1 term-budget28",
            "selection_metric":"mean internal heldout TRAIN selection Recall@10 across seeds; then Recall@1",
            "greedy_candidate_budget":GREEDY_STEPS,
        },
        "train_query_relevance":query_meta,
        "train_only_policy_selection":selections,
        "full_corpus_conventional_equivalent_to_compressed":{
            "dev_r1":full["recall"]["r1"]["hits"],
            "dev_r10":full["recall"]["r10"]["hits"],
            "disjoint_dev_r1":full_disjoint["recall"]["r1"]["hits"] if full_disjoint else None,
            "disjoint_dev_r10":full_disjoint["recall"]["r10"]["hits"] if full_disjoint else None},
        "aggregates":summary,
        "selected_development_rows":selected_rows,
        "per_seed_all_methods":rows,
        "limitations":[
            "Six prioritizers are known conventional heuristics; none is an optimized semantic retriever",
            "Fit, internal selection and dev claim IDs disjoint; source documents may overlap across all splits",
            "Source-disjoint dev cohort removes all gold sources with ANY official train evidence label, not all topical/pretraining overlap",
            "Five-seed R92 random baseline and three-seed R93 train choices are not identical experimental replications",
            "Full retrieval and compact compression share the same static BM25 ranking; no generator hallucination is tested",
            "Budget is post-VACUUM SQLite persistent bytes, not WAL, SSD reads, model weights or runtime RAM",
            "Internal heldout TRAIN claims select policy; all dev variant outcomes are public exploratory research, not untouched external tests",
            "SciFact same source corpus can make training evidence frequency look unusually strong, potentially masking generalization failure",
            "Selection by hash prefix and binary search does not solve optimal document-knapsack allocation",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=p.parse_args()
    archive,raw=fetch()
    sha=digests(archive)["sha256"]
    if sha!=EXPECTED_RELEASE_SHA:
        raise AssertionError("official SciFact archive SHA drift")
    corpus,dev,_=parse(raw)
    train,train_meta=train_claims_from_verified_archive(archive)
    result=evaluate(corpus,train,dev)
    result["source_sha256"]=sha
    result["train_provenance"]=train_meta
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND93",json.dumps({
        "source_sha256":sha,
        "cohort":result["cohort"],
        "full":result["full_corpus_conventional_equivalent_to_compressed"],
        "selected":result["train_only_policy_selection"],
        "aggregates":result["aggregates"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
