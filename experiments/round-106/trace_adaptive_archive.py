#!/usr/bin/env python3
"""R106 heldout query-history allocation of source layouts, real SQLite archives.

The independent trained Zstd9 dictionary and original QASPER paper sources
come from R102. The QASPER DEV *questions* are deterministically split by
question ID: fit queries are permitted to generate historical top-k source
reads; heldout query text/evidence labels must not influence allocations.
All full-corpus FTS5 postings and source bytes remain unchanged.

Archives implement one shared dictionary plus per-paper dynamically chosen
independent original paragraphs, groups of four, or whole-paper blocks,
with verified source SHA/rowids. Unlike offline simulations, persistent
SQLite bytes, decoded original bytes and WAL page growth are measured in
fully materialized source archives. Synthetic revisions are independent of
QA labels, not real historical human edit logs. No automatic migration yet.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-90","round-96","round-97","round-99",
          "round-101","round-102","round-103","round-104","round-105"):
    sys.path.insert(0,str(HERE.parent/r))
from contentless_cas import document_bytes,make_fts
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,paper_rank,gold_recall
from paper_block_brotli import base_fts_db,paper_id
from train_only_zstd_dictionary import (
    TRAIN_SHA,DEV_SHA,independently_trained_samples,train_dictionaries,
)
from codec_frontier import measured_percentiles

HISTORY_SALT="CDG-R106-QASPER-FIT-QUESTION-HASH-2026-v1"
POLICY_SALT="CDG-R106-PAPER-BASELINE-SHA-v1"
EDIT_SALT="CDG-R106-INDEPENDENT-SYNTHETIC-EDITS-v1"
LAYOUTS=("individual","group4","paper")
POLICIES=(
    "all_individual",
    "all_group4",
    "all_paper",
    "history_25_25",
    "history_50_25",
    "length_25_25",
    "hash_25_25",
)
MAX_BLOCK=12_000_000
BUDGETS=(8*1024*1024, 9*1024*1024)


def stablehash(value):
    return hashlib.sha256(str(value).encode("utf8")).digest()


def split_queries(cases):
    """Pseudo-history split: claim ID hashing; NOT a real chronological trace."""
    fit=[]
    test=[]
    for case in cases:
        digest=stablehash(HISTORY_SALT+"|"+case["id"])
        (fit if int.from_bytes(digest[:4],"big")%2==0 else test).append(case)
    if not fit or not test:
        raise AssertionError("question hash split empty")
    if {x["id"] for x in fit}&{x["id"] for x in test}:
        raise AssertionError("history/test query ID overlap")
    return fit,test


def all_query_rankings(db,cases):
    result={}
    for c in cases:
        result[c["id"]]=paper_rank(
            db,c["claim"],c["row_start"],c["row_end"],10)
    return result


def original_papers(docs):
    groups=defaultdict(list)
    for rid,doc in enumerate(docs,1):
        groups[paper_id(doc)].append(rid)
    return dict(groups)


def candidate_order(docgroups,docs,fit_cases,fit_ranks,kind):
    """No heldout test query text, human evidence labels, or source edits."""
    papers=sorted(docgroups)
    history=Counter()
    if kind=="history":
        for case in fit_cases:
            rows=fit_ranks[case["id"]]
            # Count actual fitted *read bytes*, not gold evidence annotations.
            history[case["paper"]]+=sum(
                len(document_bytes(docs[rid-1])) for rid in rows[:10])
        return sorted(papers,key=lambda p:(
            -history[p],stablehash(POLICY_SALT+"|"+p),p))
    if kind=="length":
        return sorted(papers,key=lambda p:(
            -len(docgroups[p]),stablehash(POLICY_SALT+"|"+p),p))
    if kind=="hash":
        return sorted(papers,key=lambda p:(
            stablehash(POLICY_SALT+"|"+p),p))
    raise ValueError("unsupported rank criterion")


def policy_layouts(docgroups,docs,fit_cases,fit_ranks,policy):
    if policy not in POLICIES:
        raise ValueError("unrecognized policy")
    papers=sorted(docgroups)
    if policy.startswith("all_"):
        layout=policy[4:]
        if layout not in LAYOUTS:
            raise AssertionError("unrecognized static policy layout")
        return {pid:layout for pid in papers}
    kind,high,medium=policy.split("_")
    if (int(high),int(medium)) not in ((25,25),(50,25)):
        raise ValueError("unsupported policy quantiles")
    ordered=candidate_order(docgroups,docs,fit_cases,fit_ranks,kind)
    first=math.ceil(len(ordered)*int(high)/100)
    second=math.ceil(len(ordered)*int(medium)/100)
    if first+second>len(papers):
        raise AssertionError("invalid source layout policy percentages")
    result={}
    for i,p in enumerate(ordered):
        result[p]=("individual" if i<first
                   else "group4" if i<first+second
                   else "paper")
    return result


class SourceReader:
    def __init__(self,db):
        import zstandard as zstd
        self.db=db
        rows=db.execute(
            "SELECT dict_id,payload,sha256,zstd_dict_id "
            "FROM source_dictionaries").fetchall()
        if len(rows)!=1 or rows[0][0]!=1:
            raise ValueError("expected one persisted training-only dictionary")
        _,data,digest,dict_id=rows[0]
        if hashlib.sha256(data).digest()!=digest:
            raise ValueError("stored shared dictionary SHA mismatch")
        self.dictionary=zstd.ZstdCompressionDict(data)
        if self.dictionary.dict_id()!=dict_id:
            raise ValueError("stored shared dictionary ID mismatch")
        self.decoder=zstd.ZstdDecompressor(dict_data=self.dictionary)
        self.encoder=zstd.ZstdCompressor(level=9,dict_data=self.dictionary)

    def inflate(self,blob,n,sha):
        if not 0<=n<=MAX_BLOCK:
            raise ValueError("untrusted source inflated-length bound")
        raw=self.decoder.decompress(blob,max_output_size=n+1)
        if len(raw)!=n or hashlib.sha256(raw).digest()!=sha:
            raise ValueError("original compressed source hash/length mismatch")
        return raw

    def read(self,rid,cache=None):
        row=self.db.execute(
            "SELECT doc_id,compressed,sha256,utf8_len,generation "
            "FROM source_individual WHERE rowid=?",(rid,)).fetchone()
        if row:
            docid,blob,digest,n,generation=row
            raw=self.inflate(blob,n,digest)
            return {
                "doc_id":docid,"source_bytes":raw,"decoded_bytes":len(raw),
                "block_id":None,"layout":"individual",
                "generation":generation,
            }
        receipt=self.db.execute(
            "SELECT doc_id,block_id,byte_offset,utf8_len,sha256,generation "
            "FROM source_receipts WHERE rowid=?",(rid,)).fetchone()
        if receipt is None:raise KeyError("source rowid not in either layout")
        docid,bid,offset,n,digest,generation=receipt
        if cache is not None and bid in cache:
            block,pid=cache[bid]
            newly_inflated=0
        else:
            blockrow=self.db.execute(
                "SELECT paper_id,compressed,sha256,utf8_len,generation "
                "FROM source_blocks WHERE block_id=?",(bid,)).fetchone()
            if blockrow is None:raise KeyError("missing cited source block")
            pid,blob,block_sha,block_n,block_gen=blockrow
            if block_gen<generation:
                raise ValueError("receipt generation newer than block")
            block=self.inflate(blob,block_n,block_sha)
            newly_inflated=len(block)
            if cache is not None:cache[bid]=(block,pid)
        if not str(docid).startswith(str(pid)+"|"):
            raise ValueError("source receipt wrong paper ID")
        if not 0<=offset<=len(block) or not 0<=n<=len(block)-offset:
            raise ValueError("source receipt offset out of bounds")
        raw=block[offset:offset+n]
        if hashlib.sha256(raw).digest()!=digest:
            raise ValueError("source receipt SHA mismatch")
        return {
            "doc_id":docid,"source_bytes":raw,
            "decoded_bytes":newly_inflated,
            "block_id":bid,"layout":"grouped",
            "generation":generation,
        }


def build_archive(path,fts_template,docs,layouts,dictionary):
    """Create one actual mixed SQLite archive without duplicating source bytes.

    All source payloads and dictionary in same SQLite main file.
    Original contentless FTS5 postings left strictly unchanged.
    """
    import shutil
    import zstandard as zstd
    shutil.copyfile(fts_template,path)
    db=sqlite3.connect(str(path),isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    d=zstd.ZstdCompressionDict(dictionary["raw"])
    encoder=zstd.ZstdCompressor(level=9,dict_data=d)
    sources=original_papers(docs)
    if set(layouts)!=set(sources):
        raise AssertionError("every original paper needs an explicit layout")
    t0=time.perf_counter()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE docs")
        db.execute("""
           CREATE TABLE source_dictionaries(
             dict_id INTEGER PRIMARY KEY,
             payload BLOB NOT NULL,
             sha256 BLOB NOT NULL CHECK(length(sha256)=32),
             zstd_dict_id INTEGER NOT NULL
           )""")
        db.execute("""
           CREATE TABLE source_individual(
             rowid INTEGER PRIMARY KEY,
             doc_id TEXT UNIQUE NOT NULL,
             compressed BLOB NOT NULL,
             sha256 BLOB NOT NULL CHECK(length(sha256)=32),
             utf8_len INTEGER NOT NULL CHECK(utf8_len>=0),
             generation INTEGER NOT NULL DEFAULT 1
           )""")
        db.execute("""
           CREATE TABLE source_blocks(
             block_id INTEGER PRIMARY KEY,
             paper_id TEXT NOT NULL,
             compressed BLOB NOT NULL,
             sha256 BLOB NOT NULL CHECK(length(sha256)=32),
             utf8_len INTEGER NOT NULL CHECK(utf8_len>=0),
             generation INTEGER NOT NULL DEFAULT 1
           )""")
        db.execute("""
           CREATE TABLE source_receipts(
             rowid INTEGER PRIMARY KEY,
             doc_id TEXT UNIQUE NOT NULL,
             block_id INTEGER NOT NULL REFERENCES source_blocks(block_id),
             byte_offset INTEGER NOT NULL CHECK(byte_offset>=0),
             utf8_len INTEGER NOT NULL CHECK(utf8_len>=0),
             sha256 BLOB NOT NULL CHECK(length(sha256)=32),
             generation INTEGER NOT NULL DEFAULT 1
           )""")
        db.execute(
            "INSERT INTO source_dictionaries VALUES(1,?,?,?)",
            (dictionary["raw"],dictionary["sha256"],
             dictionary["zstd_dict_id"]))
        next_bid=1
        for pid,rowids in sources.items():
            layout=layouts[pid]
            if layout not in LAYOUTS:
                raise ValueError("unexpected layout")
            if layout=="individual":
                for rid in rowids:
                    raw=document_bytes(docs[rid-1])
                    db.execute(
                        "INSERT INTO source_individual "
                        "(rowid,doc_id,compressed,sha256,utf8_len) "
                        "VALUES(?,?,?,?,?)",
                        (rid,str(docs[rid-1]["doc_id"]),encoder.compress(raw),
                         hashlib.sha256(raw).digest(),len(raw)))
            else:
                maxrows=4 if layout=="group4" else len(rowids)
                for start in range(0,len(rowids),maxrows):
                    selected=rowids[start:start+maxrows]
                    original=[document_bytes(docs[rid-1]) for rid in selected]
                    combined=b"".join(original)
                    if len(combined)>MAX_BLOCK:
                        raise ValueError("original source block too large")
                    db.execute(
                        "INSERT INTO source_blocks "
                        "(block_id,paper_id,compressed,sha256,utf8_len) "
                        "VALUES(?,?,?,?,?)",
                        (next_bid,pid,encoder.compress(combined),
                         hashlib.sha256(combined).digest(),len(combined)))
                    offset=0
                    for rid,raw in zip(selected,original):
                        db.execute(
                            "INSERT INTO source_receipts "
                            "(rowid,doc_id,block_id,byte_offset,utf8_len,sha256)"
                            "VALUES(?,?,?,?,?,?)",
                            (rid,str(docs[rid-1]["doc_id"]),next_bid,
                             offset,len(raw),hashlib.sha256(raw).digest()))
                        offset+=len(raw)
                    next_bid+=1
        db.execute("COMMIT")
        db.execute("VACUUM")
        n=db.execute("SELECT COUNT(*) FROM source_individual").fetchone()[0]
        m=db.execute("SELECT COUNT(*) FROM source_receipts").fetchone()[0]
        if n+m!=len(docs):
            raise AssertionError("some originals lost during archival")
        return db,{"build_seconds":round(time.perf_counter()-t0,5),
                   "independent_paragraphs":n,"grouped_paragraphs":m,
                   "groups":next_bid-1}
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        db.close()
        raise


def source_integrity(db,docs,base_stats):
    """Verify every original source, FTS5 global stats, uniqueness and corpus."""
    reader=SourceReader(db)
    cache={}
    for rid,d in enumerate(docs,1):
        data=reader.read(rid,cache)
        if data["doc_id"]!=str(d["doc_id"]) or data[
                "source_bytes"]!=document_bytes(d):
            raise AssertionError("archive source source-ID/UTF8 bytes changed")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise AssertionError("hybrid SQLite core integrity failed")
    db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
    stat=db.execute(
        "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
    if stat!=base_stats:
        raise AssertionError("hybrid index statistics drifted")
    return len(docs)


def read_cost(db,docs,cases,rankings,k):
    reader=SourceReader(db)
    requested=0
    decoded=0
    n=0
    count_decompress=0
    wall=time.perf_counter()
    for case in cases:
        cache={}
        for rid in rankings[case["id"]][:k]:
            data=reader.read(rid,cache)
            expected=document_bytes(docs[rid-1])
            if data["doc_id"]!=str(docs[rid-1]["doc_id"]) or data[
                "source_bytes"]!=expected:
                raise AssertionError("hybrid source retrieval bytes mismatch")
            requested+=len(expected)
            decoded+=data["decoded_bytes"]
            count_decompress+=int(data["decoded_bytes"]>0)
            n+=1
    return {
        "k":k,"questions":len(cases),"source_receipts_verified":n,
        "requested_original_source_bytes":requested,
        "decoded_original_source_bytes":decoded,
        "decoded_byte_amplification":round(decoded/requested,6)
             if requested else None,
        "decompressions":count_decompress,
        "warm_full_query_source_seconds":round(
            time.perf_counter()-wall,5),
        "cache":"each group inflated at most once within query; no cross-query cache",
    }


def synthetic_edit_plan(docs,n=60):
    """Pseudo-update stress. NO observed real paper revisions exist in QASPER."""
    ranked=sorted(
        range(1,len(docs)+1),
        key=lambda i:(stablehash(EDIT_SALT+"|"+str(docs[i-1]["doc_id"])),i))
    hotspots=ranked[:min(14,len(ranked))]
    result=[]
    for i in range(n):
        if i%3<2:
            rid=hotspots[(i*7+i//3)%len(hotspots)]
        else:
            rid=ranked[(i*131+29)%len(ranked)]
        row=docs[rid-1]
        new_body=" ".join(row["abstract"])+(
            " [R106 artificial revision %d on independent original row %d]"
            %(i,rid))
        result.append((rid,str(row["doc_id"]),str(row["title"]),[new_body]))
    return result


def live_expected(docs,plan):
    result=[
        {"doc_id":str(d["doc_id"]),"title":str(d["title"]),
         "abstract":list(d["abstract"])} for d in docs]
    for rid,docid,title,body in plan:
        if result[rid-1]["doc_id"]!=docid:
            raise AssertionError("mutation source ID does not match")
        result[rid-1]["title"]=title
        result[rid-1]["abstract"]=body
    return result


def edit_source(db,reader,rid,docid,title,abstract,fault=None):
    """One atomic old-text FTS deletion + new postings + SHA source replacement."""
    if db.in_transaction:
        raise RuntimeError("caller transaction not allowed")
    if "\n" in title or not isinstance(title,str):
        raise ValueError("ambiguous original title serialization")
    new=(title+"\n"+" ".join(abstract)).encode("utf8")
    if len(new)>2_000_000:
        raise ValueError("new source exceeds size bound")
    db.execute("BEGIN IMMEDIATE")
    try:
        old=reader.read(rid)
        if old["doc_id"]!=docid:
            raise KeyError("source identity changed")
        old_title,old_body=old["source_bytes"].decode("utf8").split("\n",1)
        db.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) "
            "VALUES('delete',?,?,?)",
            (rid,old_title,old_body))
        db.execute(
            "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
            (rid,title," ".join(abstract)))
        if fault=="after_fts":
            raise RuntimeError("injected fault before original source replacement")
        original_indiv=db.execute(
            "SELECT generation FROM source_individual WHERE rowid=?",
            (rid,)).fetchone()
        if original_indiv:
            db.execute(
                "UPDATE source_individual SET compressed=?,sha256=?,utf8_len=?,"
                "generation=generation+1 WHERE rowid=?",
                (reader.encoder.compress(new),hashlib.sha256(new).digest(),
                 len(new),rid))
            blob_len=db.execute(
                "SELECT length(compressed) FROM source_individual WHERE rowid=?",
                (rid,)).fetchone()[0]
        else:
            meta=db.execute(
                "SELECT block_id,byte_offset,utf8_len FROM source_receipts "
                "WHERE rowid=?",(rid,)).fetchone()
            if meta is None:raise KeyError("cannot find grouped source")
            bid,offset,n=meta
            blockrow=db.execute(
                "SELECT compressed,sha256,utf8_len FROM source_blocks "
                "WHERE block_id=?",(bid,)).fetchone()
            if blockrow is None:raise KeyError("missing original source block")
            blob,sha,block_n=blockrow
            whole=reader.inflate(blob,block_n,sha)
            if whole[offset:offset+n]!=old["source_bytes"]:
                raise ValueError("old source receipt/block mismatch")
            replacement=whole[:offset]+new+whole[offset+n:]
            if len(replacement)>MAX_BLOCK:
                raise ValueError("revised block size cap")
            compressed=reader.encoder.compress(replacement)
            db.execute(
                "UPDATE source_blocks SET compressed=?,sha256=?,utf8_len=?,"
                "generation=generation+1 WHERE block_id=?",
                (compressed,hashlib.sha256(replacement).digest(),
                 len(replacement),bid))
            db.execute(
                "UPDATE source_receipts SET sha256=?,utf8_len=?,"
                "generation=generation+1 WHERE rowid=?",
                (hashlib.sha256(new).digest(),len(new),rid))
            delta=len(new)-n
            if delta:
                db.execute(
                    "UPDATE source_receipts SET byte_offset=byte_offset+? "
                    "WHERE block_id=? AND byte_offset>?",
                    (delta,bid,offset))
            blob_len=len(compressed)
        if fault=="after_source":
            raise RuntimeError("injected fault after original source replacement")
        db.execute("COMMIT")
        return {"compressed_blob_bytes_reencoded":blob_len,
                "edited_original_source_bytes":len(new)}
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise


def dynamic_cost(db,path,docs,plan,query_cases,expected):
    from update_write_frontier import configure_wal
    configure_wal(db)
    reader=SourceReader(db)
    wal=Path(str(path)+"-wal")
    durations=[]
    encoded=[]
    original=[]
    wal_changes=[]
    for rid,docid,title,body in plan:
        prev=wal.stat().st_size if wal.exists() else 0
        start=time.perf_counter_ns()
        result=edit_source(db,reader,rid,docid,title,body)
        durations.append((time.perf_counter_ns()-start)/1e6)
        after=wal.stat().st_size if wal.exists() else 0
        if after<prev:
            raise AssertionError("uncheckpointed WAL unexpectedly shrank")
        wal_changes.append(after-prev)
        encoded.append(result["compressed_blob_bytes_reencoded"])
        original.append(result["edited_original_source_bytes"])
    # Independent full-content FTS5 control built from final synthetic sources.
    with tempfile.TemporaryDirectory() as scratch:
        control,_=make_fts(Path(scratch)/"ctrl.sqlite",expected,False)
        try:
            fts=db.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            ref=control.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            if fts!=ref:raise AssertionError("hybrid source edits changed BM25 stats")
            n_ranks=0
            for c in query_cases:
                a=paper_rank(db,c["claim"],c["row_start"],c["row_end"],10)
                b=paper_rank(control,c["claim"],c["row_start"],c["row_end"],10)
                if a!=b:raise AssertionError("hybrid edit differs from independent FTS")
                n_ranks+=1
        finally:control.close()
    cache={}
    for rid,d in enumerate(expected,1):
        recovered=reader.read(rid,cache)
        if recovered["source_bytes"]!=document_bytes(d):
            raise AssertionError("repeated synthetic edits broke source/offsets")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise AssertionError("SQLite core integrity drift")
    db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
    return {
        "synthetic_source_edits":len(plan),
        "source_rows_after_edits_verified":len(expected),
        "matched_conventional_post_edit_top10":n_ranks,
        "compressed_blob_reencoded_bytes":sum(encoded),
        "new_original_utf8_edit_bytes":sum(original),
        "blob_rewrite_per_edited_source_byte":round(
            sum(encoded)/sum(original),6),
        "wal_appended_bytes":sum(wal_changes),
        "warm_edit_ms":measured_percentiles(durations),
        "revisions":"artificial hot/diffuse, not observed scholarly edit logs",
        "wal":"FULL synchronous, wal_autocheckpoint=0; not physical SSD traffic",
    }


def evaluate(train,dev,policies=POLICIES,edit_count=60):
    if set(train)&set(dev):
        raise AssertionError("dictionary train/DEV papers overlapping")
    docs,cases,cohort=load_dev(dev)
    fit,test=split_queries(cases)
    sources=original_papers(docs)
    samples,trainmeta=independently_trained_samples(train)
    dictionary=train_dictionaries(samples,(65536,))[65536]
    edits=synthetic_edit_plan(docs,edit_count)
    expected=live_expected(docs,edits)
    with tempfile.TemporaryDirectory() as scratch:
        folder=Path(scratch)
        template=folder/"fts-template.sqlite"
        orig=base_fts_db(template,docs)
        try:
            original_stats=orig.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            ranked=all_query_rankings(orig,cases)
        finally:orig.close()
        fit_ranks={x["id"]:ranked[x["id"]] for x in fit}
        original_holdout_gold=gold_recall(
            test,{x["id"]:ranked[x["id"]] for x in test})
        outcomes=[]
        for policy in policies:
            choices=policy_layouts(sources,docs,fit,fit_ranks,policy)
            path=folder/(policy+".sqlite")
            db,build=build_archive(path,template,docs,choices,dictionary)
            try:
                initial=path.stat().st_size
                source_integrity(db,docs,original_stats)
                for case in cases:
                    if paper_rank(
                        db,case["claim"],case["row_start"],case["row_end"],10
                    )!=ranked[case["id"]]:
                        raise AssertionError("source representation changed BM25")
                held_top1=read_cost(db,docs,test,ranked,1)
                held_top10=read_cost(db,docs,test,ranked,10)
                fitted_top10=read_cost(db,docs,fit,ranked,10)
                by_layout=Counter(choices.values())
                cost=dynamic_cost(
                    db,path,docs,edits,cases,expected)
                outcomes.append({
                    "policy":policy,
                    "paper_layout_distribution":dict(by_layout),
                    "initial_source_plus_index_sqlite_bytes":initial,
                    "source_dictionaries_in_main_db":len(dictionary["raw"]),
                    "fits_budgets":{str(x):bool(initial<=x) for x in BUDGETS},
                    "building":build,
                    "fitted_question_top10_reads":fitted_top10,
                    "heldout_question_top1_reads":held_top1,
                    "heldout_question_top10_reads":held_top10,
                    "synthetic_heldout_edit_stress":cost,
                    "original_source_readbacks":len(docs),
                    "identical_original_question_ranks":len(cases),
                })
            finally:db.close()
        return {
            "round":106,
            "source":"QASPER v0.3 article-disjoint TRAIN dictionary and DEV original source",
            "source_sha256":{"train":TRAIN_SHA,"dev":DEV_SHA},
            "dictionary_source":"original TRAIN papers only, no QA labels",
            "dictionary_sha256":dictionary["sha256"].hex(),
            "dictionary_bytes":len(dictionary["raw"]),
            "question_split":{
                "method":"SHA parity of original question ID; pseudo-history, not chronological",
                "fit_queries":len(fit),"heldout_queries":len(test),
                "distinct_query_ids":len({x["id"] for x in cases}),
                "fit_and_test_can_share_article":True,
                "fit_evidence_annotations_used":False,
                "heldout_question_text_used_in_policy":False,
            },
            "original_corpus":cohort,
            "heldout_gold_evidence_recall_control":original_holdout_gold,
            "budgets_bytes":list(BUDGETS),
            "synthetic_edits":len(edits),
            "synthetic_unique_source_ids":len({x[0] for x in edits}),
            "archives":outcomes,
            "limits":[
                "QASPER has no real access/edits timeline. Split is hash-defined pseudo-history, not a prospective chronological holdout",
                "Fit and test questions can refer to the same article, a transductive access scenario, not unseen papers",
                "Update stress is fully synthetic, independent of QA labels; it does not demonstrate source edit prediction",
                "Every candidate uses complete original source and unchanged BM25 FTS postings, so original gold evidence recall cannot change",
                "Actual full source+index database, shared dictionary, source offsets/hashes, and WAL writes measured; no online layout migration measured",
                "Source plus index SQLite bytes exclude model weights, reader RAM, cold SSD and full background updates",
                "Compression and hot/cold tiering are published prior art; no novel algorithm claimed from combination",
                "One runner sequential warm measurement; source read amplification stronger than latency as mechanism",
                "Known QASPER paper ID and paragraph-level retrieval, not global open-domain scholarly search",
            ],
        }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=p.parse_args()
    release=fetch_qasper()
    if release["train"]["sha256"]!=TRAIN_SHA or (
            release["dev"]["sha256"]!=DEV_SHA):
        raise AssertionError("original QASPER release changed")
    result=evaluate(release["train"]["data"],release["dev"]["data"])
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND106",json.dumps({
        "source_docs":result["original_corpus"]["questions"],
        "question_split":result["question_split"],
        "heldout_gold":result["heldout_gold_evidence_recall_control"],
        "archives":[{
            "policy":r["policy"],"bytes":r["initial_source_plus_index_sqlite_bytes"],
            "layouts":r["paper_layout_distribution"],
            "top1":r["heldout_question_top1_reads"]["decoded_byte_amplification"],
            "top10":r["heldout_question_top10_reads"]["decoded_byte_amplification"],
            "wal":r["synthetic_heldout_edit_stress"]["wal_appended_bytes"],
            "edit_rewrite":r["synthetic_heldout_edit_stress"][
                "blob_rewrite_per_edited_source_byte"],
            "top10_rank_parity":r["synthetic_heldout_edit_stress"][
                "matched_conventional_post_edit_top10"],
        } for r in result["archives"]],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
