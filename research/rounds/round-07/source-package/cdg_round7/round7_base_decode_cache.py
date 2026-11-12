#!/usr/bin/env python3
"""Round 7B: measure per-request decoded-frame reuse, no persistent cache.
Tests whether fragmented span reconstruction redundantly decompresses the same
shared base frame multiple times within a single request. Warm Python CPU only.
"""
from __future__ import annotations
import bisect,json,random,struct,time,sys,io,contextlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).parent
src=(ROOT/'round7_span_coalescing.py').read_text().split('layouts={v:')[0]
ns={'__name__':'cdg_span_module','__file__':str(ROOT/'round7_span_coalescing.py')}
with contextlib.redirect_stdout(io.StringIO()):exec(compile(src,str(ROOT/'round7_span_coalescing.py'),'exec'),ns)
a=ns['a'];Z=a.Z;L=ns['Layout'](8)

def read_request_cached(i,start,stop):
 path,metadata,ends,litkeys=L.vs[i]
 cache={};out=[];j=bisect.bisect_right(ends,start)
 while j<len(ends) and (ends[j-1] if j else 0)<stop:
  kind,x,y,n,_=struct.unpack_from('<BIIII',metadata,17*j)
  off=ends[j-1] if j else 0
  lo=max(0,start-off);hi=min(n,stop-off)
  if lo<hi:
   if kind==0:
    xx=x+lo;yy=x+hi;chunks=[]
    for b in range(xx//32,(yy-1)//32+1):
     lines=cache.get(b)
     if lines is None:
      zz,nbytes=a.base_frames[path][b]
      lines=Z.decompress(zz,nbytes).splitlines(keepends=True)
      cache[b]=lines
     offset=b*32
     chunks.extend(lines[max(0,xx-offset):min(yy-offset,32)])
    out.append(b''.join(chunks))
   else:
    z,rawlen,israw=L.lit_store[litkeys[j]]
    raw=z if israw else Z.decompress(z,rawlen)
    out.append(b''.join(raw.splitlines(keepends=True)[lo:hi]))
  j+=1
 return b''.join(out)

def queries_for_length(n):
 arr=[]
 for i,s,t in a.test_same[:500]+a.test_shift[:500]:
  total=len(a.r.files[i].splitlines(keepends=True))
  cen=(s+t)//2;start=max(0,min(cen-n//2,max(0,total-n)))
  arr.append((i,start,min(total,start+n)))
 return arr

res={}
for n in [1,5,20,40]:
 qs=queries_for_length(n)
 for i,s,t in qs:
  correct=b''.join(a.r.files[i].splitlines(keepends=True)[s:t])
  assert L.read(i,s,t)==correct
  assert read_request_cached(i,s,t)==correct
 vals={'uncached':[],'request_cache':[]};rnd=random.Random(100000+n)
 for rep in range(5):
  modes=list(vals);rnd.shuffle(modes)
  for mode in modes:
   q=list(qs);rnd.shuffle(q)
   for i,s,t in q:
    tic=time.perf_counter_ns()
    (L.read if mode=='uncached' else read_request_cached)(i,s,t)
    vals[mode].append((time.perf_counter_ns()-tic)/1000)
 res[str(n)]={name:{'median_us':round(float(np.median(v)),2),'p95_us':round(float(np.percentile(v,95)),2)} for name,v in vals.items()}
output={'source_bytes':L.bytes,'method':'Per-query memoization of decoded 32-line base frames, compared with identical piece assembly without memoization. Cost of cache map built within every timed request.',
 'span_lengths':res,'exactness':'All 1000 exact spans per span size verified against original source and both reader implementations','limitations':['Warm Python CPU microbenchmark','Does not evaluate persistent caching nor SSD','Query windows derived from synthetic traces over genuine source edits']}
(ROOT/'round7_cache_results.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
