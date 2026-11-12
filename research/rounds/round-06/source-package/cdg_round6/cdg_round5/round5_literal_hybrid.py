"""Try raw short literals and compressed long literals for efficient change-region passage access.
Each block stores exact literal bytes, possibly compressed. No real neural model.
"""
import sys,json,time,random,struct,bisect
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_compact_metadata as c
r=c.src.r;Z=c.src.Z
rng=random.Random(9441)
queries=[]
for i,(pieces,ends) in enumerate(r.piece_tables):
  ls=[j for j,a in enumerate(pieces) if a[0]=='lit' and a[-1]>0]
  if not ls:continue
  j=rng.choice(ls);total=ends[-1];first=ends[j-1] if j else 0
  mid=first+pieces[j][-1]//2;start=min(max(0,mid-2),max(0,total-5));queries.append((i,start,min(total,start+5)))

def encode(thresh):
  blobs=[];total=0
  for pts,_ in r.piece_tables:
   arr=[]
   for a in pts:
    if a[0]!='lit':arr.append(None);continue
    raw=a[1]
    if len(raw)<=thresh:b=(0,raw,len(raw))
    else:b=(1,Z.compress(raw,3),len(raw))
    arr.append(b)
    total+=len(b[1])+5
   blobs.append(arr)
  return blobs,total

def read(i,start,stop,frames):
  records,ends,path,lit,litlen=c.compact[i]
  k=bisect.bisect_right(ends,start);out=[]
  while k<len(ends):
   prev=ends[k-1] if k else 0
   if prev>=stop:break
   kind,x,y,nlines,_=struct.unpack_from('<BIIII',records,17*k)
   a=max(0,start-prev);b=min(nlines,stop-prev)
   if a<b:
    if kind==0:piece=c.src.base_slice(path,x+a,x+b)
    else:
     codec,buf,sz=frames[i][k]
     raw=buf if codec==0 else Z.decompress(buf,sz)
     piece=b''.join(raw.splitlines(keepends=True)[a:b])
    out.append(piece)
   k+=1
  return b''.join(out)

results={}
for th in [0,32,64,128,256,512,2048,1000000]:
  frames,size=encode(th)
  times=[]
  for repeat in range(3):
   qq=list(queries);rng.shuffle(qq)
   for i,a,b in qq:
    t0=time.perf_counter_ns();got=read(i,a,b,frames);t1=time.perf_counter_ns()
    times.append((t1-t0)/1000)
    assert got==b''.join(r.files[i].splitlines(keepends=True)[a:b])
  results[str(th)]={'total_disk_source_bytes':c.src.base_bytes+c.src.piece_meta_bytes+size,
                   'median_change_window_us':round(float(np.median(times)),2),
                   'p95_change_window_us':round(float(np.percentile(times,95)),2)}
out={'change_windows':len(queries),'threshold_bytes':'literals <= threshold stored raw; larger literals independently compressed zstd3',
 'results':results,'cautions':['Byte exact changed windows only, full document reconstruction already verified for underlying piece model.',
 'Warm CPU timings and resident index; no disk I/O.', 'This storage layout replaces per-version literal payload with many small frames, so metadata and compression overhead can increase.',
 'Query windows contain a changed span, but are not generated from natural-language information needs.']}
(ROOT/'round5_literal_hybrid_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
