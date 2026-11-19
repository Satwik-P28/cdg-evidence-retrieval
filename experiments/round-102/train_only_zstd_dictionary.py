#!/usr/bin/env python3
"""R102: QASPER source-only train-split Zstandard dictionaries vs Brotli5.

Train one shared Zstd dictionary on text from ORIGINAL QASPER TRAIN papers.
Apply to the ORIGINAL ARTICLE-DISJOINT QASPER DEV source paragraphs.
Store and SHA-verify the dictionary in the SAME SQLite archive that
contains unchanged original contentless FTS5 postings. Charge the
dictionary's actual database pages, and report dictionary-training time.

No human QA answers/labels are seen in dictionary training. No new
compressor algorithm or generated answer factuality is claimed.
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
for r in ("round-86","round-90","round-96","round-97","round-99","round-101"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper,article_paragraphs
from qasper_paragraph_retrieval import load_dev
from contentless_cas import document_bytes
from old_source_incremental import create_legacy_contentless
from paper_block_brotli import queries_for_original
from codec_frontier import encode,measured_percentiles

TRAIN_SHA="9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4"
DEV_SHA="2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93"
SAMPLE_LIMIT=4096
DICT_SIZES=(8192,16384,32768,65536)
ZSTD_LEVELS=(3,9)
VARIANTS=("brotli5","zstd3","zstd9") + tuple(
    f"zstd{level}_dict{size}" for size in DICT_SIZES for level in ZSTD_LEVELS)
SAMPLE_SALT="CDG-R102-original-train-paper-sources-v1"


def independently_trained_samples(train_papers,limit=SAMPLE_LIMIT):
    """Only original TRAIN full-text paragraphs; no annotations or dev docs."""
    candidates=[]
    for pid in sorted(train_papers):
        for row in article_paragraphs(train_papers[pid]):
            original=(row["section_title"] or "").replace("\n"," ")+"\n"+row["text"]
            raw=original.encode("utf8")
            if raw:
                name=f"{pid}|{row['section']}|{row['paragraph']}"
                key=hashlib.sha256((SAMPLE_SALT+"|"+name).encode()).digest()
                candidates.append((key,name,raw))
    if not candidates:raise AssertionError("no independent train samples")
    candidates.sort(key=lambda x:(x[0],x[1]))
    selected=candidates[:limit]
    ids=[x[1] for x in selected]
    return [x[2] for x in selected],{
        "source":"Original QASPER v0.3 TRAIN text only, original paper IDs disjoint from dev",
        "train_papers":len(train_papers),
        "total_candidate_paragraphs":len(candidates),
        "chosen_sample_paragraphs":len(selected),
        "selected_docid_sha256":hashlib.sha256(
            "\n".join(ids).encode()).hexdigest(),
        "chosen_raw_sample_bytes":sum(len(x[2]) for x in selected),
        "qa_labels_seen":False,
        "dev_paper_text_seen":False,
    }


def train_dictionaries(samples,sizes=DICT_SIZES):
    """Existing Zstd trainer; output includes exact dict header and ID."""
    import zstandard as zstd
    results={}
    for size in sizes:
        if size<1024:raise ValueError("dict too small")
        begin=time.perf_counter()
        dictionary=zstd.train_dictionary(size,samples)
        elapsed=time.perf_counter()-begin
        raw=dictionary.as_bytes()
        if not 1000<=len(raw)<=size:
            raise AssertionError("trainer produced unexpected dictionary length")
        if dictionary.dict_id()==0:
            raise AssertionError("trained zstd dictionary unexpectedly has no ID")
        results[size]={
            "raw":raw,
            "sha256":hashlib.sha256(raw).digest(),
            "training_seconds":elapsed,
            "zstd_dict_id":dictionary.dict_id(),
        }
    return results


def parse_variant(name):
    if name=="brotli5":return ("brotli5",None,None)
    if name in ("zstd3","zstd9"):
        return ("zstd",int(name[-1]),None)
    if name.startswith("zstd") and "_dict" in name:
        prefix,size=name.split("_dict",1)
        level=int(prefix[4:])
        size=int(size)
        if level not in ZSTD_LEVELS or size not in DICT_SIZES:
            raise ValueError("non-predeclared dictionary variant")
        return ("zstd",level,size)
    raise ValueError("unknown codec variant")


def base_archive(path,docs):
    db=create_legacy_contentless(path,docs)
    db.execute("ALTER TABLE docs ADD COLUMN codec TEXT NOT NULL DEFAULT 'brotli5'")
    db.execute("ALTER TABLE docs ADD COLUMN dict_id INTEGER NOT NULL DEFAULT 0")
    db.execute("""
        CREATE TABLE source_dictionaries(
          dict_id INTEGER PRIMARY KEY,
          payload BLOB NOT NULL,
          sha256 BLOB NOT NULL CHECK(length(sha256)=32),
          zstd_dict_id INTEGER NOT NULL
        )""")
    db.execute("VACUUM")
    return db


def encode_rows(originals,variant,dictionaries):
    import zstandard as zstd
    codec,level,dict_size=parse_variant(variant)
    if codec=="brotli5":
        return [encode("brotli5",x) for x in originals]
    if dict_size is None:
        compressor=zstd.ZstdCompressor(level=level)
    else:
        raw=dictionaries[dict_size]["raw"]
        dictionary=zstd.ZstdCompressionDict(raw)
        compressor=zstd.ZstdCompressor(level=level,dict_data=dictionary)
    return [compressor.compress(x) for x in originals]


def make_variant(path,base,docs,variant,dictionaries):
    """One archive with dictionary identity + bytes charged inside SQLite."""
    shutil.copyfile(base,path)
    db=sqlite3.connect(str(path),isolation_level=None)
    original=[document_bytes(d) for d in docs]
    _,_,size=parse_variant(variant)
    start=time.perf_counter()
    blobs=encode_rows(original,variant,dictionaries)
    encode_seconds=time.perf_counter()-start
    try:
        db.execute("BEGIN IMMEDIATE")
        if size is not None:
            entry=dictionaries[size]
            db.execute(
                "INSERT INTO source_dictionaries(dict_id,payload,sha256,zstd_dict_id) "
                "VALUES(1,?,?,?)",
                (entry["raw"],entry["sha256"],entry["zstd_dict_id"]))
        for rid,compressed in enumerate(blobs,1):
            db.execute(
                "UPDATE docs SET compressed=?,codec=?,dict_id=? WHERE rowid=?",
                (compressed,variant,1 if size else 0,rid))
        db.execute("COMMIT")
        db.execute("VACUUM")
        return db,{
            "encode_seconds":round(encode_seconds,6),
            "source_blob_bytes":sum(map(len,blobs)),
            "dictionary_stored_bytes":len(dictionaries[size]["raw"]) if size else 0,
            "dict_training_seconds":round(dictionaries[size]["training_seconds"],6)
                                  if size else 0,
        }
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        db.close()
        raise


class OriginalSourceReader:
    """Per-archive dictionary prepared once, sources independently encoded."""
    def __init__(self,db):
        import zstandard as zstd
        self.db=db
        self.standard={3:zstd.ZstdDecompressor(),
                       9:zstd.ZstdDecompressor()}
        rows=db.execute(
            "SELECT dict_id,payload,sha256,zstd_dict_id FROM source_dictionaries"
        ).fetchall()
        if len(rows)>1:
            raise AssertionError("R102 archives use one shared dictionary")
        self.dictionary=None
        self.dictionary_id=0
        if rows:
            rid,payload,digest,dict_id=rows[0]
            if rid!=1 or hashlib.sha256(payload).digest()!=digest:
                raise ValueError("stored source dictionary SHA identity mismatch")
            zd=zstd.ZstdCompressionDict(payload)
            if zd.dict_id()!=dict_id:
                raise ValueError("stored dictionary ID mismatch")
            self.dictionary_id=rid
            self.dictionary=zstd.ZstdDecompressor(dict_data=zd)

    def read(self,rid,expected_doc_id=None):
        row=self.db.execute(
            "SELECT doc_id,compressed,sha256,utf8_len,codec,dict_id "
            "FROM docs WHERE rowid=?",(rid,)).fetchone()
        if row is None:raise KeyError("source not found")
        doc_id,compressed,expected_hash,expected_len,variant,dict_id=row
        if expected_doc_id is not None and doc_id!=expected_doc_id:
            raise ValueError("original paragraph ID mismatch")
        if expected_len<0 or expected_len>2_000_000:
            raise ValueError("unexpected uncompressed length")
        codec,level,size=parse_variant(variant)
        if codec=="brotli5":
            if dict_id!=0:raise ValueError("unexpected dictionary for Brotli")
            import brotli
            raw=brotli.decompress(compressed)
        else:
            if size is None:
                if dict_id!=0:raise ValueError("unexpected dictionary on plain zstd")
                decoder=self.standard[level]
            else:
                if dict_id!=self.dictionary_id or self.dictionary is None:
                    raise ValueError("missing or mismatched shared dictionary")
                decoder=self.dictionary
            raw=decoder.decompress(
                compressed,max_output_size=expected_len+1)
        if len(raw)!=expected_len or hashlib.sha256(raw).digest()!=expected_hash:
            raise ValueError("source original SHA or decoded byte length mismatch")
        return raw


def measure_requests(reader,docs,ranked,k,repeat=3):
    count=0
    times=[]
    for _ in range(repeat):
        for source_rids in ranked.values():
            for rid in source_rids[:k]:
                start=time.perf_counter_ns()
                original=reader.read(rid,str(docs[rid-1]["doc_id"]))
                times.append((time.perf_counter_ns()-start)/1e6)
                if original!=document_bytes(docs[rid-1]):
                    raise AssertionError("retrieved bytes differ from original")
                count+=1
    return {
        "requested_original_source_receipts":count,
        "warm_sha_source_read":measured_percentiles(times),
        "k":k,
        "per_archive_dictionary_object_reused":True,
    }


def evaluate(train_papers,dev_papers,variants=VARIANTS,dictionary_sizes=DICT_SIZES):
    train_ids=set(train_papers)
    dev_ids=set(dev_papers)
    if train_ids&dev_ids:
        raise AssertionError("QASPER source paper leakage across train/dev")
    dev_docs,cases,_=load_dev(dev_papers)
    samples,provenance=independently_trained_samples(train_papers)
    dictionaries=train_dictionaries(samples,dictionary_sizes)
    original=[document_bytes(x) for x in dev_docs]
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        source=root/"base.sqlite"
        control=base_archive(source,dev_docs)
        try:
            stats=control.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]
            rankings=queries_for_original(dev_docs,cases,control)
            baseline_rankings=rankings
        finally:control.close()
        outputs=[]
        for variant in variants:
            filepath=root/(variant+".sqlite")
            conn,metrics=make_variant(
                filepath,source,dev_docs,variant,dictionaries)
            try:
                physical=filepath.stat().st_size
                if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise AssertionError("SQLite core integrity failed")
                conn.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
                if conn.execute(
                    "SELECT hex(block) FROM sources_data WHERE id=1").fetchone()[0]!=stats:
                    raise AssertionError("source codec changed FTS posting statistics")
                new_rankings=queries_for_original(dev_docs,cases,conn)
                if new_rankings!=baseline_rankings:
                    raise AssertionError("codec changed QASPER BM25 rankings")
                reader=OriginalSourceReader(conn)
                for rid,expected in enumerate(original,1):
                    if reader.read(rid,str(dev_docs[rid-1]["doc_id"]))!=expected:
                        raise AssertionError("original source mismatch on full audit")
                outputs.append({
                    "variant":variant,
                    "documents":len(dev_docs),
                    "original_source_docs_sha_verified":len(dev_docs),
                    "identical_question_rankings":len(cases),
                    "fts_stats_unchanged":True,
                    "whole_sqlite_source_and_index_bytes":physical,
                    **metrics,
                    "top1":measure_requests(
                        reader,dev_docs,rankings,1),
                    "top10":measure_requests(
                        reader,dev_docs,rankings,10,repeat=1),
                })
            finally:conn.close()
        baseline=next(x for x in outputs if x["variant"]=="brotli5")
        for row in outputs:
            row["saved_sqlite_bytes_vs_brotli5"]=(
                baseline["whole_sqlite_source_and_index_bytes"]
                -row["whole_sqlite_source_and_index_bytes"])
        return {
            "round":102,
            "source":"Original QASPER v0.3 train/dev article-disjoint splits",
            "source_train_sha256":TRAIN_SHA,
            "source_dev_sha256":DEV_SHA,
            "training":provenance,
            "dictionary_sizes":list(dictionary_sizes),
            "n_original_dev_paragraphs":len(dev_docs),
            "n_qa_queries":len(cases),
            "archives":outputs,
            "best_persistent_bytes":min(
                outputs,key=lambda x:x["whole_sqlite_source_and_index_bytes"]
            )["variant"],
            "limits":[
                "Dictionary trained on original independent train articles, but same broad QASPER domain",
                "All source labels and question annotations ignored by dictionary training",
                "Existing Zstandard dictionary training, not novel compression mathematics",
                "All archive bytes include one persisted SHA-verified dictionary and dictionary codec IDs",
                "Original FTS5 postings and original source bytes equal across variants",
                "Single GitHub CPU runner; warm timing differences descriptive not cold SSD proof",
                "Brotli decoder output allocation not strictly capped before decoding",
                "No generated answers, hallucination accuracy, or model verification",
                "Dictionary training and encoding work measured separately, not charged as persistent bytes",
            ],
        }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=p.parse_args()
    source=fetch_qasper()
    if source["train"]["sha256"]!=TRAIN_SHA or source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("original QASPER train/dev release changed")
    result=evaluate(source["train"]["data"],source["dev"]["data"])
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND102",json.dumps({
        "source":result["source"],"train":result["training"],
        "best":result["best_persistent_bytes"],"archives":result["archives"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
