#!/usr/bin/env python3
"""R91: source-store-only FTS reconstruction and SIGKILL update fault matrix.

Source reconstruction uses only verified compressed docs rows from R90.
No dependency on original corpus or revision event log during repair.
True child-process SIGKILL covers four atomic update stages x DELETE/WAL.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import tempfile
import time
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-90"))
sys.path.insert(0,str(HERE.parent/"round-87"))
sys.path.insert(0,str(HERE.parent/"round-86"))
sys.path.insert(0,str(HERE.parent/"round-88"))
sys.path.insert(0,str(HERE.parent/"round-89"))
from old_source_incremental import (
    create_legacy_contentless,update_with_prior_source,split_verified_source,
)
from atomic_source_db import read,query,fetch,parse,digests,EXPECTED_RELEASE_SHA
from contentless_cas import make_fts,query_fts
from snapshot_kill_probe import configure_mode,retrieve_snapshot
from dynamic_workloads import fts5_global_stats

DOCS=[
 {"doc_id":101,"title":"oldzircon","abstract":["Original light source."]},
 {"doc_id":202,"title":"controlboron","abstract":["Constant comparison."]},
]
NEW_TITLE="newneutron"
NEW_ABSTRACT=["Revised light source."]
NEW_BYTES=(NEW_TITLE+"\n"+" ".join(NEW_ABSTRACT)).encode("utf8")
OLD_BYTES=(DOCS[0]["title"]+"\n"+" ".join(DOCS[0]["abstract"])).encode("utf8")


def rebuild_from_compressed_docs(conn,fault=None):
    """Rebuild index solely from current SHA-checked compressed docs.

    No original corpus or revision oracle is consulted. Requires R87's
    newline-separated title+joined abstract serialization and no title
    containing a newline. Holds exclusive write transaction throughout.
    """
    if fault not in (None,"after_delete_all","after_first_insert"):
        raise ValueError("unknown rebuild failure injection")
    start=time.perf_counter()
    conn.execute("BEGIN IMMEDIATE")
    try:
        ids=[row[0] for row in conn.execute("SELECT rowid FROM docs ORDER BY rowid")]
        # Preflight source digest validation before changing FTS in txn.
        current=[]
        for rid in ids:
            previous=read(conn,rid)
            title,abstract=split_verified_source(previous["source_bytes"])
            current.append((rid,title,abstract))
        conn.execute("INSERT INTO sources(sources) VALUES('delete-all')")
        if fault=="after_delete_all":
            raise RuntimeError("injected rebuild failure after deleting FTS")
        for idx,(rid,title,abstract) in enumerate(current):
            conn.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                         (rid,title,abstract))
            if idx==0 and fault=="after_first_insert":
                raise RuntimeError("injected partial rebuild failure")
        conn.execute("COMMIT")
        return {"docs_rebuilt":len(current),
                "wall_seconds":round(time.perf_counter()-start,5),
                "fts5_global_statistics":fts5_global_stats(conn)}
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def poison_index_without_touching_sources(conn,rowid=1):
    """Create internally valid but source-inconsistent FTS via crafted term swap."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        old=read(conn,rowid)
        title,abstract=split_verified_source(old["source_bytes"])
        conn.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) VALUES('delete',?,?,?)",
            (rowid,title,abstract))
        conn.execute(
            "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
            (rowid,"spurioussearchtoken","spurious abstract"))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:conn.execute("ROLLBACK")
        raise


def worker(path,stage,mode):
    if stage not in ("after_delete","after_insert","after_payload","after_commit"):
        raise ValueError("invalid kill point")
    conn=sqlite3.connect(path,isolation_level=None,timeout=3.0)
    conn.execute("PRAGMA synchronous="+("EXTRA" if mode=="DELETE" else "FULL"))
    conn.execute("BEGIN IMMEDIATE")
    current=conn.execute("SELECT doc_id,generation FROM docs WHERE rowid=1").fetchone()
    if current!=("101",1):
        raise AssertionError("unexpected pre-crash source")
    old_title,old_abstract=split_verified_source(read(conn,1)["source_bytes"])
    conn.execute(
        "INSERT INTO sources(sources,rowid,title,abstract) VALUES('delete',?,?,?)",
        (1,old_title,old_abstract))
    if stage=="after_delete":os.kill(os.getpid(),signal.SIGKILL)
    conn.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                 (1,NEW_TITLE," ".join(NEW_ABSTRACT)))
    if stage=="after_insert":os.kill(os.getpid(),signal.SIGKILL)
    conn.execute(
        "UPDATE docs SET compressed=?,sha256=?,utf8_len=?,generation=? WHERE rowid=1",
        (zlib.compress(NEW_BYTES,6),hashlib.sha256(NEW_BYTES).digest(),len(NEW_BYTES),2))
    if stage=="after_payload":os.kill(os.getpid(),signal.SIGKILL)
    conn.execute("COMMIT")
    os.kill(os.getpid(),signal.SIGKILL)


def verify_fresh(path,committed):
    db=sqlite3.connect(str(path),isolation_level=None)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("SQLite file corruption detected")
        db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
        source=read(db,1)
        if source["source_bytes"]!=(NEW_BYTES if committed else OLD_BYTES):
            raise AssertionError("source state torn")
        if source["generation"]!=(2 if committed else 1):
            raise AssertionError("source generation torn")
        if query(db,"newneutron")!=([1] if committed else []):
            raise AssertionError("new FTS state torn")
        if query(db,"oldzircon")!=([] if committed else [1]):
            raise AssertionError("old FTS state torn")
        stats=fts5_global_stats(db)
        if stats[0]!=2:
            raise AssertionError("FTS metadata changed unexpectedly")
        return {"fts_and_source_recovered":True,"generation":source["generation"],
                "fts_global_doc_count":stats[0]}
    finally:db.close()


def kill_matrix():
    import subprocess
    rows=[]
    with tempfile.TemporaryDirectory() as root:
        for mode in ("DELETE","WAL"):
            for stage in ("after_delete","after_insert","after_payload","after_commit"):
                p=Path(root)/(mode+"-"+stage)
                p.mkdir()
                filename=p/"source.sqlite"
                db=create_legacy_contentless(filename,DOCS)
                configure_mode(db,mode)
                db.close()
                child=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "--worker",str(filename),stage,mode],
                    capture_output=True,timeout=15)
                if child.returncode!=-signal.SIGKILL:
                    raise AssertionError(f"worker {mode}/{stage} returned {child.returncode}:"
                                         +child.stderr.decode("utf8","replace"))
                result=verify_fresh(filename,stage=="after_commit")
                rows.append({"mode":mode,"stage":stage,**result})
    return rows


def reader_snapshot_race():
    with tempfile.TemporaryDirectory() as root:
        path=Path(root)/"source.sqlite"
        db=create_legacy_contentless(path,DOCS)
        configure_mode(db,"WAL")
        db.close()
        reader=sqlite3.connect(str(path),isolation_level=None)
        writer=sqlite3.connect(str(path),isolation_level=None)
        try:
            def interleave():
                update_with_prior_source(writer,1,"101",NEW_TITLE,NEW_ABSTRACT)
            rows=retrieve_snapshot(reader,"oldzircon",1,interleave)
            if len(rows)!=1 or rows[0][1]["source_bytes"]!=OLD_BYTES:
                raise AssertionError("snapshot failed to preserve old generation")
            if read(reader,1)["source_bytes"]!=NEW_BYTES:
                raise AssertionError("committed new source not visible after transaction")
            if query(reader,"oldzircon") or query(reader,"newneutron")!=[1]:
                raise AssertionError("new index not visible after transaction")
            return {"old_generation_inside_read_snapshot":True,
                    "writer_committed_during_read":True,
                    "new_generation_visible_after_read":True}
        finally:reader.close();writer.close()


def synthetic_repair():
    with tempfile.TemporaryDirectory() as root:
        path=Path(root)/"source.sqlite"
        db=create_legacy_contentless(path,DOCS)
        try:
            old_stats=fts5_global_stats(db)
            poison_index_without_touching_sources(db)
            if query(db,"spurioussearchtoken")!=[1]:
                raise AssertionError("index poison not actually inserted")
            if read(db,1)["source_bytes"]!=OLD_BYTES:
                raise AssertionError("source was modified by index poisoning")
            db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
            # Internal integrity check passes, does not compare source BLOB.
            after_poison={"internal_fts_check":"pass but mismatched source",
                          "false_index_term_visible":True}
            for fault in ("after_delete_all","after_first_insert"):
                with_error=False
                try:rebuild_from_compressed_docs(db,fault)
                except RuntimeError:with_error=True
                if not with_error or query(db,"spurioussearchtoken")!=[1]:
                    raise AssertionError("rebuild failure was not atomic")
            repaired=rebuild_from_compressed_docs(db)
            if query(db,"spurioussearchtoken") or query(db,"oldzircon")!=[1]:
                raise AssertionError("source-only index reconstruction unsuccessful")
            if repaired["fts5_global_statistics"]!=old_stats:
                raise AssertionError("reconstructed FTS corpus stats not exact")
            return {"poisoned":after_poison,"repair":repaired,
                    "rebuild_rollback_injections":2,
                    "source_text_authenticated":True}
        finally:db.close()


def full_scifact_recovery():
    tar,raw=fetch()
    digest=digests(tar)["sha256"]
    if digest!=EXPECTED_RELEASE_SHA:raise AssertionError("upstream SciFact changed")
    corpus,claims,_=parse(raw)
    with tempfile.TemporaryDirectory() as root:
        p=Path(root)
        full,_=make_fts(p/"full.sqlite",corpus,False)
        compressed=create_legacy_contentless(p/"compressed.sqlite",corpus)
        try:
            poison_index_without_touching_sources(compressed)
            if query(compressed,"spurioussearchtoken")!=[1]:
                raise AssertionError("index poisoning not reproduced")
            before=fts5_global_stats(compressed)
            repaired=rebuild_from_compressed_docs(compressed)
            after=fts5_global_stats(compressed)
            if before==after:
                # Synthetic poison changes lengths in normal case; never rely
                # only on equality of global stats to detect semantic mismatch.
                pass
            if after!=fts5_global_stats(full):
                raise AssertionError("reconstructed full-corpus FTS global tokens wrong")
            matched=0
            byte_exact=0
            for claim in claims:
                a=query_fts(full,claim["claim"],10)
                b=[rid for rid,_ in retrieve_snapshot(compressed,claim["claim"],10)]
                if a==b:matched+=1
                else:raise AssertionError("reconstructed BM25 ranking differs")
                if b:
                    rid=b[0]
                    expected=(corpus[rid-1]["title"]+"\n"+" ".join(
                        corpus[rid-1]["abstract"])).encode("utf8")
                    if read(compressed,rid)["source_bytes"]!=expected:
                        raise AssertionError("receipt differs from original source")
                    byte_exact+=1
            return {"upstream_sha256":digest,"docs":len(corpus),
                    "claims":len(claims),"top10_equal_to_full":matched,
                    "sha_verified_top1_receipts":byte_exact,
                    "repair":repaired,
                    "independent_repair_source":"Only compressed docs table; no original corpus passed to repair"}
        finally:full.close();compressed.close()


def run(full=False):
    result={"round":91,
            "eight_process_sigkill_cases":kill_matrix(),
            "synthetic_forged_index_and_self_repair":synthetic_repair(),
            "reader_snapshot":reader_snapshot_race(),
            "not_tested":["physical SSD power-loss or network filesystem",
                          "arbitrary-byte corruption model outside tested injection",
                          "revisions with newlines in source titles",
                          "large-scale concurrent writer throughput or live-service schema migrations",
                          "human source support or generated answer hallucinations"]}
    if full:result["original_scifact"]=full_scifact_recovery()
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--worker",nargs=3,metavar=("DB","STAGE","MODE"))
    ap.add_argument("--full",action="store_true")
    ap.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=ap.parse_args()
    if a.worker:
        worker(*a.worker)
        raise AssertionError("SIGKILL worker returned normally")
    result=run(full=a.full)
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND91",json.dumps(result,sort_keys=True),flush=True)
