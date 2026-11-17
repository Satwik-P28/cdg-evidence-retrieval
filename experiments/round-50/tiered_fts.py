#!/usr/bin/env python3
"""Round 50: two-tier historical SQLite FTS5 posting density.

Keep the current generation fully ranked and phrase-searchable; compress older
posting detail and reconstruct an old-generation full index only on demand.
This is a classical, measured policy, not a novel retrieval algorithm.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
R46=ROOT.parent/'round-46'/'version_chunks.py'
TERMS=('installation','dependencies','python','uv','tools','workspace',
       'version','license','release','cache')
PHRASES=('"python package"','"install uv"','"package manager"')
MODES={
    'full':"detail=full",
    'tiered_none':"detail=none,columnsize=0",
    'tiered_column':"detail=column,columnsize=0",
    'tiered_full_nosize':"detail=full,columnsize=0",
}


def versions():
    spec=importlib.util.spec_from_file_location('cdg_r46_r50',R46)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.load_source()


class Tiered:
    def __init__(self,path,sources,mode='full'):
        if mode not in MODES:
            raise ValueError(mode)
        self.path=Path(path)
        self.mode=mode
        self.sources=sources
        self.latest=len(sources)-1
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE spans(rid INTEGER PRIMARY KEY,gen INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX spans_gen ON spans(gen)')
        if mode=='full':
            self.db.execute("CREATE VIRTUAL TABLE all_docs USING fts5(text,content='',detail=full)")
        else:
            self.db.execute("CREATE VIRTUAL TABLE current_docs USING fts5(text,content='',detail=full)")
            self.db.execute("CREATE VIRTUAL TABLE old_docs USING fts5(text,content='',"+MODES[mode]+")")
        for g,data in enumerate(sources):
            pos=0
            for line in data.splitlines(keepends=True):
                end=pos+len(line)
                text=line.decode('utf8')
                if text.strip():
                    rid=self.db.execute('INSERT INTO spans(gen,start,end) VALUES(?,?,?)',(g,pos,end)).lastrowid
                    table=('all_docs' if mode=='full' else
                           'current_docs' if g==self.latest else 'old_docs')
                    self.db.execute(f'INSERT INTO {table}(rowid,text) VALUES(?,?)',(rid,text))
                pos=end
            if pos!=len(data):raise AssertionError('byte offsets wrong')
        self.db.commit()
        self.db.execute('VACUUM')
        self.db.commit()

    def _table(self,g):
        return 'all_docs' if self.mode=='full' else ('current_docs' if g==self.latest else 'old_docs')

    def lookup(self,g,query,ranked=False,limit=None):
        table=self._table(g)
        order=f'bm25({table}),spans.rid' if ranked else 'spans.rid'
        sql=(f'SELECT spans.rid,spans.start,spans.end FROM {table} '
             f'JOIN spans ON spans.rid={table}.rowid '
             f'WHERE {table} MATCH ? AND spans.gen=? ORDER BY {order}')
        params=[query,g]
        if limit is not None:
            sql+=' LIMIT ?'
            params.append(limit)
        return self.db.execute(sql,params).fetchall()

    def fallback(self,g,query,ranked=False,limit=None):
        """Charge all work of indexing one old source in memory for phrase/ranking."""
        c=sqlite3.connect(':memory:')
        try:
            c.execute('CREATE VIRTUAL TABLE tmp USING fts5(text)')
            for rid,lo,hi in self.db.execute(
                    'SELECT rid,start,end FROM spans WHERE gen=? ORDER BY rid',(g,)):
                text=self.sources[g][lo:hi].decode('utf8')
                c.execute('INSERT INTO tmp(rowid,text) VALUES(?,?)',(rid,text))
            order='bm25(tmp),tmp.rowid' if ranked else 'tmp.rowid'
            q=f'SELECT rowid FROM tmp WHERE tmp MATCH ? ORDER BY {order}'
            params=[query]
            if limit is not None:
                q+=' LIMIT ?';params.append(limit)
            ids=[r[0] for r in c.execute(q,params)]
            if not ids:return []
            spans={rid:(start,end) for rid,start,end in
                   self.db.execute('SELECT rid,start,end FROM spans WHERE gen=?',(g,))}
            return [(rid,*spans[rid]) for rid in ids]
        finally:
            c.close()

    def guarded(self,g,query,ranked=False,limit=None):
        if self.mode!='full' and g!=self.latest and (ranked or '"' in query):
            return self.fallback(g,query,ranked,limit)
        return self.lookup(g,query,ranked,limit)

    def size(self):
        return self.path.stat().st_size

    def close(self):
        self.db.close()


def benchmark(sources):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        engines={name:Tiered(root/f'{name}.sqlite',sources,name) for name in MODES}
        full=engines['full']
        out={}
        try:
            for name,engine in engines.items():
                kw_times=[];rank_times=[];phrase_times=[]
                kw_ok=0;rank_ok=0;phrase_ok=0
                qcounts={'keyword':0,'rank':0,'phrase':0}
                for g in range(len(sources)):
                    for word in TERMS:
                        start=time.perf_counter_ns()
                        matched=engine.guarded(g,word)
                        kw_times.append((time.perf_counter_ns()-start)/1e3)
                        expected=full.lookup(g,word)
                        if matched!=expected:
                            raise AssertionError(f'keyword mismatch {name}:{g}:{word}')
                        kw_ok+=1;qcounts['keyword']+=1
                        start=time.perf_counter_ns()
                        ranked=engine.guarded(g,word,ranked=True,limit=3)
                        rank_times.append((time.perf_counter_ns()-start)/1e3)
                        expected_rank=full.lookup(g,word,ranked=True,limit=3)
                        if ranked!=expected_rank:
                            raise AssertionError(f'BM25 fallback mismatch {name}:{g}:{word}')
                        rank_ok+=1;qcounts['rank']+=1
                    for phrase in PHRASES:
                        start=time.perf_counter_ns()
                        matched=engine.guarded(g,phrase)
                        phrase_times.append((time.perf_counter_ns()-start)/1e3)
                        expected=full.lookup(g,phrase)
                        if matched!=expected:
                            raise AssertionError(f'phrase fallback mismatch {name}:{g}:{phrase}')
                        phrase_ok+=1;qcounts['phrase']+=1
                out[name]={
                    'index_bytes':engine.size(),
                    'keyword_exact_parity':kw_ok,
                    'ranked_exact_parity':rank_ok,
                    'phrase_exact_parity':phrase_ok,
                    'median_keyword_us':round(statistics.median(kw_times),3),
                    'median_ranked_us':round(statistics.median(rank_times),3),
                    'median_phrase_us':round(statistics.median(phrase_times),3),
                    'comparisons':qcounts}
            return {'versions':len(sources),'results':out,
                    'limits':['One pinned README history with same-topic keyword/phrase queries',
                              'Uncached historical ranked and phrase fallback rebuilds full old index every request',
                              'All timings are warm in-memory and SQLite CPU timings',
                              'Indexed source text is duplicated transiently during fallbacks',
                              'No end-to-end QA, robust query distribution, or long-lived cache policy']}
        finally:
            for engine in engines.values():
                engine.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    a=p.parse_args()
    result=benchmark(versions())
    print('ROUND50',json.dumps(result,sort_keys=True))
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
