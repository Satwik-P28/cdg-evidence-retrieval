#!/usr/bin/env python3
"""R103: source-exact QASPER block × independent-trained dictionary frontier.

Same original QASPER DEV paragraphs, source IDs, SHA receipts and FTS5
postings. Compare existing Brotli5 blocks vs Zstd3/9 with an ORIGINAL
TRAIN-papers-only 64 KiB shared dictionary. Include independent-per-source
Zstd dictionary and Brotli reference archives under fully charged schemas.
All paragraph text retrieved exactly; report physical SQLite bytes,
top1/top10 decompressed-byte amplification and warm read costs.
"""
from __future__ import annotations
import argparse
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
for r in ("round-86","round-90","round-96","round-97","round-99",
          "round-101","round-102"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,gold_recall
from contentless_cas import document_bytes
from paper_block_brotli import (
    GROUPS,base_fts_db,make_grouped_brotli,queries_for_original,
    paper_id,MAX_BLOCK_BYTES
)
from codec_frontier import measured_percentiles
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries,
    evaluate as individual_dictionary_baselines,TRAIN_SHA,DEV_SHA
)

VARIANTS=("brotli5","zstd3-dictionary","zstd9-dictionary")
TRAINED_SIZE=65536
WARM_SOURCE_K=(1,10)


def group_variant(path,grouped_brotli_path,variant,dictionary):
    """All group variants have same block+receipt+dictionary metadata columns."""
    if variant not in VARIANTS:
        raise ValueError("unknown source group codec")
    shutil.copyfile(grouped_brotli_path,path)
    db=sqlite3.connect(str(path),isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute(
            "ALTER TABLE source_blocks ADD COLUMN dict_id INTEGER NOT NULL DEFAULT 0")
        db.execute("""
          CREATE TABLE source_dictionaries (
            dict_id INTEGER PRIMARY KEY,
            payload BLOB NOT NULL,
            sha256 BLOB NOT NULL CHECK(length(sha256)=32),
            zstd_dict_id INTEGER NOT NULL
          )""")
        db.execute("BEGIN IMMEDIATE")
        if variant!="brotli5":
            import zstandard as zstd
            payload=dictionary["raw"]
            dict_data=zstd.ZstdCompressionDict(payload)
            if dict_data.dict_id()!=dictionary["zstd_dict_id"]:
                raise AssertionError("trained dictionary identity changed")
            db.execute(
                "INSERT INTO source_dictionaries VALUES(1,?,?,?)",
                (payload,dictionary["sha256"],dictionary["zstd_dict_id"]))
            level=3 if variant=="zstd3-dictionary" else 9
            compressor=zstd.ZstdCompressor(level=level,dict_data=dict_data)
        else:
            compressor=None
        t0=time.perf_counter()
        if compressor is not None:
            import brotli
            rows=db.execute(
                "SELECT block_id,compressed,sha256,utf8_len "
                "FROM source_blocks ORDER BY block_id").fetchall()
            for bid,blob,sha,n in rows:
                raw=brotli.decompress(blob)
                if len(raw)!=n or hashlib.sha256(raw).digest()!=sha:
                    raise AssertionError("original block corrupted before recode")
                db.execute(
                    "UPDATE source_blocks SET compressed=?,codec=?,dict_id=1 "
                    "WHERE block_id=?",
                    (compressor.compress(raw),variant,bid))
        encode_seconds=time.perf_counter()-t0
        db.execute("COMMIT")
        db.execute("VACUUM")
        return db,{
            "block_reencoding_seconds_from_existing_brotli":round(
                encode_seconds,6),
            "dictionary_charged_bytes":len(dictionary["raw"])
                if variant!="brotli5" else 0,
            "dictionary_train_seconds":round(
                dictionary["training_seconds"],6)
                if variant!="brotli5" else 0,
        }
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
        raise


class GroupSourceReader:
    """Single opened archive; one shared dictionary prepared once if required."""
    def __init__(self,db):
        self.db=db
        rows=db.execute(
            "SELECT dict_id,payload,sha256,zstd_dict_id "
            "FROM source_dictionaries").fetchall()
        if len(rows)>1:
            raise AssertionError("R103 only one dictionary per archive")
        self.dict_decoder=None
        if rows:
            import zstandard as zstd
            dict_id,payload,digest,expected_zstd_id=rows[0]
            if dict_id!=1 or hashlib.sha256(payload).digest()!=digest:
                raise ValueError("source dictionary hash or identity mismatch")
            d=zstd.ZstdCompressionDict(payload)
            if d.dict_id()!=expected_zstd_id:
                raise ValueError("source dictionary zstd ID mismatch")
            self.dict_decoder=zstd.ZstdDecompressor(dict_data=d)

    def block(self,bid):
        row=self.db.execute(
            "SELECT paper_id,compressed,codec,sha256,utf8_len,dict_id "
            "FROM source_blocks WHERE block_id=?",(bid,)).fetchone()
        if row is None:
            raise KeyError("missing source block")
        pid,blob,codec,expected_sha,length,dict_id=row
        if not 0<=length<=MAX_BLOCK_BYTES:
            raise ValueError("untrusted source block decoded length")
        if codec=="brotli5":
            if dict_id!=0:raise ValueError("Brotli cannot refer to zstd dictionary")
            import brotli
            raw=brotli.decompress(blob)
        elif codec in ("zstd3-dictionary","zstd9-dictionary"):
            if dict_id!=1 or self.dict_decoder is None:
                raise ValueError("missing original trained dictionary")
            raw=self.dict_decoder.decompress(
                blob,max_output_size=length+1)
        else:
            raise ValueError("unknown group codec")
        if len(raw)!=length or hashlib.sha256(raw).digest()!=expected_sha:
            raise ValueError("original source block length/hash mismatch")
        return raw,pid

    def read(self,rid,cache=None):
        meta=self.db.execute(
            "SELECT doc_id,block_id,byte_offset,utf8_len,sha256 "
            "FROM source_receipts WHERE rowid=?",(rid,)).fetchone()
        if meta is None:
            raise KeyError("original paragraph receipt absent")
        doc_id,bid,offset,n,expected_sha=meta
        if cache is not None and bid in cache:
            raw,pid=cache[bid]
            inflated=0
        else:
            raw,pid=self.block(bid)
            inflated=len(raw)
            if cache is not None:cache[bid]=(raw,pid)
        if not str(doc_id).startswith(str(pid)+"|"):
            raise ValueError("block crossed original article ID")
        if not 0<=offset<=len(raw) or not 0<=n<=len(raw)-offset:
            raise ValueError("source receipt offset escapes block")
        source=raw[offset:offset+n]
        if hashlib.sha256(source).digest()!=expected_sha:
            raise ValueError("source paragraph digest mismatch")
        return {"doc_id":doc_id,"source_bytes":source,
                "decoded_block_bytes":inflated,"block_id":bid}


def verify_all_originals(reader,docs):
    cache={}
    for rid,doc in enumerate(docs,1):
        found=reader.read(rid,cache)
        if found["doc_id"]!=str(doc["doc_id"]) or (
                found["source_bytes"]!=document_bytes(doc)):
            raise AssertionError("block source original SHA receipt mismatch")
    return len(docs)


def probe(reader,docs,ranked,k):
    timings=[]
    decoded=0
    requested=0
    decompressions=0
    count=0
    t0=time.perf_counter()
    for rowids in ranked.values():
        cache={}
        for rid in rowids[:k]:
            t=time.perf_counter_ns()
            receipt=reader.read(rid,cache)
            timings.append((time.perf_counter_ns()-t)/1e6)
            expected=document_bytes(docs[rid-1])
            if (receipt["source_bytes"]!=expected or
                    receipt["doc_id"]!=str(docs[rid-1]["doc_id"])):
                raise AssertionError("ranked paragraph source not original")
            inflated=receipt["decoded_block_bytes"]
            decoded+=inflated
            decompressions+=int(inflated>0)
            requested+=len(expected)
            count+=1
    return {
        "k":k,
        "source_receipts_verified":count,
        "requested_original_source_bytes":requested,
        "decompressed_original_block_bytes":decoded,
        "decode_byte_amplification":round(decoded/requested,5) if requested else None,
        "distinct_block_inflations":decompressions,
        "no_cache_between_questions":True,
        "source_cache":"One block inflated once per question",
        "full_probe_wall_seconds":round(time.perf_counter()-t0,6),
        "warm_source_read_ms":measured_percentiles(timings),
    }


def pareto_frontier(candidates):
    """Exact deterministic non-dominance on physical bytes and top1 byte inflation."""
    good=[]
    for a in candidates:
        if any(
            b["source_plus_fts_sqlite_bytes"]<=a["source_plus_fts_sqlite_bytes"]
            and b["top1"]["decode_byte_amplification"]<=a["top1"]["decode_byte_amplification"]
            and (
                b["source_plus_fts_sqlite_bytes"]<a["source_plus_fts_sqlite_bytes"]
                or b["top1"]["decode_byte_amplification"]<a["top1"]["decode_byte_amplification"]
            )
            for b in candidates
        ):continue
        good.append({"group":a["group"],"codec":a["variant"],
                     "sqlite_bytes":a["source_plus_fts_sqlite_bytes"],
                     "top1_decode_amp":a["top1"]["decode_byte_amplification"],
                     "top10_decode_amp":a["top10"]["decode_byte_amplification"]})
    return sorted(good,key=lambda x:(x["sqlite_bytes"],x["top1_decode_amp"]))


def evaluate(train_papers,dev_papers,groups=GROUPS,variants=VARIANTS):
    if set(train_papers)&set(dev_papers):
        raise AssertionError("article-identity overlap across dictionary fit and source dev")
    docs,cases,_=load_dev(dev_papers)
    samples,training=independently_trained_samples(train_papers)
    d=train_dictionaries(samples,(TRAINED_SIZE,))[TRAINED_SIZE]
    if len(d["raw"])>TRAINED_SIZE:
        raise AssertionError("unexpected dictionary training limit")
    # Build same benchmark's strong independently decoded source controls.
    individual=individual_dictionary_baselines(
        train_papers,dev_papers,
        variants=("brotli5","zstd3_dict65536","zstd9_dict65536"),
        dictionary_sizes=(TRAINED_SIZE,))
    controls=[{
        "variant":a["variant"],
        "source_plus_fts_sqlite_bytes":a["whole_sqlite_source_and_index_bytes"],
        "top1":{"decode_byte_amplification":1.0},
        "top10":{"decode_byte_amplification":1.0},
        "group":"individual",
        "source_sha_original_verified":a["original_source_docs_sha_verified"],
    } for a in individual["archives"]]
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        fts_path=root/"fts.sqlite"
        db=base_fts_db(fts_path,docs)
        try:
            stats=db.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            ranked=queries_for_original(docs,cases,db)
            original_gold=gold_recall(cases,ranked)
        finally:db.close()
        rows=[]
        for group in groups:
            grouped_path=root/("group_"+str(group)+".sqlite")
            source=make_grouped_brotli(grouped_path,fts_path,docs,group)
            source.close()
            for variant in variants:
                archive_path=root/("group_"+str(group)+"_"+variant+".sqlite")
                c,cost=group_variant(archive_path,grouped_path,variant,d)
                try:
                    if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                        raise AssertionError("SQLite source+FTS integrity failed")
                    c.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
                    if c.execute(
                        "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]!=stats:
                        raise AssertionError("source recode changed FTS5 postings")
                    if queries_for_original(docs,cases,c)!=ranked:
                        raise AssertionError("source block codec changed BM25 top-10 rankings")
                    reader=GroupSourceReader(c)
                    n_verified=verify_all_originals(reader,docs)
                    block_count=c.execute(
                        "SELECT COUNT(*) FROM source_blocks").fetchone()[0]
                    row={
                        "group":group,
                        "variant":variant,
                        "source_blocks":block_count,
                        "source_sha_original_verified":n_verified,
                        "question_rankings_exact":len(cases),
                        "source_plus_fts_sqlite_bytes":archive_path.stat().st_size,
                        "codec_dictionary_and_receipts_charged":True,
                        "block_source_codec_bytes":c.execute(
                            "SELECT SUM(length(compressed)) FROM source_blocks"
                            ).fetchone()[0],
                        "max_uncompressed_block_bytes":c.execute(
                            "SELECT MAX(utf8_len) FROM source_blocks").fetchone()[0],
                        "top1":probe(reader,docs,ranked,1),
                        "top10":probe(reader,docs,ranked,10),
                        **cost,
                    }
                    rows.append(row)
                finally:c.close()
            grouped_path.unlink(missing_ok=True)
        frontier=pareto_frontier(rows+controls)
        return {
            "round":103,
            "source_dataset":"Original QASPER v0.3 DEV articles",
            "independent_train_sha256":TRAIN_SHA,
            "dev_sha256":DEV_SHA,
            "source_docs":len(docs),
            "questions":len(cases),
            "training":training,
            "trained_dictionary_bytes":len(d["raw"]),
            "trained_dictionary_sha256":d["sha256"].hex(),
            "trained_dictionary_seconds":round(d["training_seconds"],6),
            "same_original_gold_paragraph_recall":original_gold,
            "individual_reference":controls,
            "grouped_variants":rows,
            "non_dominated_storage_vs_top1_decode_amp":frontier,
            "limitations":[
                "Published Zstd dictionary training and Brotli group compression, not original codec mathematics",
                "QASPER article is provided, so not an open-domain paper search result",
                "All original text and FTS5 postings unchanged; human retrieval cannot improve by codec alone",
                "Decoder amplification measures uncompressed bytes, not compressed SSD pages, GPU memory or token use",
                "Group size can change update/write amplification; untested revisions, power loss and concurrent consistency",
                "Single warm GitHub CI runner, non-randomized sequential variants; timing not independent latency evidence",
                "Individual source reference database schema differs from grouped receipt schema, both metadata sizes fully charged",
                "Dictionary comes exclusively from distinct QASPER train articles; training CPU not added to stored bytes",
                "No generated QA, fact-checker, or measured response hallucination suppression",
            ],
        }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=p.parse_args()
    source=fetch_qasper()
    if source["train"]["sha256"]!=TRAIN_SHA or source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("original QASPER full text source changed")
    result=evaluate(source["train"]["data"],source["dev"]["data"])
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND103",json.dumps({
        "docs":result["source_docs"],"queries":result["questions"],
        "dict_bytes":result["trained_dictionary_bytes"],
        "dictionary_sha256":result["trained_dictionary_sha256"],
        "individual":result["individual_reference"],
        "frontier":result["non_dominated_storage_vs_top1_decode_amp"],
        "grouped_variants":[{
            "group":x["group"],"variant":x["variant"],
            "bytes":x["source_plus_fts_sqlite_bytes"],
            "blocks":x["source_blocks"],
            "top1_amp":x["top1"]["decode_byte_amplification"],
            "top10_amp":x["top10"]["decode_byte_amplification"],
            "top1_wall":x["top1"]["full_probe_wall_seconds"],
            "top10_wall":x["top10"]["full_probe_wall_seconds"],
        } for x in result["grouped_variants"]],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
