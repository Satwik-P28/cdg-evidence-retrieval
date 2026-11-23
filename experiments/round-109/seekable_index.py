#!/usr/bin/env python3
"""R109: independently seekable, real SQLite BLOB posting list stores.

Compares exact *physical* SQLite database sizes and warm per-term lookups for
identical original-SciFact/QASPER SHA-locked FTS5-derived doc-ID sets. Each
codec is a substitute for a simple docID posting store, not SQLite FTS5's
native positions, frequencies, BM25, or phrase indexes. The reference
contentless FTS5 index is kept solely as a docID correctness oracle.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'round-108'))
from authentic_postings import docs_from_release,sample_postings,BANDS,SAMPLE_SALT
from codec_controls import CODECS,encode,decode

QUERY_SALT='CDG-R109-QUERY-SAMPLE-2026-11'
CODECS_COMPARE=('barm_r','ef_partitioned','varint','streamvbyte','bitpack','zlib_varint')


def _sort_hash(s:str)->bytes:
    return hashlib.sha256((QUERY_SALT+'|'+s).encode()).digest()


def list_plan(terms:list[str], max_queries:int=384, max_pairs:int=128):
    ordered=sorted(terms,key=lambda s:(_sort_hash(s),s))
    singled=ordered[:min(len(ordered),max_queries)]
    # Disjoint adjacent pairs from stable ordering, independent of labels/codecs.
    pairs=[(ordered[i],ordered[i+1]) for i in range(0,min(len(ordered)-1,2*max_pairs),2)]
    return singled,pairs


def ids_to_gaps(ids:list[int]):
    last=0
    gaps=[]
    for i in ids:
        if type(i) is not int or i<=last:
            raise ValueError('row IDs must be positive/increasing integers')
        gaps.append(i-last);last=i
    return gaps


def gaps_to_ids(gaps:list[int]):
    ids=[];t=0
    for g in gaps:
        if g<=0:raise ValueError('nonpositive gap')
        t+=g
        ids.append(t)
    return ids


def make_fts(path:Path,docs:list[tuple[str,str]]):
    db=sqlite3.connect(path)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE VIRTUAL TABLE docs USING fts5(title,body,content="")')
    db.executemany('INSERT INTO docs(rowid,title,body) VALUES(?,?,?)',
                   ((i,t,b) for i,(t,b) in enumerate(docs,1)))
    db.commit()
    return db


def make_store(path:Path, groups:dict, codec:str):
    if codec not in CODECS_COMPARE:raise ValueError('invalid codec')
    db=sqlite3.connect(path)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA auto_vacuum=NONE')
    db.execute('CREATE TABLE postings (term TEXT PRIMARY KEY, df INTEGER NOT NULL CHECK (df>0), payload BLOB NOT NULL) WITHOUT ROWID')
    blob_bytes=0
    nrows=0
    start=time.perf_counter()
    try:
        rows=sorted([(term,ids) for items in groups.values() for term,ids in items])
        if len({t for t,_ in rows})!=len(rows):raise AssertionError('duplicate term')
        for term,ids in rows:
            gaps=ids_to_gaps(ids)
            blob=encode(gaps,codec)
            if gaps_to_ids(decode(blob,codec))!=ids:raise AssertionError('encoder corrupted doc IDs')
            db.execute('INSERT INTO postings(term,df,payload) VALUES(?,?,?)',(term,len(ids),blob))
            blob_bytes+=len(blob);nrows+=1
        db.commit()
        db.execute('VACUUM')
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise AssertionError('damaged SQLite database')
        db.close()
        return {'physical_sqlite_bytes':path.stat().st_size,
                'encoded_payload_bytes':blob_bytes,
                'sqlite_overhead_bytes':path.stat().st_size-blob_bytes,
                'term_rows':nrows,
                'build_elapsed_s_exploratory':round(time.perf_counter()-start,4)}
    except BaseException:
        db.close()
        raise


def query_ids(db:sqlite3.Connection,term:str,codec:str):
    row=db.execute('SELECT df,payload FROM postings WHERE term=?',(term,)).fetchone()
    if row is None:return []
    df,blob=row
    ids=gaps_to_ids(decode(blob,codec))
    if len(ids)!=df:raise ValueError('posting list length corrupted')
    return ids


def _fts_query(db,term):
    # FTS5 quote escaping for an original vocabulary token.
    match='"'+term.replace('"','""')+'"'
    return [int(x[0]) for x in db.execute('SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY rowid',(match,))]


def time_and_verify_store(db:sqlite3.Connection,fts:sqlite3.Connection,terms:list[str],
                          pairs:list[tuple[str,str]],codec:str, expected:dict):
    # warm check one pass before measuring
    for term in terms:
        if query_ids(db,term,codec)!=expected[term]:raise AssertionError('warm mismatch')
    durations=[]
    for term in terms:
        t0=time.perf_counter_ns()
        actual=query_ids(db,term,codec)
        dt=time.perf_counter_ns()-t0
        durations.append(dt)
        if actual!=expected[term]:raise AssertionError('decoded postings differ')
        if actual!=_fts_query(fts,term):raise AssertionError('FTS5 term result differs')
    checked_pairs=0
    for a,b in pairs:
        x,y=set(query_ids(db,a,codec)),set(query_ids(db,b,codec))
        if sorted(x&y)!=sorted(set(expected[a])&set(expected[b])):raise AssertionError('AND mismatch')
        if sorted(x|y)!=sorted(set(expected[a])|set(expected[b])):raise AssertionError('OR mismatch')
        checked_pairs+=1
    ms=[x/1e6 for x in durations]
    ordered=sorted(ms)
    return {'exact_single_term_queries':len(terms),
            'exact_pair_AND_OR_queries':checked_pairs,
            'warm_median_ms_python_sqlite':round(statistics.median(ms),6) if ms else None,
            'warm_p95_ms_python_sqlite':round(ordered[min(len(ordered)-1,int(.95*len(ordered)))],6) if ordered else None,
            'not_cold_or_hardware_controlled':True}


def run(dataset:str,docs=None,external_meta=None):
    if docs is None:docs,meta=docs_from_release(dataset)
    else:meta=external_meta or {'dataset':'synthetic fixture, not original scientific source'}
    if not docs:raise ValueError('empty docs')
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='cdg-r109-') as folder:
        base=Path(folder)
        fts=make_fts(base/'fts5.sqlite',docs)
        try:
            groups,eligible=sample_postings(fts,dataset)
            fts.commit()
            fts.execute('VACUUM')
            fts.commit()
            fts_bytes=(base/'fts5.sqlite').stat().st_size
            expected={t:ids for items in groups.values() for t,ids in items}
            terms,pairs=list_plan(list(expected))
            metrics={}
            for codec in CODECS_COMPARE:
                path=base/(codec+'.sqlite')
                met=make_store(path,groups,codec)
                with closing(sqlite3.connect(path)) as db:
                    met['lookups']=time_and_verify_store(db,fts,terms,pairs,codec,expected)
                metrics[codec]=met
        finally:fts.close()
    total_terms=len(expected)
    return {
      'round':109,'dataset':dataset,'source':meta,'num_original_documents':len(docs),
      'original_fts5_index_bytes_not_semantically_equivalent':fts_bytes,
      'selected_term_count':total_terms,
      'selected_docid_postings':sum(len(i) for i in expected.values()),
      'original_term_sampling':'identical SHA-minimal df-stratified R108 sample',
      'term_sample_salt':SAMPLE_SALT,'total_eligible_terms_per_stratum':eligible,
      'query_sample_salt':QUERY_SALT,'metrics':metrics,
      'total_pipeline_wall_seconds':round(time.perf_counter()-start,2),
      'limitations':[
        'External SQLite postings table supports docID-only term lookup, not full FTS5 native ranking/positions/frequencies',
        'Original contentless FTS5 index size is contextual only and is NOT a feature-equivalent baseline',
        'All codec stores have same term set and same WITHOUT ROWID table schema with actual file bytes',
        'Warm SQLite+Python decoder timings are descriptive one-runner samples, not cold SSD or SIMD throughput',
        'QASPER/SciFact source payloads fetched with existing SHA locks; no source text committed',
        'Selected vocabulary is a hashed doc-frequency-stratified sample, not a complete external index or overall FTS compression estimate',
        'No source archive/citation receipt/versioning coupled into external store',
      ]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['qasper','scifact'],required=True);p.add_argument('--out',required=True)
    a=p.parse_args();res=run(a.dataset)
    Path(a.out).write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'dataset':a.dataset,'terms':res['selected_term_count'],'postings':res['selected_docid_postings'],
                      'physical_sqlite_bytes':{k:v['physical_sqlite_bytes'] for k,v in res['metrics'].items()}},indent=2))
if __name__=='__main__':main()