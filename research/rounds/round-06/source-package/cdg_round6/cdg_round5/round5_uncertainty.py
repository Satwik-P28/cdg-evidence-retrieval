import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from round5_anchor_budget import prep_data,bm25
samples,vec,F,D,Q=prep_data()
N=len(samples)
Fw=bm25(F);Dw=bm25(D)
Sf=(Q@Fw.T).toarray();Sd=(Q@Dw.T).toarray();Sm=(Q@(Fw+Dw).T).toarray()

def target_hit(S,k=5):
  # target match, stable ties
  return np.array([i in np.argsort(-S[i],kind='stable')[:k] for i in range(N)],dtype=bool)

rng=np.random.default_rng(92)
ix=np.arange(N)
boot=rng.integers(0,N,size=(10000,N))
results={}
for name,A,B in [('diff_minus_full',target_hit(Sd),target_hit(Sf)),('merged_minus_diff',target_hit(Sm),target_hit(Sd))]:
 d=A.astype(int)-B.astype(int)
 ci=np.percentile(d[boot].mean(axis=1),[2.5,97.5]).tolist()
 results[name]={'delta_hit5':round(float(d.mean()),4),'paired_95pct_bootstrap_interval':[round(float(x),4) for x in ci],
 'improved_queries':int((d==1).sum()),'worsened_queries':int((d==-1).sum())}
result={'n':N,'method':'percentile paired bootstrap 10,000 samples over automatically labeled commit queries', 'comparisons':results}
(ROOT/'round5_uncertainty_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
