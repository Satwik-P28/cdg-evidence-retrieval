#!/usr/bin/env python3
"""Round 43: row-ID-based FTS5 historical baseline and non-no-op edit controls.

Inputs are inherited from Round 42 (five internal CDG reports, optional identity
replication); no semantic QA, crash durability, or independent corpus claims.
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
OLD = ROOT.parent / 'round-42' / 'lab.py'


def round42():
    spec = importlib.util.spec_from_file_location('cdg_round42', OLD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Round 42 code missing: {OLD}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def nonnoop_edit(blob: bytes, step: int, mode: str) -> bytes:
    if mode == 'append':
        result = blob + f'\nRound43 provenance addition {step} evidence and revision.\n'.encode()
    elif mode == 'replace':
        pos = next((i for i, b in enumerate(blob) if 97 <= b <= 122), None)
        if pos is None:
            result = blob + b'changed'
        else:
            data = bytearray(blob)
            data[pos] = 97 + (data[pos] - 97 + 1) % 26
            result = bytes(data)
    elif mode == 'insert':
        lines = blob.splitlines(keepends=True)
        mid = len(lines) // 2
        lines.insert(mid, f'Round43 inserted evidence line {step}.\n'.encode())
        result = b''.join(lines)
    elif mode == 'delete':
        lines = blob.splitlines(keepends=True)
        if len(lines) < 2:
            result = blob + b'nonempty revision'
        else:
            lines.pop((len(lines) // 2 + step) % len(lines))
            result = b''.join(lines)
    else:
        raise ValueError(f'unknown mutation mode {mode}')
    if result == blob:
        raise AssertionError(f'edit must change source bytes: {mode} step={step}')
    return result


class IndexedDelta:
    """Incremental FTS5 by stable row ID with CAS payload and backed-up index.

    'lines' owns the row-ID to source map. A contentless FTS5 index stores tokens,
    not duplicate plaintext. SequenceMatcher retains row IDs for equal lines and
    deletes/inserts only edited lines. This is still a conventional single-writer
    SQLite control, not a proposed original indexing algorithm.
    """
    def __init__(self, root: Path, sources: dict[str, bytes]):
        self.root = root
        root.mkdir(parents=True)
        self.db = sqlite3.connect(root / 'live.sqlite')
        self.db.execute('CREATE TABLE lines (rid INTEGER PRIMARY KEY, name TEXT NOT NULL, text TEXT NOT NULL)')
        self.db.execute('CREATE INDEX lines_name_idx ON lines(name)')
        self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='')")
        self.old: dict[str, list[tuple[int, str]]] = {}
        self.maps: dict[str, str] = {}
        self.update(sources)

    def _remove(self, rid: int, content: str) -> None:
        self.db.execute("INSERT INTO fts(fts,rowid,text) VALUES('delete',?,?)", (rid, content))
        self.db.execute('DELETE FROM lines WHERE rid=?', (rid,))

    def _insert(self, name: str, content: str) -> tuple[int, str]:
        cursor = self.db.execute('INSERT INTO lines(name,text) VALUES(?,?)', (name, content))
        rid = cursor.lastrowid
        self.db.execute('INSERT INTO fts(rowid,text) VALUES(?,?)', (rid, content))
        return (rid, content)

    def update(self, sources: dict[str, bytes]) -> dict:
        started = time.perf_counter_ns()
        changed = [name for name, blob in sources.items() if self.maps.get(name) != digest(blob)]
        removed = set(self.maps) - set(sources)
        for name in removed:
            for rid, content in self.old.pop(name):
                self._remove(rid, content)
            self.maps.pop(name)
        reused = inserted = deleted = 0
        for name in changed:
            new = [line for line in sources[name].decode('utf8').splitlines() if line.strip()]
            prior = self.old.get(name, [])
            matcher = difflib.SequenceMatcher(a=[text for _, text in prior], b=new, autojunk=False)
            updated: list[tuple[int, str]] = []
            for tag, i0, i1, j0, j1 in matcher.get_opcodes():
                if tag == 'equal':
                    updated.extend(prior[i0:i1]); reused += i1 - i0
                else:
                    for rid, text in prior[i0:i1]:
                        self._remove(rid, text); deleted += 1
                    for text in new[j0:j1]:
                        updated.append(self._insert(name, text)); inserted += 1
            self.old[name] = updated
            self.maps[name] = digest(sources[name])
        self.db.commit()
        history = self.root / 'history'; history.mkdir(exist_ok=True)
        generation = len(list(history.glob('*.sqlite')))
        backup = sqlite3.connect(history / f'{generation:04d}.sqlite')
        try:
            self.db.backup(backup)
        finally:
            backup.close()
        payload = self.root / 'payload'; payload.mkdir(exist_ok=True)
        for blob in sources.values():
            path = payload / (digest(blob) + '.z')
            if not path.exists():
                path.write_bytes(zlib.compress(blob, 6))
        maps = self.root / 'maps'; maps.mkdir(exist_ok=True)
        (maps / f'{generation:04d}.json').write_text(json.dumps(self.maps, sort_keys=True))
        return {'ms': (time.perf_counter_ns() - started) / 1e6,
                'changed': len(changed), 'removed': len(removed),
                'reused_rows': reused, 'inserted_rows': inserted, 'deleted_rows': deleted}

    def search(self, term: str):
        return self.db.execute('SELECT lines.name, fts.rowid FROM fts JOIN lines ON fts.rowid=lines.rid WHERE fts MATCH ? ORDER BY lines.name,fts.rowid', (term,)).fetchall()

    def read_gen(self, generation: int, name: str) -> bytes:
        index = json.loads((self.root / 'maps' / f'{generation:04d}.json').read_text())
        blob = zlib.decompress((self.root / 'payload' / (index[name] + '.z')).read_bytes())
        if digest(blob) != index[name]:
            raise ValueError('CAS content digest mismatch')
        return blob

    def close(self):
        self.db.close()


def dir_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def compare(engines, docs, histories, generation: int, queries: list[str]) -> None:
    for term in queries:
        names = [sorted(name for name, _ in obj.search(term)) for obj in engines]
        if not all(names[0] == seq for seq in names[1:]):
            raise AssertionError(f'search result mismatch: {term}: {names}')
    for gen, previous in enumerate(histories):
        for name, blob in previous.items():
            for engine in engines:
                if engine.read_gen(gen, name) != blob:
                    raise AssertionError(f'historical corruption {engine.__class__.__name__} {gen} {name}')
    if generation + 1 != len(histories):
        raise AssertionError('generation counter mismatch')


def exercise(n: int, fraction: float, seed: int, mode: str, updates: int = 4) -> dict:
    older = round42()
    rng = random.Random(seed)
    docs = older.source_docs(n)
    queries = ['evidence', 'compression', 'retrieval', 'source', 'algorithm', 'revision']
    with tempfile.TemporaryDirectory() as dirname:
        root = Path(dirname)
        legacy = older.GlobalDelta(root / 'legacy', docs)
        hybrid = older.Hybrid(root / 'hybrid', docs)
        indexed = IndexedDelta(root / 'indexed', docs)
        engines = [legacy, hybrid, indexed]
        snapshots = [dict(docs)]
        try:
            compare(engines, docs, snapshots, 0, queries)
            changes = []
            for step in range(1, updates + 1):
                selected = rng.sample(sorted(docs), max(1, round(n * fraction)))
                old = dict(docs)
                for key in selected:
                    docs[key] = nonnoop_edit(docs[key], step, mode)
                actual = sum(docs[k] != old[k] for k in docs)
                if actual != len(selected):
                    raise AssertionError('nominal updates must equal actual changes')
                timings = [engine.update(docs) for engine in engines]
                snapshots.append(dict(docs))
                compare(engines, docs, snapshots, step, queries)
                changes.append({'changed': actual, 'legacy_ms': timings[0]['ms'],
                                'hybrid_ms': timings[1]['ms'], 'indexed_ms': timings[2]['ms'],
                                'indexed_reused': timings[2]['reused_rows']})
            timings = {}
            for tag, engine in zip(('legacy', 'hybrid', 'indexed'), engines):
                observations = []
                for _ in range(3):
                    for query in queries:
                        t = time.perf_counter_ns(); engine.search(query)
                        observations.append((time.perf_counter_ns() - t)/1000)
                timings[tag] = round(statistics.median(observations), 3)
            return {'sources': n, 'fraction': fraction, 'seed': seed, 'mode': mode,
                    'updates': updates, 'actual_changed_total': sum(x['changed'] for x in changes),
                    'update_p50_ms': {k: round(statistics.median(row[k+'_ms'] for row in changes), 3)
                                      for k in ('legacy', 'hybrid', 'indexed')},
                    'storage_bytes': {k: dir_bytes(root/k) for k in ('legacy','hybrid','indexed')},
                    'warm_query_p50_us': timings,
                    'reused_rows_total': sum(x['indexed_reused'] for x in changes)}
        finally:
            for engine in engines:
                engine.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'results.json'))
    parser.add_argument('--quick', action='store_true', help='small reproducibility smoke run')
    args = parser.parse_args()
    grid = [(5, .2, 11, 'replace')] if args.quick else [
        (n, fraction, seed, mode)
        for mode in ('append','replace','insert','delete')
        for n in (5,20) for fraction in (.05,.2,.8) for seed in (11,23)]
    rows = []
    for n, fraction, seed, mode in grid:
        result = exercise(n, fraction, seed, mode)
        rows.append(result)
        print(f'{mode:7} n={n:2} changed={fraction:.2f} seed={seed} '
              f'update ms {result["update_p50_ms"]}', flush=True)
    output = {'study': 'Round43: indexed row-ID SQLite plus live historical controls',
              'scope': 'same five internal CDG reports as Round42 with distinct identity replicas',
              'limitations': ['not held-out independent documents', 'synthetic edits',
                              'full SQLite backup per generation for indexed and legacy',
                              'warm small-sample CPU/OS timing, no fsync, GC, cold cache, or QA'],
              'rows': rows}
    Path(args.out).write_text(json.dumps(output, indent=2) + '\n')

if __name__ == '__main__':
    main()
