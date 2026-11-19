#!/usr/bin/env python3
"""R105: QASPER grouped archive write-amplification and WAL cost frontier.

Same original 13,266 QASPER source paragraphs and same 120 deterministic
synthetic revisions under 17 strongly controlled archival approaches:
  - independent source Brotli5 and dictionary-backed zstd9
  - original paper-local source blocks 1/4/8/16/paper ×
    Brotli5, trained dictionary zstd3 and dictionary zstd9.
Charge static source+index bytes; separately measure source BLOB bytes
re-encoded, WAL bytes appended (autocheckpoint disabled), warm SQLite
transaction latency, post-VACUUM archive bytes, exact original-source
receipts and independent contentful-FTS5 ranking/statistics parity.

No human-answer labels are scored after deliberately mutating documents.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-90","round-96","round-97","round-99",
          "round-101","round-102","round-103","round-104"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,paper_rank
from contentless_cas import document_bytes,make_fts
from paper_block_brotli import base_fts_db,make_grouped_brotli
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries,
    base_archive as individual_base,make_variant as individual_variant,
    OriginalSourceReader,TRAIN_SHA,DEV_SHA
)
from joint_group_dictionary import GroupSourceReader,group_variant
from atomic_grouped_updates import (
    update_grouped,migrate_generations,fts_stats
)
from codec_frontier import measured_percentiles

GROUPS=(1,4,8,16,"paper")
GROUP_CODECS=("brotli5","zstd3-dictionary","zstd9-dictionary")
INDIVIDUAL_CODECS=("brotli5","zstd9_dict65536")
EDITS=120


def deterministic_edit_plan(docs,count=EDITS):
    """Fixed original source IDs and edits, independent of gold evidence."""
    if not docs:raise AssertionError("empty source input")
    mutations=[]
    for step in range(count):
        rid=1 if step%3==0 else ((step*131)%len(docs))+1
        original=docs[rid-1]
        new_title=str(original["title"])
        original_body=" ".join(original["abstract"])
        source_body=original_body+(
            " [R105 synthetic revision %d; original rowid=%d]"%(step,rid))
        if step%11==0:
            source_body+=" Additional independent observation."
        mutations.append((rid,str(original["doc_id"]),new_title,[source_body]))
    return mutations


def expected_corpus(docs,plan):
    out=[
        {"doc_id":str(d["doc_id"]),"title":str(d["title"]),
         "abstract":list(d["abstract"])} for d in docs
    ]
    for rid,docid,title,abstract in plan:
        if out[rid-1]["doc_id"]!=docid:
            raise AssertionError("update plan source ID changed")
        out[rid-1]["title"]=title
        out[rid-1]["abstract"]=list(abstract)
    return out


def update_individual(db,rid,docid,title,abstract):
    """Independent-source source-assisted atomic FTS5 updating control."""
    if not isinstance(title,str) or "\n" in title:
        raise ValueError("invalid original section title")
    if not isinstance(abstract,list) or not all(isinstance(x,str) for x in abstract):
        raise ValueError("invalid original paragraph body")
    content=(title+"\n"+" ".join(abstract)).encode("utf8")
    if db.in_transaction:
        raise RuntimeError("source writer already in transaction")
    db.execute("BEGIN IMMEDIATE")
    try:
        old=OriginalSourceReader(db).read(rid,docid)
        before=old.decode("utf8")
        if "\n" not in before:
            raise ValueError("old source title/body serialization invalid")
        old_title,old_body=before.split("\n",1)
        oldrow=db.execute(
            "SELECT codec,dict_id,generation FROM docs WHERE rowid=?",
            (rid,)).fetchone()
        if oldrow is None:
            raise KeyError("missing original source")
        codec,dict_id,old_generation=oldrow
        db.execute(
            "INSERT INTO sources(sources,rowid,title,abstract) "
            "VALUES('delete',?,?,?)",(rid,old_title,old_body))
        db.execute(
            "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
            (rid,title," ".join(abstract)))
        if codec=="brotli5":
            if dict_id!=0:raise ValueError("unexpected source dictionary")
            import brotli
            blob=brotli.compress(content,quality=5)
        elif codec=="zstd9_dict65536":
            if dict_id!=1:raise ValueError("missing dictionary for source codec")
            import zstandard as zstd
            row=db.execute(
                "SELECT payload,sha256,zstd_dict_id "
                "FROM source_dictionaries WHERE dict_id=1").fetchone()
            if row is None:
                raise ValueError("missing required source dictionary")
            payload,digest,source_dict_id=row
            if hashlib.sha256(payload).digest()!=digest:
                raise ValueError("shared source dictionary SHA mismatch")
            diction=zstd.ZstdCompressionDict(payload)
            if diction.dict_id()!=source_dict_id:
                raise ValueError("source dictionary ID mismatch")
            blob=zstd.ZstdCompressor(
                level=9,dict_data=diction).compress(content)
        else:
            raise ValueError("non-predeclared independently encoded codec")
        db.execute(
            "UPDATE docs SET compressed=?,sha256=?,utf8_len=?,"
            "generation=generation+1 WHERE rowid=?",
            (blob,hashlib.sha256(content).digest(),len(content),rid))
        db.execute("COMMIT")
        return {"compressed_blob_bytes_replaced":len(blob),
                "original_source_utf8_bytes_replaced":len(content),
                "generation":old_generation+1}
    except BaseException:
        if db.in_transaction:db.execute("ROLLBACK")
        raise


def blob_size_for_revision(db,rid,grouped):
    if grouped:
        row=db.execute(
            "SELECT length(b.compressed) FROM source_blocks b "
            "JOIN source_receipts r ON b.block_id=r.block_id "
            "WHERE r.rowid=?",(rid,)).fetchone()
    else:
        row=db.execute(
            "SELECT length(compressed) FROM docs WHERE rowid=?",
            (rid,)).fetchone()
    if row is None or row[0] is None:
        raise AssertionError("cannot identify revised source payload size")
    return int(row[0])


def archive_file_bytes(path):
    return path.stat().st_size if path.exists() else 0


def configure_wal(db):
    if db.in_transaction:
        raise AssertionError("can only set WAL outside transactions")
    if db.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower()!="wal":
        raise AssertionError("WAL mode unavailable")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA wal_autocheckpoint=0")


def run_edits(db,path,docs,plan,grouped):
    """Update cost is measured *excluding* validation/ranking readbacks."""
    configure_wal(db)
    wal_path=Path(str(path)+"-wal")
    durations=[]
    wal_deltas=[]
    compressed_payloads=[]
    original_payloads=[]
    wal_peak=archive_file_bytes(wal_path)
    for rid,docid,title,abstract in plan:
        prev=archive_file_bytes(wal_path)
        start=time.perf_counter_ns()
        if grouped:
            update_grouped(db,rid,docid,title,abstract)
        else:
            update_individual(db,rid,docid,title,abstract)
        durations.append((time.perf_counter_ns()-start)/1e6)
        now=archive_file_bytes(wal_path)
        if now<prev:
            raise AssertionError("WAL unexpectedly reset despite disabled autocheckpoint")
        wal_deltas.append(now-prev)
        wal_peak=max(wal_peak,now)
        compressed_payloads.append(
            blob_size_for_revision(db,rid,grouped))
        original_payloads.append(
            len((title+"\n"+" ".join(abstract)).encode("utf8")))
    if not durations or not original_payloads:
        raise AssertionError("empty source revision workload")
    return {
        "revisions":len(plan),
        "source_revision_ms":measured_percentiles(durations),
        "source_original_utf8_bytes_revised":sum(original_payloads),
        "source_reencoded_BLOB_bytes_sum":sum(compressed_payloads),
        "compressed_BLOB_rewrite_to_changed_original_ratio":round(
            sum(compressed_payloads)/sum(original_payloads),5),
        "WAL_bytes_appended_sum":sum(wal_deltas),
        "WAL_file_peak_bytes":wal_peak,
        "WAL_append_per_source_edit_ms_source_ratio":round(
            sum(wal_deltas)/sum(original_payloads),5),
        "journal_mode":"WAL, synchronous=FULL, wal_autocheckpoint=0",
    }


def exact_source_and_fts_diff(db,docs,expected,ref,cases,grouped):
    """Fail closed if dynamic archive differs from independently built final FTS."""
    if fts_stats(db)!=fts_stats(ref):
        raise AssertionError("FTS5 BM25 global source posting stats mismatch")
    reader=GroupSourceReader(db) if grouped else OriginalSourceReader(db)
    cache={} if grouped else None
    for rid,(before,after) in enumerate(zip(docs,expected),1):
        if str(before["doc_id"])!=str(after["doc_id"]):
            raise AssertionError("source ID unexpectedly replaced")
        if grouped:
            receipt=reader.read(rid,cache)
            got=receipt["source_bytes"]
            identity=receipt["doc_id"]
        else:
            identity=str(before["doc_id"])
            got=reader.read(rid,identity)
        if identity!=str(after["doc_id"]) or got!=document_bytes(after):
            raise AssertionError("update source or receipt drift versus trusted edits")
    for case in cases:
        a=paper_rank(
            ref,case["claim"],case["row_start"],case["row_end"],10)
        b=paper_rank(
            db,case["claim"],case["row_start"],case["row_end"],10)
        if a!=b:
            raise AssertionError("post-revision BM25 rankings not identical")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        raise AssertionError("SQLite source store core integrity failed")
    db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
    return {
        "verified_source_receipts":len(expected),
        "unchanged_FTS_global_stats":True,
        "identical_top10_question_rankings":len(cases),
        "sqlite_and_fts_integrity":"ok",
    }


def stable_vacuum_size(db,path):
    """Charge compacted main SQLite file separately from peak live WAL size."""
    checkpoint=db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint[0]!=0:
        raise RuntimeError("WAL checkpoint blocked before compaction")
    db.execute("VACUUM")
    checkpoint=db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint[0]!=0:
        raise RuntimeError("WAL checkpoint blocked after vacuum")
    if archive_file_bytes(Path(str(path)+"-wal")):
        raise AssertionError("WAL left nonzero after successful TRUNCATE")
    return path.stat().st_size


def benchmark_archives(train_papers,dev_papers,groups=GROUPS,
                       group_codecs=GROUP_CODECS,indiv_codecs=INDIVIDUAL_CODECS,
                       n_edits=EDITS):
    if set(train_papers)&set(dev_papers):
        raise AssertionError("train/dev article source identity overlap")
    samples,train_meta=independently_trained_samples(train_papers)
    dictionaries=train_dictionaries(samples,(65536,))
    dictionary=dictionaries[65536]
    docs,cases,_=load_dev(dev_papers)
    plan=deterministic_edit_plan(docs,n_edits)
    expected=expected_corpus(docs,plan)
    with tempfile.TemporaryDirectory() as scratch:
        root=Path(scratch)
        ref,_=make_fts(root/"expected-full-fts.sqlite",expected,False)
        individual_source=root/"initial-individual.sqlite"
        init=individual_base(individual_source,docs);init.close()
        results=[]
        try:
            for variant in indiv_codecs:
                path=root/("indiv-"+variant+".sqlite")
                db,_=individual_variant(
                    path,individual_source,docs,variant,dictionaries)
                try:
                    before=path.stat().st_size
                    cost=run_edits(db,path,docs,plan,grouped=False)
                    checked=exact_source_and_fts_diff(
                        db,docs,expected,ref,cases,False)
                    after=stable_vacuum_size(db,path)
                    results.append({
                        "source_layout":"individual",
                        "group":"individual",
                        "codec":variant,
                        "initial_static_archive_bytes":before,
                        "final_compacted_archive_bytes":after,
                        **cost,**checked,
                    })
                finally:db.close()
            groupbase=root/"original-group-fts.sqlite"
            base=base_fts_db(groupbase,docs)
            base.close()
            for group in groups:
                grouped=root/("group-"+str(group)+".sqlite")
                frame=make_grouped_brotli(grouped,groupbase,docs,group)
                frame.close()
                for variant in group_codecs:
                    path=root/("group-"+str(group)+"-"+variant+".sqlite")
                    db,_=group_variant(path,grouped,variant,dictionary)
                    migrate_generations(db)
                    try:
                        before=path.stat().st_size
                        cost=run_edits(db,path,docs,plan,grouped=True)
                        checked=exact_source_and_fts_diff(
                            db,docs,expected,ref,cases,True)
                        after=stable_vacuum_size(db,path)
                        results.append({
                            "source_layout":"paper-local blocks",
                            "group":group,
                            "codec":variant,
                            "initial_static_archive_bytes":before,
                            "final_compacted_archive_bytes":after,
                            **cost,**checked,
                        })
                    finally:db.close()
                grouped.unlink(missing_ok=True)
            return {
                "round":105,
                "dataset":"original QASPER v0.3 article-disjoint TRAIN source vs DEV original paragraphs",
                "source_sha256":{"train":TRAIN_SHA,"dev":DEV_SHA},
                "dev_source_docs":len(docs),
                "original_questions_used_only_for_rank_parity":len(cases),
                "n_edits":len(plan),
                "unique_source_rowids_mutated":len({
                    x[0] for x in plan}),
                "train_dictionary_sha256":dictionary["sha256"].hex(),
                "dictionary_stored_bytes":len(dictionary["raw"]),
                "training_sample_provenance":train_meta,
                "arms":results,
                "limits":[
                    "120 synthetic source edits per archive; original QASPER gold answers NOT scored after mutated text",
                    "WAL physical file-growth measured with autocheckpoint disabled; actual SSD write bytes may differ",
                    "Each revision transaction includes source SHA verification, FTS posting revision and full block recompression",
                    "Elapsed time covers Python SQLite writer, crypto, dictionary setup and compression; one warm GitHub Actions runner",
                    "Final archive post-VACUUM main SQLite size and live peak main+WAL footprint are distinct resources",
                    "No block update policy trained or selected on QASPER dev gold annotation",
                    "No physical power-loss simulation, network filesystems, multiwriter throughput or dense retrieval",
                    "This is existing standard FTS5/Brotli/Zstandard and SQLite transactions, not a novel compression algorithm",
                ],
            }
        finally:ref.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=p.parse_args()
    source=fetch_qasper()
    if source["train"]["sha256"]!=TRAIN_SHA or source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("original QASPER source release hash drift")
    result=benchmark_archives(source["train"]["data"],source["dev"]["data"])
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND105",json.dumps({
        "docs":result["dev_source_docs"],"questions":result[
            "original_questions_used_only_for_rank_parity"],
        "edits":result["n_edits"],"unique_sources":result[
            "unique_source_rowids_mutated"],
        "arms":[{
            "group":x["group"],"codec":x["codec"],
            "initial":x["initial_static_archive_bytes"],
            "final":x["final_compacted_archive_bytes"],
            "wal_peak":x["WAL_file_peak_bytes"],
            "wal_append":x["WAL_bytes_appended_sum"],
            "write_amplification":x["compressed_BLOB_rewrite_to_changed_original_ratio"],
            "latency":x["source_revision_ms"],
            "fts_parity":x["identical_top10_question_rankings"],
        } for x in result["arms"]],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
