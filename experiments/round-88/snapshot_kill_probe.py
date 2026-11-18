#!/usr/bin/env python3
"""R88: read-snapshot coherence and process SIGKILL recovery for R87.

Tests an existing R87 retrieval race: a ranking computed before an update
may be paired with compressed source bytes read after that update. The fix
is a single read transaction around query+verified source retrieval.
Only process-kill, not power-loss or storage crash, is tested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-87"))
from atomic_source_db import (  # noqa: E402
    EXPECTED_RELEASE_SHA,
    atomic_update,
    create_db,
    digests,
    document_bytes,
    fetch,
    parse,
    query,
    read,
)

FIXTURE = [
    {"doc_id": 101, "title": "oldquartz",
     "abstract": ["Original observation baseline."]},
    {"doc_id": 202, "title": "thirdlarch",
     "abstract": ["A completely unrelated control document."]},
]
NEW_TITLE = "newnebula"
NEW_ABSTRACT = ["Changed observation published."]
NEW_BYTES = (NEW_TITLE + "\n" + " ".join(NEW_ABSTRACT)).encode("utf8")
OLD_BYTES = document_bytes(FIXTURE[0])
SIGKILL_RETURN = -signal.SIGKILL


def configure_mode(conn, mode):
    """Change journal mode only outside a transaction."""
    if mode not in ("DELETE", "WAL"):
        raise ValueError("journal mode must be DELETE or WAL")
    observed = conn.execute("PRAGMA journal_mode=" + mode).fetchone()[0].upper()
    if observed != mode:
        raise RuntimeError(f"journal mode requested {mode}, got {observed}")
    # SQLite documents EXTRA as a stronger rollback-journal durability setting.
    # Neither setting proves storage power-loss safety in this experiment.
    conn.execute("PRAGMA synchronous=" + ("EXTRA" if mode == "DELETE" else "FULL"))
    conn.execute("PRAGMA busy_timeout=3000")
    return observed


def retrieve_snapshot(conn, claim, k=1, interleave=None):
    """Bind FTS ranking and SHA-verified evidence bytes to one read snapshot.

    The optional interleave hook is exclusively for deterministic tests.
    This function must own the transaction to prevent ambiguous nesting.
    """
    if conn.in_transaction:
        raise RuntimeError("retrieve_snapshot requires no existing transaction")
    conn.execute("BEGIN")
    try:
        ranks = query(conn, claim, k)
        if interleave is not None:
            interleave()
        output = [(rid, read(conn, rid)) for rid in ranks]
        conn.execute("COMMIT")
        return output
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def kill_worker(db_path, stage, mode):
    """Executed in a separate OS process. Never called in the test process."""
    if stage not in ("after_payload", "after_index", "after_commit"):
        raise ValueError(stage)
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=3.0)
    conn.execute("PRAGMA synchronous=" + ("EXTRA" if mode == "DELETE" else "FULL"))
    conn.execute("BEGIN IMMEDIATE")
    rec = conn.execute("SELECT doc_id,generation FROM docs WHERE rowid=1").fetchone()
    if rec is None or str(rec[0]) != "101":
        raise AssertionError("wrong source before worker update")
    conn.execute(
        "UPDATE docs SET compressed=?,sha256=?,utf8_len=?,generation=? WHERE rowid=1",
        (zlib.compress(NEW_BYTES, 6),
         hashlib.sha256(NEW_BYTES).digest(), len(NEW_BYTES), rec[1] + 1),
    )
    if stage == "after_payload":
        os.kill(os.getpid(), signal.SIGKILL)
    conn.execute("DELETE FROM sources WHERE rowid=1")
    conn.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                 (1, NEW_TITLE, " ".join(NEW_ABSTRACT)))
    if stage == "after_index":
        os.kill(os.getpid(), signal.SIGKILL)
    conn.execute("COMMIT")
    os.kill(os.getpid(), signal.SIGKILL)


def verify_recovered(path, committed):
    """Check both index and SHA-bound original bytes on a fresh connection."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        core_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if core_integrity != "ok":
            raise AssertionError(f"SQLite integrity: {core_integrity}")
        # FTS5's own check validates internal index structure, NOT equality
        # between postings and compressed source bytes.
        conn.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
        source = read(conn, 1)
        expected = NEW_BYTES if committed else OLD_BYTES
        if source["source_bytes"] != expected:
            raise AssertionError("recovered compressed source mismatch")
        if source["generation"] != (2 if committed else 1):
            raise AssertionError("recovered generation mismatch")
        if query(conn, "oldquartz") != ([] if committed else [1]):
            raise AssertionError("recovered old-term index mismatch")
        if query(conn, "newnebula") != ([1] if committed else []):
            raise AssertionError("recovered new-term index mismatch")
        return {"generation": source["generation"],
                "core_integrity": core_integrity,
                "fts5_integrity": "pass",
                "source_sha256_checked": True}
    finally:
        conn.close()


def crash_matrix():
    """Six fully independent DBs, child SIGKILL at three transaction stages."""
    records = []
    with tempfile.TemporaryDirectory() as root:
        for mode in ("DELETE", "WAL"):
            for stage in ("after_payload", "after_index", "after_commit"):
                folder = Path(root) / (mode + "-" + stage)
                folder.mkdir()
                path = folder / "source.sqlite"
                conn, _ = create_db(path, FIXTURE)
                configure_mode(conn, mode)
                conn.close()
                command = [sys.executable, str(Path(__file__).resolve()),
                           "--worker", str(path), stage, mode]
                proc = subprocess.run(command, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, timeout=15,
                                      check=False)
                if proc.returncode != SIGKILL_RETURN:
                    raise AssertionError(
                        f"worker {mode}/{stage} exited {proc.returncode}: "
                        + proc.stderr.decode("utf8", "replace")[-1500:])
                committed = stage == "after_commit"
                verified = verify_recovered(path, committed)
                records.append({"journal_mode": mode, "kill_stage": stage,
                                "child_exit": "SIGKILL",
                                "expected_state": "new" if committed else "old",
                                **verified})
    return records


def concurrency_probe():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "concurrent.sqlite"
        conn, _ = create_db(path, FIXTURE)
        configure_mode(conn, "WAL")
        conn.close()
        reader = sqlite3.connect(str(path), isolation_level=None)
        writer = sqlite3.connect(str(path), isolation_level=None)
        try:
            # Deliberately unsafe legacy pattern: query and read on separate
            # implicit SQLite snapshots. The rowid is still valid, but source
            # bytes can be from a different generation than the ranking.
            old_rank = query(reader, "oldquartz")
            assert old_rank == [1]
            atomic_update(writer, 1, "101", NEW_TITLE, NEW_ABSTRACT)
            fractured = read(reader, old_rank[0])
            if fractured["source_bytes"] != NEW_BYTES:
                raise AssertionError("unsafe fracture not reproduced")
            if query(reader, "oldquartz"):
                raise AssertionError("updated index still matched old term")
            # Restore old source through the same existing R87 atomic API.
            atomic_update(writer, 1, "101", FIXTURE[0]["title"],
                          FIXTURE[0]["abstract"])
            # A WAL read transaction sees old source even when a writer commits
            # a new version after the search and before source materialization.
            def interleave():
                atomic_update(writer, 1, "101", NEW_TITLE, NEW_ABSTRACT)
            result = retrieve_snapshot(reader, "oldquartz", 1, interleave)
            if len(result) != 1 or result[0][0] != 1:
                raise AssertionError("missing snapshot source")
            if result[0][1]["source_bytes"] != OLD_BYTES:
                raise AssertionError("read snapshot became torn")
            if read(reader, 1)["source_bytes"] != NEW_BYTES:
                raise AssertionError("post-commit reader did not advance")
            return {
                "journal_mode": "WAL",
                "legacy_split_search_then_read_fractured": True,
                "committed_writer_during_snapshot_read": True,
                "snapshot_old_bytes_preserved": True,
                "source_changes_visible_after_snapshot": True,
                "note": "R87 index and compressed source are atomically updated; "
                        "R88 fixes query/read transaction isolation at caller boundary",
            }
        finally:
            reader.close()
            writer.close()


def warm_synthetic_latency():
    """Synthetic descriptive latency. No cold-storage or throughput claim."""
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "warm.sqlite"
        conn, _ = create_db(path, FIXTURE)
        configure_mode(conn, "WAL")
        try:
            latency = {"split_autocommit": [], "snapshot_transaction": []}
            for run_index in range(12):
                order = (["split_autocommit", "snapshot_transaction"] if run_index % 2
                         else ["snapshot_transaction", "split_autocommit"])
                for mode in order:
                    for _ in range(50):
                        t0 = time.perf_counter_ns()
                        if mode == "split_autocommit":
                            r = query(conn, "oldquartz", 1)
                            out = [(i, read(conn, i)) for i in r]
                        else:
                            out = retrieve_snapshot(conn, "oldquartz", 1)
                        latency[mode].append((time.perf_counter_ns()-t0)/1e6)
                        if out[0][1]["source_bytes"] != OLD_BYTES:
                            raise AssertionError("benchmark source incorrect")
            return {key: {"calls": len(v), "median_ms": round(statistics.median(v), 6),
                          "p95_ms": round(sorted(v)[int(.95*(len(v)-1))], 6)}
                    for key,v in latency.items()}
        finally:
            conn.close()


def original_scifact_probe():
    """No semantic model; 300 source-read equivalence tests on original corpus."""
    tar, raw = fetch()
    actual_sha = digests(tar)["sha256"]
    if actual_sha != EXPECTED_RELEASE_SHA:
        raise AssertionError("original SciFact release digest mismatch")
    corpus, claims, _ = parse(raw)
    with tempfile.TemporaryDirectory() as root:
        db, meta = create_db(Path(root)/"scifact.sqlite", corpus)
        configure_mode(db, "WAL")
        try:
            intact = 0
            for row in claims:
                for rid, rec in retrieve_snapshot(db, row["claim"], k=1):
                    if rec["source_bytes"] != document_bytes(corpus[rid-1]):
                        raise AssertionError("SciFact original source mismatch")
                    intact += 1
            if intact != len(claims):
                raise AssertionError("missing SciFact source for a claim")
            return {"upstream_sha256": actual_sha,
                    "docs": len(corpus),
                    "queries": len(claims),
                    "matching_sha_verified_top1_receipts": intact,
                    "sqlite_version": sqlite3.sqlite_version,
                    "original_r87_storage_bytes": meta["persistent_index_and_source_bytes"],
                    "note": "No changes to BM25 query, gold Recall or semantic verifier"}
        finally:
            db.close()


def run(full=False):
    result = {
        "round": 88,
        "risk": "inter-query/index-to-source time-of-check/time-of-use race",
        "concurrency_reproduction": concurrency_probe(),
        "process_sigkill_matrix": crash_matrix(),
        "synthetic_warm_latency": warm_synthetic_latency(),
        "not_tested": [
            "Kernel panic, actual power loss, arbitrary-byte-level tear",
            "Networked filesystems, SSD cold reads, full concurrent throughput",
            "Semantic answer grounding, multiple retrieved documents with updates",
            "Version history and adversarial corruption of FTS postings",
        ],
    }
    if full:
        result["original_scifact"] = original_scifact_probe()
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", nargs=3, metavar=("DB", "STAGE", "MODE"))
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", default=str(HERE/"ci-results.json"))
    args = ap.parse_args()
    if args.worker:
        kill_worker(*args.worker)
        raise RuntimeError("worker must die with SIGKILL")
    result = run(full=args.full)
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("ROUND88", json.dumps(result, sort_keys=True), flush=True)
