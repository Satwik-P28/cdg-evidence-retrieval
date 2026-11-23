#!/usr/bin/env python3
"""R110: frozen original-source, identical-wire decoder-only CPU comparison.

This is a repeated warm Python microbenchmark on CI and not production-native
SIMD, randomized machine-independent latency, or physical disk I/O.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from contextlib import closing

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-108'))
from authentic_postings import docs_from_release, sample_postings, SAMPLE_SALT
from codec_controls import encode, decode
from fast_barm import fast_decode_series

METHODS=('barm_legacy','barm_fast','varint','ef_partitioned','streamvbyte')
REPS=7
RANDOM_SEED=20261123


def run(dataset, docs=None):
    if docs is None:docs,meta=docs_from_release(dataset)
    else:meta={'dataset':'synthetic fixture, not original upstream'}
    with tempfile.TemporaryDirectory(prefix='cdg-r110-') as d:
        with closing(sqlite3.connect(Path(d)/'fts.sqlite')) as db:
            db.execute('CREATE VIRTUAL TABLE docs USING fts5(title,body,content="")')
            db.executemany('INSERT INTO docs(rowid,title,body) VALUES(?,?,?)',
                           ((i,a,b) for i,(a,b) in enumerate(docs,1)))
            db.commit()
            selected,eligible=sample_postings(db,dataset)
    lists=sorted((t,ids) for items in selected.values() for t,ids in items)
    def gaps_for(ids):
        prev=0;g=[]
        for v in ids:g.append(v-prev);prev=v
        return g
    gaps=[gaps_for(ids) for _,ids in lists]
    mapping={}
    for method in METHODS:
        fmt={'barm_legacy':'barm_r','barm_fast':'barm_r'}.get(method,method)
        mapping[method]=[encode(g,fmt) for g in gaps]
    if mapping['barm_fast']!=mapping['barm_legacy']:
        raise AssertionError('fast decoder must consume byte-identical source BARM')
    reference=HERE.parent/'round-108'/('results-'+dataset+'.json')
    if docs is None and reference.exists():
        old=json.loads(reference.read_text())
        if len(lists)!=old['sampled_terms'] or sum(map(len,gaps))!=old['sampled_posting_entries']:
            raise AssertionError('original corpus selected terms changed')
        if sum(len(v) for v in mapping['barm_fast'])!=old['sizes_bytes']['barm_r']:
            raise AssertionError('BARM wire accounting differs from R108')
    def decode_method(method,blob):
        if method=='barm_fast':return fast_decode_series(blob)
        codec={'barm_legacy':'barm_r'}.get(method,method)
        return decode(blob,codec)
    for method in METHODS:
        for expected,blob in zip(gaps,mapping[method]):
            if decode_method(method,blob)!=expected:
                raise AssertionError(f'lossless compatibility failure {method}')
    trial_times={method:[] for method in METHODS}
    for rep in range(REPS):
        order=list(METHODS)
        random.Random(RANDOM_SEED+rep).shuffle(order)
        for method in order:
            start=time.perf_counter_ns()
            n_values=0
            for blob in mapping[method]:
                n_values+=len(decode_method(method,blob))
            elapsed=(time.perf_counter_ns()-start)/1e6
            if n_values!=sum(map(len,gaps)):
                raise AssertionError('benchmark decoded output length mismatch')
            trial_times[method].append(round(elapsed,5))
    medians={k:round(statistics.median(v),5) for k,v in trial_times.items()}
    return {
        'round':110,'dataset':dataset,'source':meta,'original_documents':len(docs),
        'sampled_terms':len(lists),'sampled_posting_entries':sum(map(len,gaps)),
        'original_R108_sampling_salt':SAMPLE_SALT,
        'wire_identical_barm_bytes':sum(map(len,mapping['barm_fast'])),
        'decode_warm_batch_ms_trials':trial_times,
        'decode_warm_median_batch_ms':medians,
        'relative_fast_vs_legacy_wall_median':round(medians['barm_legacy']/medians['barm_fast'],5),
        'relative_fast_vs_varint_wall_median':round(medians['barm_fast']/medians['varint'],5),
        'repetitions':REPS,
        'randomized_method_order_seed':RANDOM_SEED,
        'notes':[
            'Same BARM encoded bytes for legacy and optimized decoder; no source data or QA labels in results',
            'All five methods decoded every original selected list exactly before timing',
            'Warm single-runner Python batch decode; no CPU affinity, native SIMD, cache flush, hardware repeats or SSD reads',
            'Codecs have different data-dependent list decode complexity, and source selection is stratified rather than a natural workload probability',
            'No full native FTS5 replacement or hallucination result',
        ],
    }


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['qasper','scifact'],required=True);p.add_argument('--out',required=True)
    a=p.parse_args();result=run(a.dataset)
    Path(a.out).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'dataset':a.dataset,'terms':result['sampled_terms'], 'postings':result['sampled_posting_entries'],
        'median_ms':result['decode_warm_median_batch_ms']},indent=2))
if __name__=='__main__':main()