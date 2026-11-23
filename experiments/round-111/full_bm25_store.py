#!/usr/bin/env python3
"""CDG R111: complete-vocabulary, term-frequency-aware materialized posting store.

Separately decodable docID gaps and term frequency streams can reproduce BM25
for single lexical terms and conjunctive term queries. This does NOT replace
FTS5's native positional/phrase index, tokenizer or production query planner.
Each arm has identical SQLite schema and all columns/metadata charged.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-108'))
from codec_controls import encode,decode
from authentic_postings import docs_from_release

CODECS=('barm_r','varint','ef_partitioned','bitpack','hybrid_df4','oracle_min')
ATOMIC_CODECS=('barm_r','varint','ef_partitioned','bitpack')
TAGS={name:i for i,name in enumerate(ATOMIC_CODECS)}
REV_TAGS={v:k for k,v in TAGS.items()}
K1=1.2
B=.75
SALT='CDG-R111-BM25-FULL-VOCAB-2026-v1'


def make_fts(db_path:Path,docs:list[tuple[str,str]]):
    db=sqlite3.connect(db_path)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE VIRTUAL TABLE docs USING fts5(body,content="")')
    db.executemany('INSERT INTO docs(rowid,body) VALUES(?,?)',
                   ((i,t+'\n'+b) for i,(t,b) in enumerate(docs,1)))
    db.commit()
    return db


def collect_postings(db:sqlite3.Connection,n_docs:int):
    """Read FTS5's real term occurrences, preserving true per-document tf and dl.

    Store aggregate posting tuples only, never original source text in outputs.
    """
    db.execute('CREATE VIRTUAL TABLE vocab_r111 USING fts5vocab(docs,"instance")')
    lengths=[0]*(n_docs+1)
    by_term={}
    active=None
    ids=[]
    freqs=[]
    last_doc=0
    for term,doc in db.execute('SELECT term,doc FROM vocab_r111 ORDER BY term,doc'):
        doc=int(doc)
        if not 1<=doc<=n_docs:raise AssertionError('invalid native FTS5 row ID')
        lengths[doc]+=1
        if term!=active:
            if active is not None:by_term[active]=(ids,freqs)
            active=term
            ids=[];freqs=[]
            last_doc=0
        if doc!=last_doc:
            if doc<=last_doc:raise AssertionError('unsorted FTS5 term postings')
            ids.append(doc);freqs.append(1)
            last_doc=doc
        else:
            freqs[-1]+=1
    if active is not None:by_term[active]=(ids,freqs)
    db.execute('DROP TABLE vocab_r111')
    if not by_term or not any(lengths):raise ValueError('empty original FTS5 vocabulary')
    if sum(lengths)!=sum(sum(tfs) for _,tfs in by_term.values()):
        raise AssertionError('FTS5 tf and document length disagree')
    return by_term,lengths


def ids_to_gaps(ids:list[int]):
    prev=0;res=[]
    for i in ids:
        if type(i) is not int or i<=prev:raise ValueError('nonincreasing posting')
        res.append(i-prev);prev=i
    return res


def gaps_to_ids(gaps:list[int]):
    prev=0;res=[]
    for g in gaps:
        if type(g) is not int or g<1:raise ValueError('nonpositive posting gap')
        prev+=g;res.append(prev)
    return res


def choose_codec(gaps:list[int],family:str):
    if family in ATOMIC_CODECS:return family
    if family=='hybrid_df4':return 'varint' if len(gaps)<4 else 'barm_r'
    if family=='oracle_min':
        return min(ATOMIC_CODECS,key=lambda c:(len(encode(gaps,c)),TAGS[c]))
    raise ValueError(f'unknown family {family}')


def pack_postings(ids:list[int],freqs:list[int],family:str)->bytes:
    if not ids or len(ids)!=len(freqs) or any(type(t) is not int or t<1 for t in freqs):
        raise ValueError('nonpositive or mismatched term-frequency postings')
    gaps=ids_to_gaps(ids)
    mode=choose_codec(gaps,family)
    encoded_gaps=encode(gaps,mode)
    encoded_tf=encode(freqs,'varint')
    # 1 byte mode tag + 4 byte gap blob size + gaps + tf blob.
    return bytes([TAGS[mode]])+len(encoded_gaps).to_bytes(4,'little')+encoded_gaps+encoded_tf


def unpack_postings(blob:bytes,expected_df:int,allowed_family:str|None=None):
    if not isinstance(blob,bytes) or len(blob)<6 or type(expected_df) is not int or expected_df<=0:
        raise ValueError('truncated/invalid postings')
    try:mode=REV_TAGS[blob[0]]
    except KeyError:raise ValueError('invalid posting codec') from None
    if allowed_family in ATOMIC_CODECS and mode!=allowed_family:
        raise ValueError('unexpected fixed codec tag')
    n=int.from_bytes(blob[1:5],'little')
    if n<1 or n>len(blob)-6:raise ValueError('bad gap span')
    ids=gaps_to_ids(decode(blob[5:5+n],mode))
    freqs=decode(blob[5+n:],'varint')
    if len(ids)!=expected_df or len(freqs)!=expected_df or any(x<=0 for x in freqs):
        raise ValueError('corrupted df or term frequencies')
    return ids,freqs


def build_store(path:Path,by_term:dict[str,tuple[list[int],list[int]]],lengths:list[int],family:str):
    if family not in CODECS:raise ValueError('bad codec family')
    db=sqlite3.connect(path)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL) WITHOUT ROWID')
    db.execute('CREATE TABLE dl(docid INTEGER PRIMARY KEY, length INTEGER NOT NULL CHECK(length>=0))')
    db.execute('CREATE TABLE postings(term TEXT PRIMARY KEY,df INTEGER NOT NULL CHECK(df>0), payload BLOB NOT NULL) WITHOUT ROWID')
    n_docs=len(lengths)-1
    db.executemany('INSERT INTO meta VALUES(?,?)', [('num_docs',n_docs),('total_tokens',sum(lengths))])
    db.executemany('INSERT INTO dl(docid,length) VALUES(?,?)', enumerate(lengths[1:],1))
    sums=Counter()
    time_start=time.perf_counter()
    for term,(ids,tf) in sorted(by_term.items()):
        packed=pack_postings(ids,tf,family)
        if unpack_postings(packed,len(ids),family)!=(ids,tf):
            raise AssertionError('payload roundtrip mismatch')
        db.execute('INSERT INTO postings VALUES(?,?,?)',(term,len(ids),packed))
        sums[packed[0]]+=1
    db.commit();db.execute('VACUUM');db.commit()
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise AssertionError('corrupt physical SQLite archive')
    stored=db.execute('SELECT SUM(LENGTH(payload)) FROM postings').fetchone()[0] or 0
    physical=path.stat().st_size
    db.close()
    return {'sqlite_bytes':physical,'payload_bytes':stored,
            'sqlite_plus_lexicon_plus_doclength_overhead_bytes':physical-stored,
            'number_of_terms':len(by_term),'codec_assignments':{REV_TAGS[k]:v for k,v in sums.items()},
            'build_wall_s_exploratory':round(time.perf_counter()-time_start,4)}


def fetch_term(db:sqlite3.Connection,term:str):
    row=db.execute('SELECT df,payload FROM postings WHERE term=?',(term,)).fetchone()
    if row is None:return [],[]
    return unpack_postings(row[1],int(row[0]))


def score_doc(terms:list[str],tf_by_term:dict[str,dict[int,int]],df:dict[str,int],
              docid:int,doc_len:int,n_docs:int,avg_len:float):
    accum=0.0
    for term in terms:
        tf=tf_by_term[term].get(docid,0)
        if not tf:continue
        dft=df[term]
        idf=math.log((n_docs-dft+0.5)/(dft+0.5))
        idf=max(idf,1e-6)
        accum+=idf*(tf*(K1+1.0))/(tf+K1*(1.0-B+B*doc_len/avg_len))
    return -accum


def quote_fts_term(term:str):
    return '"'+term.replace('"','""')+'"'


def rank_query(db:sqlite3.Connection,terms:list[str],n_docs:int,avg_len:float,k:int=10):
    fetched={t:fetch_term(db,t) for t in terms}
    if not fetched or any(not v[0] for v in fetched.values()):return []
    docids=set.intersection(*(set(ids) for ids,tf in fetched.values()))
    tf_by_term={t:dict(zip(ids,tf)) for t,(ids,tf) in fetched.items()}
    dfs={t:len(ids) for t,(ids,tf) in fetched.items()}
    lens=dict(db.execute('SELECT docid,length FROM dl WHERE docid IN ('+
                 ','.join('?'*len(docids))+')',tuple(sorted(docids)))) if docids else {}
    return sorted([(docid,score_doc(terms,tf_by_term,dfs,docid,lens[docid],n_docs,avg_len))
                   for docid in docids],key=lambda x:(x[1],x[0]))[:k]


def query_plan(by_term:dict[str,tuple[list[int],list[int]]],n_docs:int):
    """SHA-selected tests across all df ranges including df1 and saturated idf."""
    buckets={
      'df1':(1,1,8), 'df2_3':(2,3,8), 'df4_31':(4,31,32),
      'df32_256':(32,256,24), 'df257_plus':(257,n_docs,8),
    }
    singleton=[]
    pool=[]
    for band,(lo,hi,k) in buckets.items():
        eligible=[t for t,(ids,_) in by_term.items() if lo<=len(ids)<=hi]
        eligible.sort(key=lambda t:(hashlib.sha256((SALT+'|'+band+'|'+t).encode()).digest(),t))
        singleton.extend((t,) for t in eligible[:k])
        if band in ('df4_31','df32_256'):
            pool.extend(eligible[k:k+32])
    pairs=[(pool[i],pool[i+1]) for i in range(0,min(len(pool),64)-1,2)]
    if not singleton:raise ValueError('no original vocabulary terms')
    return singleton+pairs


def verify_queries(store:sqlite3.Connection,native:sqlite3.Connection,queries,
                   n_docs:int,avg_len:float):
    checked=0;topk_docs=0;ties=0;max_abs_error=0.0;with_hits=0
    for terms in queries:
        query=' AND '.join(quote_fts_term(t) for t in terms)
        native_results=[(int(rid),float(score)) for rid,score in
             native.execute('SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ? '
                            'ORDER BY bm25(docs),rowid LIMIT 10',(query,))]
        ours=rank_query(store,list(terms),n_docs,avg_len,k=10)
        # Score comparison is by row identity, not arbitrary rank position.
        a=dict(ours);b=dict(native_results)
        if set(a)!=set(b):
            raise AssertionError('BM25 top-k document identity mismatch')
        if native_results:with_hits+=1
        for docid in a:
            err=abs(a[docid]-b[docid]);max_abs_error=max(max_abs_error,err)
            if err>1e-12:
                raise AssertionError('BM25 score differs from SQLite')
        ar=[x[0] for x in ours]
        nr=[x[0] for x in native_results]
        if ar!=nr:
            # Accept only mathematically indistinguishable score ties. Track
            # them rather than claiming exact floating-point rank agreement.
            for ix,docid in enumerate(ar):
                if nr[ix]!=docid:
                    if abs(a[docid]-a[nr[ix]])>1e-14:
                        raise AssertionError('untied ranking inversion')
                    ties+=1
        topk_docs+=len(ours)
        checked+=1
    return {'queries':checked,'queries_with_hits':with_hits,'ranked_rowid_positions_checked':topk_docs,
            'ranking_tie_positions':ties,'max_score_abs_delta':max_abs_error,
            'scores_match_abs_1e_12':True,
            'note':'Equal-score ordering may vary by floating arithmetic; no phrase/positional queries'}


def run(dataset:str,docs=None,meta=None):
    if docs is None:
        docs,source_meta=docs_from_release(dataset)
    else:source_meta=meta or {'dataset':'synthetic fixture, not official source'}
    if not docs:raise ValueError('empty corpus')
    with tempfile.TemporaryDirectory(prefix='cdg-r111-') as root:
        root=Path(root)
        native=make_fts(root/'native.sqlite',docs)
        try:
            by_term,lengths=collect_postings(native,len(docs))
            native.commit();native.execute('VACUUM');native.commit()
            baseline_bytes=(root/'native.sqlite').stat().st_size
            terms_count=len(by_term)
            total_postings=sum(len(x[0]) for x in by_term.values())
            total_occurrences=sum(lengths)
            plan=query_plan(by_term,len(docs))
            avg=total_occurrences/len(docs)
            out={}
            for family in CODECS:
                path=root/(family+'.sqlite')
                metrics=build_store(path,by_term,lengths,family)
                with closing(sqlite3.connect(path)) as store:
                    metrics['bm25_verification']=verify_queries(store,native,plan,len(docs),avg)
                out[family]=metrics
        finally:native.close()
    return {'round':111,'dataset':dataset,'source':source_meta,'documents':len(docs),
            'native_fts5_one_column_physical_bytes_not_feature_equivalent':baseline_bytes,
            'full_token_vocabulary_terms':terms_count,'full_distinct_docid_postings':total_postings,
            'full_token_occurrences':total_occurrences,'queried_terms_and_pairs':len(plan),
            'query_sampling_salt':SALT,'codecs':out,
            'limitations':[
                'External store has full corpus vocabulary and exact term frequencies, but not token positions, phrase queries or native FTS5 implementation',
                'Original source text is not stored inside compared SQLite posting tables; identical schema and doc length metadata are charged to each arm',
                'Query plan uses fixed SHA-selected df 3..256 terms, not actual user query logs or human evidence labels',
                'BM25 checks use one text column formed by original title plus body and conjunctive terms only',
                'Comparison to original FTS5 is contextual, NOT feature-equivalent because native FTS5 stores token positions',
                'All codecs are Python implementations, without native SIMD controls; no trustworthy latency or CPU gain claim',
                'Oracle_min chooses smallest actual encoded list including a charged codec tag; it is an in-sample attainable lower envelope, not learned workload policy',
                'No RH theorem use, new lossless optimality proof, end-to-end RAG response, or hallucination result',
            ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',choices=['qasper','scifact'],required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    result=run(a.dataset)
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'dataset':a.dataset,'terms':result['full_token_vocabulary_terms'],
                      'docid_postings':result['full_distinct_docid_postings'],
                      'physical_bytes':{k:v['sqlite_bytes'] for k,v in result['codecs'].items()}},indent=2))
if __name__=='__main__':main()