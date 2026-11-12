"""Build-time pilot routing: choose flat or group-bounded exact cosine search.
Does not use relevance labels. Synthetic vectors simulate tight and diffuse document families.
Cost of source compression, index training, pilot, model inference excluded from query timings.
"""
import numpy as np,time,json,heapq
from pathlib import Path
rng=np.random.default_rng(608)
D=96;k=5
res=[]

def direct(v,q):
 s=v@q
 return np.argpartition(-s,k-1)[:k]
def group(v,c,r,q,gsize):
 bd=c@q+r
 order=np.argsort(-bd)
 heap=[]
 for g in order:
  if len(heap)>=k and bd[g]<heap[0][0]-1e-5:break
  sc=v[g*gsize:(g+1)*gsize]@q
  for j,x in enumerate(sc):
   rec=(float(x),-(g*gsize+j))
   if len(heap)<k:heapq.heappush(heap,rec)
   elif rec[0]>heap[0][0]:heapq.heapreplace(heap,rec)
 return np.array([-j for _,j in heap],dtype=np.int32)

def timed(fun,*args):
 t=time.perf_counter_ns(); ret=fun(*args); return (time.perf_counter_ns()-t)/1000,ret

for n in [250,5000,50000]:
 gsize=5 if n==250 else 25
 centers=rng.standard_normal((n//gsize,D),dtype=np.float32)
 centers/=np.linalg.norm(centers,axis=1,keepdims=True)
 for sigma in [0.02,0.10,0.25]:
  V=np.repeat(centers,gsize,axis=0)+sigma*rng.standard_normal((n,D),dtype=np.float32)
  V/=np.linalg.norm(V,axis=1,keepdims=True)
  C=V.reshape(-1,gsize,D).mean(axis=1)
  R=np.linalg.norm(V.reshape(-1,gsize,D)-C[:,None,:],axis=2).max(axis=1)
  indices=rng.choice(n,size=70,replace=False)
  Q=V[indices]+0.025*rng.standard_normal((70,D),dtype=np.float32)
  Q/=np.linalg.norm(Q,axis=1,keepdims=True)
  for q in Q[:10]:direct(V,q);group(V,C,R,q,gsize)
  pilot={'flat':[],'bounded':[]};test={'flat':[],'bounded':[]}
  valid=0;checked=0
  for idx,q in enumerate(Q):
   ta,a=timed(direct,V,q)
   tb,b=timed(group,V,C,R,q,gsize)
   if idx<10:
    pilot['flat'].append(ta);pilot['bounded'].append(tb)
   else:
    test['flat'].append(ta);test['bounded'].append(tb)
    sc=V@q
    kth=float(np.partition(sc,-k)[-k]);bsc=np.sort(sc[b])
    checked+=1
    valid+=int(abs(float(bsc[0])-kth)<1e-4)
  mode=min(pilot,key=lambda m:np.median(pilot[m]))
  metrics={'N':n,'sigma':sigma,'median_group_radius':round(float(np.median(R)),4),
           'chosen_mode':mode,'pilot_flat_us':round(float(np.median(pilot['flat'])),1),
           'pilot_bounded_us':round(float(np.median(pilot['bounded'])),1),
           'heldout_flat_us':round(float(np.median(test['flat'])),1),
           'heldout_bounded_us':round(float(np.median(test['bounded'])),1),
           'heldout_adaptive_us':round(float(np.median(test[mode])),1),
           'bounded_top5_score_correct':f'{valid}/{checked}'}
  print(metrics,flush=True);res.append(metrics)
(Path(__file__).resolve().parent/'round4_adaptive_results.json').write_text(json.dumps(res,indent=2))
