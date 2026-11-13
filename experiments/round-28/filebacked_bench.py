#!/usr/bin/env python3
"""Round 28 file-backed Zstd frame+SQLite receipt baseline.

Data-independent physical-access benchmark. Real source files, raw bytes,
compressed frames, serialized frame/line indexes and os.pread. Locations of
sampled spans are given to the physical reader (oracle coordinates). The FTS5
index is real and charged in footprint, but retrieval accuracy is NOT measured.
No claim of actual cold-cache I/O or QA accuracy.
"""
from __future__ import annotations
import argparse, ctypes, ctypes.util, hashlib, json, os, random, sqlite3, statistics, tempfile, time
from pathlib import Path

lib=ctypes.CDLL(ctypes.util.find_library('zstd') or 'libzstd.so')
lib.ZSTD_compressBound.argtypes=[ctypes.c_size_t];lib.ZSTD_compressBound.restype=ctypes.c_size_t
lib.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];lib.ZSTD_compress.restype=ctypes.c_size_t
lib.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];lib.ZSTD_decompress.restype=ctypes.c_size_t
lib.ZSTD_isError.argtypes=[ctypes.c_size_t];lib.ZSTD_isError.restype=ctypes.c_uint

def compress(src:bytes)->bytes:
    cap=lib.ZSTD_compressBound(len(src));out=ctypes.create_string_buffer(cap)
    inp=ctypes.create_string_buffer(src);n=lib.ZSTD_compress(out,cap,inp,len(src),3)
    if lib.ZSTD_isError(n):raise RuntimeError('zstd compress')
    return out.raw[:n]
def decompress(src:bytes,n:int)->bytes:
    out=ctypes.create_string_buffer(n); inp=ctypes.create_string_buffer(src)
    m=lib.ZSTD_decompress(out,n,inp,len(src))
    if lib.ZSTD_isError(m) or m!=n: raise ValueError('zstd frame corruption')
    return out.raw[:m]

def chunks(data:bytes,layout:str,size:int):
    if layout=='whole':return [(0,data)]
    if layout=='fixed':return [(i,data[i:i+size]) for i in range(0,len(data),size)]
    if layout!='lines':raise ValueError(layout)
    lines=data.splitlines(keepends=True)
    cur=bytearray(); start=0; out=[]
    for line in lines:
        if len(cur) and len(cur)+len(line)>size:
            out.append((start,bytes(cur)));start+=len(cur);cur=bytearray()
        while len(line)>size:
            need=size-len(cur)
            cur.extend(line[:need]);line=line[need:]
            out.append((start,bytes(cur)));start+=len(cur);cur=bytearray()
        cur.extend(line)
    if cur:out.append((start,bytes(cur)))
    return out

def make_db(dbpath:Path):
    db=sqlite3.connect(str(dbpath));db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL');db.executescript('''
      CREATE TABLE sources (source_id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,version INTEGER NOT NULL,sha256 TEXT NOT NULL,raw_len INTEGER NOT NULL);
      CREATE TABLE frames (source_id INTEGER NOT NULL, raw_start INTEGER NOT NULL,raw_end INTEGER NOT NULL, payload_offset INTEGER NOT NULL,payload_length INTEGER NOT NULL, PRIMARY KEY(source_id,raw_start));
      CREATE TABLE lines (line_id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,raw_start INTEGER NOT NULL,raw_end INTEGER NOT NULL,body TEXT NOT NULL);
      CREATE INDEX frames_source_end ON frames(source_id,raw_end);
      CREATE INDEX lines_source_start ON lines(source_id,raw_start);
      CREATE VIRTUAL TABLE lines_fts USING fts5(body,content='lines',content_rowid='line_id');
    ''');return db

def line_spans(data:bytes):
    off=0;out=[]
    for line in data.splitlines(keepends=True):
        out.append((off,off+len(line),line.decode('utf-8',errors='replace').strip()));off+=len(line)
    return out

def build(root:Path,inputs:list[Path],layout:str,size:int):
    root.mkdir(parents=True,exist_ok=True);db=make_db(root/'index.sqlite');payload=(root/'frames.zst').open('wb');records=[]
    try:
      for source_id,p in enumerate(inputs,1):
        data=p.read_bytes(); digest=hashlib.sha256(data).hexdigest();db.execute('INSERT INTO sources VALUES (?,?,?,?,?)',(source_id,p.name,1,digest,len(data)))
        offset=payload.tell()
        for start,block in chunks(data,layout,size):
            c=compress(block);payload.write(c)
            db.execute('INSERT INTO frames VALUES (?,?,?,?,?)',(source_id,start,start+len(block),offset,len(c)))
            offset+=len(c)
        for low,high,txt in line_spans(data):
            db.execute('INSERT INTO lines(source_id,raw_start,raw_end,body) VALUES (?,?,?,?)',(source_id,low,high,txt))
            line_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO lines_fts(rowid,body) VALUES (?,?)',(line_id,txt))
        records.append({'name':p.name,'bytes':len(data),'sha256':digest})
      db.commit()
    finally:payload.close();db.close()
    return records

def read_spans(db:sqlite3,fd:int,source_id:int,intervals:list[tuple[int,int]]):
    # Correct physical byte reads; do not count a shared frame twice.
    needed={}
    for a,b in intervals:
        if a<0 or b<a:raise ValueError('bad interval')
        if a==b:continue
        for frame in db.execute('SELECT raw_start,raw_end,payload_offset,payload_length FROM frames WHERE source_id=? AND raw_end>? AND raw_start<? ORDER BY raw_start',(source_id,a,b)):
            needed[frame[0]]=frame
    decoded=[];compressed_bytes=0
    for fr in sorted(needed.values()):
        start,end,offset,n=fr;compressed=os.pread(fd,n,offset)
        if len(compressed)!=n:raise IOError('short read')
        decoded.append((start,decompress(compressed,end-start)));compressed_bytes+=n
    result=[]
    for a,b in intervals:
        spans=[]
        for start,content in decoded:
            low=max(a,start);high=min(b,start+len(content))
            if low<high:spans.append((low,content[low-start:high-start]))
        spans.sort(key=lambda z:z[0]);out=b''.join(x for _,x in spans)
        if len(out)!=b-a:raise AssertionError('non-covering frames')
        result.append(out)
    return result,compressed_bytes,len(needed)

def make_queries(inputs:list[Path],n:int,seed:int,subspan:bool):
    rnd=random.Random(seed);lines=[]
    for si,p in enumerate(inputs,1):
        data=p.read_bytes()
        spans=[(a,b) for a,b,txt in line_spans(data) if b-a>=45]
        for j,(a,b) in enumerate(spans):lines.append((si,a,b,j))
    q=[]
    for iteration in range(n):
        si,a,b,j=rnd.choice(lines)
        matching=[(sj,x,y,k) for sj,x,y,k in lines if sj==si and abs(k-j)<=2 and k!=j]
        other=rnd.choice(matching) if iteration%3==0 and matching else rnd.choice(lines)
        selected=[]
        for s,x,y,k in [(si,a,b,j),other]:
            if subspan:
                length=min(64,max(12,(y-x)//3));pos=rnd.randint(x,y-length);x,y=pos,pos+length
            selected.append((s,x,y))
        q.append(selected)
    return q

def evaluate(indexdir:Path,queries,refs):
    db=sqlite3.connect(str(indexdir/'index.sqlite'));fd=os.open(indexdir/'frames.zst',os.O_RDONLY)
    elapsed=[];bytes_read=[];frames=[];fail=0
    # FTS query proves the serialized search index is operational; it is not used to generate spans.
    fts_hits=db.execute('SELECT count(*) FROM lines_fts WHERE lines_fts MATCH ?',('retrieval',)).fetchone()[0]
    try:
      for query in queries:
        start=time.perf_counter_ns();got=[];bc=0;nf=0
        for sid in sorted(set(s for s,a,b in query)):
            iv=[(a,b) for s,a,b in query if s==sid]
            data,br,fn=read_spans(db,fd,sid,iv);got+=[(sid,a,b,t) for (a,b),t in zip(iv,data)];bc+=br;nf+=fn
        elapsed.append((time.perf_counter_ns()-start)/1000);bytes_read.append(bc);frames.append(nf)
        for sid,a,b,t in got:
            if t!=refs[sid][a:b]:fail+=1
    finally:os.close(fd);db.close()
    if fail:raise AssertionError(f'{fail} failed roundtrips')
    disk=indexdir/'index.sqlite';payload=indexdir/'frames.zst';db=sqlite3.connect(str(disk))
    nframes=db.execute('SELECT count(*) FROM frames').fetchone()[0];nlines=db.execute('SELECT count(*) FROM lines').fetchone()[0];db.close()
    return {'query_count':len(queries),'verified_bytewise':fail==0,'compressed_payload_bytes':payload.stat().st_size,'sqlite_index_bytes':disk.stat().st_size,'total_persistent_bytes':payload.stat().st_size+disk.stat().st_size,'frames':nframes,'lines':nlines,'fts_retrieval_hits':fts_hits,'mean_compressed_bytes_per_request':round(statistics.mean(bytes_read),1),'median_compressed_bytes_per_request':statistics.median(bytes_read),'mean_frames_per_request':round(statistics.mean(frames),2),'warm_p50_us':round(statistics.median(elapsed),1),'warm_p95_us':round(sorted(elapsed)[int(.95*(len(elapsed)-1))],1),'latency_scope':'Python sqlite queries + os.pread + zstd decode + extraction, page cache NOT explicitly dropped, no answer model'}

def mutation_trial(root:Path,inputs:list[Path],size:int):
    with tempfile.TemporaryDirectory(prefix='cdg-version-') as td:
        p=Path(td)/'source.txt';p.write_bytes(inputs[0].read_bytes())
        build(root,[p],'lines',size)
        db=sqlite3.connect(root/'index.sqlite');fr=db.execute('SELECT raw_start,raw_end FROM frames ORDER BY raw_start LIMIT 1').fetchone();db.close();fd=os.open(root/'frames.zst',os.O_RDONLY);db=sqlite3.connect(root/'index.sqlite');old=read_spans(db,fd,1,[(fr[0],fr[1])])[0][0];os.close(fd);db.close()
        p.write_bytes(b'UPDATED SOURCE\n'+p.read_bytes())
        candidate=hashlib.sha256(p.read_bytes()).hexdigest();db=sqlite3.connect(root/'index.sqlite');record=db.execute('SELECT sha256 FROM sources WHERE source_id=1').fetchone()[0];db.close();rejected=record!=candidate
        # Rebuild in a new location atomically via rename of directory would be production work.
        replacement=Path(td)/'replacement';build(replacement,[p],'lines',size)
        db=sqlite3.connect(replacement/'index.sqlite');new_hash=db.execute('SELECT sha256 FROM sources').fetchone()[0];db.close()
        return {'stale_hash_refused':rejected,'replacement_hash_current':new_hash==candidate,'old_byte_receipt_unchanged':len(old)==fr[1]-fr[0],'update_mode':'full rebuild, not incremental; no atomic switch or concurrent readers'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--files',type=Path,nargs='+',required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--workdir',type=Path);ap.add_argument('--queries',type=int,default=250);args=ap.parse_args()
    inputs=args.files;refs={i:p.read_bytes() for i,p in enumerate(inputs,1)}
    output={'version':'round28-v1','source_provenance':[],'workloads':{},'mutation':{},'notes':['All compressed payload and SQLite index bytes are actual local files','Queries use known source spans; index/search cost is charged as storage but search accuracy is not evaluated','Warm latencies include Python and OS file reads, do not establish cold NVMe performance']}
    with tempfile.TemporaryDirectory(prefix='cdg-r28-') if not args.workdir else _unused_context(args.workdir) as home:
        root=Path(home)
        for mode in ('wholeline','subspan'):
            q=make_queries(inputs,args.queries,28026,mode=='subspan')
            output['workloads'][mode]={}
            for layout,size in [('whole',0),('fixed',256),('lines',256),('fixed',512),('lines',512),('fixed',2048),('lines',2048)]:
                name=f'{layout}_{size}';directory=root/mode/name
                src=build(directory,inputs,layout,size)
                if not output['source_provenance']:output['source_provenance']=src
                output['workloads'][mode][name]=evaluate(directory,q,refs)
        output['mutation']=mutation_trial(root/'mutation',inputs,512)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({'sources':len(inputs),'workloads':{m:{k:(v['total_persistent_bytes'],v['mean_compressed_bytes_per_request'],v['warm_p50_us']) for k,v in block.items()} for m,block in output['workloads'].items()},'mutation':output['mutation']},indent=2))
class _unused_context:
    def __init__(self,path):self.path=path
    def __enter__(self):self.path.mkdir(parents=True,exist_ok=True);return self.path
    def __exit__(self,*args):return False
if __name__=='__main__':main()