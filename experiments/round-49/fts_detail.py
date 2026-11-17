#!/usr/bin/env python3
"""Round 49: FTS5 posting-detail compression vs keyword/phrase semantics.

Historical 12-version README indexing. Tests index-size savings, exact keyword
row parity, BM25 ranking differences, and phrase support. This is not semantic QA.
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

def load_versions():
    spec=importlib.util.spec_from_file_location('cdg_round46_r49',R46)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_source()

CONFIGS={
    'full':"fts5(body,content='',detail=full)",
    'full_no_columnsize':"fts5(body,content='',detail=full,columnsize=0)",
    'column':"fts5(body,content='',detail=column)",
    'column_no_columnsize':"fts5(body,content='',detail=column,columnsize=0)",
    'none':"fts5(body,content='',detail=none)",
    'none_no_columnsize':"fts5(body,content='',detail=none,columnsize=0)",
}
TERMS=('installation','dependencies','python','uv','tools',
       'workspace','version','license','release','cache')
PHRASES=('"python package"','"install uv"','"package manager"')


class Index:
    def __init__(self,path,versions,config):
        self.path=path
        self.versions=versions
        self.config=config
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA page_size=4096')
        self.db.execute('CREATE TABLE spans (rid INTEGER PRIMARY KEY,generation INTEGER NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX spans_generation_idx ON spans(generation)')
        self.db.execute('CREATE VIRTUAL TABLE fts USING '+CONFIGS[config])
        self.rows=0
        for gen,source in enumerate(versions):
            offset=0
            for line in source.splitlines(keepends=True):
                stop=offset+len(line)
                text=line.decode('utf8')
                if text.strip():
                    row=self.db.execute('INSERT INTO spans(generation,start,end) VALUES(?,?,?)',
                                        (gen,offset,stop)).lastrowid
                    self.db.execute('INSERT INTO fts(rowid,body) VALUES(?,?)',(row,text))
                    self.rows+=1
                offset=stop
            if offset!=len(source):raise ValueError('source bytes missed')
        self.db.commit()
        self.db.execute('VACUUM')
        self.db.commit()

    def matches(self,version,query,ranking='rowid',limit=None):
        if ranking=='bm25':
            suffix='ORDER BY bm25(fts),spans.rid'
        else:
            suffix='ORDER BY spans.rid'
        sql=('SELECT spans.rid,spans.start,spans.end FROM fts JOIN spans ON spans.rid=fts.rowid '
             'WHERE fts MATCH ? AND spans.generation=? '+suffix)
        args=[query,version]
        if limit is not None:
            sql+=' LIMIT ?';args.append(limit)
        return self.db.execute(sql,args).fetchall()

    def bytes(self):
        return self.path.stat().st_size

    def close(self):
        self.db.close()


def experiment(versions):
    with tempfile.TemporaryDirectory() as home:
        engines={key:Index(Path(home)/f'{key}.sqlite',versions,key) for key in CONFIGS}
        metrics={}
        try:
            for key,obj in engines.items():
                latency=[]
                phrase=[]
                top_overlap=[]
                rowsets=[]
                bm25supported=0
                bm25_exact_order=0
                for gen in range(len(versions)):
                    for term in TERMS:
                        start=time.perf_counter_ns()
                        rows=obj.matches(gen,term,'rowid',limit=3)
                        latency.append((time.perf_counter_ns()-start)/1000)
                        base=engines['full'].matches(gen,term,'rowid',limit=None)
                        got=obj.matches(gen,term,'rowid',limit=None)
                        if [r[0] for r in base]!=[r[0] for r in got]:
                            raise AssertionError(f'inexact token row set {key} {gen} {term}')
                        for _,begin,end in rows:
                            line=versions[gen][begin:end].decode('utf8').casefold()
                            if term not in line:
                                # FTS5 can match stem/Unicode token boundaries but not substrings;
                                # with these exact plain words, substring should still hold.
                                raise AssertionError(f'bad retrieved span {key} {gen} {term}')
                        full_ranked=[r[0] for r in engines['full'].matches(gen,term,'bm25',limit=3)]
                        full_top=set(full_ranked)
                        try:
                            ranked=[r[0] for r in obj.matches(gen,term,'bm25',limit=3)]
                            bm25supported+=1
                            bm25_exact_order+=int(ranked==full_ranked)
                            top_overlap.append(len(full_top & set(ranked))/max(1,len(full_top)))
                        except sqlite3.Error:
                            top_overlap.append(0.0)
                    for term in PHRASES:
                        try:
                            hits=obj.matches(gen,term,'rowid',limit=None)
                            phrase.append({'supported':True,'count':len(hits)})
                        except sqlite3.Error:
                            phrase.append({'supported':False,'count':0})
                metrics[key]={
                    'index_bytes':obj.bytes(),
                    'rows':obj.rows,
                    'keyword_queries':len(TERMS)*len(versions),
                    'keyword_match_parity':True,
                    'p50_keyword_query_us':round(statistics.median(latency),3),
                    'mean_top3_overlap_with_full_bm25':round(statistics.mean(top_overlap),4),
                    'bm25_queries_supported':bm25supported,
                    'bm25_exact_top3_order_matches':bm25_exact_order,
                    'phrase_queries_supported':sum(int(p['supported']) for p in phrase),
                    'phrase_queries_total':len(phrase),
                    'phrase_match_total':sum(p['count'] for p in phrase)}
            return {'versions':len(versions),'configurations':metrics,
                    'caveats':['keyword row parity does not imply equal BM25 order or phrase capability',
                               'candidate query terms chosen from the indexed README',
                               'SQLite VACUUM performed on all variants',
                               'no end-to-end answer quality, cold SSD or index updates',
                               'index bytes include row-to-source byte offset tables',
                               'all historical version lines indexed, not current-only']}
        finally:
            for obj in engines.values():
                obj.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    a=p.parse_args()
    results=experiment(load_versions())
    print('ROUND49',json.dumps(results,sort_keys=True))
    Path(a.out).write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    main()
