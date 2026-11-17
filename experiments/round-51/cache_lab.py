#!/usr/bin/env python3
"""Round 51: LRU cache vs historical FTS5 index recomputation.

Uses actual 12-version uv README, synthetic query frequency traces, validates
every cached result against full-index BM25 order and exact phrase result set.
Reports current Python in-memory SQLite page metrics, not process RSS.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import random
import sqlite3
import statistics
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
R50=ROOT.parent/'round-50'/'tiered_fts.py'
KEYWORDS=('installation','dependencies','python','uv','tools','workspace',
          'version','license','release','cache')
PHRASES=('"python package"','"install uv"','"package manager"')


def dependencies():
    spec=importlib.util.spec_from_file_location('cdg_round50_r51',R50)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(m)
    return m


class HistoricIndexCache:
    def __init__(self,engine,capacity):
        self.engine=engine
        self.capacity=capacity
        self.entries=OrderedDict()
        self.hits=0
        self.misses=0
        self.peak_pages=0

    def _make_index(self,g):
        c=sqlite3.connect(':memory:')
        c.execute('CREATE VIRTUAL TABLE docs USING fts5(text)')
        for rid,start,end in self.engine.db.execute(
                'SELECT rid,start,end FROM spans WHERE gen=? ORDER BY rid',(g,)):
            c.execute('INSERT INTO docs(rowid,text) VALUES (?,?)',
                      (rid,self.engine.sources[g][start:end].decode('utf8')))
        c.commit()
        return c

    def _bytes(self):
        return sum(c.execute('PRAGMA page_size').fetchone()[0] *
                   c.execute('PRAGMA page_count').fetchone()[0]
                   for c in self.entries.values())

    def search(self,g,term,ranked=False,limit=None):
        if g==self.engine.latest or (not ranked and '"' not in term):
            return self.engine.lookup(g,term,ranked,limit)
        if g in self.entries:
            self.hits+=1
            conn=self.entries.pop(g)
            self.entries[g]=conn
        else:
            self.misses+=1
            conn=self._make_index(g)
            if self.capacity:
                self.entries[g]=conn
                if len(self.entries)>self.capacity:
                    _,evicted=self.entries.popitem(last=False)
                    evicted.close()
                self.peak_pages=max(self.peak_pages,self._bytes())
        order='bm25(docs),docs.rowid' if ranked else 'docs.rowid'
        sql=f'SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY {order}'
        params=[term]
        if limit is not None:
            sql+=' LIMIT ?';params.append(limit)
        ids=[r[0] for r in conn.execute(sql,params)]
        if not self.capacity:
            conn.close()
        lookup=dict((rid,(start,end)) for rid,start,end in self.engine.db.execute(
            'SELECT rid,start,end FROM spans WHERE gen=?',(g,)))
        return [(rid,*lookup[rid]) for rid in ids]

    def close(self):
        for entry in self.entries.values():entry.close()
        self.entries.clear()


def make_queries(count,distribution,latest,seed=20261117):
    rng=random.Random(seed)
    queries=[]
    for i in range(count):
        if distribution=='hot':
            gen=0 if rng.random()<.8 else rng.randrange(latest)
        elif distribution=='uniform':
            gen=rng.randrange(latest)
        elif distribution=='recent':
            gen=latest if rng.random()<.6 else latest-1-rng.randrange(0,min(3,latest))
        else:
            raise ValueError(distribution)
        if i%3==0:
            query=PHRASES[i%len(PHRASES)]
            ranked=False
        else:
            query=KEYWORDS[rng.randrange(len(KEYWORDS))]
            ranked=True
        queries.append((gen,query,ranked))
    return queries


def bench(sources,counts=90):
    d=dependencies()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        full=d.Tiered(root/'full.sqlite',sources,'full')
        thin=d.Tiered(root/'thin.sqlite',sources,'tiered_none')
        entries=[]
        try:
            for distribution in ('hot','uniform','recent'):
                queries=make_queries(counts,distribution,thin.latest)
                for capacity in (0,1,2,4,12):
                    cache=HistoricIndexCache(thin,capacity)
                    latency=[]
                    try:
                        for generation,term,ranked in queries:
                            begin=time.perf_counter_ns()
                            actual=cache.search(generation,term,ranked,3 if ranked else None)
                            latency.append((time.perf_counter_ns()-begin)/1000)
                            expected=full.lookup(generation,term,ranked,3 if ranked else None)
                            if actual!=expected:
                                raise AssertionError(
                                    f'retrieval mismatch dist={distribution} capacity={capacity} '
                                    f'version={generation}, query={term}')
                        entries.append({
                            'distribution':distribution,'capacity':capacity,
                            'queries':len(queries),'cache_hits':cache.hits,
                            'cache_misses':cache.misses,
                            'median_query_us':round(statistics.median(latency),3),
                            'p95_query_us':round(sorted(latency)[int(.95*(len(latency)-1))],3),
                            'aggregate_query_ms':round(sum(latency)/1000,3),
                            'peak_sqlite_cache_page_bytes':cache.peak_pages,
                            'persistent_index_bytes':thin.size(),
                            'effective_index_plus_peak_cache_bytes':thin.size()+cache.peak_pages})
                    finally:
                        cache.close()
                times=[]
                for generation,term,ranked in queries:
                    begin=time.perf_counter_ns()
                    full.lookup(generation,term,ranked,3 if ranked else None)
                    times.append((time.perf_counter_ns()-begin)/1000)
                entries.append({
                    'distribution':distribution,'capacity':'all_full',
                    'queries':len(queries),'cache_hits':None,'cache_misses':None,
                    'median_query_us':round(statistics.median(times),3),
                    'p95_query_us':round(sorted(times)[int(.95*(len(times)-1))],3),
                    'aggregate_query_ms':round(sum(times)/1000,3),
                    'peak_sqlite_cache_page_bytes':0,
                    'persistent_index_bytes':full.size(),
                    'effective_index_plus_peak_cache_bytes':full.size()})
            return {'source_versions':len(sources),
                    'rows':entries,
                    'limitations':['trace probabilities chosen artificially, not measured user workload',
                                   'cached SQLite pages not equal to process RSS',
                                   'single Python-process warm OS cache',
                                   'cache counts all pages in SQLite in-memory DB only',
                                   'no concurrent writers, crash recovery, or end-to-end factual QA',
                                   'full BM25 parity is only verified for these generated queries']}
        finally:
            full.close();thin.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(ROOT/'results.json'))
    p=parser.parse_args()
    results=bench(dependencies().versions())
    print('ROUND51',json.dumps(results,sort_keys=True))
    Path(p.out).write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    main()
