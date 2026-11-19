#!/usr/bin/env python3
"""R97: independent QASPER exact-evidence paragraph retrieval parity.

Original QASPER 0.3 dev questions know their target paper. A query is
scoped to that paper's paragraph interval and returned by fixed SciFact
FTS5/BM25 title5/body1 token28-OR policy, to compare conventional vs
compressed source layout. Human evidence paragraph matches are used
*only* after retrieval for Recall@1/3/5/10. No generated QA correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-87","round-88","round-90","round-96"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import (
    fetch as fetch_qasper,article_paragraphs,questions,answer_evidences,normalize
)
from contentless_cas import make_fts,query_text,document_bytes
from old_source_incremental import create_legacy_contentless
from atomic_source_db import read
from snapshot_kill_probe import retrieve_snapshot

K=(1,3,5,10)
POLICY="BM25(title weight 5, abstract weight 1), quoted OR <=28 distinct terms"
SCOPE="known article id; only paragraph rowids from question article considered"


def load_dev(papers):
    """Flatten original dev sections to paragraphs and map exact annotated gold.

    Question paper ID is supplied by QASPER. All paragraphs are globally
    indexed for storage costs; retrieval explicitly filters paper interval.
    No gold annotation enters index or query ranking.
    """
    docs=[]
    cases=[]
    totals=Counter()
    seen=set()
    for pid in sorted(papers):
        article=papers[pid]
        start=len(docs)+1
        text_to_ids={}
        for row in article_paragraphs(article):
            rid=len(docs)+1
            # Exact original paragraph is retained in 'abstract' as one string;
            # title is its section heading. This is the same format for both.
            section_title=row["section_title"]
            if "\n" in section_title:
                section_title=section_title.replace("\n"," ")
            docs.append({
                "doc_id":f"{pid}|{row['section']}|{row['paragraph']}",
                "title":section_title,
                "abstract":[row["text"]],
            })
            text_to_ids.setdefault(normalize(row["text"]),[]).append(rid)
        end=len(docs)
        if end<start:
            totals["empty_papers"]+=1
        for qa in questions(article):
            qid=f"{pid}|{qa['question_id']}"
            if qid in seen:
                raise AssertionError("duplicate paper-question id")
            seen.add(qid)
            relevant=set()
            matched_annotations=0
            total_annotations=0
            float_only=0
            unmatched=0
            for a in qa["answers"]:
                for texts in answer_evidences(a):
                    total_annotations+=1
                    match=set()
                    for string in texts:
                        if normalize(string).startswith("FLOAT SELECTED"):
                            float_only+=1
                            continue
                        hit=text_to_ids.get(normalize(string),[])
                        if string and not hit:
                            unmatched+=1
                        match.update(hit)
                    if match:
                        matched_annotations+=1
                        relevant.update(match)
            cases.append({
                "id":qid,"paper":pid,"claim":qa["question"],
                "row_start":start,"row_end":end,
                "gold_rowids":relevant,
                "gold_annotation_count":matched_annotations,
            })
            totals["questions"]+=1
            totals["annotations"]+=total_annotations
            totals["annotations_with_paragraph_evidence"]+=matched_annotations
            totals["nonmatching_evidence_strings"]+=unmatched
            totals["figure_table_references"]+=float_only
            if relevant:
                totals["questions_with_at_least_one_exact_text_evidence"]+=1
            else:
                totals["questions_without_exact_text_evidence"]+=1
    if len(docs)!=sum(len(article_paragraphs(v)) for v in papers.values()):
        raise AssertionError("paragraph flattening lost texts")
    if len(cases)!=len(seen):
        raise AssertionError("question identity mismatch")
    return docs,cases,dict(totals)


def paper_rank(db,claim,row_start,row_end,k=10):
    """FTS search constrained to supplied known article, not to gold source."""
    if row_end<row_start:
        return []
    tokens=query_text(claim)
    if not tokens:
        return []
    result=db.execute(
        "SELECT rowid FROM sources "
        "WHERE sources MATCH ? AND rowid BETWEEN ? AND ? "
        "ORDER BY bm25(sources,5.0,1.0),rowid LIMIT ?",
        (tokens,row_start,row_end,k)).fetchall()
    return [int(r[0]) for r in result]


def scoped_rankings(db,docs,cases,compressed):
    """Verify original source bytes for every selected top-10 result."""
    selected={}
    checks=0
    elapsed_start=time.perf_counter()
    for case in cases:
        hits=paper_rank(
            db,case["claim"],case["row_start"],case["row_end"],10)
        for rid in hits:
            if not case["row_start"]<=rid<=case["row_end"]:
                raise AssertionError("paper-scope leakage in retrieval")
            expected=document_bytes(docs[rid-1])
            if compressed:
                recovered=read(db,rid)
                if recovered["source_bytes"]!=expected:
                    raise AssertionError("compressed source original bytes mismatch")
                if recovered["doc_id"]!=str(docs[rid-1]["doc_id"]):
                    raise AssertionError("compressed source identity mismatch")
            else:
                row=db.execute(
                    "SELECT title,abstract FROM sources WHERE rowid=?",
                    (rid,)).fetchone()
                if row is None:
                    raise AssertionError("unreadable FTS source")
                text=(row[0]+"\n"+row[1]).encode("utf8")
                if text!=expected:
                    raise AssertionError("conventional FTS source text altered")
            checks+=1
        selected[case["id"]]=hits
    return selected,{
        "scoped_queries":len(cases),
        "source_receipts_exact_original":checks,
        "warm_query_and_source_read_seconds":round(
            time.perf_counter()-elapsed_start,5),
    }


def gold_recall(cases,rankings):
    valid=[x for x in cases if x["gold_rowids"]]
    if not valid:
        raise AssertionError("no exact human evidence in QASPER sample")
    hist={}
    for k in K:
        hits=sum(bool(x["gold_rowids"]&set(
            rankings.get(x["id"],[])[:k])) for x in valid)
        hist["r"+str(k)]={"hits":hits,"denominator":len(valid),
                          "rate":round(hits/len(valid),6)}
    return {
        "eligible_text_evidence_questions":len(valid),
        "all_questions":len(cases),
        "excluded_no_exact_text_evidence":len(cases)-len(valid),
        "recall":hist,
        "note":"Known-paper paragraph hit, not answer EM/F1, support/contradiction or open-domain source retrieval",
    }


def bootstrap_eligible(cases,rank_a,rank_b,k=10,reps=1500):
    """Paired question bootstrap, descriptive only due clustered paper topics."""
    valid=[x for x in cases if x["gold_rowids"]]
    differences=[
        int(bool(x["gold_rowids"]&set(rank_a[x["id"]][:k])))
        -int(bool(x["gold_rowids"]&set(rank_b[x["id"]][:k])))
        for x in valid
    ]
    if any(differences):
        raise AssertionError("same-source compressed/full rankings should not diverge")
    return {
        "paired_gold_questions":len(valid),
        "retrieval_hit_difference":0,
        "mismatched_ranks":0,
    }


def evaluate(papers):
    docs,cases,cohort=load_dev(papers)
    with tempfile.TemporaryDirectory() as root:
        folder=Path(root)
        a=folder/"full.sqlite"
        b=folder/"compressed.sqlite"
        full,_=make_fts(a,docs,False)
        compact=create_legacy_contentless(b,docs)
        try:
            a_bytes=a.stat().st_size
            b_bytes=b.stat().st_size
            full_rank,full_cost=scoped_rankings(full,docs,cases,False)
            comp_rank,comp_cost=scoped_rankings(compact,docs,cases,True)
            if full_rank!=comp_rank:
                difference=[q for q in full_rank if full_rank[q]!=comp_rank[q]]
                raise AssertionError("compressed source architecture changed BM25: "+
                                     repr(difference[:5]))
            full_gold=gold_recall(cases,full_rank)
            compressed_gold=gold_recall(cases,comp_rank)
            for k in K:
                assert full_gold["recall"]["r"+str(k)]==compressed_gold[
                    "recall"]["r"+str(k)]
            control=bootstrap_eligible(cases,full_rank,comp_rank,10)
            return {
                "round":97,
                "dataset":"QASPER official version 0.3 dev",
                "cohort":cohort,
                "documents_indexed":len(docs),
                "retrieval_policy":POLICY,
                "retrieval_scope":SCOPE,
                "full_source_and_index_bytes":a_bytes,
                "compressed_sha_verified_source_and_index_bytes":b_bytes,
                "persisted_byte_savings_pct":round(
                    100*(a_bytes-b_bytes)/a_bytes,4),
                "exact_rankings_all_questions":len(cases),
                "same_source_recall_control":control,
                "human_evidence_paragraph_recall":compressed_gold,
                "source_read_costs":{"conventional":full_cost,
                                     "compressed":comp_cost},
                "static_sqlite_fts_integrity":{
                    "conventional":full.execute(
                        "PRAGMA integrity_check").fetchone()[0],
                    "compressed":compact.execute(
                        "PRAGMA integrity_check").fetchone()[0],
                },
                "limitations":[
                    "QASPER question article known; not global open-domain evidence retrieval",
                    "Paragraph-level exact gold match excludes nontext evidence and altered evidence strings",
                    "Original paragraph is stored intact but section title newlines normalized only in derived index title",
                    "Single original development corpus; no independent heldout future questions",
                    "No generated answer accuracy, human faithfulness or model verifier",
                    "Warm source-read comparison in single GitHub runner, not cold SSD or write-heavy workflow",
                    "Original paragraph paper-scope filtering is equivalent across source representations",
                ],
            }
        finally:
            full.close()
            compact.close()


def run():
    members=fetch_qasper()
    data=members["dev"]["data"]
    result=evaluate(data)
    result["source"]={
        "official_archive_sha256":
            "a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a",
        "dev_member_sha256":members["dev"]["sha256"],
        "dev_articles":len(data),
    }
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=p.parse_args()
    result=run()
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND97",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
