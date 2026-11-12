#!/usr/bin/env python3
"""Look for number-of-piece reconstruction overhead on held-out window queries."""
import sys,contextlib,io,bisect,time,random,collections,json
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
with contextlib.redirect_stdout(io.StringIO()):import round6_access_policy as a

def stats(i,start,stop):
 rec,ends,path,items=a.metas[i]
 k=bisect.bisect_right(ends,start)
 pieces=literals=baseframes=0
 while k<len(ends) and (ends[k-1] if k else 0)<stop:
  before=ends[k-1] if k else 0
  hi=min(stop-before,ends[k]-before);lo=max(0,start-before)
  if hi>lo:
   pieces+=1
   if items[k] is None:
    p=a.r.piece_tables[i][0][k]
    x=p[1]+lo;y=p[1]+hi
    baseframes+=(y-1)//32-x//32+1
   else:literals+=1
  k+=1
 return pieces,literals,baseframes

qs=list(a.test_same+a.test_shift)
samples=[];rr=random.Random(81782)
for rep in range(3):
 qq=list(qs);rr.shuffle(qq)
 for i,s,t in qq:
  pieces,lits,frames=stats(i,s,t)
  start=time.perf_counter_ns();got=a.read_policy(a.policies['threshold256'],i,s,t)
  dt=(time.perf_counter_ns()-start)/1000
  samples.append((pieces,lits,frames,dt))
  assert got==b''.join(a.r.files[i].splitlines(keepends=True)[s:t])
rows={}
for name,filterfn in [('one_piece',lambda p,l,f:p==1),('two_pieces',lambda p,l,f:p==2),('3plus_pieces',lambda p,l,f:p>=3),('literals_in_window',lambda p,l,f:l>0),('stable_only',lambda p,l,f:l==0)]:
 data=[t for p,l,f,t in samples if filterfn(p,l,f)]
 rows[name]={'n':len(data),'median_us':round(float(np.median(data)),2),'p95_us':round(float(np.percentile(data,95)),2)} if data else {'n':0}
cor=spearmanr([p for p,l,f,t in samples],[t for p,l,f,t in samples])
result={'rows':rows,'spearman_piece_count_vs_time':round(float(cor.statistic),3),'sample_count':len(samples),'interpretation':'Descriptive association; larger/crossed windows may have other differences in code paths and source sizes.', 'limitations':['One process, repeated warm timings, synthetic windows.','Not a causal ablation of piece count.']}
(HERE/'round6_piece_diagnostics_results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
