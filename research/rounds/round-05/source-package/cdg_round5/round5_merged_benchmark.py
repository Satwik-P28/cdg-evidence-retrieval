#!/usr/bin/env python3
"""Benchmark one merged BM25 posting matrix vs two separately evaluated field matrices.
No pretrained encoder, no LLM. Matrices contain full source + change-region term weights."""
import sys,json,time,statistics,gc
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from round5_anchor_budget import prep_data,bm25,eval_rank,index_size

samples,v,F,D,Q=prep_data()
FW=bm25(F).tocsr();DW=bm25(D).tocsr()
M=(FW+DW).tocsr()
FWT=FW.T.tocsc(); DWT=DW.T.tocsc(); MT=M.T.tocsc()
# Multiplication order fixed and normalized. Data held in memory, warm cache.
exact=(Q@FWT).toarray()+(Q@DWT).toarray()
merged=(Q@MT).toarray()
assert np.allclose(exact,merged,rtol=3e-5,atol=1e-5), np.max(abs(exact-merged))
# Scores can be reordered at floating point ties; reports rank consistency
N=Q.shape[0]
assert N==250
rng=np.random.default_rng(312)
perquery={'separate':[],'merged':[]}
rep=10
queries=np.arange(N)
# Alternating to control thermals and CPU caches
for repeat in range(rep):
  for method in (['separate','merged'] if repeat%2==0 else ['merged','separate']):
    order=rng.permutation(queries)
    clock=[]
    for j in order:
      qi=Q.getrow(int(j))
      t0=time.perf_counter_ns()
      if method=='separate':s=(qi@FWT).toarray()+(qi@DWT).toarray()
      else:s=(qi@MT).toarray()
      clock.append((time.perf_counter_ns()-t0)/1000)
    perquery[method].extend(clock)

result={'source':'noVNC source git history, 250 genuine commit queries','note':'CPU query-time sparse score calculation only. No tokenizer, loading, disk I/O or ANN.',
'index':{'full_bytes':index_size(FW),'changes_bytes':index_size(DW),'separate_bytes':index_size(FW)+index_size(DW),'merged_bytes':index_size(M),'vocabulary_size':len(v.vocabulary_),
 'full_nnz':int(FW.nnz),'changes_nnz':int(DW.nnz),'merged_nnz':int(M.nnz)},
'score_max_abs_diff':float(np.max(np.abs(exact-merged))),
'query_scores':{'separate_hit5':eval_rank(exact,np.arange(N))['hit5'],'merged_hit5':eval_rank(merged,np.arange(N))['hit5']},
'query_time_microseconds':{m:{'median':round(float(np.median(x)),2),'p95':round(float(np.percentile(x,95)),2),'mean':round(float(np.mean(x)),2)} for m,x in perquery.items()},
'repetitions':rep,'queries_per_repetition':N}
(ROOT/'round5_merged_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
