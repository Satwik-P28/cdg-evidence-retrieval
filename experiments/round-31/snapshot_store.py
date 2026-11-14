#!/usr/bin/env python3
"""Round 31: immutable SQLite/seekable-Zstd snapshot publication.

A reader pins one published generation and its two data files, never consulting
CURRENT again during the request. Sources, full-text postings and title edges
are built together, and a receipt carries the generation and exact SHA-256.

Not a distributed concurrency protocol: local single writer, POSIX rename,
no crash-recovery journal, reader lifetime GC, origin authorization, or ACL.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import uuid

from contentless_bench import build_contentless, query as search_lines
from filebacked_bench import read_spans

SCHEMA_VERSION = 1

def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def canonical(text: str) -> str:
    return ' '.join(re.findall(r'[^\W_]+', text.lower(), flags=re.UNICODE))

def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def make_link_table(db: sqlite3.Connection, source_paths: list[Path]) -> int:
    """Materialize exact whole-token title mentions, excluding self-links."""
    db.executescript('''
    CREATE TABLE title_links (src INTEGER NOT NULL, dst INTEGER NOT NULL,
      PRIMARY KEY(src,dst));
    CREATE INDEX title_links_dst ON title_links(dst);
    ''')
    names = [p.name for p in source_paths]
    bodies = [' ' + canonical(p.read_text(encoding='utf-8')) + ' ' for p in source_paths]
    # Basename is a fixture title here; prod datasets should supply explicit
    # titles, versions and authorization, not infer them from filenames.
    records = [(i+1,j+1) for i,body in enumerate(bodies)
               for j,title in enumerate(names)
               if i != j and len(canonical(title)) > 2
               and (' ' + canonical(title) + ' ') in body]
    db.executemany('INSERT INTO title_links(src,dst) VALUES (?,?)',records)
    db.commit()
    return len(records)

def publish(root: Path, paths: list[Path], *, frame_size: int=512,
            fail_before_switch: bool=False) -> dict:
    """Build complete generation privately and replace CURRENT atomically.

    A failed validation or induced failure leaves CURRENT unchanged. The
    generation directory name is random, not a claim of content addressability.
    """
    root=Path(root);root.mkdir(parents=True, exist_ok=True)
    if not paths or len(set(p.name for p in paths))!=len(paths):
        raise ValueError('sources require distinct filenames')
    sources=[Path(p) for p in paths]
    stage=root/('.build-'+uuid.uuid4().hex)
    stage.mkdir()
    published=False
    try:
        build_contentless(stage,sources,layout='fixed',size=frame_size)
        db=sqlite3.connect(stage/'index.sqlite')
        try:
            count=make_link_table(db,sources)
            source_rows=db.execute('SELECT source_id,name,sha256,raw_len FROM sources ORDER BY source_id').fetchall()
        finally:
            db.close()
        # If a source changed during building, abort before publishing a mixed
        # source generation. This catches post-read mutation, not malicious races.
        for sid,name,digest,size in source_rows:
            original=next(p for p in sources if p.name==name)
            if sha256_file(original)!=digest or original.stat().st_size!=size:
                raise ValueError('source changed during build')
        file_hashes={name:sha256_file(stage/name) for name in ('index.sqlite','frames.zst')}
        manifest={
          'schema_version':SCHEMA_VERSION,
          'generation':uuid.uuid4().hex,
          'frame_size':frame_size,
          'files':file_hashes,
          'sources':[{'source_id':sid,'name':name,'sha256':digest,'size':size}
                     for sid,name,digest,size in source_rows],
          'links':count,
          'contract':'immutable physical snapshot; no origin freshness or ACL guarantee'
        }
        (stage/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        # Keep generation stable before publishing the pointer.
        for name in ('index.sqlite','frames.zst','manifest.json'):
            with (stage/name).open('rb') as handle:os.fsync(handle.fileno())
        fsync_directory(stage)
        if fail_before_switch:raise RuntimeError('injected failure before atomic switch')
        final=root/manifest['generation']
        os.rename(stage, final)
        fsync_directory(root)
        current_temp=root/('.CURRENT-'+uuid.uuid4().hex)
        try:
            current_temp.write_text(manifest['generation']+'\n',encoding='ascii')
            with current_temp.open('rb') as handle:os.fsync(handle.fileno())
            os.replace(current_temp,root/'CURRENT')
            fsync_directory(root)
        finally:
            current_temp.unlink(missing_ok=True)
        published=True
        return {'generation':manifest['generation'],'sources':len(sources),
                'links':count,'index_bytes':(final/'index.sqlite').stat().st_size,
                'payload_bytes':(final/'frames.zst').stat().st_size,
                'manifest':manifest}
    finally:
        if not published and stage.exists():shutil.rmtree(stage)

class SnapshotReader:
    """Pin a snapshot generation and fail closed on stale/corrupt receipts."""
    def __init__(self, root:Path, generation:str|None=None):
        root=Path(root)
        if generation is None:generation=(root/'CURRENT').read_text(encoding='ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{32}', generation):
            raise ValueError('invalid generation identifier')
        self.generation=generation
        self.folder=root/generation
        self.manifest=json.loads((self.folder/'manifest.json').read_text(encoding='utf-8'))
        if self.manifest['generation']!=generation or self.manifest['schema_version']!=SCHEMA_VERSION:
            raise ValueError('manifest generation/schema mismatch')
        for name,expected in self.manifest['files'].items():
            if sha256_file(self.folder/name)!=expected:
                raise ValueError(f'corrupt indexed snapshot {name}')
        self.db=sqlite3.connect('file:'+str(self.folder/'index.sqlite')+'?mode=ro&immutable=1',uri=True)
        self.fd=os.open(self.folder/'frames.zst',os.O_RDONLY)
        self.sources={x['source_id']:x for x in self.manifest['sources']}
        self._closed=False

    def close(self):
        if not self._closed:
            self.db.close();os.close(self.fd);self._closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def search(self, term:str, k:int=5) -> list[dict]:
        if self._closed:raise ValueError('reader closed')
        if not term or k<1:raise ValueError('invalid query')
        found=search_lines(self.db,term,k)
        output=[]
        for line_id,sid,a,b,score in found:
            receipt=self.receipt(sid,a,b)
            payload,bytes_read,frame_count=read_spans(self.db,self.fd,sid,[(a,b)])
            output.append({'receipt':receipt,'text':payload[0].decode('utf-8'),
                           'compressed_bytes':bytes_read,'frames':frame_count})
        return output

    def receipt(self,sid:int,start:int,end:int)->dict:
        source=self.sources.get(sid)
        if source is None:raise KeyError(sid)
        if not 0<=start<=end<=source['size']:raise ValueError('out-of-range source span')
        return {'generation':self.generation,'source_id':sid,
                'source_sha256':source['sha256'],'start':start,'end':end}

    def read_receipt(self,receipt:dict)->bytes:
        if self._closed:raise ValueError('reader closed')
        if receipt.get('generation')!=self.generation:
            raise ValueError('stale or mismatched generation receipt')
        sid=receipt.get('source_id')
        if sid not in self.sources or receipt.get('source_sha256')!=self.sources[sid]['sha256']:
            raise ValueError('source digest mismatch')
        a,b=receipt.get('start'),receipt.get('end')
        if not isinstance(a,int) or not isinstance(b,int) or not 0<=a<=b<=self.sources[sid]['size']:
            raise ValueError('out-of-range source span')
        return read_spans(self.db,self.fd,sid,[(a,b)])[0][0]

    def outgoing_links(self,sid:int)->list[int]:
        if self._closed:raise ValueError('reader closed')
        return [x[0] for x in self.db.execute('SELECT dst FROM title_links WHERE src=? ORDER BY dst',(sid,))]


def cli():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    sub=ap.add_subparsers(dest='op',required=True)
    pub=sub.add_parser('publish');pub.add_argument('paths',type=Path,nargs='+');pub.add_argument('--frame-size',type=int,default=512)
    qry=sub.add_parser('search');qry.add_argument('query');qry.add_argument('--topk',type=int,default=5)
    args=ap.parse_args()
    if args.op=='publish':
        result=publish(args.root,args.paths,frame_size=args.frame_size)
        print(json.dumps({k:v for k,v in result.items() if k!='manifest'},indent=2))
    else:
        with SnapshotReader(args.root) as r:print(json.dumps(r.search(args.query,args.topk),indent=2,ensure_ascii=False))
if __name__=='__main__':cli()