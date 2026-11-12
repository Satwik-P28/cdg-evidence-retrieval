"""CDG experiment: exact top-k pruning on shared version groups, and compressed vector proxies.
Real noVNC commit subject queries (no human-annotated relevance). SVD vectors are NOT neural embeddings.
"""
import os,sys,json,time,math,zlib,statistics,collections
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from scipy import sparse
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'prev'/'cdg_round3'))
from git_history_retrieval import create
OUT=BASE
np.random.seed(17)
samples=create(250)
qtexts=[s['message'] for s in samples]
texts=[s['after'] for s in samples]
changes=[s['changed'] for s in samples]
paths=[s['path'] for s in samples]
N=len(samples)
assert N>=200
import re

def prep(s):
 s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s)
 return s.replace('_',' ').replace('.',' ').lower()
vec=TfidfVectorizer(preprocessor=prep,ngram_range=(1,2),min_df=1,sublinear_tf=True,token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
X=vec.fit_transform(texts+changes)
Q=vec.transform(qtexts)
# SVD proxy trained on corpus text only. Queries never used in its fitting.
svd=TruncatedSVD(n_components=96,n_iter=5,random_state=17)
t0=time.perf_counter()
Z=svd.fit_transform(X)
V=normalize(Z[:N].astype(np.float32))
W=normalize((Q@svd.components_.T).astype(np.float32))
svd_seconds=time.perf_counter()-t0
scores=W@V.T
k=5
order=np.argsort(-scores,axis=1,kind='stable');labels=np.arange(N)
ranks=np.empty(N,dtype=np.int32)
for i in range(N):ranks[i]=int(np.flatnonzero(order[i]==i)[0]+1)

def metrics(scores):
 order=np.argsort(-scores,axis=1,kind='stable')
 rr=np.array([int(np.flatnonzero(order[i]==i)[0]+1) for i in range(N)])
 return {'hit@1':round(float((rr<=1).mean()),4),'hit@5':round(float((rr<=5).mean()),4),'hit@10':round(float((rr<=10).mean()),4),'mrr@10':round(float(np.mean((rr<=10)/rr)),4)}

families=collections.defaultdict(list)
for i,p in enumerate(paths):families[p].append(i)

# All groupings are source-path aware; do not use query labels or query text to form groups.
def groups_for_size(max_group):
 groups=[]
 for p,ids in sorted(families.items()):
  for j in range(0,len(ids),max_group):
   groups.append(ids[j:j+max_group])
 return groups

def boundsearch(groups,k=5):
 # Exact certification for dot products in the 96D LSA proxy space.
 centroids=[];radii=[]
 for ids in groups:
  vv=V[ids];c=vv.mean(axis=0);centroids.append(c)
  radii.append(float(np.linalg.norm(vv-c,axis=1).max()))
 C=np.asarray(centroids);R=np.asarray(radii)
 upper=W@C.T+R[None,:]
 docs_processed=[];groups_examined=[];exact=[];safety_fail=0
 for qi in range(N):
  gorder=np.argsort(-upper[qi],kind='stable')
  retrieved=[];current=-float('inf');dcount=0;gcount=0
  for gid in gorder:
   # Skip only if upper bound is STRICTLY below current kth exact score.
   if len(retrieved)>=k and upper[qi,gid]<current-1e-6:break
   gcount+=1
   for d in groups[gid]:
    retrieved.append((float(scores[qi,d]),d));dcount+=1
   retrieved.sort(key=lambda s:(-s[0],s[1]))
   retrieved=retrieved[:k]
   if len(retrieved)>=k:current=retrieved[-1][0]
  got={d for _,d in retrieved}
  true={int(d) for d in order[qi,:k]}
  if got!=true:
   # tie cases where scores are exactly equal in top-k are possible; any tied docs are equally optimal
   kth=float(scores[qi,order[qi,k-1]])
   if not all(d in got or abs(float(scores[qi,d])-kth)<1e-5 for d in true):safety_fail+=1
  docs_processed.append(dcount);groups_examined.append(gcount)
 return {'groups':len(groups),'mean_group_size':round(N/len(groups),2),
         'mean_docs_scored':round(float(np.mean(docs_processed)),2),
         'median_docs_scored':float(np.median(docs_processed)),
         'p95_docs_scored':float(np.percentile(docs_processed,95)),
         'mean_groups_examined':round(float(np.mean(groups_examined)),2),
         'skipped_document_fraction':round(1-float(np.mean(docs_processed))/N,4),
         'safety_failures_excluding_ties':safety_fail,
         'centroid_bytes_fp32':int(C.nbytes),'radius_bytes_fp32':int(R.nbytes)}

out={'dataset':{'repo':'noVNC','commits':N,'families':len(families),'query_type':'real commit subjects','evaluation':'same-commit file-version weak label'},'method':'Non-neural TruncatedSVD(96) surrogate on TF-IDF, normalized vectors', 'fit_svd_seconds':round(svd_seconds,3),'full_svd_metrics':metrics(scores),'bounds':{}}
for g in [1,2,3,4,5,8,999]:
 out['bounds'][str(g)]=boundsearch(groups_for_size(g))
 print('bound',g,out['bounds'][str(g)],flush=True)

# Low-memory vector proxy: source-family shared centers plus top-m residual coordinates.
# This is lossy INDEX compression; original text always stays losslessly stored elsewhere.
def encode_residuals(m):
 groups=groups_for_size(999)
 centers=np.zeros_like(V)
 center_table=[]
 for ids in groups:
  centroid=V[ids].mean(axis=0)
  center_table.append(centroid)
  centers[ids]=centroid
 delta=V-centers
 arr=np.zeros_like(delta)
 for i in range(N):
  ix=np.argsort(-np.abs(delta[i]))[:m]
  arr[i,ix]=delta[i,ix].astype(np.float16).astype(np.float32)
 rec=centers+arr
 rec=normalize(rec)
 approx=W@rec.T
 # Search over quantized proxy, then optionally rerank candidate pool exactly.
 ord0=np.argsort(-approx,axis=1,kind='stable')
 qs={}
 for oversample in [1,2,4,8,16]:
  k=5
  mcan=min(N,k*oversample)
  cand=ord0[:,:mcan]
  # Rerank exactly inside candidate set only
  pred=[]
  for i in range(N):
   c=cand[i]
   pred.append(list(c[np.argsort(-scores[i,c],kind='stable')[:k]]))
  pred=np.array(pred)
  overlap=float(np.mean([len(set(pred[i])&set(order[i,:k]))/k for i in range(N)]))
  hit=float(np.mean([i in pred[i] for i in range(N)]))
  qs[str(oversample)]={'mean_exact_top5_overlap':round(overlap,4),'same_commit_hit_at5':round(hit,4),'exact_candidates_scored':mcan}
 # Uncompressed logical bytes: center fp16, per version m int8 indices + fp16 weights + mapping uint16
 # In practice indices could be compressed; account all here including per-doc group id.
 bytes_stored=len(groups)*96*2 + N*m*(1+2)+N*2
 full_fp32_bytes=V.nbytes
 full_int8_bytes=V.shape[0]*V.shape[1]+N*4
 return {'m':m,'bytes_shared_residual':bytes_stored,'full_fp32_bytes':full_fp32_bytes,
         'full_int8_bytes_excl_global_quantization':full_int8_bytes,
         'size_ratio_vs_full_fp32':round(full_fp32_bytes/bytes_stored,3),
         'top5_overlap_no_rerank':round(float(np.mean([len(set(ord0[i,:5])&set(order[i,:5]))/5 for i in range(N)])),4),
         'oversampling':qs}

out['residuals']={}
for m in [4,8,12,16,24,32,48,64,96]:
 out['residuals'][str(m)]=encode_residuals(m)
 print('residual',m,out['residuals'][str(m)]['size_ratio_vs_full_fp32'],out['residuals'][str(m)]['oversampling']['4'],flush=True)

# Strong challenge: quantized-full int8 vectors plus exact re-score against the same LSA surrogate.
scales=np.maximum(np.max(np.abs(V),axis=1,keepdims=True),1e-9)/127
approxv=np.rint(V/scales).astype(np.int8).astype(np.float32)*scales
approxv=normalize(approxv)
scoreq=W@approxv.T
ordo=np.argsort(-scoreq,axis=1,kind='stable')
for ov in [1,2,4,8]:
 hits=[];ovr=[]
 for qi in range(N):
  c=ordo[qi,:min(N,5*ov)]
  ix=c[np.argsort(-scores[qi,c],kind='stable')[:5]]
  hits.append(qi in ix)
  ovr.append(len(set(ix)&set(order[qi,:5]))/5)
 out.setdefault('full_int8',{})[str(ov)]={'hit_at5':round(float(np.mean(hits)),4),'overlap_exact_top5':round(float(np.mean(ovr)),4)}
OUT.joinpath('round4_bounds_results.json').write_text(json.dumps(out,indent=2))
print('RESULTS '+str(OUT/'round4_bounds_results.json'))

# End-to-end CPU timing for EXACT top-k retrieval in the LSA surrogate space.
# Full exhaustive dot-product baseline is vectorized and highly optimized.
# Bounds include group scoring, sorting, exact candidate scoring and result selection.
import heapq

def timed_exhaustive(q,k=5):
 sc=V@q
 ix=np.argpartition(-sc,k-1)[:k]
 return ix[np.argsort(-sc[ix],kind='stable')], int(N)

def timed_bounded(q,groups,C,R,k=5):
 bounds=C@q+R
 gorder=np.argsort(-bounds,kind='stable')
 heap=[];docs_scored=0
 for gid in gorder:
  if len(heap)>=k and bounds[gid]<heap[0][0]-1e-6:break
  ids=groups[gid]
  sc=V[ids]@q
  docs_scored+=len(ids)
  for j,d in enumerate(ids):
   score=float(sc[j]);rec=(score,-d)
   if len(heap)<k:heapq.heappush(heap,rec)
   elif score>heap[0][0]+1e-7:heapq.heapreplace(heap,rec)
 # index sorted by descending score
 ix=np.array([-d for s,d in sorted(heap,reverse=True)],dtype=np.int32)
 return ix,docs_scored

def run_timing(max_group):
 groups=groups_for_size(max_group)
 C=[];R=[]
 for ids in groups:
  cv=V[ids].mean(axis=0)
  C.append(cv)
  R.append(float(np.max(np.linalg.norm(V[ids]-cv,axis=1))))
 C=np.asarray(C,dtype=np.float32);R=np.asarray(R,dtype=np.float32)
 # warm up both paths
 for q in W[:20]:timed_exhaustive(q);timed_bounded(q,groups,C,R)
 times_full=[];times_bound=[];totals=[];correct=0
 for rep in range(3):
  for q in W:
   s=time.perf_counter_ns();ix_full,_=timed_exhaustive(q);t=time.perf_counter_ns();ix_g,num=timed_bounded(q,groups,C,R);end=time.perf_counter_ns()
   times_full.append((t-s)/1000);times_bound.append((end-t)/1000)
   totals.append(num)
   if len(set(ix_full)&set(ix_g))==5:correct+=1
 return {'max_group_size':max_group,'groups':len(groups),'median_us_exhaustive':round(float(np.median(times_full)),2),
         'median_us_bounded_python':round(float(np.median(times_bound)),2),
         'p95_us_exhaustive':round(float(np.percentile(times_full,95)),2),
         'p95_us_bounded_python':round(float(np.percentile(times_bound,95)),2),
         'mean_docs_scored':round(float(np.mean(totals)),2),
         'top5_set_agreement':round(correct/len(times_full),4)}

out['runtime']={}
for g in [2,3,4,8,999]:
 out['runtime'][str(g)]=run_timing(g)
 print('runtime',g,out['runtime'][str(g)],flush=True)
OUT.joinpath('round4_bounds_results.json').write_text(json.dumps(out,indent=2))

# Does the real document-change signal survive the same semantic proxy?
# Predefined 0.5/0.5 fusion, no relevance-label tuning.
V_change=normalize(Z[N:].astype(np.float32))
change_scores=W@V_change.T
out['semantic_proxy_comparison']={
 'full_document':metrics(scores),
 'changes_only':metrics(change_scores),
 'fused_half_half':metrics(.5*scores+.5*change_scores),
 'index_bytes_fp32_full':int(V.nbytes),
 'index_bytes_fp32_change':int(V_change.nbytes),
 'both_indexes_bytes_fp32':int(V.nbytes+V_change.nbytes)
}

# Benchmark compressed on-disk arrays (not preloaded index RAM) against common int8 baseline.
import zlib
base_groups=groups_for_size(999)
centers=np.zeros_like(V)
center_list=[]
for ids in base_groups:
 c=V[ids].mean(axis=0)
 center_list.append(c)
 centers[ids]=c
centerv=np.array(center_list,dtype=np.float16)
delta=V-centers
out['physical_vector_encoding']={
 'full_fp16_zlib_bytes':len(zlib.compress(V.astype(np.float16).tobytes(),6)),
 'full_fp32_zlib_bytes':len(zlib.compress(V.astype(np.float32).tobytes(),6)),
 'full_int8_zlib_bytes_including_scales':len(zlib.compress((np.rint(V/scales).astype(np.int8)).tobytes()+scales.astype(np.float32).tobytes(),6)),
}
for m in [4,8,16,24,32]:
 idx=np.argpartition(-np.abs(delta),m-1,axis=1)[:,:m]
 vals=np.take_along_axis(delta,idx,axis=1).astype(np.float16)
 bytestream=centerv.tobytes()+idx.astype(np.uint8).tobytes()+vals.tobytes()+np.array([next(g for g,ids in enumerate(base_groups) if i in ids) for i in range(N)],dtype=np.uint16).tobytes()
 out['physical_vector_encoding'][f'shared_residual_top{m}_zlib_bytes']=len(zlib.compress(bytestream,6))
print('SVD quality comparison',out['semantic_proxy_comparison'])
print('Vector storage comparison',out['physical_vector_encoding'])
OUT.joinpath('round4_bounds_results.json').write_text(json.dumps(out,indent=2))
np.savez_compressed(OUT/'round4_proxy_vectors.npz',v=V,q=W,changes=V_change,paths=np.array(paths,dtype='U256'))
