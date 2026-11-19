#!/usr/bin/env python3
"""R99: lossless source codec ablation at constant original FTS5 postings.

Compared codecs: zlib6, zstd3, zstd9, Brotli5, Brotli9, lzma6.
Source bytes and index postings identical across experiments; only
lossless compressed docs BLOB values and explicit codec IDs change.
Measure total static persisted SQLite bytes, cold-uncontrolled encode
and warm SHA-verified decode costs on original SciFact & QASPER.
No learned compression or semantic accuracy claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import lzma
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-83","round-86","round-90","round-96","round-97"):
    sys.path.insert(0,str(HERE.parent/r))
from scifact_data_probe import fetch as scifact_fetch,parse as scifact_parse,digests
from contentless_cas import document_bytes,EXPECTED_RELEASE_SHA,query_fts
from old_source_incremental import create_legacy_contentless
from qasper_source_probe import fetch as qasper_fetch
from qasper_paragraph_retrieval import load_dev,paper_rank

CODECS=("zlib6","zstd3","zstd9","brotli5","brotli9","lzma6")
WARM_REPEATS=3
MAX_OUTPUT=2_000_000


def encode(name,data):
    if not isinstance(data,bytes):
        raise ValueError("source payload must be bytes")
    if name=="zlib6":
        return zlib.compress(data,6)
    if name in ("zstd3","zstd9"):
        import zstandard as zstd
        return zstd.ZstdCompressor(level=int(name[-1])).compress(data)
    if name in ("brotli5","brotli9"):
        import brotli
        return brotli.compress(data,quality=int(name[-1]))
    if name=="lzma6":
        return lzma.compress(data,preset=6)
    raise ValueError("unknown codec")


def decode(name,data,expected_len):
    if not 0<=expected_len<=MAX_OUTPUT:
        raise ValueError("invalid decoded length bound")
    if name=="zlib6":
        decoder=zlib.decompressobj()
        result=decoder.decompress(data,expected_len+1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("non-exact zlib stream")
    elif name in ("zstd3","zstd9"):
        import zstandard as zstd
        # max_output_size protects against false huge original length.
        result=zstd.ZstdDecompressor().decompress(data,max_output_size=expected_len+1)
    elif name in ("brotli5","brotli9"):
        import brotli
        result=brotli.decompress(data)
    elif name=="lzma6":
        decoder=lzma.LZMADecompressor()
        result=decoder.decompress(data,max_length=expected_len+1)
        if not decoder.eof or decoder.unused_data:
            raise ValueError("non-exact lzma stream")
    else:
        raise ValueError("unknown codec")
    if len(result)!=expected_len:
        raise ValueError("unexpected source decoded length")
    return result


def read_codec(db,rid,expected_identity=None):
    row=db.execute(
        "SELECT doc_id,compressed,sha256,utf8_len,codec "
        "FROM docs WHERE rowid=?",(rid,)
    ).fetchone()
    if row is None:
        raise KeyError("source missing")
    doc_id,blob,expected_sha,n,codec=row
    if expected_identity is not None and doc_id!=expected_identity:
        raise AssertionError("source identity mismatch")
    raw=decode(codec,blob,n)
    if hashlib.sha256(raw).digest()!=expected_sha:
        raise ValueError("decoded source SHA-256 mismatch")
    return raw


def input_datasets():
    tar,raw=scifact_fetch()
    digest=digests(tar)["sha256"]
    if digest!=EXPECTED_RELEASE_SHA:
        raise AssertionError("SciFact original data changed")
    corpus,claims,_=scifact_parse(raw)
    sci_docs=corpus
    sci_probe=[]
    # This uses an independent one-off full index only to pick a *fixed*
    # original scientific top1 read distribution; codecs do not change it.
    with tempfile.TemporaryDirectory() as scratch:
        db=create_legacy_contentless(Path(scratch)/"sci.sqlite",sci_docs)
        try:
            for claim in claims:
                ranks=query_fts(db,claim["claim"],1)
                if ranks:sci_probe.extend(ranks)
        finally:db.close()
    qmembers=qasper_fetch()
    if qmembers["dev"]["sha256"]!=(
        "2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93"
    ):
        raise AssertionError("QASPER v0.3 original dev member SHA changed")
    q_docs,q_cases,_=load_dev(qmembers["dev"]["data"])
    q_probe=[]
    with tempfile.TemporaryDirectory() as scratch:
        db=create_legacy_contentless(Path(scratch)/"q.sqlite",q_docs)
        try:
            for case in q_cases:
                ranks=paper_rank(db,case["claim"],case["row_start"],
                                 case["row_end"],1)
                if ranks:q_probe.extend(ranks)
        finally:db.close()
    return [
        ("SciFact",sci_docs,sci_probe,digest),
        ("QASPER-dev",q_docs,q_probe,qmembers["dev"]["sha256"]),
    ]


def measured_percentiles(data):
    if not data:raise ValueError("no timing observations")
    order=sorted(data)
    return {
        "count":len(order),
        "median_ms":round(statistics.median(order),6),
        "p95_ms":round(order[int(.95*(len(order)-1))],6),
        "sum_ms":round(sum(order),4),
    }


def check_uniform_original_bytes(corpus):
    original=[document_bytes(x) for x in corpus]
    if len({str(x["doc_id"]) for x in corpus})!=len(corpus):
        raise AssertionError("repeated original document id")
    if any(len(x)>MAX_OUTPUT for x in original):
        raise ValueError("source exceeds R99 bounded decoder size")
    return original


def benchmark_corpus(name,corpus,probe,source_sha,codecs=CODECS):
    if not probe:raise ValueError("no evidence source read probes")
    originals=check_uniform_original_bytes(corpus)
    total_raw_bytes=sum(map(len,originals))
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        base=root/"base.sqlite"
        db=create_legacy_contentless(base,corpus)
        try:
            db.execute("ALTER TABLE docs ADD COLUMN codec TEXT NOT NULL DEFAULT 'zlib6'")
            db.execute("VACUUM")
            n_docs=db.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            fts_stats_before=db.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            if n_docs!=len(corpus):
                raise AssertionError("database doc count mismatch")
        finally:db.close()
        rows=[]
        for codec in codecs:
            path=root/(codec+".sqlite")
            shutil.copyfile(base,path)
            archive=sqlite3.connect(str(path),isolation_level=None)
            try:
                compressed_blobs=[]
                encode_start=time.perf_counter()
                for raw in originals:
                    compressed_blobs.append(encode(codec,raw))
                encode_seconds=time.perf_counter()-encode_start
                archive.execute("BEGIN IMMEDIATE")
                try:
                    for rid,blob in enumerate(compressed_blobs,1):
                        archive.execute(
                            "UPDATE docs SET compressed=?,codec=? WHERE rowid=?",
                            (blob,codec,rid))
                    archive.execute("COMMIT")
                except BaseException:
                    if archive.in_transaction:
                        archive.execute("ROLLBACK")
                    raise
                archive.execute("VACUUM")
                persisted=path.stat().st_size
                if archive.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise AssertionError("SQLite core integrity failed")
                archive.execute(
                    "INSERT INTO sources(sources) VALUES('integrity-check')")
                if archive.execute(
                    "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]!=fts_stats_before:
                    raise AssertionError("FTS global index statistics changed with source codec")
                verified=0
                for rid,expected in enumerate(originals,1):
                    actual=read_codec(archive,rid,str(corpus[rid-1]["doc_id"]))
                    if actual!=expected:
                        raise AssertionError("decoded source differs from upstream original")
                    verified+=1
                latency=[]
                for _ in range(WARM_REPEATS):
                    for rid in probe:
                        start=time.perf_counter_ns()
                        got=read_codec(archive,rid,str(corpus[rid-1]["doc_id"]))
                        latency.append((time.perf_counter_ns()-start)/1e6)
                        if got!=originals[rid-1]:
                            raise AssertionError("sampled source byte drift")
                rows.append({
                    "codec":codec,
                    "docs":len(corpus),
                    "static_source_and_fts_bytes":persisted,
                    "source_compressed_blob_bytes":sum(map(len,compressed_blobs)),
                    "source_raw_utf8_bytes":total_raw_bytes,
                    "source_blob_ratio":round(sum(map(len,compressed_blobs))/total_raw_bytes,6),
                    "source_blob_encode_seconds":round(encode_seconds,5),
                    "sha_verified_original_source_docs":verified,
                    "retained_fts_global_stats_unchanged":True,
                    "warm_decode_and_SHA_source_reads":measured_percentiles(latency),
                    "fixed_source_probe_count":len(probe),
                    "source_sha256":source_sha,
                })
            finally:
                archive.close()
        reference=next(x for x in rows if x["codec"]=="zlib6")
        for x in rows:
            x["db_bytes_delta_vs_zlib6"]=(
                x["static_source_and_fts_bytes"]
                -reference["static_source_and_fts_bytes"])
        return {
            "dataset":name,
            "source_provenance_sha256":source_sha,
            "docs":len(corpus),
            "source_bytes_original":total_raw_bytes,
            "probe_source_reads":len(probe),
            "codecs":rows,
            "fastest_warm_median":min(
                rows,key=lambda x:x["warm_decode_and_SHA_source_reads"]["median_ms"]
            )["codec"],
            "smallest_persisted_db":min(
                rows,key=lambda x:x["static_source_and_fts_bytes"]
            )["codec"],
            "notes":[
                "FTS postings, query policy, source IDs and original source bytes held constant",
                "Codec field stored in every schema, so all database sizes include explicit decoder identity",
                "No separate dictionary training, cross-document dedup, cold SSD, memory peak or power-loss tests",
                "Wall times are one CI runner with warm cache and serial method execution; differences descriptive",
                "Brotli source decoder does not enforce an output cap prior to decoding",
            ],
        }


def run():
    results=[]
    for name,corpus,probes,sha in input_datasets():
        results.append(benchmark_corpus(name,corpus,probes,sha))
    return {
        "round":99,
        "codecs":list(CODECS),
        "datasets":results,
        "method":"constant-source and constant-contentless FTS5, six lossless encoded BLOB methods",
        "scientific_limits":[
            "Standard public compressors only, not a novel lossless compression method",
            "No answer generation or retrieval ranking changes and no semantic factuality improvement",
            "Independent QASPER vs SciFact show corpus effects, but corpus units differ (paragraph vs abstract)",
            "One runner, warm source reads and no probabilistic independent timing replication",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=p.parse_args()
    result=run()
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND99",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
