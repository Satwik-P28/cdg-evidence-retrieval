#!/usr/bin/env python3
"""Round 32: single-writer copy-on-write source segments and frame CAS.

Experimental local protocol. Zstandard CLI; contentless SQLite FTS5; no ACL,
origin authentication, GC/leases, multiwriter isolation or power-loss proof.
"""
from __future__ import annotations
import ctypes, ctypes.util, hashlib, json, os, re, sqlite3, tempfile, uuid
from pathlib import Path

def digest(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def atomic(path: Path, content: bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name('.tmp-'+uuid.uuid4().hex)
    try:
        temp.write_bytes(content)
        with temp.open('rb') as f: os.fsync(f.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

_zstd=ctypes.CDLL(ctypes.util.find_library('zstd'))
_zstd.ZSTD_compressBound.argtypes=[ctypes.c_size_t]
_zstd.ZSTD_compressBound.restype=ctypes.c_size_t
_zstd.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
_zstd.ZSTD_compress.restype=ctypes.c_size_t
_zstd.ZSTD_getFrameContentSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
_zstd.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong
_zstd.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
_zstd.ZSTD_decompress.restype=ctypes.c_size_t
_zstd.ZSTD_isError.argtypes=[ctypes.c_size_t]
_zstd.ZSTD_isError.restype=ctypes.c_uint

def compress(data:bytes)->bytes:
    bound=_zstd.ZSTD_compressBound(len(data)); out=ctypes.create_string_buffer(bound)
    src=ctypes.create_string_buffer(data);n=_zstd.ZSTD_compress(out,bound,src,len(data),3)
    if _zstd.ZSTD_isError(n):raise RuntimeError('Zstd compress failed')
    return out.raw[:n]

def decompress(data:bytes)->bytes:
    src=ctypes.create_string_buffer(data)
    expected=_zstd.ZSTD_getFrameContentSize(src,len(data))
    if expected>100_000_000:raise ValueError('missing or excessive Zstd frame content size')
    out=ctypes.create_string_buffer(expected)
    n=_zstd.ZSTD_decompress(out,expected,src,len(data))
    if _zstd.ZSTD_isError(n) or n!=expected:raise ValueError('Zstd decompression failed')
    return out.raw[:n]

def chunks(blob:bytes, max_size=512):
    """Line-stable framing, including UTF-8 and arbitrary long individual lines."""
    if max_size<32:raise ValueError('frame size too small')
    off=0
    for line in blob.splitlines(keepends=True):
        # A long UTF-8 line can be split at byte positions; entire source bytes
        # are reconstructed before decoding; no partial fragment is decoded.
        for start in range(0,len(line),max_size):
            x=line[start:start+max_size]
            yield (off+start,off+start+len(x),x)
        off+=len(line)

def line_ranges(blob:bytes):
    pos=0
    for line in blob.splitlines(keepends=True):
        # FTS records all nonempty physical source lines.
        a,b=pos,pos+len(line)
        pos=b
        if line.strip():yield a,b,line.decode('utf-8').rstrip('\r\n')

def _make_index(out:Path,blob:bytes):
    db=sqlite3.connect(out)
    try:
        db.executescript("CREATE VIRTUAL TABLE terms USING fts5(body,content=''); CREATE TABLE spans(lineid INTEGER PRIMARY KEY,a INTEGER,b INTEGER);")
        for rowid,(a,b,content) in enumerate(line_ranges(blob),1):
            db.execute('INSERT INTO terms(rowid,body) VALUES(?,?)',(rowid,content))
            db.execute('INSERT INTO spans(lineid,a,b) VALUES(?,?,?)',(rowid,a,b))
        db.commit()
    finally:db.close()

class Store:
    def __init__(self,root:Path,full_rebuild=False,frame_size=512):
        self.root=Path(root);self.full_rebuild=full_rebuild;self.frame_size=frame_size
        self.root.mkdir(parents=True,exist_ok=True)
    def publish(self,sources:dict[str,bytes],fail_before_pointer=False):
        """One atomic pointer switch. Old generations remain addressable."""
        if not sources or any('/' in n or not n or n.startswith('.') for n in sources):raise ValueError('bad source names')
        gen=uuid.uuid4().hex
        manifest={'generation':gen,'sources':{},'frame_size':self.frame_size,'mode':'full' if self.full_rebuild else 'cas'}
        produced=0
        for name,blob in sorted(sources.items()):
            if not isinstance(blob,bytes):raise TypeError('source must be bytes')
            sha=digest(blob)
            seg=self.root/'indexes'/(f'{gen}-{name}.sqlite' if self.full_rebuild else f'{sha}.sqlite')
            if not seg.exists():
                seg.parent.mkdir(exist_ok=True)
                temp=seg.with_name('.tmp-'+uuid.uuid4().hex+'.sqlite')
                try:
                    _make_index(temp,blob)
                    os.replace(temp,seg)
                finally:temp.unlink(missing_ok=True)
                produced+=seg.stat().st_size
            shafile=digest(seg.read_bytes())
            fragments=[]
            for start,end,raw in chunks(blob,self.frame_size):
                h=digest(raw)
                dest=self.root/'frames'/(f'{gen}-{name}-{start}.zst' if self.full_rebuild else f'{h}.zst')
                if not dest.exists():
                    compressed=compress(raw)
                    atomic(dest,compressed)
                    produced+=len(compressed)
                fragments.append({'start':start,'end':end,'sha256':h,'path':dest.relative_to(self.root).as_posix(),'compressed_sha256':digest(dest.read_bytes())})
            source_record={'sha256':sha,'length':len(blob),'index':seg.relative_to(self.root).as_posix(),'index_sha256':shafile,'frames':fragments}
            if self.full_rebuild:
                manifest['sources'][name]=source_record
            else:
                # The potentially large frame offset table belongs to an immutable
                # source version, not every global snapshot manifest.
                desc=self.root/'descriptors'/f'{sha}.json'
                if not desc.exists():
                    binary=json.dumps(source_record,sort_keys=True,separators=(',',':')).encode()
                    atomic(desc,binary)
                    produced+=len(binary)
                manifest['sources'][name]={'sha256':sha,'descriptor':desc.relative_to(self.root).as_posix(),'descriptor_sha256':digest(desc.read_bytes())}
        manifest_path=self.root/'manifests'/f'{gen}.json'
        atomic(manifest_path,json.dumps(manifest,sort_keys=True).encode())
        produced+=manifest_path.stat().st_size
        if fail_before_pointer:raise RuntimeError('injected publication failure')
        atomic(self.root/'CURRENT',(gen+'\n').encode())
        return {'generation':gen,'new_written_bytes':produced,'manifest':manifest}

    def reader(self,generation=None):
        if generation is None:generation=(self.root/'CURRENT').read_text().strip()
        if not re.fullmatch('[0-9a-f]{32}',generation):raise ValueError('invalid generation')
        path=self.root/'manifests'/f'{generation}.json'
        d=json.loads(path.read_text())
        if d['generation']!=generation:raise ValueError('wrong generation')
        for name,record in d['sources'].items():
            if 'descriptor' in record:
                desc=(self.root/record['descriptor']).read_bytes()
                if digest(desc)!=record['descriptor_sha256']:raise ValueError('modified descriptor')
                expanded=json.loads(desc)
                if expanded['sha256']!=record['sha256']:raise ValueError('descriptor source digest mismatch')
                d['sources'][name]=expanded
        return Reader(self.root,d)

class Reader:
    def __init__(self,root:Path,manifest:dict):
        self.root=root;self.manifest=manifest
        for name,s in manifest['sources'].items():
            if digest((root/s['index']).read_bytes())!=s['index_sha256']:raise ValueError('modified index')
            for f in s['frames']:
                if digest((root/f['path']).read_bytes())!=f['compressed_sha256']:raise ValueError('modified frame')
    def receipt(self,name,a,b):
        s=self.manifest['sources'][name]
        if not (0<=a<=b<=s['length']):raise ValueError('range')
        return {'generation':self.manifest['generation'],'name':name,'sha256':s['sha256'],'start':a,'end':b}
    def read(self,receipt):
        s=self.manifest['sources'].get(receipt.get('name'))
        if s is None or receipt.get('generation')!=self.manifest['generation'] or receipt.get('sha256')!=s['sha256']:raise ValueError('stale receipt')
        a,b=receipt.get('start'),receipt.get('end')
        if type(a)!=int or type(b)!=int or not (0<=a<=b<=s['length']):raise ValueError('range')
        pieces=[]
        for f in s['frames']:
            if f['start']>=b:break
            if f['end']<=a:continue
            raw=decompress((self.root/f['path']).read_bytes())
            if digest(raw)!=f['sha256']:raise ValueError('corrupt source fragment')
            pieces.append(raw[max(0,a-f['start']):min(f['end'],b)-f['start']])
        data=b''.join(pieces)
        if len(data)!=b-a:raise ValueError('missing frame')
        return data
    def search(self,term,limit=5):
        if not term or limit<1:raise ValueError('query')
        # Each-source FTS is queried independently. Local FTS ranks are NOT
        # globally calibrated. This intentionally uses stable name,rowid order.
        out=[]
        for name,s in sorted(self.manifest['sources'].items()):
            uri=f'file:{(self.root/s["index"]).as_posix()}?mode=ro&immutable=1'
            with sqlite3.connect(uri,uri=True) as db:
                q=db.execute('SELECT spans.a,spans.b FROM terms JOIN spans ON spans.lineid=terms.rowid WHERE terms MATCH ? ORDER BY spans.lineid LIMIT ?', (term,limit))
                for a,b in q:
                    r=self.receipt(name,a,b)
                    out.append({'receipt':r,'text':self.read(r).decode('utf-8')})
        return out[:limit]

def stored_bytes(root:Path):return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())
