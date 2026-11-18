#!/usr/bin/env python3
"""R90: old-source-assisted FTS5 contentless incremental revision.

Test the documented FTS5 'delete' command for ordinary contentless
tables (NOT contentless_delete=1). Recover old title/abstract bytes from
the verified compressed docs table. Independently compare FTS global
statistics, BM25 rankings, exact sources, latency and disk space against
the strong full-content FTS5 control and R87 contentless-delete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/"round-86"))
sys.path.insert(0, str(HERE.parent/"round-87"))
sys.path.insert(0, str(HERE.parent/"round-88"))
sys.path.insert(0, str(HERE.parent/"round-89"))
from atomic_source_db import (
    create_db, atomic_update, read, query, EXPECTED_RELEASE_SHA, fetch, parse, digests
)
from contentless_cas import make_fts, query_fts
from snapshot_kill_probe import configure_mode, retrieve_snapshot
from dynamic_workloads import (
    revision_events, fts5_global_stats, file_bytes, summarize_latency
)


def split_verified_source(data):
    """R87's title/newline/abstract serialization requires no title newlines."""
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("source must be verified bytes")
    text = data.decode("utf8", "strict")
    title, delim, abstract = text.partition("\n")
    if not delim or "\n" in title:
        raise ValueError("R90 title/abstract boundary missing")
    return title, abstract


def create_legacy_contentless(path, corpus):
    """Reuse R87 compressed docs then replace only its FTS implementation."""
    conn, _ = create_db(path, corpus)
    conn.execute("DROP TABLE sources")
    conn.execute("CREATE VIRTUAL TABLE sources USING fts5("
                 "title,abstract,content='',tokenize='unicode61')")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for i, row in enumerate(corpus, 1):
            # We can construct from original text in this initial build only.
            conn.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                         (i, row["title"], " ".join(row["abstract"])))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        conn.close()
        raise
    conn.execute("VACUUM")
    return conn


def update_with_prior_source(conn, rowid, doc_id, title, abstract, fault=None):
    """One transaction holds manual FTS delete, insert and compressed source.

    FTS 'delete' MUST receive precisely the prior indexed title and abstract,
    verified against SHA-bound compressed bytes, or it can damage index state.
    """
    if fault not in (None, "after_delete", "after_insert", "after_payload"):
        raise ValueError("unrecognized fault stage")
    if not isinstance(title, str) or "\n" in title:
        raise ValueError("title must contain no newline for current encoding")
    if not isinstance(abstract, list) or not all(isinstance(v, str) for v in abstract):
        raise ValueError("invalid abstract sequence")
    next_abstract = " ".join(abstract)
    next_bytes = (title + "\n" + next_abstract).encode("utf8")
    conn.execute("BEGIN IMMEDIATE")
    try:
        prev = conn.execute(
            "SELECT doc_id,generation FROM docs WHERE rowid=?", (rowid,)
        ).fetchone()
        if prev is None or str(prev[0]) != str(doc_id):
            raise KeyError("source identity mismatch")
        prev_source = read(conn, rowid)
        old_title, old_abstract = split_verified_source(prev_source["source_bytes"])
        if prev_source["generation"] != prev[1]:
            raise AssertionError("unstable generation within transaction")
        conn.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) "
            "VALUES('delete',?,?,?)", (rowid,old_title,old_abstract))
        if fault == "after_delete":
            raise RuntimeError("injected failure after FTS delete")
        conn.execute(
            "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
            (rowid,title,next_abstract))
        if fault == "after_insert":
            raise RuntimeError("injected failure after FTS insert")
        conn.execute(
            "UPDATE docs SET compressed=?,sha256=?,utf8_len=?,generation=? "
            "WHERE rowid=?",
            (zlib.compress(next_bytes,6), hashlib.sha256(next_bytes).digest(),
             len(next_bytes),prev[1]+1,rowid))
        if fault == "after_payload":
            raise RuntimeError("injected failure after source update")
        conn.execute("COMMIT")
        return prev[1]+1
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def delete_with_prior_source(conn,rowid,doc_id,fault=None):
    if fault not in (None,"after_index"):
        raise ValueError("unrecognized fault stage")
    conn.execute("BEGIN IMMEDIATE")
    try:
        old=conn.execute("SELECT doc_id FROM docs WHERE rowid=?", (rowid,)).fetchone()
        if old is None or str(old[0]) != str(doc_id):
            raise KeyError("source identity mismatch")
        old_title,old_abstract=split_verified_source(read(conn,rowid)["source_bytes"])
        conn.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) "
            "VALUES('delete',?,?,?)", (rowid,old_title,old_abstract))
        if fault=="after_index":
            raise RuntimeError("injected delete failure")
        conn.execute("DELETE FROM docs WHERE rowid=?", (rowid,))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def run_one(corpus, claims, mode, pattern, n, hotset):
    events=revision_events(corpus,pattern,n,hotset)
    with tempfile.TemporaryDirectory() as root:
        p=Path(root)
        paths={name:p/(name+".sqlite") for name in ("full","r87","r90")}
        full,_=make_fts(paths["full"],corpus,False)
        original,_=create_db(paths["r87"],corpus)
        manual=create_legacy_contentless(paths["r90"],corpus)
        conns={"full":full,"r87":original,"r90":manual}
        try:
            full.isolation_level=None
            for conn in conns.values():
                configure_mode(conn,mode)
            before={name:file_bytes(path) for name,path in paths.items()}
            costs={name:[] for name in conns}
            expected={}
            for i,(rid,docid,title,abstract) in enumerate(events):
                # Rotate execution order to avoid a consistent second-run bias.
                order=(list(conns) if i%3==0 else
                       (["r87","r90","full"] if i%3==1 else
                        ["r90","full","r87"]))
                for method in order:
                    t0=time.perf_counter_ns()
                    if method=="full":
                        full.execute("UPDATE sources SET title=?,abstract=? WHERE rowid=?",
                                     (title," ".join(abstract),rid))
                        full.commit()
                    elif method=="r87":
                        atomic_update(original,rid,docid,title,abstract)
                    else:
                        update_with_prior_source(manual,rid,docid,title,abstract)
                    costs[method].append((time.perf_counter_ns()-t0)/1e6)
                expected[rid]=(title,abstract)
            stats={name:fts5_global_stats(conn) for name,conn in conns.items()}
            live={name:conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                  for name,conn in conns.items()}
            if any(count!=len(corpus) for count in live.values()):
                raise AssertionError("live row count changed")
            if stats["full"]!=stats["r90"]:
                raise AssertionError("old-text FTS5 delete not statistics-equivalent: "
                                     +repr(stats))
            exact={"r90":0,"r87":0}
            for row in claims:
                ranked_full=query_fts(full,row["claim"],10)
                ranked_old=[rid for rid,_ in retrieve_snapshot(original,row["claim"],10)]
                ranked_manual=[rid for rid,_ in retrieve_snapshot(manual,row["claim"],10)]
                exact["r87"]+=int(ranked_full==ranked_old)
                exact["r90"]+=int(ranked_full==ranked_manual)
            if exact["r90"]!=len(claims):
                raise AssertionError("source-assisted contentless ranking drift")
            for rid,(title,abstract) in expected.items():
                target=(title+"\n"+" ".join(abstract)).encode("utf8")
                if read(manual,rid)["source_bytes"]!=target:
                    raise AssertionError("r90 compressed source invalid")
                if read(original,rid)["source_bytes"]!=target:
                    raise AssertionError("r87 compressed source invalid")
                if full.execute("SELECT title,abstract FROM sources WHERE rowid=?",
                                (rid,)).fetchone()!=(title," ".join(abstract)):
                    raise AssertionError("baseline text mismatch")
            internal_check={}
            for name,conn in conns.items():
                result=conn.execute("PRAGMA integrity_check").fetchone()[0]
                if result!="ok":
                    raise AssertionError(name+" core integrity check "+result)
                conn.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
                internal_check[name]="pass"
            active={name:file_bytes(path) for name,path in paths.items()}
            if mode=="WAL":
                for conn in conns.values():
                    if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
                        raise AssertionError("checkpoint blocked")
            checkpointed={name:file_bytes(path) for name,path in paths.items()}
            for conn in conns.values():
                conn.execute("VACUUM")
            if mode=="WAL":
                for conn in conns.values():
                    if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]!=0:
                        raise AssertionError("vacuum checkpoint blocked")
            vacuumed={name:file_bytes(path) for name,path in paths.items()}
            return {
                "journal_mode":mode, "pattern":pattern,
                "events":n, "distinct_modified":len(expected),
                "docs":len(corpus), "claims":len(claims),
                "stats":stats,"live_rows":live,
                "top10_equal_to_full_control":exact,
                "updated_docs_verified":len(expected),
                "fts_integrity":internal_check,
                "storage_bytes":{"initial":before,"active":active,
                                 "checkpointed":checkpointed,"vacuumed":vacuumed},
                "median_write_latency_ms":{
                    k:round(statistics.median(v),5) for k,v in costs.items()},
                "p95_write_latency_ms":{
                    k:round(sorted(v)[int(.95*(len(v)-1))],5) for k,v in costs.items()},
                "r90_persist_savings_vs_full_pct":round(
                    100*(vacuumed["full"]-vacuumed["r90"])/vacuumed["full"],4),
            }
        finally:
            for conn in conns.values():
                conn.close()


def run(full_data=False):
    if full_data:
        tar, raw=fetch()
        digest=digests(tar)["sha256"]
        if digest!=EXPECTED_RELEASE_SHA:
            raise AssertionError("SciFact release digest changed")
        corpus,claims,_=parse(raw)
        n=500
        hotset=50
        provenance={"dataset":"SciFact original","sha256":digest}
    else:
        corpus=[{"doc_id":i+1,"title":"mineral"+str(i),
                 "abstract":["Previously observed batch "+str(i)+"."]}
                for i in range(30)]
        claims=[{"id":i,"claim":"mineral"+str(i)} for i in range(10)]
        n=20
        hotset=4
        provenance={"dataset":"deterministic synthetic 30-doc control"}
    results=[]
    for mode in ("DELETE","WAL"):
        for pattern in ("diffuse","hot"):
            results.append(run_one(corpus,claims,mode,pattern,n,hotset))
    return {
        "round":90,
        "provenance":provenance,
        "intervention":"ordinary contentless FTS5 'delete' with SHA-verified old source terms, then insert new, all in one SQLite transaction",
        "results":results,
        "scientific_limits":[
            "Uses R87 title + newline + joined abstract format; title must contain no newline",
            "FTS5 'delete' requires exact old text; SHA verifies stored bytes but independent verification of indexed prior text is limited",
            "Benchmark writes are single-process, warm cache, and synthetic artificial revisions",
            "No power-loss, SSD cold-I/O, multi-process throughput, human claim labels or generated answers",
            "Old-source-assisted contentless FTS5 is documented prior art, not a novel ranking or compression algorithm",
        ],
    }


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--full",action="store_true")
    ap.add_argument("--out",default=str(HERE/"ci-results.json"))
    opts=ap.parse_args()
    result=run(full_data=opts.full)
    Path(opts.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND90",json.dumps(result,sort_keys=True),flush=True)
