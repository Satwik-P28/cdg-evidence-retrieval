#!/usr/bin/env python3
"""Round 44: independently test indexing, edit-diff and history-retention layouts.

This is a classical controlled SQLite experiment on five internal CDG reports.
All edits are synthetic; no LLM QA, SSD durability or new compression theory.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import importlib.util
import json
import random
import sqlite3
import statistics
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R43 = ROOT.parent / 'round-43' / 'lab.py'


def load43():
    spec = importlib.util.spec_from_file_location('cdg_round43_for_round44', R43)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def digest(content):
    return hashlib.sha256(content).hexdigest()


def plain_lines(content):
    return [x for x in content.decode('utf8').splitlines() if x.strip()]


def blocks(old, new, policy):
    """Yield (tag, start-old, end-old, start-new, end-new)."""
    if policy == 'sequence':
        yield from difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes()
    elif policy == 'edges':
        start = 0
        while start < min(len(old), len(new)) and old[start] == new[start]:
            start += 1
        end = 0
        while (end < len(old)-start and end < len(new)-start and
               old[len(old)-1-end] == new[len(new)-1-end]):
            end += 1
        if start:
            yield ('equal', 0, start, 0, start)
        if start != len(old)-end or start != len(new)-end:
            yield ('replace', start, len(old)-end, start, len(new)-end)
        if end:
            yield ('equal', len(old)-end, len(old), len(new)-end, len(new))
    elif policy == 'rebuild':
        yield ('replace', 0, len(old), 0, len(new))
    else:
        raise ValueError(policy)


class Variant:
    """Same CAS payloads, mutable FTS5 current index, optional SQLite history.

    mode=legacy: original contentless FTS + explicit 'delete' command.
    mode=delete: FTS5 contentless_delete=1 and SQL DELETE rowid.
    mode=trigger: external content FTS5 maintained by ordinary-table triggers.
    diff=sequence / edges / rebuild. history=all / live-only.
    """
    def __init__(self, root, docs, mode='legacy', diff='sequence', history='all'):
        self.root = root
        root.mkdir(parents=True)
        self.mode, self.diff, self.history = mode, diff, history
        self.db = sqlite3.connect(root/'live.sqlite')
        self.db.execute('CREATE TABLE lines (rid INTEGER PRIMARY KEY, name TEXT NOT NULL, text TEXT NOT NULL)')
        self.db.execute('CREATE INDEX lines_name_idx ON lines(name)')
        if mode == 'legacy':
            self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='')")
        elif mode == 'delete':
            self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='', contentless_delete=1)")
        elif mode == 'trigger':
            self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='lines', content_rowid='rid')")
            self.db.execute("""CREATE TRIGGER line_insert AFTER INSERT ON lines BEGIN
                INSERT INTO fts(rowid,text) VALUES (new.rid,new.text); END""")
            self.db.execute("""CREATE TRIGGER line_delete AFTER DELETE ON lines BEGIN
                INSERT INTO fts(fts,rowid,text) VALUES ('delete',old.rid,old.text); END""")
        else:
            raise ValueError(mode)
        self.old = {}
        self.maps = {}
        self.updates = 0
        self.update(docs)

    def _remove(self, rowid, old_text):
        if self.mode == 'legacy':
            self.db.execute("INSERT INTO fts(fts,rowid,text) VALUES('delete',?,?)",(rowid,old_text))
        elif self.mode == 'delete':
            self.db.execute("DELETE FROM fts WHERE rowid=?",(rowid,))
        self.db.execute('DELETE FROM lines WHERE rid=?',(rowid,))

    def _insert(self,name,text):
        cursor = self.db.execute('INSERT INTO lines(name,text) VALUES (?,?)',(name,text))
        rowid = cursor.lastrowid
        if self.mode != 'trigger':
            self.db.execute('INSERT INTO fts(rowid,text) VALUES (?,?)',(rowid,text))
        return rowid,text

    def update(self, sources):
        start = time.perf_counter_ns()
        changed = [name for name,blob in sources.items() if self.maps.get(name) != digest(blob)]
        removed = set(self.maps) - set(sources)
        for name in removed:
            for rowid,text in self.old.pop(name):
                self._remove(rowid,text)
            self.maps.pop(name)
        counts = {'inserted':0,'deleted':0,'reused':0,'changed_sources':len(changed)}
        for name in changed:
            new = plain_lines(sources[name])
            prev = self.old.get(name,[])
            out = []
            for tag,i0,i1,j0,j1 in blocks([t for _,t in prev],new,self.diff):
                if tag == 'equal':
                    out.extend(prev[i0:i1])
                    counts['reused'] += i1-i0
                else:
                    for rowid,text in prev[i0:i1]:
                        self._remove(rowid,text)
                        counts['deleted'] += 1
                    for text in new[j0:j1]:
                        out.append(self._insert(name,text))
                        counts['inserted'] += 1
            self.old[name] = out
            self.maps[name] = digest(sources[name])
        self.db.commit()
        if self.history == 'all':
            directory = self.root/'snapshots'
            directory.mkdir(exist_ok=True)
            dest = sqlite3.connect(directory/f'{self.updates:04d}.sqlite')
            try:
                self.db.backup(dest)
            finally:
                dest.close()
        elif self.history != 'live-only':
            raise ValueError(self.history)
        cas = self.root/'payload'
        cas.mkdir(exist_ok=True)
        for blob in sources.values():
            target = cas/(digest(blob)+'.z')
            if not target.exists():
                target.write_bytes(zlib.compress(blob,6))
        manifests = self.root/'manifests'
        manifests.mkdir(exist_ok=True)
        (manifests/f'{self.updates:04d}.json').write_text(json.dumps(self.maps,sort_keys=True))
        self.updates += 1
        counts['ms'] = (time.perf_counter_ns()-start)/1e6
        return counts

    def _manifest(self,generation):
        return json.loads((self.root/'manifests'/f'{generation:04d}.json').read_text())

    def read_gen(self,generation,name):
        index=self._manifest(generation)
        original = zlib.decompress((self.root/'payload'/(index[name]+'.z')).read_bytes())
        if digest(original)!=index[name]:
            raise ValueError('bad historical source digest')
        return original

    def search(self,query):
        return self.db.execute('SELECT lines.name,fts.rowid FROM fts JOIN lines ON lines.rid=fts.rowid WHERE fts MATCH ? ORDER BY lines.name,fts.rowid',(query,)).fetchall()

    def search_gen(self,generation,query):
        if generation == self.updates - 1:
            return sorted(name for name,_ in self.search(query))
        if self.history=='all':
            file=self.root/'snapshots'/f'{generation:04d}.sqlite'
            conn=sqlite3.connect(f'file:{file}?mode=ro&immutable=1',uri=True)
            try:
                rows=conn.execute('SELECT lines.name FROM fts JOIN lines ON lines.rid=fts.rowid WHERE fts MATCH ? ORDER BY lines.name',(query,)).fetchall()
                return [row[0] for row in rows]
            finally:
                conn.close()
        # Fairly charge historical-on-demand reconstruction and indexing.
        conn=sqlite3.connect(':memory:')
        try:
            conn.execute('CREATE VIRTUAL TABLE tmp USING fts5(name UNINDEXED,text)')
            for name in sorted(self._manifest(generation)):
                for line in plain_lines(self.read_gen(generation,name)):
                    conn.execute('INSERT INTO tmp(name,text) VALUES(?,?)',(name,line))
            return sorted(row[0] for row in conn.execute('SELECT name FROM tmp WHERE tmp MATCH ?',(query,)).fetchall())
        finally:
            conn.close()

    def total_bytes(self):
        return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())

    def close(self):
        self.db.close()


CONFIGS = {
    'P_sequence': ('legacy','sequence','all'),
    'P_edges': ('legacy','edges','all'),
    'E_edges': ('delete','edges','all'),
    'T_edges': ('trigger','edges','all'),
    'E_rebuild': ('delete','rebuild','all'),
    'E_live': ('delete','edges','live-only'),
}


def check(engines, histories, terms):
    latest=histories[-1]
    for term in terms:
        outputs=[sorted(name for name,_ in eng.search(term)) for eng in engines.values()]
        if any(outs!=outputs[0] for outs in outputs[1:]):
            raise AssertionError(f'FTS disagreement at {term}: {dict(zip(engines, outputs))}')
    for generation,docs in enumerate(histories):
        for name,blob in docs.items():
            for tag,engine in engines.items():
                if engine.read_gen(generation,name)!=blob:
                    raise AssertionError(f'{tag} historical bytes mismatch {generation} {name}')


def exercise(n,fraction,seed,mode,steps=4,include_historical=True):
    r43=load43()
    baseline=r43.round42()
    docs=baseline.source_docs(n)
    rng=random.Random(seed)
    terms=['evidence','compression','retrieval','source','algorithm','revision']
    with tempfile.TemporaryDirectory() as home:
        root=Path(home)
        engines={tag:Variant(root/tag,docs,*options) for tag,options in CONFIGS.items()}
        histories=[dict(docs)]
        update_samples={name:[] for name in engines}
        rowstats={name:{'reused':0,'inserted':0,'deleted':0} for name in engines}
        try:
            check(engines,histories,terms)
            for t in range(1,steps+1):
                names=rng.sample(sorted(docs),max(1,round(n*fraction)))
                old_docs=dict(docs)
                for name in names:
                    docs[name]=r43.nonnoop_edit(docs[name],t,mode)
                if any(docs[name]==old_docs[name] for name in names):
                    raise AssertionError('unexpected no-op')
                for tag,engine in engines.items():
                    output=engine.update(docs)
                    update_samples[tag].append(output['ms'])
                    for key in ('reused','inserted','deleted'):
                        rowstats[tag][key]+=output[key]
                histories.append(dict(docs))
                check(engines,histories,terms)
            current_latency={}
            historical_latency={}
            for tag,engine in engines.items():
                times=[]
                for _ in range(3):
                    for term in terms:
                        start=time.perf_counter_ns()
                        engine.search(term)
                        times.append((time.perf_counter_ns()-start)/1000)
                current_latency[tag]=round(statistics.median(times),3)
                if include_historical:
                    observed=[]
                    for generation in (0, max(0,steps//2)):
                        for term in ('evidence','algorithm'):
                            start=time.perf_counter_ns()
                            names=engine.search_gen(generation,term)
                            observed.append((time.perf_counter_ns()-start)/1000)
                            control=engines['P_sequence'].search_gen(generation,term)
                            if names!=control:
                                raise AssertionError(f'historical query mismatch {tag} {generation} {term}')
                    historical_latency[tag]=round(statistics.median(observed),3)
            return {'mode':mode,'n':n,'fraction':fraction,'seed':seed,
                    'update_p50_ms':{tag:round(statistics.median(samples),3) for tag,samples in update_samples.items()},
                    'stored_bytes':{tag:engine.total_bytes() for tag,engine in engines.items()},
                    'current_search_p50_us':current_latency,
                    'history_search_p50_us':historical_latency,'rowstats':rowstats}
        finally:
            for eng in engines.values():
                eng.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--quick',action='store_true')
    p.add_argument('--out',default=str(ROOT/'results.json'))
    args=p.parse_args()
    scenarios=[('replace',5,.2,11)] if args.quick else [
        (mode,n,fraction,seed)
        for mode in ('append','replace','insert','delete')
        for n in (5,20)
        for fraction in (.05,.2,.8)
        for seed in (11,23)]
    data=[]
    for mode,n,fraction,seed in scenarios:
        row=exercise(n,fraction,seed,mode)
        data.append(row)
        print(f'{mode:7} n={n:2} p={fraction:.2f} seed={seed} '
              f'updates(ms) {row["update_p50_ms"]}',flush=True)
    summary={'scenarios':len(data),'variants':list(CONFIGS)}
    for metric in ('update_p50_ms','stored_bytes','current_search_p50_us','history_search_p50_us'):
        summary[metric+'_median']={
            tag:round(statistics.median(x[metric][tag] for x in data),3) for tag in CONFIGS}
    summary['wins_update']={
        tag:sum(x['update_p50_ms'][tag] == min(x['update_p50_ms'].values()) for x in data)
        for tag in CONFIGS}
    print('SUMMARY',json.dumps(summary,sort_keys=True))
    output={'description':'Round44 multi-policy SQLite FTS5, edit script, and history archival controlled comparison',
            'limitations':['five internal reports; 20 IDs replicate these five reports',
                           '48 seeded synthetic scenarios; short warm timings, not independent samples',
                           'historical-on-demand queries rebuild entire index, no cache',
                           'no LLM QA or source entailment; no durability tests'],
            'summary':summary,'rows':data}
    Path(args.out).write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':
    main()
