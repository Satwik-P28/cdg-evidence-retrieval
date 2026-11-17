#!/usr/bin/env python3
"""Round 52: eliminate per-query O(source-lines) span map construction.

Compare whole-generation scan with indexed point lookup and one batched row-ID
lookup. Same historical FTS LRU, exact ranking/phrase responses and pinned
12-revision README source; measured CPU and in-memory DB cost only.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import statistics
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
R51=ROOT.parent/'round-51'/'cache_lab.py'

def load():
    spec=importlib.util.spec_from_file_location('cdg_r51_r52',R51)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(m)
    return m


def bench(count=120):
    original=load()
    r50=original.dependencies()
    sources=r50.versions()
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        thin=r50.Tiered(root/'thin.db',sources,'tiered_none')
        full=r50.Tiered(root/'full.db',sources,'full')
        try:
            output=[]
            for trace in ('hot','uniform','recent'):
                tasks=original.make_queries(count,trace,thin.latest)
                reference=[full.lookup(g,q,ranked,3 if ranked else None)
                           for g,q,ranked in tasks]
                for capacity in (1,2,4,12):
                    for strategy in ('scan','point','batch'):
                        cache=original.HistoricIndexCache(thin,capacity,strategy)
                        times=[]
                        try:
                            for (generation,term,ranked),correct in zip(tasks,reference):
                                start=time.perf_counter_ns()
                                got=cache.search(generation,term,ranked,3 if ranked else None)
                                times.append((time.perf_counter_ns()-start)/1000)
                                if got!=correct:
                                    raise AssertionError(f'{strategy} changed ranking or phrase result')
                            output.append({
                                'trace':trace,'capacity':capacity,'span_lookup':strategy,
                                'queries':len(tasks),'cache_hits':cache.hits,
                                'cache_misses':cache.misses,
                                'query_p50_us':round(statistics.median(times),3),
                                'query_p95_us':round(sorted(times)[int(.95*(len(times)-1))],3),
                                'sum_query_ms':round(sum(times)/1000,3),
                                'peak_cache_sqlite_pages_bytes':cache.peak_pages,
                                'disk_index_bytes':thin.size()})
                        finally:
                            cache.close()
            return {'version_count':len(sources),
                    'rows':output,'limitations':[
                        'same single 12-revision README and synthetic query distributions',
                        'point/batch use source row ID B-tree and are conventional SQL optimizations',
                        'run order and Python/SQLite warm cache can affect microseconds',
                        'peak cache SQLite page bytes excludes Python object/process RSS',
                        'no source entailment, production I/O, or workload-tail robustness']}
        finally:
            thin.close();full.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    a=p.parse_args()
    out=bench()
    print('ROUND52',json.dumps(out,sort_keys=True))
    Path(a.out).write_text(json.dumps(out,indent=2)+'\n')


if __name__=='__main__':
    main()
