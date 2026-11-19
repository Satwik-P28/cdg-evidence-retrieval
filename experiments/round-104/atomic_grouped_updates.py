#!/usr/bin/env python3
"""R104: atomic, source-verified QASPER grouped paragraph revisions.

Use R103 original grouped zstd-dict or Brotli source store. A single
SQLite BEGIN IMMEDIATE transaction updates:
  (1) verified old-text standard-contentless FTS5 delete,
  (2) new-text FTS postings,
  (3) re-compressed entire affected source block and its digest,
  (4) original paragraph receipt SHA/length and following byte offsets.
Add source/block generation to guard repeated edits. All original source
metadata belongs to the same database. Test SIGKILL vs rollback in WAL
and DELETE journal modes. Not a physical power-cut durability proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-90","round-96","round-97","round-101",
          "round-102","round-103"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,paper_rank
from contentless_cas import document_bytes,make_fts
from paper_block_brotli import base_fts_db,make_grouped_brotli
from joint_group_dictionary import (
    GroupSourceReader,group_variant,TRAINED_SIZE
)
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries,TRAIN_SHA,DEV_SHA
)

FAULTS=("after_fts_delete","after_fts_insert",
        "after_block_recompress","after_receipts","after_commit")


def migrate_generations(db):
    """One-time migration for R103 static archive: original versions start at 1."""
    for table in ("source_blocks","source_receipts"):
        columns={str(x[1]) for x in db.execute(
            "PRAGMA table_info("+table+")").fetchall()}
        if "generation" not in columns:
            db.execute(
                "ALTER TABLE "+table+
                " ADD COLUMN generation INTEGER NOT NULL DEFAULT 1")
    db.execute("PRAGMA foreign_keys=ON")


def verified_source(db,rid):
    reader=GroupSourceReader(db)
    return reader.read(rid)


def stage(fault,at):
    if fault==at:
        raise RuntimeError("injected transactional failure: "+at)
    if fault=="kill_"+at:
        os.kill(os.getpid(),signal.SIGKILL)


def update_grouped(db,rid,doc_id,title,abstract,fault=None):
    """Update one original source record and its FTS5 postings in one transaction.

    Requires an ordinary contentless FTS5 and verified original source.
    To undo old postings, the original title/body *must* come from SHA
    verified, trusted prior source bytes. Never use contentless_delete=1
    DELETE+INSERT due known inflated index metadata in R89.
    """
    legal={None,*FAULTS,*("kill_"+x for x in FAULTS)}
    if fault not in legal:raise ValueError("invalid fault injection stage")
    if not isinstance(title,str) or "\n" in title:
        raise ValueError("source section title must be string without newline")
    if not isinstance(abstract,list) or not all(
            isinstance(part,str) for part in abstract):
        raise ValueError("source body must be list of strings")
    new_source=(title+"\n"+" ".join(abstract)).encode("utf8")
    if len(new_source)>2_000_000:
        raise ValueError("source paragraph too large")
    if db.in_transaction:
        raise RuntimeError("update requires independent write transaction")
    db.execute("BEGIN IMMEDIATE")
    committed=False
    try:
        reader=GroupSourceReader(db)
        receipt=db.execute(
            "SELECT doc_id,block_id,byte_offset,utf8_len,sha256,generation "
            "FROM source_receipts WHERE rowid=?",(rid,)).fetchone()
        if receipt is None or str(receipt[0])!=str(doc_id):
            raise KeyError("original source identity mismatch")
        old_docid,bid,offset,old_n,old_digest,generation=receipt
        old=reader.read(rid)
        if old["doc_id"]!=old_docid or len(old["source_bytes"])!=old_n or (
                hashlib.sha256(old["source_bytes"]).digest()!=old_digest):
            raise ValueError("prior source receipt failed verification")
        raw,pid=reader.block(bid)
        if not str(doc_id).startswith(str(pid)+"|"):
            raise ValueError("block paper ID mismatch")
        if offset<0 or offset+old_n>len(raw):
            raise ValueError("invalid receipt block bounds")
        if raw[offset:offset+old_n]!=old["source_bytes"]:
            raise ValueError("prior source block does not contain exact receipt")
        prev=old["source_bytes"].decode("utf8")
        if "\n" not in prev:
            raise ValueError("old source title and body cannot be separated")
        old_title,old_body=prev.split("\n",1)
        block_codec=db.execute(
            "SELECT codec,dict_id,generation FROM source_blocks WHERE block_id=?",
            (bid,)).fetchone()
        if block_codec is None:raise KeyError("missing block metadata")
        codec,dict_id,block_generation=block_codec
        if not 1<=generation<=block_generation:
            raise ValueError("unexpected source/block generation version")
        # Original verified title/body, NOT a stale external untrusted text.
        db.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) "
            "VALUES('delete',?,?,?)",
            (rid,old_title,old_body))
        stage(fault,"after_fts_delete")
        db.execute(
            "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
            (rid,title," ".join(abstract)))
        stage(fault,"after_fts_insert")
        next_block=raw[:offset]+new_source+raw[offset+old_n:]
        if len(next_block)>12_000_000:
            raise ValueError("new original source block exceeds safety cap")
        if codec=="brotli5":
            if dict_id!=0:raise ValueError("brotli has unexpected dictionary")
            import brotli
            compressed=brotli.compress(next_block,quality=5)
        elif codec in ("zstd3-dictionary","zstd9-dictionary"):
            if dict_id!=1 or reader.dict_decoder is None:
                raise ValueError("missing referenced shared dictionary")
            import zstandard as zstd
            dictionary_row=db.execute(
                "SELECT payload,sha256,zstd_dict_id "
                "FROM source_dictionaries WHERE dict_id=1").fetchone()
            if dictionary_row is None:
                raise ValueError("missing source dictionary")
            stored,digest,did=dictionary_row
            if hashlib.sha256(stored).digest()!=digest:
                raise ValueError("corrupted dictionary")
            dictionary=zstd.ZstdCompressionDict(stored)
            if dictionary.dict_id()!=did:
                raise ValueError("mismatched source dictionary ID")
            level=3 if codec.startswith("zstd3") else 9
            compressed=zstd.ZstdCompressor(
                level=level,dict_data=dictionary).compress(next_block)
        else:
            raise ValueError("unknown block codec")
        db.execute(
            "UPDATE source_blocks SET compressed=?,sha256=?,utf8_len=?,"
            "generation=generation+1 WHERE block_id=?",
            (compressed,hashlib.sha256(next_block).digest(),
             len(next_block),bid))
        stage(fault,"after_block_recompress")
        delta=len(new_source)-old_n
        db.execute(
            "UPDATE source_receipts SET utf8_len=?,sha256=?,generation=generation+1 "
            "WHERE rowid=?",
            (len(new_source),hashlib.sha256(new_source).digest(),rid))
        if delta:
            db.execute(
                "UPDATE source_receipts SET byte_offset=byte_offset+? "
                "WHERE block_id=? AND byte_offset>?",
                (delta,bid,offset))
        stage(fault,"after_receipts")
        db.execute("COMMIT")
        committed=True
        stage(fault,"after_commit")
        return {"doc_id":str(doc_id),"source_generation":generation+1,
                "block_generation":block_generation+1,
                "source_utf8_len":len(new_source),
                "subsequent_block_offset_delta":delta}
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise


def retrieve_snapshot(db,query,start,end,k=10,interleave=None):
    """WAL-safe read transaction keeps ranking and verified original source coherent."""
    if db.in_transaction:
        raise RuntimeError("snapshot must start outside caller transaction")
    db.execute("BEGIN")
    try:
        ids=paper_rank(db,query,start,end,k)
        if interleave is not None:
            interleave()
        reader=GroupSourceReader(db)
        receipts=[(rid,reader.read(rid)) for rid in ids]
        db.execute("COMMIT")
        return receipts
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise


def create_test_archive(path,docs,group,variant="zstd9-dictionary",dictionary=None):
    """Build original reference with same SQLite schema and R90 FTS semantics."""
    root=path.parent
    source=root/(path.stem+"-fts.sqlite")
    grouped=root/(path.stem+"-blocks.sqlite")
    base=base_fts_db(source,docs)
    base.close()
    block=make_grouped_brotli(grouped,source,docs,group)
    block.close()
    db,_=group_variant(path,grouped,variant,dictionary or {})
    migrate_generations(db)
    return db


def conventional_source_update(db,rid,title,abstract):
    db.execute(
        "UPDATE sources SET title=?,abstract=? WHERE rowid=?",
        (title," ".join(abstract),rid))
    db.commit()


def fts_stats(db):
    return db.execute("SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]


def kill_worker_main(path,fault,source_id,new_value):
    db=sqlite3.connect(path,isolation_level=None,timeout=8)
    try:
        update_grouped(db,1,source_id,"Section",
                       ["changed original source "+new_value],fault=fault)
        return 0
    finally:db.close()


def subprocess_crash_probe(docs,dictionary):
    """Ten actual SIGKILL cases: 2 journal modes × 5 update stages.

    Restart SQLite connection to verify old state if uncommitted, new if
    post-COMMIT; count FTS and source hashes. No physical device power-loss.
    """
    if not docs:raise AssertionError("empty source corpus")
    original=dict(docs[0])
    expected=document_bytes(original)
    outcomes=[]
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        for mode in ("DELETE","WAL"):
            for stage_name in FAULTS:
                path=root/f"kill-{mode}-{stage_name}.sqlite"
                db=create_test_archive(path,docs,group=4,dictionary=dictionary)
                db.execute("PRAGMA journal_mode="+mode)
                db.execute("PRAGMA synchronous=FULL")
                db.close()
                process=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--kill-worker",str(path),"kill_"+stage_name,
                     str(original["doc_id"]),str(stage_name)],
                    check=False,capture_output=True,text=True,timeout=30)
                # -9 on POSIX is actual process SIGKILL.
                if process.returncode!=-signal.SIGKILL:
                    raise AssertionError(
                        f"expected SIGKILL ({mode},{stage_name}): "
                        f"{process.returncode} {process.stderr[-500:]}")
                recovered=sqlite3.connect(str(path),isolation_level=None)
                try:
                    reader=GroupSourceReader(recovered)
                    receipt=reader.read(1)
                    committed=stage_name=="after_commit"
                    target=(b"Section\nchanged original source "+stage_name.encode()
                            if committed else expected)
                    if receipt["source_bytes"]!=target:
                        raise AssertionError(
                            "SIGKILL recovered mismatched source or generation")
                    total=recovered.execute(
                        "SELECT count(*) FROM source_receipts").fetchone()[0]
                    if total!=len(docs):
                        raise AssertionError("source receipt count lost on process kill")
                    if recovered.execute(
                        "PRAGMA integrity_check").fetchone()[0]!="ok":
                        raise AssertionError("SQLite integrity failed after SIGKILL")
                    recovered.execute(
                        "INSERT INTO sources(sources) VALUES('integrity-check')")
                    generation=recovered.execute(
                        "SELECT generation FROM source_receipts WHERE rowid=1"
                    ).fetchone()[0]
                    if generation!=(2 if committed else 1):
                        raise AssertionError("generation leaked before COMMIT")
                    outcomes.append({
                        "mode":mode,"kill_stage":stage_name,
                        "committed_source_visible":committed,
                        "fts_and_core_integrity":"ok",
                        "source_generations":generation,
                    })
                finally:recovered.close()
    return outcomes


def original_corpus_revisions(train_papers,dev_papers,edits=120):
    """Frozen original dev paragraph texts but synthetic *test-only* revisions.

    No post-mutation human answer quality measurement: original QASPER
    labels refer to original evidence and are invalid for edited text.
    """
    if set(train_papers)&set(dev_papers):
        raise AssertionError("train/dev original paper overlap")
    from train_only_zstd_dictionary import (
        independently_trained_samples,train_dictionaries
    )
    samples,training=independently_trained_samples(train_papers)
    dictionary=train_dictionaries(samples,(TRAINED_SIZE,))[TRAINED_SIZE]
    docs,cases,_=load_dev(dev_papers)
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        path=root/"grouped.sqlite"
        db=create_test_archive(path,docs,group=4,dictionary=dictionary)
        ref,_=make_fts(root/"fullcontrol.sqlite",docs,False)
        # Use a journal mode that supports a separate snapshot writer.
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        ref.execute("PRAGMA journal_mode=WAL")
        original=[dict(x) for x in docs]
        try:
            edits_details=[]
            for i in range(edits):
                # Alternating hot and diffuse original rowids. Deterministic
                # source bodies, no human evidence labels or dev questions.
                rid=1 if i%3==0 else ((i*131)%len(docs))+1
                row=original[rid-1]
                title=str(row["title"])
                base_body=" ".join(row["abstract"])
                body=base_body+" [R104 synthetic edit %d, source %s]"%(
                    i,str(row["doc_id"]))
                if i%11==0:
                    body=body+" added supporting text"
                result=update_grouped(
                    db,rid,str(row["doc_id"]),title,[body])
                conventional_source_update(ref,rid,title,[body])
                row["abstract"]=[body]
                if i%15==0:
                    if fts_stats(db)!=fts_stats(ref):
                        raise AssertionError("grouped incremental FTS stats drifted")
                if GroupSourceReader(db).read(rid)["source_bytes"]!=document_bytes(row):
                    raise AssertionError("updated source receipt differs")
                edits_details.append(result)
            if fts_stats(db)!=fts_stats(ref):
                raise AssertionError("FTS stats drift after full revision workload")
            # Read *every* original/live source; unrelated paragraphs must
            # remain byte-exact and offsets must be kept in sync.
            reader=GroupSourceReader(db)
            for rid,row in enumerate(original,1):
                if reader.read(rid)["source_bytes"]!=document_bytes(row):
                    raise AssertionError("repeated updates broke source offsets")
            expected_rank=[]
            for claim in cases:
                ids=paper_rank(
                    ref,claim["claim"],claim["row_start"],claim["row_end"],10)
                actual=paper_rank(
                    db,claim["claim"],claim["row_start"],claim["row_end"],10)
                if ids!=actual:
                    raise AssertionError("incremental BM25 differs from conventional")
                expected_rank.append(ids)
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("grouped original store integrity lost")
            db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
            # Real single reader snapshot with an interleaved writer in WAL.
            read_conn=sqlite3.connect(str(path),isolation_level=None,timeout=10)
            writer=sqlite3.connect(str(path),isolation_level=None,timeout=10)
            # q "fixed" matches the chosen original index? query first source
            # paper and title to ensure evidence source at least one.
            one=original[0]
            query=one["title"]+" "+one["abstract"][0][:25]
            source_before=GroupSourceReader(read_conn).read(1)["source_bytes"]
            new_source=(one["title"]+"\n"+" ".join(one["abstract"])+
                        " [interleaved writer]").encode("utf8")
            def interleave():
                update_grouped(
                    writer,1,str(one["doc_id"]),one["title"],
                    [one["abstract"][0]+" [interleaved writer]"])
            snapshot=retrieve_snapshot(
                read_conn,query,cases[0]["row_start"],cases[0]["row_end"],
                k=10,interleave=interleave)
            if not snapshot:
                raise AssertionError("snapshot probe did not find any source")
            # Source 1 might not be the ranked top 1. The read transaction
            # must see OLD version for any row it retrieves, and a new
            # transaction must observe the newly committed row-1 bytes.
            if GroupSourceReader(read_conn).read(1)["source_bytes"]!=new_source:
                raise AssertionError("post snapshot reader cannot see new source")
            if source_before==new_source:
                raise AssertionError("update didn't change source")
            read_conn.close();writer.close()
            return {
                "round":104,"source_docs":len(docs),
                "questions_original":len(cases),
                "synthetic_source_revisions":edits,
                "different_rowids_mutated":len({
                    1 if i%3==0 else ((i*131)%len(docs))+1 for i in range(edits)}),
                "original_source_readbacks_verified":len(docs),
                "unchanged_fts_stats_against_full_content":True,
                "identical_1005_query_top10_after_synthetic_edits":len(cases),
                "snapshot_interleaved_WAL_writer":"committed new source visible after reader transaction",
                "first_edit":edits_details[0],
                "last_edit":edits_details[-1],
                "dictionary_trained_on_only_source_train_articles":True,
                "prior_art":"ordinary contentless FTS5 old-text special delete plus SQLite transaction and grouped SHA receipts",
            }
        finally:
            db.close();ref.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    parser.add_argument("--kill-worker",nargs=4,metavar=(
        "DB_PATH","FAULT","DOC_ID","VALUE"))
    args=parser.parse_args()
    if args.kill_worker:
        path,fault,doc_id,value=args.kill_worker
        return kill_worker_main(path,fault,doc_id,value)
    source=fetch_qasper()
    if source["train"]["sha256"]!=TRAIN_SHA or source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("original QASPER source release changed")
    result=original_corpus_revisions(
        source["train"]["data"],source["dev"]["data"])
    docs,_,_=load_dev({
        k:v for k,v in list(source["dev"]["data"].items())[:1]})
    # For kill fixtures, use the first four original QASPER paragraphs
    # within one paper and *original* immutable source identity.
    docs=docs[:min(len(docs),12)]
    if len(docs)<4:
        raise AssertionError("SIGKILL original source fixture unexpectedly tiny")
    samples,_=independently_trained_samples(source["train"]["data"])
    dictionary=train_dictionaries(samples,(TRAINED_SIZE,))[TRAINED_SIZE]
    result["sigkill_crash_cases"]=subprocess_crash_probe(docs,dictionary)
    result["original_train_sha256"]=TRAIN_SHA
    result["original_dev_sha256"]=DEV_SHA
    result["caveats"]=[
        "Only synthetic post-ingestion source edits; no original human answer claim evaluation after mutation",
        "One SQLite transaction for old FTS posting delete, new posting, block payload and offsets",
        "SIGKILL simulated process termination, not physical power-loss or SSD cache durability",
        "WAL concurrent snapshot read verifies source generation consistency, not high-throughput multiwriter scalability",
        "Reader code for grouped source is experimental; production upgrade and migration require further audit",
        "All shared dictionary training uses original article-disjoint TRAIN source text without QA labels",
    ]
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND104",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
