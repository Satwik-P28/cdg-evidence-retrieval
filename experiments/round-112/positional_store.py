#!/usr/bin/env python3
"""R112: full original token positions, separate BM25 and phrase access planes.

This is a research comparison of materialized SQLite external posting stores,
not a replacement for SQLite's internal FTS5 posting format or an RH result.
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

ATOMIC=('barm_r','varint','ef_partitioned','bitpack','zlib_varint')
FAMILIES=ATOMIC+('static_hybrid','per_term_oracle')
TAGS={k:i for i,k in enumerate(ATOMIC)}
REVERSE={v:k for k,v in TAGS.items()}
SALT='CDG-R112-POSITIONS-2026-V1'
K1=1.2
B=0.75


def make_fts(path:Path, docs:list[tuple[str,str]]):
    db=sqlite3.connect(path)
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('CREATE VIRTUAL TABLE docs USING fts5(body, content="", detail=full, tokenize="unicode61")')
    db.executemany('INSERT INTO docs(rowid,body) VALUES(?,?)',((i,title+'\n'+body) for i,(title,body) in enumerate(docs,1)))
    db.commit()
    return db


def collect_positions(db:sqlite3.Connection, n_docs:int, chosen_documents:int=64):
    """Only a SHA-selected set of documents holds phrase candidate offsets."""
    selected=set(sorted(range(1,n_docs+1),key=lambda d:hashlib.sha256((SALT+'|doc|'+str(d)).encode()).digest())[:chosen_documents])
    samples={d:{} for d in selected}
    db.execute('CREATE VIRTUAL TABLE r112vocab USING fts5vocab(docs,"instance")')
    lengths=[0]*(n_docs+1)
    posting={}
    prevterm=None
    ids=[]
    positions=[]
    lastdoc=0
    total_occ=0
    try:
        for term,doc,offset in db.execute('SELECT term,doc,offset FROM r112vocab ORDER BY term,doc,offset'):
            doc=int(doc);offset=int(offset)
            if not (1<=doc<=n_docs and 0<=offset<(1<<32)):
                raise AssertionError('invalid original FTS5 offset')
            lengths[doc]+=1;total_occ+=1
            if doc in samples:
                if offset in samples[doc]:raise AssertionError('multiple tokens at same position')
                samples[doc][offset]=term
            if term!=prevterm:
                if prevterm is not None:posting[prevterm]=(ids,positions)
                prevterm=term;ids=[];positions=[];lastdoc=0
            if doc!=lastdoc:
                if doc<=lastdoc:raise AssertionError('unsorted docIDs')
                ids.append(doc);positions.append([]);lastdoc=doc
            if positions[-1] and offset<=positions[-1][-1]:raise AssertionError('unsorted token positions')
            positions[-1].append(offset)
        if prevterm is not None:posting[prevterm]=(ids,positions)
    finally:
        db.execute('DROP TABLE r112vocab')
    if not posting or sum(lengths)!=total_occ:raise ValueError('empty corpus or missing occurrences')
    return posting,lengths,samples


def to_positive_gaps(ids):
    prev=0;out=[]
    for v in ids:
        if type(v) is not int or v<=prev:raise ValueError('not increasing positive integer sequence')
        out.append(v-prev);prev=v
    return out


def from_positive_gaps(gaps):
    total=0;out=[]
    for g in gaps:
        if type(g) is not int or g<=0:raise ValueError('nonpositive gap')
        total+=g;out.append(total)
    return out


def positions_to_gaps(groups):
    """Each document's first position is stored plus one; subsequent deltas."""
    out=[]
    for group in groups:
        if not group:raise ValueError('empty occurrence group')
        prev=-1
        for p in group:
            if type(p) is not int or p<=prev:raise ValueError('out of order position')
            out.append(p-prev);prev=p
    return out


def gaps_to_positions(gaps,frequencies):
    if sum(frequencies)!=len(gaps) or any(x<=0 for x in frequencies):raise ValueError('frequency mismatch')
    cursor=0;result=[]
    for freq in frequencies:
        prev=-1;group=[]
        for g in gaps[cursor:cursor+freq]:
            if g<=0:raise ValueError('nonpositive position difference')
            prev+=g;group.append(prev)
        result.append(group);cursor+=freq
    return result


def _encode_by_policy(gaps, family, is_position=False, df=0):
    if family in ATOMIC:
        return TAGS[family],encode(gaps,family)
    if family=='static_hybrid':
        # Corpus-independent rule: pay no multi-bit code header for tiny arrays.
        method='varint' if len(gaps)<(32 if is_position else 4) else 'barm_r'
        return TAGS[method],encode(gaps,method)
    if family=='per_term_oracle':
        sizes=[(len(encode(gaps,c)),TAGS[c],c) for c in ATOMIC]
        _,tag,method=min(sizes)
        return tag,encode(gaps,method)
    raise ValueError('unrecognized codec family')


def pack_term(ids,groups,family):
    if not ids or len(ids)!=len(groups):raise ValueError('posting mismatch')
    dg=to_positive_gaps(ids)
    pg=positions_to_gaps(groups)
    tf=[len(x) for x in groups]
    dtag,docblob=_encode_by_policy(dg,family,df=len(ids))
    ptag,posblob=_encode_by_policy(pg,family,is_position=True,df=len(ids))
    tfblob=encode(tf,'varint')
    return (dtag,ptag,docblob,tfblob,posblob)


def unpack_term(df:int,dtag:int,ptag:int,docblob:bytes,tfblob:bytes,posblob:bytes|None=None):
    if df<=0 or dtag not in REVERSE or ptag not in REVERSE:raise ValueError('bad posting header')
    ids=from_positive_gaps(decode(docblob,REVERSE[dtag]))
    tf=decode(tfblob,'varint')
    if len(ids)!=df or len(tf)!=df or any(f<=0 for f in tf):raise ValueError('doc/TF length mismatch')
    if posblob is None:return ids,tf,None
    pg=decode(posblob,REVERSE[ptag]);groups=gaps_to_positions(pg,tf)
    return ids,tf,groups


def build_store(path:Path, posting:dict, lengths:list[int],family:str):
    if family not in FAMILIES:raise ValueError('bad family')
    db=sqlite3.connect(path)
    try:
        db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL) WITHOUT ROWID')
        db.execute('CREATE TABLE dl(docid INTEGER PRIMARY KEY,length INTEGER NOT NULL CHECK(length>=0))')
        db.execute('CREATE TABLE postings(term TEXT PRIMARY KEY,df INTEGER NOT NULL CHECK(df>0),dtag INTEGER NOT NULL,ptag INTEGER NOT NULL,doc_payload BLOB NOT NULL,tf_payload BLOB NOT NULL,pos_payload BLOB NOT NULL) WITHOUT ROWID')
        db.executemany('INSERT INTO meta VALUES(?,?)', [('num_docs',len(lengths)-1),('num_tokens',sum(lengths))])
        db.executemany('INSERT INTO dl VALUES(?,?)',enumerate(lengths[1:],1))
        sizes=Counter();tags=Counter();start=time.perf_counter()
        for term,(ids,groups) in sorted(posting.items()):
            dtag,ptag,dbits,tbits,pbits=pack_term(ids,groups,family)
            if unpack_term(len(ids),dtag,ptag,dbits,tbits,pbits)!=(ids,[len(x) for x in groups],groups):
                raise AssertionError('lossless stored term mismatch')
            db.execute('INSERT INTO postings VALUES(?,?,?,?,?,?,?)',(term,len(ids),dtag,ptag,dbits,tbits,pbits))
            sizes['doc']+=len(dbits);sizes['tf']+=len(tbits);sizes['pos']+=len(pbits)
            tags[(REVERSE[dtag],REVERSE[ptag])]+=1
        db.commit();db.execute('VACUUM');db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise AssertionError('SQLite corruption')
        physical=path.stat().st_size
        return {'physical_sqlite_bytes':physical,'encoded_doc_bytes':sizes['doc'],
                'encoded_tf_bytes':sizes['tf'],'encoded_position_bytes':sizes['pos'],
                'sqlite_lexicon_and_doclength_overhead_bytes':physical-sum(sizes.values()),
                'per_plane_codec_assignments':{'/'.join(k):v for k,v in tags.items()},
                'build_elapsed_s_exploratory':round(time.perf_counter()-start,3)}
    finally:db.close()


def fetch(db,term,positions=False):
    columns='df,dtag,ptag,doc_payload,tf_payload'+(',pos_payload' if positions else '')
    row=db.execute('SELECT '+columns+' FROM postings WHERE term=?',(term,)).fetchone()
    if row is None:return [],[],([] if positions else None)
    if positions:return unpack_term(*row)
    return unpack_term(*row,None)


def score(docid,terms,tf_map,dfs,length,n_docs,avglen):
    s=0.0
    for term in terms:
        frequency=tf_map[term].get(docid,0)
        if not frequency:continue
        df=dfs[term]
        idf=max(math.log((n_docs-df+0.5)/(df+0.5)),1e-6)
        s+=idf*(frequency*(K1+1))/(frequency+K1*(1-B+B*length/avglen))
    return -s


def bm25_query(db,terms,n_docs,avglen,k=10):
    fetched={t:fetch(db,t,False) for t in terms}
    if not fetched or any(not v[0] for v in fetched.values()):return []
    common=set.intersection(*(set(v[0]) for v in fetched.values()))
    if not common:return []
    tf_map={t:dict(zip(v[0],v[1])) for t,v in fetched.items()}
    dfs={t:len(v[0]) for t,v in fetched.items()}
    doclens=dict(db.execute('SELECT docid,length FROM dl WHERE docid IN ('+','.join('?'*len(common))+')',tuple(sorted(common))))
    return sorted(((d,score(d,terms,tf_map,dfs,doclens[d],n_docs,avglen)) for d in common),key=lambda x:(x[1],x[0]))[:k]


def phrase_match(db,terms):
    if len(terms)!=2:raise ValueError('only exact ordered bigrams supported')
    a,b=terms
    ids_a,_,pa=fetch(db,a,True)
    ids_b,_,pb=fetch(db,b,True)
    if not ids_a or not ids_b:return []
    ma=dict(zip(ids_a,pa));mb=dict(zip(ids_b,pb));out=[]
    for docid in sorted(ma.keys()&mb.keys()):
        b_positions=set(mb[docid])
        if any(p+1 in b_positions for p in ma[docid]):out.append(docid)
    return out


def quote(term:str):
    return '"'+term.replace('"','""')+'"'


def plan(posting,n_docs,samples,max_single=80,max_pairs=32,max_phrases=32):
    vocab=list(posting)
    eligible=sorted(vocab,key=lambda t:(hashlib.sha256((SALT+'|single|'+t).encode()).digest(),t))
    # Ensure narrow and wide df are represented without content-label tuning.
    bins=[(1,1,10),(2,3,10),(4,31,28),(32,256,24),(257,n_docs,8)]
    singles=[]
    for lo,hi,count in bins:
        cohort=[t for t in eligible if lo<=len(posting[t][0])<=hi]
        singles.extend((t,) for t in cohort[:count])
    mid=[t for t in eligible if 4<=len(posting[t][0])<=256]
    pairs=[(mid[i],mid[i+1]) for i in range(0,min(len(mid),2*max_pairs)-1,2)]
    phrases=set()
    for offsets in samples.values():
        for pos,term in offsets.items():
            other=offsets.get(pos+1)
            if other and term!=other:
                phrases.add((term,other))
    phrase_plan=sorted(phrases,key=lambda pair:(hashlib.sha256((SALT+'|phrase|'+pair[0]+'|'+pair[1]).encode()).digest(),pair))[:max_phrases]
    if not singles or not phrase_plan:raise AssertionError('benchmark query plan empty')
    return singles+pairs,phrase_plan


def verify(store,native,queries,phrase_queries,lengths):
    N=len(lengths)-1
    avg=sum(lengths)/N
    checked=0;checked_ranked=0;maxerror=0.0;ties=0
    for q in queries:
        sqlquery=' AND '.join(quote(t) for t in q)
        original=[(int(r[0]),float(r[1])) for r in native.execute('SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs),rowid LIMIT 10',(sqlquery,))]
        actual=bm25_query(store,q,N,avg)
        oa=dict(original);aa=dict(actual)
        if oa.keys()!=aa.keys():raise AssertionError('BM25 rowid mismatch')
        for d in oa:
            delta=abs(oa[d]-aa[d]);maxerror=max(delta,maxerror)
            if delta>1e-12:raise AssertionError('BM25 score delta >1e-12')
        if [x[0] for x in original]!=[x[0] for x in actual]:ties+=1
        checked+=1;checked_ranked+=len(original)
    phrase_hits=0
    for q in phrase_queries:
        native_ids=[int(x[0]) for x in native.execute('SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY rowid',(quote(' '.join(q)),))]
        ours=phrase_match(store,q)
        if ours!=native_ids:
            raise AssertionError('exact phrase query mismatch for SHA '+hashlib.sha256((' '.join(q)).encode()).hexdigest())
        phrase_hits+=len(native_ids)
    return {'bm25_queries':checked,'bm25_ranked_rows':checked_ranked,'max_bm25_score_abs_error':maxerror,
            'bm25_rank_tie_or_float_order_queries':ties,'exact_bigram_phrase_queries':len(phrase_queries),
            'original_phrase_hits_checked':phrase_hits,'all_matched':True}


def run(dataset,docs=None,source_meta=None):
    if docs is None:docs,meta=docs_from_release(dataset)
    else:meta=source_meta or {'dataset':'synthetic development fixture'}
    if not docs:raise ValueError('empty corpus')
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='cdg-r112-') as folder:
        base=Path(folder)
        native=make_fts(base/'native.sqlite',docs)
        try:
            posting,lengths,samples=collect_positions(native,len(docs))
            native.commit();native.execute('VACUUM');native.commit()
            native_bytes=(base/'native.sqlite').stat().st_size
            queries,phrases=plan(posting,len(docs),samples)
            result={}
            for family in FAMILIES:
                path=base/(family+'.sqlite')
                met=build_store(path,posting,lengths,family)
                with closing(sqlite3.connect(path)) as store:
                    met['checks']=verify(store,native,queries,phrases,lengths)
                result[family]=met
        finally:native.close()
    return {'round':112,'dataset':dataset,'source':meta,'docs':len(docs),
            'full_vocabulary_terms':len(posting),
            'full_distinct_docid_postings':sum(len(ids) for ids,_ in posting.values()),
            'full_token_occurrences':sum(lengths),
            'original_contentless_native_fts5_detail_full_bytes':native_bytes,
            'query_salt':SALT,'bm25_query_count':len(queries),'phrase_query_count':len(phrases),
            'codecs':result,'wall_seconds':round(time.perf_counter()-started,3),
            'caveats':[
                'All methods encode same complete original FTS5 one-column token positions and frequencies, but external store does not implement arbitrary FTS5 syntax or native search engine',
                'Native FTS5 detail=full compared as positional feature reference, not controlled implementation performance comparator',
                'Position BLOB is stored separately: non-phrase queries avoid Python position decoding, not necessarily physical SQLite page reads',
                'Python codec controls are not production SIMD implementations; no CPU or SSD throughput superiority claimed',
                'Per-term oracle chooses best codec after seeing test list and is not a deployable learned selection policy',
                'Full original corpus SHA locks inherited from R83/R96; raw source text and query passages are never committed',
                'Corpus is original QASPER DEV or SciFact only; no user query timing traces or generated answers',
                'Not a test or consequence of RH/GRH',
            ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',choices=['qasper','scifact'],required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args();r=run(args.dataset)
    Path(args.out).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'dataset':args.dataset,'native_bytes':r['original_contentless_native_fts5_detail_full_bytes'],
                      'terms':r['full_vocabulary_terms'],'positions':r['full_token_occurrences'],
                      'stores':{k:v['physical_sqlite_bytes'] for k,v in r['codecs'].items()}},indent=2))
if __name__=='__main__':main()