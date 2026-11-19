#!/usr/bin/env python3
"""R98: jointly binding QASPER 6/8 MiB paragraph evidence retrieval.

Human paragraph evidence never enters selection. Two predeclared policies:
(1) SHA-uniform paragraph retention, (2) balance number of passages
across papers before additional passages. Compare compressed and
conventional source+index under actual SQLite disk byte caps.
No claims about answer generation or global open-domain retrieval.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import hashlib
import json
import random
import statistics
import sys
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-90","round-92","round-96","round-97"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import (
    load_dev,scoped_rankings,gold_recall,evaluate as full_source_control
)
from contentless_cas import make_fts
from old_source_incremental import create_legacy_contentless

BUDGETS=(6*1024*1024,8*1024*1024)
SEEDS=(11,37,71)
POLICIES=("global_hash","paper_balanced_hash")
ARCHITECTURES=("conventional","compressed")
SALT="CDG-R98-QASPER-UNLABELLED-ARTICLE-PARAGRAPH-v1"
K=(1,5,10)


def paper_id(doc):
    # The original section/paragraph numbers occupy the final two fields.
    fields=str(doc["doc_id"]).rsplit("|",2)
    if len(fields)!=3:
        raise AssertionError("lost original paper section paragraph identity")
    return fields[0]


def doc_hash(doc_id,seed):
    return hashlib.sha256((SALT+"|"+str(seed)+"|"+str(doc_id))
                          .encode("utf8")).digest()


def prioritization_indices(docs,seed,policy):
    """Priorities computed from only source IDs and grouping, not QA labels."""
    if policy=="global_hash":
        return sorted(range(len(docs)),
                      key=lambda i:(doc_hash(docs[i]["doc_id"],seed),i))
    if policy!="paper_balanced_hash":
        raise ValueError("unrecognized paper policy")
    groups=defaultdict(list)
    for i,row in enumerate(docs):
        groups[paper_id(row)].append(i)
    rank_in_paper={}
    for group,positions in groups.items():
        order=sorted(positions,key=lambda i:(
            doc_hash(docs[i]["doc_id"],seed),i))
        for j,position in enumerate(order):
            rank_in_paper[position]=j
    return sorted(range(len(docs)),key=lambda i:(
        rank_in_paper[i],doc_hash(docs[i]["doc_id"],seed),i))


def build_db(file,corpus,arch):
    if arch=="conventional":
        conn,_=make_fts(file,corpus,False)
    elif arch=="compressed":
        conn=create_legacy_contentless(file,corpus)
    else:
        raise ValueError("invalid architecture")
    return conn


def selected_original_order(docs,priority,k):
    """Preserve contiguous original article rowid ranges for scoped retrieval."""
    chosen=sorted(priority[:k])
    return [docs[i] for i in chosen]


def physical_prefix_bytes(folder,docs,priority,k,arch,cache):
    key=(k,arch)
    if key in cache:
        return cache[key]
    if not 1<=k<=len(docs):
        raise AssertionError("invalid prefix length")
    data=selected_original_order(docs,priority,k)
    filename=folder/f"size_{arch}_{k}.sqlite"
    db=build_db(filename,data,arch)
    try:
        size=filename.stat().st_size
        page_count=db.execute("PRAGMA page_count").fetchone()[0]
        page_size=db.execute("PRAGMA page_size").fetchone()[0]
        if page_count*page_size!=size:
            raise AssertionError("SQLite file page count mismatch")
    finally:
        db.close()
        filename.unlink(missing_ok=True)
    cache[key]=size
    return size


def largest_prefix(folder,docs,priority,budget,arch,cache):
    """Observed-prefix search, not a globally optimal byte knapsack."""
    lo,hi=0,len(docs)
    while lo<hi:
        mid=(lo+hi+1)//2
        measured=physical_prefix_bytes(folder,docs,priority,mid,arch,cache)
        if measured<=budget:
            lo=mid
        else:
            hi=mid-1
    if lo<1:
        raise AssertionError("budget cannot retain any source")
    selected_size=physical_prefix_bytes(folder,docs,priority,lo,arch,cache)
    if selected_size>budget:
        raise AssertionError("selected index over budget")
    if lo<len(docs):
        if physical_prefix_bytes(folder,docs,priority,lo+1,arch,cache)<=budget:
            raise AssertionError("next prefix still fits: invalid search")
    return lo,selected_size


def paragraph_gold_ids(docs,cases):
    mapping={i+1:str(row["doc_id"]) for i,row in enumerate(docs)}
    return {
        x["id"]:{mapping[rid] for rid in x["gold_rowids"]}
        for x in cases
    }


def ranges_by_article(chosen):
    ranges={}
    for rid,row in enumerate(chosen,1):
        pid=paper_id(row)
        if pid not in ranges:
            ranges[pid]=[rid,rid]
        else:
            if ranges[pid][1]!=rid-1:
                raise AssertionError("source rows for paper not contiguous")
            ranges[pid][1]=rid
    return ranges


def subset_cases(cases,ranges):
    out=[]
    for case in cases:
        start,end=ranges.get(case["paper"],(1,0))
        out.append({**case,"row_start":start,"row_end":end})
    return out


def evidence_recall(cases,ranked_document_ids,gold):
    valid=[x for x in cases if gold[x["id"]]]
    if not valid:
        raise AssertionError("no source human evidence eligible")
    metrics={}
    binary={}
    for k in K:
        bits=[int(bool(gold[x["id"]]&set(
            ranked_document_ids[x["id"]][:k]))) for x in valid]
        metrics["r"+str(k)]={"hits":sum(bits),"denom":len(bits),
                             "rate":round(sum(bits)/len(bits),6)}
        binary[str(k)]=bits
    return metrics,binary


def evaluate_subset(db,chosen,cases,arch,gold):
    ranges=ranges_by_article(chosen)
    new_cases=subset_cases(cases,ranges)
    rank,cost=scoped_rankings(db,chosen,new_cases,arch=="compressed")
    rid_to_doc={i+1:str(row["doc_id"]) for i,row in enumerate(chosen)}
    ranked={
        caseid:[rid_to_doc[rid] for rid in values]
        for caseid,values in rank.items()
    }
    metrics,bits=evidence_recall(cases,ranked,gold)
    source_ids=set(rid_to_doc.values())
    return {
        "metrics":metrics,
        "bits":bits,
        "paper_coverage":len(ranges),
        "papers_without_any_source":len({x["paper"] for x in cases}-set(ranges)),
        "gold_source_available_claims":sum(
            bool(gold[x["id"]]&source_ids) for x in cases if gold[x["id"]]),
        "source_checks":cost,
    }


def one_policy(docs,cases,gold,policy,seed,budgets=BUDGETS):
    order=prioritization_indices(docs,seed,policy)
    result=[]
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for arch in ARCHITECTURES:
            cache={}
            for budget in budgets:
                n,measured=largest_prefix(folder,docs,order,budget,arch,cache)
                if n==len(docs):
                    raise AssertionError("budget must bind both architectures")
                selected=selected_original_order(docs,order,n)
                path=folder/"evidence.sqlite"
                db=build_db(path,selected,arch)
                try:
                    if path.stat().st_size!=measured or measured>budget:
                        raise AssertionError("actual SQLite file budget mismatches probe")
                    outcome=evaluate_subset(db,selected,cases,arch,gold)
                    result.append({
                        "policy":policy,"seed":seed,"architecture":arch,
                        "budget":budget,"docs_retained":n,
                        "source_index_bytes":measured,
                        **outcome,
                    })
                finally:
                    db.close()
                    path.unlink(missing_ok=True)
    return result


def paired_seed(rows,budget,policy,seed):
    selection={}
    for arch in ARCHITECTURES:
        match=[row for row in rows if row["architecture"]==arch
               and row["budget"]==budget and row["policy"]==policy
               and row["seed"]==seed]
        if len(match)!=1:
            raise AssertionError("expected exactly one selected experiment")
        selection[arch]=match[0]
    full=selection["conventional"]
    comp=selection["compressed"]
    return {
        "budget":budget,"policy":policy,"seed":seed,
        "conventional_docs":full["docs_retained"],
        "compressed_docs":comp["docs_retained"],
        "conventional_papers":full["paper_coverage"],
        "compressed_papers":comp["paper_coverage"],
        "conventional_r1":full["metrics"]["r1"]["hits"],
        "compressed_r1":comp["metrics"]["r1"]["hits"],
        "conventional_r10":full["metrics"]["r10"]["hits"],
        "compressed_r10":comp["metrics"]["r10"]["hits"],
        "paired_r10_wins":sum(a>b for a,b in zip(
            comp["bits"]["10"],full["bits"]["10"])),
        "paired_r10_losses":sum(a<b for a,b in zip(
            comp["bits"]["10"],full["bits"]["10"])),
    }


def evaluate(papers,seeds=SEEDS,budgets=BUDGETS):
    docs,cases,cohort=load_dev(papers)
    gold=paragraph_gold_ids(docs,cases)
    if not any(gold.values()):
        raise AssertionError("no QASPER exact evidence")
    results=[]
    for policy in POLICIES:
        for seed in seeds:
            results.extend(one_policy(docs,cases,gold,policy,seed,budgets))
    pairs=[paired_seed(results,budget,policy,seed)
           for budget in budgets for policy in POLICIES for seed in seeds]
    aggregate=[]
    for budget in budgets:
        for policy in POLICIES:
            for arch in ARCHITECTURES:
                rows=[x for x in results if x["budget"]==budget and
                      x["policy"]==policy and x["architecture"]==arch]
                aggregate.append({
                    "budget":budget,"policy":policy,"architecture":arch,
                    "mean_docs_retained":round(statistics.mean(
                        x["docs_retained"] for x in rows),3),
                    "mean_papers_with_source":round(statistics.mean(
                        x["paper_coverage"] for x in rows),3),
                    "mean_r1_hits":round(statistics.mean(
                        x["metrics"]["r1"]["hits"] for x in rows),4),
                    "mean_r5_hits":round(statistics.mean(
                        x["metrics"]["r5"]["hits"] for x in rows),4),
                    "mean_r10_hits":round(statistics.mean(
                        x["metrics"]["r10"]["hits"] for x in rows),4),
                    "eligible_questions":rows[0]["metrics"]["r10"]["denom"],
                })
    # Strong full-corpus identical-source control from R97, recomputed here.
    full=full_source_control(papers)
    full_size=full["full_source_and_index_bytes"]
    compact_size=full["compressed_sha_verified_source_and_index_bytes"]
    if not all(min(full_size,compact_size)>b for b in budgets):
        raise AssertionError("R98 expects both complete architectures over budget")
    return {
        "round":98,
        "source":"QASPER official v0.3 dev, SHA locked in R96",
        "source_papers":len(papers),
        "cohort":cohort,
        "budgets":list(budgets),
        "seeds":list(seeds),
        "policies":list(POLICIES),
        "both_architectures_must_drop_some_paragraphs":True,
        "full_source_control":{
            "conventional_bytes":full_size,
            "compressed_bytes":compact_size,
            "full_paragraph_evidence_recall":full["human_evidence_paragraph_recall"],
            "identical_1005_query_rankings":full["exact_rankings_all_questions"],
        },
        "aggregate":aggregate,
        "paired_by_seed":pairs,
        "all_runs":[
            {k:v for k,v in x.items() if k!="bits"}
            for x in results],
        "limitations":[
            "QASPER questions know their article; paper-scoped retrieval, not open-domain",
            "Each budget uses original SQLite source+index files only; model weights, WAL, RAM and cold SSD excluded",
            "Human gold used after retrieval for exact paragraph evidence recall only",
            "Global hash and paper-balanced hash are unsupervised fixed policies, not optimized evidence selection",
            "Paper-balanced uses article ID and source metadata, not question text or gold evidence",
            "Prefix search verifies next document but does not solve globally optimal storage allocation",
            "Multiple paragraph evidence annotations may include figures or unmatched text and are excluded if no exact text match",
            "Same dev papers and questions evaluated across seeds, not independent statistical replication",
            "No free-form generated answers or human answer-grounding/hallucination outcomes",
        ],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=parser.parse_args()
    members=fetch_qasper()
    result=evaluate(members["dev"]["data"])
    result["official_source_sha256"]=( 
        "a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a")
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND98",json.dumps({
        "cohort":result["cohort"],"budgets":result["budgets"],
        "full":result["full_source_control"],
        "aggregate":result["aggregate"],
        "paired":result["paired_by_seed"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
