#!/usr/bin/env python3
"""R101: Lossless QASPER paragraph blocks with source-exact receipts.

Compare one-per-paragraph Brotli5 against paper-local grouped Brotli5:
1, 2, 4, 8, 16, and all paragraphs per original paper.

Fixed identical full-corpus FTS5 postings and original source texts. One
transaction constructs a separate block table + rowid receipt table;
full database size includes all offsets, hashes, block IDs and postings.
Measure decompressed byte amplification and warm top1/top10 original
source receipts under no cross-query cache. No answer-quality claim.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-90","round-96","round-97","round-99","round-100"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,paper_rank,gold_recall
from contentless_cas import document_bytes
from old_source_incremental import create_legacy_contentless
from codec_frontier import encode,read_codec,measured_percentiles

GROUPS=(1,2,4,8,16,"paper")
MAX_BLOCK_BYTES=12_000_000
DEV_SHA="2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93"


def paper_id(doc):
    fields=str(doc["doc_id"]).rsplit("|",2)
    if len(fields)!=3:
        raise AssertionError("original QASPER row identity lost")
    return fields[0]


def partition_paper_blocks(docs,group):
    if group not in GROUPS:
        raise ValueError("unexpected group length")
    out=[]
    active=[]
    last_paper=None
    for rid,doc in enumerate(docs,1):
        p=paper_id(doc)
        if last_paper is not None and p!=last_paper:
            if active:out.append(active)
            active=[]
        if len(active)==group and group!="paper":
            out.append(active)
            active=[]
        active.append(rid)
        last_paper=p
    if active:out.append(active)
    if [rid for block in out for rid in block]!=list(range(1,len(docs)+1)):
        raise AssertionError("block partition missing a rowid")
    for block in out:
        if len({paper_id(docs[rid-1]) for rid in block})!=1:
            raise AssertionError("source block crosses article boundary")
    return out


def source_sha(data):
    return hashlib.sha256(data).digest()


def base_fts_db(path,docs):
    db=create_legacy_contentless(path,docs)
    db.execute("ALTER TABLE docs ADD COLUMN codec TEXT NOT NULL DEFAULT 'brotli5'")
    db.execute("VACUUM")
    return db


def make_individual_brotli(path,source_db_path,docs):
    shutil.copyfile(source_db_path,path)
    db=sqlite3.connect(str(path),isolation_level=None)
    try:
        db.execute("BEGIN IMMEDIATE")
        for i,doc in enumerate(docs,1):
            raw=document_bytes(doc)
            db.execute(
                "UPDATE docs SET compressed=?,codec='brotli5' WHERE rowid=?",
                (encode("brotli5",raw),i))
        db.execute("COMMIT")
        db.execute("VACUUM")
        return db
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        db.close()
        raise


def make_grouped_brotli(path,source_db_path,docs,group):
    shutil.copyfile(source_db_path,path)
    blocks=partition_paper_blocks(docs,group)
    db=sqlite3.connect(str(path),isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE docs")
        db.execute("""
        CREATE TABLE source_blocks(
          block_id INTEGER PRIMARY KEY,
          paper_id TEXT NOT NULL,
          compressed BLOB NOT NULL,
          codec TEXT NOT NULL,
          sha256 BLOB NOT NULL CHECK(length(sha256)=32),
          utf8_len INTEGER NOT NULL,
          source_rows INTEGER NOT NULL
        )""")
        db.execute("""
        CREATE TABLE source_receipts(
          rowid INTEGER PRIMARY KEY,
          doc_id TEXT UNIQUE NOT NULL,
          block_id INTEGER NOT NULL REFERENCES source_blocks(block_id),
          byte_offset INTEGER NOT NULL CHECK(byte_offset>=0),
          utf8_len INTEGER NOT NULL CHECK(utf8_len>=0),
          sha256 BLOB NOT NULL CHECK(length(sha256)=32)
        )""")
        for block_id,rowids in enumerate(blocks,1):
            raw_parts=[document_bytes(docs[rid-1]) for rid in rowids]
            block_bytes=b"".join(raw_parts)
            if len(block_bytes)>MAX_BLOCK_BYTES:
                raise ValueError("group exceeds bounded decompression size")
            db.execute(
                "INSERT INTO source_blocks VALUES(?,?,?,?,?,?,?)",
                (block_id,paper_id(docs[rowids[0]-1]),
                 encode("brotli5",block_bytes),"brotli5",
                 source_sha(block_bytes),len(block_bytes),len(rowids)))
            offset=0
            for rid,raw in zip(rowids,raw_parts):
                db.execute(
                    "INSERT INTO source_receipts VALUES(?,?,?,?,?,?)",
                    (rid,str(docs[rid-1]["doc_id"]),block_id,
                     offset,len(raw),source_sha(raw)))
                offset+=len(raw)
        db.execute("COMMIT")
        db.execute("VACUUM")
        if db.execute(
            "SELECT COUNT(*) FROM source_receipts").fetchone()[0]!=len(docs):
            raise AssertionError("every source lacks exactly one receipt")
        return db
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        db.close()
        raise


def decode_block(db,block_id):
    row=db.execute(
        "SELECT paper_id,compressed,codec,sha256,utf8_len,source_rows "
        "FROM source_blocks WHERE block_id=?",(block_id,)).fetchone()
    if row is None:raise KeyError("missing original source block")
    pid,blob,codec,expected_sha,n,source_rows=row
    if codec!="brotli5" or n>MAX_BLOCK_BYTES or n<0:
        raise ValueError("bad source block codec or decoded bound")
    import brotli
    raw=brotli.decompress(blob)
    if len(raw)!=n or source_sha(raw)!=expected_sha:
        raise ValueError("source block hash/length mismatch")
    return raw,pid,n,source_rows


def read_receipt(db,rid,cache=None):
    row=db.execute(
        "SELECT doc_id,block_id,byte_offset,utf8_len,sha256 "
        "FROM source_receipts WHERE rowid=?",(rid,)).fetchone()
    if row is None:raise KeyError("missing individual original source")
    doc_id,block_id,offset,length,expected_sha=row
    if cache is not None and block_id in cache:
        block,source_paper,decoded_len,nrows=cache[block_id]
        inflated=0
    else:
        block,source_paper,decoded_len,nrows=decode_block(db,block_id)
        if cache is not None:
            cache[block_id]=(block,source_paper,decoded_len,nrows)
        inflated=decoded_len
    if not str(doc_id).startswith(source_paper+"|"):
        raise ValueError("source receipt crosses paper provenance")
    if offset<0 or length<0 or offset+length>len(block):
        raise ValueError("receipt offsets escape authenticated block")
    original=block[offset:offset+length]
    if source_sha(original)!=expected_sha:
        raise ValueError("source receipt digest mismatch")
    return {"doc_id":doc_id,"source_bytes":original,
            "block_id":block_id,"decoded_block_bytes":inflated,
            "requested_source_bytes":length}


def queries_for_original(docs,cases,db):
    hits={}
    for case in cases:
        hits[case["id"]]=paper_rank(
            db,case["claim"],case["row_start"],case["row_end"],10)
    return hits


def read_probe(db,docs,hits,grouped,k):
    """No inter-query cache. Cache each decompressed block within one query."""
    total_requested=0
    total_inflated=0
    receipt_count=0
    block_decompressions=0
    source_decode_times=[]
    start=time.perf_counter()
    for rowids in hits.values():
        cache={} if grouped else None
        for rid in rowids[:k]:
            t0=time.perf_counter_ns()
            if grouped:
                receipt=read_receipt(db,rid,cache)
                got=receipt["source_bytes"]
                inflated=receipt["decoded_block_bytes"]
                block_decompressions+=int(inflated>0)
            else:
                got=read_codec(db,rid,str(docs[rid-1]["doc_id"]))
                inflated=len(got)
                block_decompressions+=1
            source_decode_times.append(
                (time.perf_counter_ns()-t0)/1e6)
            expected=document_bytes(docs[rid-1])
            if got!=expected:
                raise AssertionError("source differs from original QASPER bytes")
            total_requested+=len(expected)
            total_inflated+=inflated
            receipt_count+=1
    return {
        "k":k,
        "requested_sources_sha_exact":receipt_count,
        "requested_original_source_utf8_bytes":total_requested,
        "decompressed_original_block_bytes":total_inflated,
        "decoded_byte_amplification":round(total_inflated/total_requested,5)
        if total_requested else None,
        "block_decompressions":block_decompressions,
        "warm_inprocess_source_receipt_ms":measured_percentiles(source_decode_times),
        "warm_full_probe_seconds":round(time.perf_counter()-start,5),
        "cache":"Per-query block cache, no cache across questions" if grouped
        else "Each independently encoded original source decoded on request",
    }


def evaluate(docs,cases,groups=GROUPS):
    originals=[document_bytes(doc) for doc in docs]
    if len(originals)!=len({str(doc["doc_id"]) for doc in docs}):
        raise AssertionError("QASPER source identity collision")
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        baseline=root/"fts-base.sqlite"
        temp=base_fts_db(baseline,docs)
        try:
            fts_stats=temp.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            queries=queries_for_original(docs,cases,temp)
        finally:temp.close()
        expected_gold=gold_recall(cases,queries)
        ref_file=root/"individual.sqlite"
        db=make_individual_brotli(ref_file,baseline,docs)
        try:
            expected_size=ref_file.stat().st_size
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("bad individual source database")
            individual={
                "name":"individual_brotli5",
                "source_plus_fts_sqlite_bytes":expected_size,
                "blocks":len(docs),
                "original_sources_verified":len(docs),
                "fts_stats_same":True,
                "read_top1":read_probe(db,docs,queries,False,1),
                "read_top10":read_probe(db,docs,queries,False,10),
            }
            for i,raw in enumerate(originals,1):
                if read_codec(db,i,str(docs[i-1]["doc_id"]))!=raw:
                    raise AssertionError("invalid baseline original source")
        finally:db.close()
        results=[]
        for group in groups:
            path=root/("blocks_"+str(group)+".sqlite")
            c=make_grouped_brotli(path,baseline,docs,group)
            try:
                if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise AssertionError("bad block SQLite integrity")
                c.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
                if c.execute(
                    "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]!=fts_stats:
                    raise AssertionError("group transformation changed search index")
                for rid,raw in enumerate(originals,1):
                    receipt=read_receipt(c,rid)
                    if receipt["source_bytes"]!=raw or receipt[
                        "doc_id"]!=str(docs[rid-1]["doc_id"]):
                        raise AssertionError("block/source receipt original mismatch")
                blocks=c.execute("SELECT COUNT(*) FROM source_blocks").fetchone()[0]
                max_decoded=c.execute(
                    "SELECT MAX(utf8_len) FROM source_blocks").fetchone()[0]
                row={
                    "group":group,
                    "source_plus_fts_sqlite_bytes":path.stat().st_size,
                    "bytes_saved_vs_individual":expected_size-path.stat().st_size,
                    "source_blocks":blocks,
                    "original_sources_verified":len(originals),
                    "fts_stats_same":True,
                    "max_uncompressed_block_bytes":max_decoded,
                    "read_top1":read_probe(c,docs,queries,True,1),
                    "read_top10":read_probe(c,docs,queries,True,10),
                }
                results.append(row)
            finally:c.close()
        return {
            "round":101,
            "source_docs":len(docs),
            "queries":len(cases),
            "full_original_evidence_recall":expected_gold,
            "source_sha_provenance":DEV_SHA,
            "index":"Original unchanged contentless FTS5 title5, body1, original question paper scope",
            "individual":individual,
            "groups":results,
            "limitations":[
                "All original QASPER sources are exact and SHA verified; only storage representation is changed",
                "Block compression is existing Brotli5 and boundary offsets, not novel compression mathematics",
                "Global FTS5 index and original source IDs unchanged; evidence recall cannot improve from grouping alone",
                "Block decompress amplification excludes SQLite page reads, CPU cache effects and disk I/O amplification",
                "Per-query block cache is ephemeral; cross-query cache could help but consumes more RAM",
                "Block rebuild/write amplification not measured; changes require recompressing entire affected block",
                "Brotli decompression not strict pre-inflate memory bounded; source block expected length and SHA checked after",
                "No free-form answer generation, source citations in generator, semantic verification or hallucination accuracy",
                "One GitHub CI runner warm timings do not give reliable SSD p99 latency claims",
            ],
        }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=parser.parse_args()
    source=fetch_qasper()
    if source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("original QASPER release unexpectedly changed")
    docs,cases,_=load_dev(source["dev"]["data"])
    result=evaluate(docs,cases)
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND101",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
