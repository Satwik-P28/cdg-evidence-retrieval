#!/usr/bin/env python3
"""R89: matched dynamic FTS5 update and persistence experiment.

Compare existing full-content FTS5 to R87 atomic contentless-delete+compressed
source after *identical* revision events. Each method retains readable original
source data. Report active WAL, post-checkpoint and VACUUM storage separately.
No inference-model, cold SSD, or power-loss results are claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-86"))
sys.path.insert(0, str(HERE.parent / "round-87"))
sys.path.insert(0, str(HERE.parent / "round-88"))
from contentless_cas import make_fts, query_fts, document_bytes, EXPECTED_RELEASE_SHA
from atomic_source_db import create_db, atomic_update, read, fetch, parse, digests
from snapshot_kill_probe import configure_mode, retrieve_snapshot


def revision_events(corpus, pattern, n=500, hotset=50, seed=1989):
    if not corpus:
        raise ValueError("empty source corpus")
    rng = random.Random(seed)
    ids = list(range(1, len(corpus) + 1))
    rng.shuffle(ids)
    if pattern == "diffuse":
        if n > len(corpus):
            raise ValueError("diffuse requires n unique documents")
        picks = ids[:n]
    elif pattern == "hot":
        hot = ids[:min(hotset, len(corpus))]
        picks = [hot[i % len(hot)] for i in range(n)]
    else:
        raise ValueError("pattern must be diffuse or hot")
    events = []
    for step, rid in enumerate(picks, 1):
        base = corpus[rid-1]
        # Synthetic replacement, never append to prior revision. The fixed
        # token distinguishes generations and exercises both FTS columns.
        title = base["title"] + " cdgversion" + str(step)
        abstract = list(base["abstract"]) + ["Revision token batch" + str(step) + "."]
        events.append((rid, str(base["doc_id"]), title, abstract))
    return events


def file_bytes(path):
    return sum(p.stat().st_size for p in
               (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"))
               if p.exists())


def summarize_latency(ms):
    order = sorted(ms)
    return {"events": len(order),
            "median_ms": round(statistics.median(order), 5),
            "p95_ms": round(order[int(.95 * (len(order)-1))], 5),
            "total_ms": round(sum(order), 3)}


def do_full_update(conn, rid, title, abstract):
    # Existing SQLite FTS5 contentful UPDATE is the fair source-readable
    # baseline; it stores source text and postings in the same one DB.
    conn.execute("UPDATE sources SET title=?,abstract=? WHERE rowid=?",
                 (title, " ".join(abstract), rid))
    conn.commit()


def fts5_global_stats(conn):
    """Decode FTS5 %_data row 1's varint [documents, tokens per column]."""
    row = conn.execute("SELECT block FROM sources_data WHERE id=1").fetchone()
    if row is None:
        raise AssertionError("missing FTS5 global stats")
    values, current = [], 0
    for byte in row[0]:
        current = (current << 7) | (byte & 127)
        if byte < 128:
            values.append(current)
            current = 0
    if current or len(values) != 3:
        raise AssertionError("unexpected FTS5 two-column statistics encoding")
    return values


def verify_pair(full, atomic, corpus, claims, expected):
    """Diagnose divergence but always enforce exact source integrity."""
    for label, db in (("full", full), ("atomic", atomic)):
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise AssertionError(f"{label} PRAGMA integrity_check: {result}")
        db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
        db.commit()
    stat_full = fts5_global_stats(full)
    stat_atomic = fts5_global_stats(atomic)
    live_full = full.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    live_atomic = atomic.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    if live_full != len(corpus) or live_atomic != len(corpus):
        raise AssertionError("live document count actually changed")
    identical = 0
    total_overlap = 0
    first_differences = []
    sha_readbacks = 0
    for row in claims:
        a = query_fts(full, row["claim"], 10)
        b = [rid for rid, _ in retrieve_snapshot(atomic, row["claim"], 10)]
        if a == b:
            identical += 1
        elif len(first_differences) < 3:
            first_differences.append({
                "claim_id": str(row["id"]),
                "conventional_top10": a,
                "compressed_top10": b,
            })
        total_overlap += len(set(a).intersection(b))
        for label, ranked in (("full", a), ("atomic", b)):
            if not ranked:
                continue
            rid = ranked[0]
            title, abstract = expected.get(
                rid, (corpus[rid-1]["title"], list(corpus[rid-1]["abstract"])))
            raw = (title + "\n" + " ".join(abstract)).encode("utf8")
            if label == "full":
                got = full.execute(
                    "SELECT title,abstract FROM sources WHERE rowid=?", (rid,)
                ).fetchone()
                if got != (title, " ".join(abstract)):
                    raise AssertionError("full source content mismatch")
            else:
                if read(atomic, rid)["source_bytes"] != raw:
                    raise AssertionError("compressed verified source mismatch")
                sha_readbacks += 1
    for rid, (title, abstract) in expected.items():
        raw = (title + "\n" + " ".join(abstract)).encode("utf8")
        if read(atomic, rid)["source_bytes"] != raw:
            raise AssertionError("compressed updated source mismatch")
        if full.execute("SELECT title,abstract FROM sources WHERE rowid=?",
                        (rid,)).fetchone() != (title, " ".join(abstract)):
            raise AssertionError("full updated source mismatch")
    return {
        "full_fts5_stat_doc_count_and_column_tokens": stat_full,
        "atomic_fts5_stat_doc_count_and_column_tokens": stat_atomic,
        "actual_live_docs_full": live_full,
        "actual_live_docs_atomic": live_atomic,
        "queries": len(claims),
        "identical_top10_rankings": identical,
        "mean_top10_intersection": round(total_overlap / len(claims), 4),
        "first_three_mismatched_queries": first_differences,
        "sha_verified_top1_source_reads": sha_readbacks,
        "revised_source_bytes_verified": len(expected),
    }


def rebuild_fts_from_structured_truth(atomic, corpus, expected):
    """Recompute contentless postings and BM25 stats from all current sources.

    Controlled oracle uses the original structured corpus plus known revisions.
    This is O(corpus) and NOT yet a production migration/recovery implementation.
    """
    t0 = time.perf_counter()
    atomic.execute("BEGIN IMMEDIATE")
    try:
        atomic.execute("INSERT INTO sources(sources) VALUES('delete-all')")
        for rid, row in enumerate(corpus, 1):
            title, abstract = expected.get(
                rid, (row["title"], list(row["abstract"])))
            raw = (title + "\n" + " ".join(abstract)).encode("utf8")
            if read(atomic, rid)["source_bytes"] != raw:
                raise AssertionError("repair oracle disagrees with stored source")
            atomic.execute(
                "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                (rid, title, " ".join(abstract)))
        atomic.execute("COMMIT")
    except BaseException:
        if atomic.in_transaction:
            atomic.execute("ROLLBACK")
        raise
    return round(time.perf_counter() - t0, 5)


def benchmark(corpus, claims, events, mode, pattern):
    if mode not in ("DELETE", "WAL"):
        raise ValueError(mode)
    with tempfile.TemporaryDirectory() as root:
        dirpath = Path(root)
        fp = dirpath / "full.sqlite"
        ap = dirpath / "atomic.sqlite"
        full, full_meta = make_fts(fp, corpus, False)
        atomic, atom_meta = create_db(ap, corpus)
        try:
            # make_fts uses a default legacy transaction mode. Set known
            # durable settings before the timed section for both DBs.
            full.isolation_level = None
            configure_mode(full, mode)
            configure_mode(atomic, mode)
            initial = {"full": file_bytes(fp), "atomic": file_bytes(ap)}
            expected = {}
            costs = {"full": [], "atomic": []}
            for i, (rid, doc_id, title, abstract) in enumerate(events):
                # Alternate method timing order to reduce simple warm-order bias.
                pair = (("atomic", "full") if i % 2 else ("full", "atomic"))
                for method in pair:
                    t0 = time.perf_counter_ns()
                    if method == "full":
                        do_full_update(full, rid, title, abstract)
                    else:
                        atomic_update(atomic, rid, doc_id, title, abstract)
                    costs[method].append((time.perf_counter_ns() - t0)/1e6)
                expected[rid] = (title, abstract)
            active = {"full": file_bytes(fp), "atomic": file_bytes(ap)}
            before_repair = verify_pair(full, atomic, corpus, claims, expected)
            rebuild_seconds = rebuild_fts_from_structured_truth(atomic, corpus, expected)
            after_repair = verify_pair(full, atomic, corpus, claims, expected)
            if (after_repair["identical_top10_rankings"] != len(claims)
                    or after_repair["full_fts5_stat_doc_count_and_column_tokens"]
                       != after_repair["atomic_fts5_stat_doc_count_and_column_tokens"]):
                raise AssertionError("controlled FTS5 delete-all/reindex failed "
                                     "to restore exact BM25 parity")
            # Measure all checkpointed bytes and once-compacted bytes, not
            # merely SQLite main DB pages while a large WAL remains pending.
            if mode == "WAL":
                for conn in (full, atomic):
                    result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if result[0] != 0:
                        raise AssertionError("checkpoint blocked; uncontrolled reader?")
            checkpointed = {"full": file_bytes(fp), "atomic": file_bytes(ap)}
            for conn in (full, atomic):
                conn.execute("VACUUM")
            if mode == "WAL":
                for conn in (full, atomic):
                    result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if result[0] != 0:
                        raise AssertionError("VACUUM checkpoint blocked")
            vacuumed = {"full": file_bytes(fp), "atomic": file_bytes(ap)}
            pages = {
                "full": {"page_count": full.execute("PRAGMA page_count").fetchone()[0],
                         "freelist": full.execute("PRAGMA freelist_count").fetchone()[0]},
                "atomic": {"page_count": atomic.execute("PRAGMA page_count").fetchone()[0],
                           "freelist": atomic.execute("PRAGMA freelist_count").fetchone()[0]},
            }
            return {
                "journal_mode": mode, "revision_pattern": pattern,
                "revisions": len(events), "distinct_documents_revised": len(expected),
                "source_documents": len(corpus), "claim_queries": len(claims),
                "latency": {name: summarize_latency(ms) for name, ms in costs.items()},
                "storage_bytes": {"initial": initial, "active_after_updates": active,
                                  "after_checkpoint": checkpointed,
                                  "after_vacuum_and_checkpoint": vacuumed},
                "page_statistics_after_vacuum": pages,
                "verification_before_rebuild": before_repair,
                "verification": after_repair,
                "rebuild_all_docs_seconds": rebuild_seconds,
                "after_vacuum_savings_vs_full_pct": round(
                    100*(vacuumed["full"]-vacuumed["atomic"])/vacuumed["full"], 4),
                "metadata": {"full_initial_main_bytes": full_meta["database_bytes"],
                             "atomic_initial_main_bytes": atom_meta["persistent_index_and_source_bytes"]},
            }
        finally:
            full.close()
            atomic.close()


def run(full_data=False):
    if full_data:
        tar, raw = fetch()
        release_sha = digests(tar)["sha256"]
        if release_sha != EXPECTED_RELEASE_SHA:
            raise AssertionError("original SciFact source changed")
        corpus, claims, _ = parse(raw)
        n, hotset = 500, 50
        source = {"dataset": "official original SciFact",
                  "original_tar_sha256": release_sha}
    else:
        corpus = [
            {"doc_id": x+1, "title": "sampleterm"+str(x),
             "abstract": ["This is document sample "+str(x)+"."]}
            for x in range(30)
        ]
        claims = [{"id":x, "claim":"sampleterm"+str(x)} for x in range(10)]
        n, hotset = 20, 4
        source = {"dataset": "synthetic micro corpus"}
    results = []
    for mode in ("DELETE", "WAL"):
        for pattern in ("diffuse", "hot"):
            events = revision_events(corpus, pattern, n, hotset)
            results.append(benchmark(corpus, claims, events, mode, pattern))
    return {
        "round": 89, "source": source, "comparison": "contentful FTS5 vs same-posting contentless-delete FTS5 and compressed SHA-verified source",
        "experiments": results,
        "limitations": [
            "Synthetic title+abstract version-marker updates, not natural document revisions",
            "Only one writer and no overlapping readers during timed updates",
            "All timed writes include SQLite commit but OS caching is uncontrolled",
            "WAL size includes current -wal/-shm and is not a cold SSD measurement",
            "Changes are meaningful only for this workload and SQLite version",
            "No generation model, human truth labels or hallucination results",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true")
    p.add_argument("--out", default=str(HERE/"ci-results.json"))
    args = p.parse_args()
    result = run(full_data=args.full)
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("ROUND89", json.dumps(result, sort_keys=True), flush=True)
