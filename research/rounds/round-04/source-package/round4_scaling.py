"""Controlled synthetic vector index microbenchmark. Clusters emulate version families.
Measures wall-clock and exact top-k score preservation; NOT neural RAG or real corpus.
"""
import os,json,time,numpy as np
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1'
rng=np.random.default_rng(1729)
out=[]
D=96;k=5
for N in [250,5000,50000]:
 group_size=25 if N>=5000 else 5
 NG=N//group_size
 base=rng.normal(size=(NG,D)).astype(np.float32)
 base/=np.linalg.norm(base,axis=1,keepdims=True)
 for sigma in [0.02,0.10,0.25]:
  V=np.repeat(base,group_size,axis=0)+sigma*rng.normal(size=(N,D)).astype(np.float32)
  V/=np.linalg.norm(V,axis=1,keepdims=True)
  V=np.ascontiguousarray(V)
  C=V.reshape(NG,group_size,D).mean(axis=1)
  R=np.linalg.norm(V.reshape(NG,group_size,D)-C[:,None,:],axis=2).max(axis=1)
  picks=rng.choice(N,size=80,replace=False)
  queries=V[picks]+0.025*rng.normal(size=(len(picks),D)).astype(np.float32)
  queries/=np.linalg.norm(queries,axis=1,keepdims=True)
  # warmup
  V@queries[0];C@queries[0]
  full_us=[];bound_us=[];nsc=[];nfam=[];wrong=0;regret=[]
  for q in queries:
   s=time.perf_counter_ns()
   full=V@q
   part=np.argpartition(-full,k-1)[:k]
   exact_ids=part[np.argsort(-full[part])]
   t=time.perf_counter_ns()
   bounds=C@q+R
   gi=np.argsort(-bounds)
   # Exact-score topk maintained after block-level upper bound pruning
   keep=np.empty((0,),dtype=np.float32)
   gids=np.empty((0,),dtype=np.int32)
   docs=0;gs=0;threshold=-np.inf
   for g in gi:
    if len(keep)>=k and bounds[g]<threshold-1e-6:break
    gs+=1
    ix=np.arange(g*group_size,(g+1)*group_size,dtype=np.int32)
    sc=V[g*group_size:(g+1)*group_size]@q
    docs+=len(sc)
    keep=np.concatenate((keep,sc));gids=np.concatenate((gids,ix))
    if len(keep)>k:
     ixk=np.argpartition(-keep,k-1)[:k]
     keep,gids=keep[ixk],gids[ixk]
    if len(keep)>=k:threshold=float(np.min(keep))
   end=time.perf_counter_ns()
   full_us.append((t-s)/1e3);bound_us.append((end-t)/1e3)
   nsc.append(docs);nfam.append(gs)
   if set(gids)!=set(exact_ids):
    kth=float(full[exact_ids[-1]])
    missed=[d for d in exact_ids if d not in gids]
    if any(full[d]>kth+1e-5 for d in missed):wrong+=1
   regret.append(float(max(0,np.min(full[exact_ids])-np.min(full[gids]))))
  o={'N':N,'group_size':group_size,'sigma':sigma,'num_groups':NG,
     'median_exhaustive_us':round(float(np.median(full_us)),2),
     'median_bounded_us':round(float(np.median(bound_us)),2),
     'p95_exhaustive_us':round(float(np.percentile(full_us,95)),2),
     'p95_bounded_us':round(float(np.percentile(bound_us,95)),2),
     'mean_docs_exact_scored':round(float(np.mean(nsc)),2),
     'mean_groups_exact_scored':round(float(np.mean(nfam)),2),
     'fraction_docs_pruned':round(1-float(np.mean(nsc))/N,4),
     'errors_beyond_ties':wrong,
     'max_topk_score_regret':round(float(max(regret)),7)}
  print(o,flush=True);out.append(o)
(Path(__file__).resolve().parent/'round4_scaling_results.json').write_text(json.dumps(out,indent=2))
