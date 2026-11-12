#!/usr/bin/env python3
"""Workload-learned selective seekable evidence frames on top of a shared base/patch source.
Uses held-out synthetic access traces over real Git revision bytes; not neural retrieval.
"""
from pathlib import Path
import sys,contextlib,io,bisect,collections,random,time,json
import numpy as np
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
with contextlib.redirect_stdout(io.StringIO()):
 import round6_access_policy as a
selected=a.policies['threshold256'];rng=random.Random(812)
FRAME=32
# Prebuild optional independent frames, but charge all selected ones to stored source bytes.
# These are an *additional* fast-path representation; cold queries fall through to lossless piece store.
possible={};counts=collections.Counter();overlap=collections.Counter()
for i,start,stop in a.train:
 for k in range(start//FRAME,(stop-1)//FRAME+1):
  key=(i,k);counts[key]+=1
  if key not in possible:
   lines=a.r.files[i].splitlines(keepends=True)
   raw=b''.join(lines[k*FRAME:(k+1)*FRAME]);possible[key]=(a.Z.compress(raw,3),len(raw))

# For selecting frames score expected frequency per compressed byte, with edit-aware
# penalty proxy for crossing multiple pieces; this is estimated only on train windows.
def pc(i,start,stop):
 rec,ends,path,items=a.metas[i];j=bisect.bisect_right(ends,start);c=0
 while j<len(ends) and (ends[j-1] if j else 0)<stop:
  c+=1;j+=1
 return c

for i,start,stop in a.train:
 if pc(i,start,stop)>=3:
  for k in range(start//FRAME,(stop-1)//FRAME+1):overlap[(i,k)]+=1

def choose(budget,mode):
 keys=list(possible)
 if mode=='hot':keys.sort(key=lambda key:(counts[key]*(1+overlap[key]/max(counts[key],1)))/(len(possible[key][0])+8),reverse=True)
 elif mode=='hot_plain':keys.sort(key=lambda key:counts[key]/(len(possible[key][0])+8),reverse=True)
 elif mode=='random':random.Random(912).shuffle(keys)
 remain=budget;chosen=set()
 for key in keys:
  n=len(possible[key][0])+8
  if n<=remain:chosen.add(key);remain-=n
 return chosen,budget-remain

def read(i,start,stop,chosen):
 first=start//FRAME;last=(stop-1)//FRAME
 if all((i,k) in chosen for k in range(first,last+1)):
  parts=[]
  for k in range(first,last+1):
   z,n=possible[(i,k)];decoded=a.Z.decompress(z,n).splitlines(keepends=True);off=k*FRAME
   parts.extend(decoded[max(0,start-off):min(stop-off,FRAME)])
  return b''.join(parts),True
 return a.read_policy(selected,i,start,stop),False

results={}
for budget in [48*1024,128*1024]:
 policy={m:choose(budget,m) for m in ['hot','hot_plain','random']}
 modes={'piece_only':(set(),0),**policy}
 experiment={}
 for split,qs in [('same',a.test_same),('shift',a.test_shift)]:
  duration={m:[] for m in modes};direct={m:0 for m in modes}
  rr=random.Random(17271)
  for rep in range(4):
   order=list(modes);rr.shuffle(order)
   for mode in order:
    qq=list(qs);rr.shuffle(qq)
    for i,s,t in qq:
     t0=time.perf_counter_ns();got,used=read(i,s,t,modes[mode][0]);duration[mode].append((time.perf_counter_ns()-t0)/1000)
     direct[mode]+=int(used)
     assert got==b''.join(a.r.files[i].splitlines(keepends=True)[s:t])
  experiment[split]={m:{'median_us':round(float(np.median(d)),2),'p95_us':round(float(np.percentile(d,95)),2), 'direct_hit_fraction':round(direct[m]/(len(qs)*4),3), 'source_bytes':a.storage(selected)+modes[m][1]} for m,d in duration.items()}
 results[str(budget)]={'selected_frames':{m:len(s) for m,(s,n) in modes.items()}, 'measured':experiment}

out={'study':'Access-trained selective 32-line materializations on real versioned source, synthetic query logs',
 'total_source_raw_bytes':sum(len(x) for x in a.r.files),'compressed_piece_store_bytes':a.storage(selected),
 'policy':'Choose materialized compressed frames using training access frequency and multi-piece overlap, constrained by extra storage budget',
 'results':results,
 'exactness':'All sampled held-out windows verified byte exact',
 'limitations':['Materialized frames only generated for frames observed in training queries; unseen frames fall back.', 'Hot selection is workload-specific.','Warm CPU, loaded metadata. No SSD or LLM.','This is selective materialized-view caching, an established technique; no novelty claim.', 'No full-frame rebuild/update cost measured.']}
(ROOT/'round6_materialized_results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
