#!/usr/bin/env python3
"""Fair fixed RAM-budget cache comparison: shared immutable base frames vs per-version frames.
No model or actual SSD; query traces synthetic over real noVNC versioned bytes.
"""
import sys,contextlib,io,random,time,collections,bisect,struct,json,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
with contextlib.redirect_stdout(io.StringIO()): import round6_access_policy as a

class LRU:
 def __init__(self,budget):self.budget=budget;self.data=collections.OrderedDict();self.bytes=0;self.hits=0;self.misses=0
 def get(self,key,decode):
  if key in self.data:
   val=self.data.pop(key);self.data[key]=val;self.hits+=1;return val
  self.misses+=1;val=decode();size=sum(map(len,val))
  if size>self.budget:return val
  while self.bytes+size>self.budget:
   _,old=self.data.popitem(last=False);self.bytes-=sum(map(len,old))
  self.data[key]=val;self.bytes+=size
  return val

def shared_read(i,start,stop,cache,selected):
 recs,ends,path,items=a.metas[i];out=[]
 k=bisect.bisect_right(ends,start)
 while k<len(ends):
  prev=ends[k-1] if k else 0
  if prev>=stop:break
  kind,x,y,n,_=struct.unpack_from('<BIIII',recs,k*17)
  aa=max(0,start-prev);bb=min(n,stop-prev)
  if aa<bb:
   if kind==0:
    parts=[];j0=x+aa;j1=x+bb
    for fr in range(j0//32,(j1-1)//32+1):
     z,zlen=a.base_frames[path][fr]
     lines=cache.get((path,fr),lambda z=z,zlen=zlen:a.Z.decompress(z,zlen).splitlines(keepends=True))
     off=fr*32;parts.extend(lines[max(0,j0-off):min(j1-off,32)])
    out.append(b''.join(parts))
   else:
    raw,z=a.literal_data[items[k]]
    piece=raw if items[k] in selected else a.Z.decompress(z,len(raw))
    out.append(b''.join(piece.splitlines(keepends=True)[aa:bb]))
  k+=1
 return b''.join(out)

def independent_read(i,start,stop,cache):
 parts=[]
 for fr in range(start//32,(stop-1)//32+1):
  z,zlen=a.frames[i][fr]
  lines=cache.get((i,fr),lambda z=z,zlen=zlen:a.Z.decompress(z,zlen).splitlines(keepends=True))
  off=fr*32;parts.extend(lines[max(0,start-off):min(stop-off,32)])
 return b''.join(parts)

result={}
for workload_name,qs in [('same',a.test_same),('shift',a.test_shift)]:
 result[workload_name]={}
 for budget in [512*1024,1024*1024]:
  data={}
  for mode in ['shared','independent']:
   cache=LRU(max(0,budget-a.resident_meta) if mode=='shared' else budget);times=[]
   # Warm beginning by standard stream order; measure steady state afterward.
   for i,s,t in qs[:250]:
    if mode=='shared':shared_read(i,s,t,cache,a.policies['threshold256'])
    else:independent_read(i,s,t,cache)
   cache.hits=cache.misses=0
   for i,s,t in qs:
    t0=time.perf_counter_ns()
    got=shared_read(i,s,t,cache,a.policies['threshold256']) if mode=='shared' else independent_read(i,s,t,cache)
    times.append((time.perf_counter_ns()-t0)/1000)
    assert got==b''.join(a.r.files[i].splitlines(keepends=True)[s:t])
   data[mode]={'median_us':round(float(np.median(times)),2),'p95_us':round(float(np.percentile(times,95)),2),
       'frame_cache_hits':cache.hits,'frame_cache_misses':cache.misses,
       'frame_hit_rate':round(cache.hits/(cache.hits+cache.misses),4) if cache.hits+cache.misses else 0,
       'resident_decoded_bytes':cache.bytes}
  result[workload_name][str(budget)]=data
out={'study':'Equal RAM budgets for decoded base-frame caching; real version bytes, synthetic requests.',
 'source_storage':{'cdg_threshold256':a.storage(a.policies['threshold256']),'independently_seekable32':a.frame_size},
 'resident_piece_map_bytes_cdg_deducted_from_shared_cache_budget':a.resident_meta,
 'nominal_payload_budget_identical_and_shared_piece_map_deducted':True,'measurements':result,
 'limitations':['Warm CPU only, no SSD or actual semantic retrieval.','Packed CDG piece-map bytes are deducted from the nominal budget; Python object overhead for both cached line lists and metadata is not counted, so this is NOT a true equal-process-RSS comparison.', 'One pass steady-state latency per workload, subject to CPU variance.', 'The source layout and queries remain favorable to shared document version representations.']}
(ROOT/'round6_fair_ram_cache_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
