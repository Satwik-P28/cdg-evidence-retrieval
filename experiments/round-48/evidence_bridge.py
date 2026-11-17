#!/usr/bin/env python3
"""Round 48: FTS5 source-span retrieval through verifiable, versioned frame storage.

Integration experiment only. Retrieval questions are source-derived keyword probes,
not independent QA. No authority, entailment, crash-safety or signed provenance.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import sqlite3
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'round-46'/'version_chunks.py'
PACK=ROOT.parent/'round-47'/'manifest_lab.py'


def dynamic(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(m)
    return m


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class Receipt:
    generation:int
    source_sha256:str
    manifest_sha256:str
    byte_start:int
    byte_end:int


class EvidenceFTS:
    def __init__(self,versions,path):
        self.versions=versions
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE spans (rid INTEGER PRIMARY KEY, generation INTEGER NOT NULL, byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX spans_generation ON spans(generation)')
        self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(body,content='')")
        for generation,data in enumerate(versions):
            offset=0
            for line in data.splitlines(keepends=True):
                end=offset+len(line)
                text=line.decode('utf8')
                if text.strip():
                    row=self.db.execute('INSERT INTO spans(generation,byte_start,byte_end) VALUES(?,?,?)',
                                        (generation,offset,end)).lastrowid
                    self.db.execute('INSERT INTO fts(rowid,body) VALUES(?,?)',(row,text))
                offset=end
            if offset!=len(data):raise AssertionError('line offset accounting bug')
        self.db.commit()

    def query(self,generation,term,k=3):
        hits=self.db.execute('''SELECT spans.byte_start,spans.byte_end FROM fts
                                JOIN spans ON spans.rid=fts.rowid
                                WHERE fts MATCH ? AND spans.generation=?
                                ORDER BY bm25(fts),spans.rid LIMIT ?''',
                             (term,generation,k)).fetchall()
        return hits

    def index_bytes(self):
        return Path(self.db.execute('PRAGMA database_list').fetchone()[2]).stat().st_size

    def close(self):
        self.db.close()


class VersionedReader:
    def __init__(self,versions,frames='gear512',manifest='binary-zlib'):
        self.prior=dynamic('cdg_r46_for_48',OLD)
        self.pack=dynamic('cdg_r47_for_48',PACK)
        self.archive=self.prior.FramedArchive(versions,frames)
        self.packed_manifest=self.pack.encode(self.archive.manifests,manifest)
        self.manifest_style=manifest
        self.manifest_sha=digest(self.packed_manifest)
        self.current=len(versions)-1
        self.manifests=self.pack.decode(self.packed_manifest,manifest)
        self.frame_style=frames

    def receipt(self,generation,start,end):
        m=self.manifests[generation]
        if not (0<=start<=end<=m['size']):
            raise ValueError('invalid receipt range')
        return Receipt(generation,m['sha'],self.manifest_sha,start,end)

    def read(self,receipt,pin_generation=None,decode_manifest=False):
        permitted=self.current if pin_generation is None else pin_generation
        if receipt.generation!=permitted:
            raise ValueError('stale or unpinned generation')
        if receipt.manifest_sha256!=digest(self.packed_manifest):
            raise ValueError('manifest receipt mismatch')
        manifests=(self.pack.decode(self.packed_manifest,self.manifest_style)
                   if decode_manifest else self.manifests)
        m=manifests[receipt.generation]
        if m['sha']!=receipt.source_sha256:
            raise ValueError('source digest changed')
        return self.pack.read_span(self.archive.frames,m,receipt.byte_start,receipt.byte_end)

    def size(self):
        return self.archive.payload_bytes()+len(self.packed_manifest)


CONFIGS=[
    ('whole_json','whole','json'),
    ('fixed512_binary','fixed512','binary-zlib'),
    ('gear512_binary','gear512','binary-zlib'),
    ('gear512_json','gear512','json-zlib'),
    ('gear1024_binary','gear1024','binary-zlib'),
]
TERMS=('installation','dependencies','python','uv','tools','workspace',
       'version','license','release','cache')


def experiment(versions):
    with tempfile.TemporaryDirectory() as home:
        index=EvidenceFTS(versions,Path(home)/'fts.sqlite')
        results={}
        lookups=[]
        try:
            for generation in range(len(versions)):
                for term in TERMS:
                    started=time.perf_counter_ns()
                    hits=index.query(generation,term,k=3)
                    lookups.append((time.perf_counter_ns()-started)/1000)
                    for start,end in hits:
                        if not 0<=start<=end<=len(versions[generation]):
                            raise AssertionError('invalid byte range from FTS')
            requests=[(generation,term,start,end)
                      for generation in range(len(versions))
                      for term in TERMS
                      for start,end in index.query(generation,term,k=3)]
            for label,frames,encoding in CONFIGS:
                engine=VersionedReader(versions,frames,encoding)
                warm=[];cold=[];read_bytes=[]
                for generation,term,start,end in requests:
                    receipt=engine.receipt(generation,start,end)
                    begin=time.perf_counter_ns()
                    decoded,cost=engine.read(receipt,pin_generation=generation)
                    warm.append((time.perf_counter_ns()-begin)/1000)
                    begin=time.perf_counter_ns()
                    check,again=engine.read(receipt,pin_generation=generation,decode_manifest=True)
                    cold.append((time.perf_counter_ns()-begin)/1000)
                    if decoded!=versions[generation][start:end] or check!=decoded or again!=cost:
                        raise AssertionError(f'inexact source evidence {label}: {term}')
                    read_bytes.append(cost)
                old=engine.receipt(0,0,min(30,len(versions[0])))
                try:
                    engine.read(old)
                    raise AssertionError('stale receipt must fail with unpinned current reader')
                except ValueError:
                    pass
                results[label]={
                    'frame_style':frames,'manifest_style':encoding,
                    'archive_bytes':engine.size(),
                    'combined_archive_index_bytes':engine.size()+index.index_bytes(),
                    'read_span_p50_us':round(statistics.median(warm),3),
                    'cold_metadata_read_p50_us':round(statistics.median(cold),3),
                    'mean_compressed_bytes_activated':round(statistics.mean(read_bytes),2),
                    'median_compressed_bytes_activated':round(statistics.median(read_bytes),2)}
            return {'versions':len(versions),'queries':len(versions)*len(TERMS),
                    'retrieved_evidence_spans':len(requests),
                    'persistent_fts_index_bytes':index.index_bytes(),
                    'fts_query_p50_us':round(statistics.median(lookups),3),
                    'methods':results,
                    'limits':['keywords from source topic, not independent QA',
                              'one versioned README; all FTS spans evaluated',
                              'index covers all historical generations and duplicates source tokens',
                              'cold metadata reparse in memory, not disk I/O',
                              'receipts bind local manifests, not authenticated author identity',
                              'no model answer grounding or SSD crash-durability benchmark']}
        finally:
            index.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(ROOT/'results.json'))
    x=ap.parse_args()
    source=dynamic('cdg_r46_loader_48',OLD)
    results=experiment(source.load_source())
    print('ROUND48',json.dumps(results,sort_keys=True))
    Path(x.out).write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    main()
