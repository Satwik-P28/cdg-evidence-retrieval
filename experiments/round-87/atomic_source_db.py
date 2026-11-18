#!/usr/bin/env python3
"""R87: one SQLite transaction couples contentless FTS5 and compressed source.

Existing features: SQLite FTS5 contentless-delete and SQLite ACID transaction.
Tests 5,183 original SciFact sources, 300 claims, exact BM25 ranking equivalence,
persistent bytes and fail-closed source integrity; injection tests exercise
single-process rollback, NOT power-loss crash consistency or concurrent load.
"""
from __future__ import annotations
import argparse,hashlib,json,sqlite3,sys,tempfile,time,zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-83'))
sys.path.insert(0,str(HERE.parent/'round-86'))
from scifact_data_probe import fetch,parse,digests
from contentless_cas import (
    document_bytes,make_fts,query_text,compute_rankings,
    validate_ranks,label_recall,EXPECTED_RELEASE_SHA
)


def strict_inflate(compressed):
    obj=zlib.decompressobj()
    content=obj.decompress(compressed)
    content+=obj.flush()
    if not obj.eof or obj.unused_data or obj.unconsumed_tail:
        raise ValueError('compressed source stream truncated, trailing, or malformed')
    return content


def sha(data):
    return hashlib.sha256(data).digest()


def create_db(path,corpus):
    start=time.perf_counter()
    db=sqlite3.connect(str(path),isolation_level=None)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA synchronous=FULL')
    db.execute("""
        CREATE TABLE docs (
            rowid INTEGER PRIMARY KEY,
            doc_id TEXT UNIQUE NOT NULL,
            compressed BLOB NOT NULL,
            sha256 BLOB NOT NULL CHECK(length(sha256)=32),
            utf8_len INTEGER NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1
        )""")
    db.execute("""
        CREATE VIRTUAL TABLE sources USING fts5(
            title,abstract,content='',contentless_delete=1,
            tokenize='unicode61'
        )""")
    db.execute('BEGIN IMMEDIATE')
    try:
        for i,row in enumerate(corpus,1):
            text=document_bytes(row)
            db.execute("INSERT INTO docs(rowid,doc_id,compressed,sha256,utf8_len,generation) "
                       "VALUES(?,?,?,?,?,1)",
                       (i,str(row['doc_id']),zlib.compress(text,6),sha(text),len(text)))
            db.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                       (i,str(row['title']),' '.join(row['abstract'])))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        db.close()
        raise
    db.execute('VACUUM')
    retained=path.stat().st_size
    return db,{
        'persistent_index_and_source_bytes':retained,
        'sqlite_version':sqlite3.sqlite_version,
        'source_count':len(corpus),
        'build_and_vacuum_seconds':round(time.perf_counter()-start,4),
        'configuration':"contentless_delete=1, zlib6 source BLOB, source SHA256 BLOB, indexed title and abstract",
        'transactional_contract':'compressed source and FTS5 postings updated in one SQLite BEGIN IMMEDIATE/COMMIT or ROLLBACK',
    }


def read(db,rowid):
    record=db.execute(
        "SELECT doc_id,compressed,sha256,utf8_len,generation "
        "FROM docs WHERE rowid=?",(rowid,)).fetchone()
    if record is None:raise KeyError(f'no source rowid {rowid}')
    doc_id,compressed,digest,length,generation=record
    try:
        raw=strict_inflate(compressed)
    except Exception as exc:
        raise ValueError('source compressed payload failed integrity check') from exc
    if len(raw)!=length or sha(raw)!=digest:
        raise ValueError('source SHA-256 or byte length mismatch')
    return {'doc_id':doc_id,'source_bytes':raw,'generation':generation}


def atomic_update(db,rowid,doc_id,title,abstract,fault=None):
    """One transaction: update both compressed evidence and search postings.

    Fault stages are test-only failure injections. No external file mutation.
    """
    payload=(title+'\n'+' '.join(abstract)).encode('utf8')
    if fault not in (None,'after_payload','after_index'):
        raise ValueError('unrecognized fault stage')
    db.execute('BEGIN IMMEDIATE')
    try:
        existing=db.execute("SELECT doc_id,generation FROM docs WHERE rowid=?",(rowid,)).fetchone()
        if existing is None or str(existing[0])!=str(doc_id):
            raise KeyError('document identity mismatch')
        generation=existing[1]+1
        db.execute("UPDATE docs SET compressed=?,sha256=?,utf8_len=?,generation=? WHERE rowid=?",
                   (zlib.compress(payload,6),sha(payload),len(payload),generation,rowid))
        if fault=='after_payload':
            raise RuntimeError('injected interrupted update after source payload')
        db.execute("DELETE FROM sources WHERE rowid=?",(rowid,))
        db.execute("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                   (rowid,title,' '.join(abstract)))
        if fault=='after_index':
            raise RuntimeError('injected interrupted update after index')
        db.execute('COMMIT')
        return generation
    except Exception:
        db.execute('ROLLBACK')
        raise


def atomic_delete(db,rowid,doc_id,fault=None):
    if fault not in (None,'after_payload'):
        raise ValueError('unknown fault stage')
    db.execute('BEGIN IMMEDIATE')
    try:
        existing=db.execute("SELECT doc_id FROM docs WHERE rowid=?",(rowid,)).fetchone()
        if existing is None or str(existing[0])!=str(doc_id):
            raise KeyError('wrong source identity')
        db.execute("DELETE FROM docs WHERE rowid=?",(rowid,))
        if fault=='after_payload':
            raise RuntimeError('injected deletion')
        db.execute("DELETE FROM sources WHERE rowid=?",(rowid,))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise


def query(db,claim,k=10):
    q=query_text(claim)
    if q is None:return []
    return [int(x[0]) for x in db.execute(
        "SELECT rowid FROM sources WHERE sources MATCH ? "
        "ORDER BY bm25(sources,5.0,1.0),rowid LIMIT ?",
        (q,k)).fetchall()]


def ranks(db,claims,k=10):
    t0=time.perf_counter()
    result={str(x['id']):query(db,x['claim'],k) for x in claims}
    return result,round(time.perf_counter()-t0,5)


def benchmark(corpus,claims):
    if len({str(x['doc_id']) for x in corpus})!=len(corpus):
        raise AssertionError('duplicate document identity')
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)
        full,meta_full=make_fts(p/'full.sqlite',corpus,False)
        # The separate contentless-index+archive model from R86 is a known
        # reference. These are the exact same original source bytes.
        lean,meta_lean=make_fts(p/'lean.sqlite',corpus,True)
        db,meta=create_db(p/'atomic.sqlite',corpus)
        try:
            full_r,full_cost=ranks(full,claims)
            lean_r,lean_cost=ranks(lean,claims)
            atomic_r,atomic_cost=ranks(db,claims)
            validate_ranks(full_r,lean_r)
            validate_ranks(lean_r,atomic_r)
            read_seconds=0.;read_count=0;byte_total=0
            for r in claims:
                ranked=atomic_r[str(r['id'])]
                if not ranked:continue
                source_rowid=ranked[0]
                t0=time.perf_counter()
                out=read(db,source_rowid)
                read_seconds+=time.perf_counter()-t0
                expected=document_bytes(corpus[source_rowid-1])
                if out['source_bytes']!=expected or out['doc_id']!=str(corpus[source_rowid-1]['doc_id']):
                    raise AssertionError('retrieved source bytes differ')
                byte_total+=len(out['source_bytes'])
                read_count+=1
            gold=label_recall(corpus,claims,atomic_r)
            for k in (1,3,5,10):
                gold['recall_at_'+str(k)]['rate']=round(
                    gold['recall_at_'+str(k)]['hits']/gold['denominator'],6)
            return {
                'corpus_size':len(corpus),'claim_queries':len(claims),
                'top10_rankings_identical_for_all_claims':True,
                'gold_retrieval':gold,
                'atomic_single_db':meta,
                'full_content_control':meta_full,
                'contentless_index_only_control':meta_lean,
                'source_reads':{
                    'top1_docs_read':read_count,
                    'source_bytes_verified':byte_total,
                    'warm_inprocess_decompress_plus_SHA_seconds':round(read_seconds,5)},
                'index_query_wall_seconds':{
                    'full_content':full_cost,'contentless_external':lean_cost,
                    'atomic_single_db':atomic_cost},
                'retained_savings_vs_full_fts_bytes':
                    meta_full['database_bytes']-meta['persistent_index_and_source_bytes'],
                'retained_savings_vs_r86_external_archive_bytes':
                    8609749-meta['persistent_index_and_source_bytes'],
                'r86_separate_contentless_index_plus_archive_plus_mapping_reference':8609749,
                'warning':'real physical SSD I/O, process crash kill, concurrent updates, and power loss not tested',
            }
        finally:
            full.close();lean.close();db.close()


def run():
    tar,raw=fetch()
    if digests(tar)['sha256']!=EXPECTED_RELEASE_SHA:
        raise AssertionError('source corpus SHA changed')
    corpus,claims,_=parse(raw)
    result=benchmark(corpus,claims)
    result['provenance']={
        'original_scifact_tar_sha256':digests(tar)['sha256'],
        'sqlite_version':sqlite3.sqlite_version,
        'methods':'SQLite contentless-delete FTS5, zlib6 compressed source BLOB, SHA256 and atomic same-DB transactions',
    }
    result['scientific_limitations']=[
        'The compressed source is in SQLite itself, not an external CAS with independent crash recovery',
        'Atomic update and rollback are tested with deterministic exceptions, not kill -9 or power interruption',
        'SQLite transactions provide general ACID semantics but power-loss durability is not measured in this experiment',
        'No concurrent multi-process p99 tests, full incremental indexing profiles or SSD cold reads',
        'Ranking unchanged does not establish human-supported answer faithfulness or claim verification',
        'Already existing SQLite contentless-delete plus compressed BLOB technology, no new compression or search algorithm',
        'One source document per row; deduplication across related sources not evaluated',
        'This corpus is immutable so versioned history and journal compaction are not represented in persisted byte totals',
        'Single-run latency is descriptive and includes OS caching; not a fair throughput ranking',
    ]
    print('ROUND87',json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    Path(args.out).write_text(json.dumps(run(),indent=2)+'\n')
