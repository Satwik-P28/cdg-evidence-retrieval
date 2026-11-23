#!/usr/bin/env python3
"""R108: real original-source QASPER/SciFact -> SQLite FTS5 logical docID gaps.

No native SQLite index encoding is replaced. Source tarballs are fetched by
existing SHA-locked R83/R96 readers and original source text is never emitted.
Term selection is hash-stable, independent of codec sizes, and df-stratified.
All compared lists are represented by exact independently decodable codecs.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
EXPERIMENTS=HERE.parent
for dep in ('round-83','round-96'):
    sys.path.insert(0,str(EXPERIMENTS/dep))
from codec_controls import CODECS,encode,decode

BANDS = {
  'df1': (1,1,350),
  'df2_3': (2,3,400),
  'df4_31': (4,31,650),
  'df32_127': (32,127,350),
  'df128_plus': (128,10**9,200),
}
SAMPLE_SALT='CDG-R108-SOURCE-POSTINGS-V1'


def docs_from_release(dataset: str):
    if dataset=='qasper':
        from qasper_source_probe import fetch,article_paragraphs,EXPECTED_SHA,EXPECTED_ARCHIVE_BYTES
        pairs=fetch()
        papers=pairs['dev']['data']
        rows=[]
        for paper_id in sorted(papers):
            for para in article_paragraphs(papers[paper_id]):
                rows.append((para['section_title'],para['text']))
        if len(rows)!=13266:
            raise AssertionError(f'QASPER DEV paragraph count unexpectedly changed: {len(rows)}')
        return rows,{'dataset':'QASPER v0.3 DEV original paragraphs',
            'official_archive_sha256':EXPECTED_SHA,'archive_bytes':EXPECTED_ARCHIVE_BYTES,
            'source_member_sha256':pairs['dev']['sha256'],
            'num_papers':len(papers)}
    if dataset=='scifact':
        from scifact_data_probe import fetch,parse,digests,LOCK,UPSTREAM
        archive,members=fetch()
        corpus,_,schema=parse(members)
        rows=[]
        for doc in corpus:
            rows.append((doc['title'],' '.join(doc['abstract'])))
        lock=json.loads(LOCK.read_text())
        if digests(archive)['sha256']!=lock['archive_sha256']:
            raise AssertionError('SciFact upstream changed')
        return rows,{'dataset':'SciFact official original corpus',
            'official_archive_sha256':lock['archive_sha256'],
            'source_member_sha256':digests(members['data/corpus.jsonl'])['sha256'],
            'num_corpus_docs':schema['corpus_docs'],
            'source_url':UPSTREAM}
    raise ValueError('unknown dataset '+dataset)


def _band_name(df:int):
    for key,(low,high,_) in BANDS.items():
        if low<=df<=high:return key
    raise AssertionError('invalid df')


def sample_postings(db:sqlite3.Connection, dataset:str, bands=BANDS):
    """Keep hash-minimal terms per df band; no ranking labels or codec cost used."""
    db.execute('CREATE VIRTUAL TABLE vocab USING fts5vocab(docs, "instance")')
    pools={name:[] for name in bands}
    counts=defaultdict(int)
    current=None;doc_ids=[];last=-1
    def ingest(term,ids):
        if term is None:return
        band=_band_name(len(ids))
        if band not in bands:return
        counts[band]+=1
        k=bands[band][2]
        h=int.from_bytes(hashlib.sha256((SAMPLE_SALT+'|'+dataset+'|'+term).encode()).digest()[:8],'big')
        item=(-h,term,ids)
        if len(pools[band])<k:heapq.heappush(pools[band],item)
        elif h< -pools[band][0][0]:heapq.heapreplace(pools[band],item)
    # fts5vocab(instance) returns a (term, rowid) for each term instance.
    # The same term repeated inside a document is collapsed to a posting.
    for term,rid in db.execute('SELECT term,doc FROM vocab ORDER BY term,doc'):
        rid=int(rid)
        if term!=current:
            ingest(current,doc_ids)
            current=term;doc_ids=[];last=-1
        if rid!=last:
            if rid<=last:raise AssertionError('non-increasing SQLite postings')
            doc_ids.append(rid);last=rid
    ingest(current,doc_ids)
    grouped={name:sorted([(term,ids) for _,term,ids in heap]) for name,heap in pools.items()}
    db.execute('DROP TABLE vocab')
    return grouped,dict(counts)


def compare_lists(grouped):
    summary={}
    for band,items in grouped.items():
        totals={name:0 for name in CODECS}
        best={name:0 for name in CODECS}
        postings=0
        for term,doc_ids in items:
            prev=0;gaps=[]
            for v in doc_ids:
                if v<=prev:raise AssertionError('doc ID out of order')
                gaps.append(v-prev);prev=v
            postings+=len(gaps)
            sizes={}
            for name in CODECS:
                blob=encode(gaps,name)
                if decode(blob,name)!=gaps:
                    raise AssertionError(f'{name} round-trip failure for term sha {hashlib.sha256(term.encode()).hexdigest()}')
                sizes[name]=len(blob)
                totals[name]+=len(blob)
            best_size=min(sizes.values())
            for name,sz in sizes.items():
                if sz==best_size:best[name]+=1
        summary[band]={
            'sampled_terms':len(items),'posting_entries':postings,
            'sizes_bytes':totals,
            'bits_per_posting':{c:round(8*v/postings,5) if postings else None for c,v in totals.items()},
            'ties_included_number_lists_smallest':best,
            'selected_term_sha256':hashlib.sha256('\n'.join(t for t,_ in items).encode()).hexdigest(),
        }
    return summary


def run(dataset:str,docs=None,external_meta=None,bands=BANDS):
    if docs is None:docs,metadata=docs_from_release(dataset)
    else:metadata=external_meta or {'dataset':'synthetic fixture; NOT authentic dataset'}
    if not docs:raise ValueError('empty corpus')
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='cdg-r108-') as folder:
        path=Path(folder)/'index.sqlite'
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE VIRTUAL TABLE docs USING fts5(title,body, content='')")
            db.executemany('INSERT INTO docs(rowid,title,body) VALUES (?,?,?)',
                           ((i,a,b) for i,(a,b) in enumerate(docs,1)))
            db.commit()
            groups,available=sample_postings(db,dataset,bands)
            db.commit()
            db.execute('VACUUM')
            db.commit()
            sqlite_bytes=path.stat().st_size
            summaries=compare_lists(groups)
    merged={c:sum(b['sizes_bytes'][c] for b in summaries.values()) for c in CODECS}
    result={
        'round':108,'dataset':dataset,'source':metadata,
        'num_documents':len(docs),
        'original_contentless_fts_sqlite_bytes':sqlite_bytes,
        'selection':{'method':'SHA256-minimal terms within fixed doc-frequency strata',
            'salt':SAMPLE_SALT,'band_limits':{k:list(v) for k,v in bands.items()},
            'total_eligible_terms_by_band':dict(available)},
        'sampled_posting_entries':sum(s['posting_entries'] for s in summaries.values()),
        'sampled_terms':sum(s['sampled_terms'] for s in summaries.values()),
        'sizes_bytes':merged,'by_df':summaries,
        'wall_seconds_pipeline':round(time.perf_counter()-start,2),
        'limitations':[
            'Logical gap streams extracted via SQLite fts5vocab(instance); SQLite native segment encoding not replaced',
            'Python scalar reference codecs; no SIMD throughput or random-access latency claims',
            'Adaptive EF partition DP can inspect entire input list; tuned reference, not production PEF',
            'Total SQLite index bytes refer to existing unchanged FTS5, not a codec-substituted database',
            'Corpus data streamed from locked official upstream; only aggregate metrics/hashes persisted',
            'Term sampling is stratified, not representative of unsampled overall index bytes',
            'No semantic retrieval improvement or RAG answer-level experiment',
        ],
    }
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',choices=['qasper','scifact'],required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    res=run(args.dataset)
    Path(args.out).write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:res[k] for k in ('dataset','num_documents','sampled_terms','sampled_posting_entries','sizes_bytes','wall_seconds_pipeline')},indent=2))

if __name__=='__main__':main()