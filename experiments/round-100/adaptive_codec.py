#!/usr/bin/env python3
"""R100: per-document lossless codec admission versus strong all-Brotli5 control.

Original SciFact and QASPER sources, fixed R90 contentless FTS5 index.
Static codec policies use only original source bytes, no human claim labels.
Compute all source SHA-verified receipts; compare stored SQLite source+index
bytes and warm decode costs, charging candidate encoding effort separately.
This is conventional codec scheduling, not a new compression algorithm.
"""
from __future__ import annotations
import argparse
from collections import Counter
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
for r in ("round-86","round-90","round-99"):
    sys.path.insert(0,str(HERE.parent/r))
from old_source_incremental import create_legacy_contentless
from codec_frontier import (
    encode,read_codec,input_datasets,check_uniform_original_bytes,
    measured_percentiles,WARM_REPEATS
)

CANDIDATES=("zlib6","zstd3","brotli5")
POLICIES=(
    "all_zlib6",
    "all_zstd3",
    "all_brotli5",
    "per_source_smallest_of_three",
    "zstd3_unless_brotli_saves_64",
    "zstd3_unless_brotli_saves_128",
    "zlib6_unless_brotli_saves_64",
)
BENEFIT_THRESHOLD_BYTES=(64,128)


def policy_candidates(policy):
    if policy not in POLICIES:
        raise ValueError("unknown predeclared codec policy")
    if policy=="all_zlib6":return ("zlib6",)
    if policy=="all_zstd3":return ("zstd3",)
    if policy=="all_brotli5":return ("brotli5",)
    if policy=="per_source_smallest_of_three":return CANDIDATES
    if policy.startswith("zstd3_unless"):return ("zstd3","brotli5")
    if policy.startswith("zlib6_unless"):return ("zlib6","brotli5")
    raise AssertionError("unhandled codec policy")


def choose_codec(policy,encoded):
    """Choice consults only the unlabelled original source's encoded lengths."""
    if policy not in POLICIES:
        raise ValueError("unrecognized choice")
    if policy=="all_zlib6":return "zlib6"
    if policy=="all_zstd3":return "zstd3"
    if policy=="all_brotli5":return "brotli5"
    if policy=="per_source_smallest_of_three":
        # Tie break toward fast small-source decoder, not a learned model.
        tie_order={"zstd3":0,"brotli5":1,"zlib6":2}
        return min(CANDIDATES,key=lambda code:(
            len(encoded[code]),tie_order[code]))
    if policy.startswith("zstd3_unless_brotli"):
        old="zstd3"
    elif policy.startswith("zlib6_unless_brotli"):
        old="zlib6"
    else:
        raise ValueError("invalid source admission method")
    threshold=int(policy.rsplit("_",1)[-1])
    if threshold not in BENEFIT_THRESHOLD_BYTES:
        raise ValueError("threshold not predeclared")
    if len(encoded[old])-len(encoded["brotli5"])>=threshold:
        return "brotli5"
    return old


def build_candidate_pool(originals):
    """Compress once per codec to isolate and count candidate encoding cost."""
    outputs={code:[] for code in CANDIDATES}
    times={}
    for code in CANDIDATES:
        t0=time.perf_counter()
        outputs[code]=[encode(code,raw) for raw in originals]
        times[code]=time.perf_counter()-t0
    return outputs,times


def benchmark_corpus(name,corpus,source_probes,source_sha,policies=POLICIES):
    originals=check_uniform_original_bytes(corpus)
    if not source_probes:
        raise ValueError("empty original source retrieval probes")
    pool,encode_times=build_candidate_pool(originals)
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        base=root/"standard.sqlite"
        db=create_legacy_contentless(base,corpus)
        try:
            db.execute(
                "ALTER TABLE docs ADD COLUMN codec TEXT NOT NULL DEFAULT 'zlib6'")
            db.execute("VACUUM")
            base_stats=db.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
        finally:
            db.close()
        results=[]
        for policy in policies:
            path=root/(policy+".sqlite")
            shutil.copyfile(base,path)
            c=sqlite3.connect(str(path),isolation_level=None)
            chosen=[]
            try:
                c.execute("BEGIN IMMEDIATE")
                try:
                    for rid,raw in enumerate(originals,1):
                        codes={name:pool[name][rid-1]
                               for name in policy_candidates(policy)}
                        codec=choose_codec(policy,codes)
                        chosen.append(codec)
                        c.execute(
                            "UPDATE docs SET compressed=?,codec=? WHERE rowid=?",
                            (pool[codec][rid-1],codec,rid))
                    c.execute("COMMIT")
                except BaseException:
                    if c.in_transaction:
                        c.execute("ROLLBACK")
                    raise
                c.execute("VACUUM")
                bytes_on_disk=path.stat().st_size
                if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise AssertionError("database integrity check failed")
                c.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
                if c.execute(
                    "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]!=base_stats:
                    raise AssertionError("FTS indexing changed")
                verified=0
                for rid,raw in enumerate(originals,1):
                    if read_codec(c,rid,str(corpus[rid-1]["doc_id"]))!=raw:
                        raise AssertionError("original source failed SHA check")
                    verified+=1
                latency=[]
                for _ in range(WARM_REPEATS):
                    for rid in source_probes:
                        start=time.perf_counter_ns()
                        data=read_codec(c,rid,str(corpus[rid-1]["doc_id"]))
                        latency.append((time.perf_counter_ns()-start)/1e6)
                        if data!=originals[rid-1]:
                            raise AssertionError("original source changed")
                requested=policy_candidates(policy)
                sum_encoded=sum(
                    len(pool[code][i]) for i,code in enumerate(chosen))
                result={
                    "policy":policy,
                    "documents":len(corpus),
                    "source_original_bytes":sum(map(len,originals)),
                    "persisted_index_and_source_bytes":bytes_on_disk,
                    "source_blob_bytes":sum_encoded,
                    "source_codec_histogram":dict(Counter(chosen)),
                    "candidate_codecs_to_encode":list(requested),
                    "candidate_encoding_seconds_sum":round(
                        sum(encode_times[k] for k in requested),6),
                    "candidate_encoding_calls":len(originals)*len(requested),
                    "original_sources_sha_verified":verified,
                    "warm_reads_with_sha":measured_percentiles(latency),
                    "index_stats_unchanged":True,
                    "source_provenance_sha256":source_sha,
                }
                results.append(result)
            finally:
                c.close()
        baseline=next(x for x in results if x["policy"]=="all_brotli5")
        for row in results:
            row["saved_persistent_bytes_vs_all_brotli5"]=(
                baseline["persisted_index_and_source_bytes"]
                -row["persisted_index_and_source_bytes"])
        return {
            "dataset":name,"docs":len(corpus),
            "source_provenance_sha256":source_sha,
            "source_probes":len(source_probes),
            "codecs":list(CANDIDATES),
            "policies":results,
            "smallest_policy":min(results,key=lambda x:
                x["persisted_index_and_source_bytes"])["policy"],
            "warnings":[
                "All candidate source compressions built once for controlled comparisons; per-policy candidate encoding cost is sum of measured codec pass costs, not a separately timed deployment ingest pipeline",
                "Per-source optimal of three may be an overfit byte oracle for three tested prior-art compressors, not a learned novel model",
                "Warm single-run serial read timings are descriptive only; no cold SSD, concurrency or power-loss inference",
                "Source compressor selection checks original text only, not QASPER or SciFact human labels",
                "Semantic retrieval and generated answers unchanged; FTS postings original",
            ],
        }


def run():
    cases=[]
    for dataset,corpus,source_probes,sha in input_datasets():
        cases.append(benchmark_corpus(dataset,corpus,source_probes,sha))
    return {
        "round":100,
        "datasets":cases,
        "candidate_codecs":list(CANDIDATES),
        "candidate_policies":list(POLICIES),
        "scientific_conclusion_scope":"Only source-encoding codec scheduling and total SQLite persisted bytes at unchanged retrieval index",
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=ap.parse_args()
    data=run()
    Path(args.out).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("ROUND100",json.dumps(data,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
