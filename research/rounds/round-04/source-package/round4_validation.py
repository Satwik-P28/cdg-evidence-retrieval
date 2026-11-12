"""Independent score-level validation for grouped pruning on real-history LSA vectors.
The top-k document set can differ under ties; this checks top-k SCORES rather than IDs.
"""
import json, heapq, collections
from pathlib import Path
import numpy as np
p=Path(__file__).resolve().parent
D=np.load(p/'round4_proxy_vectors.npz')
V=D['v'];W=D['q'];paths=D['paths']
DIMS=V.shape[1];N=len(V);k=5
fam=collections.defaultdict(list)
for i,path in enumerate(paths): fam[str(path)].append(i)
res={}
for size in [2,3,4,8,999]:
 groups=[]
 for name,ids in sorted(fam.items()):
  for j in range(0,len(ids),size): groups.append(ids[j:j+size])
 C=[];R=[]
 for ids in groups:
  c=V[ids].mean(axis=0);C.append(c)
  R.append(np.linalg.norm(V[ids]-c,axis=1).max())
 C=np.array(C);R=np.array(R)
 gap=[];argset=[]
 for q in W:
  fs=V@q
  true=np.sort(np.partition(fs,-k)[-k:])
  bd=C@q+R
  heap=[]
  for g in np.argsort(-bd):
   if len(heap)>=k and bd[g]<heap[0][0]-1e-6:break
   ds=V[groups[g]]@q
   for d,sc in zip(groups[g],ds):
    rec=(float(sc),-int(d))
    if len(heap)<k: heapq.heappush(heap,rec)
    elif rec>heap[0]:heapq.heapreplace(heap,rec)
  got=np.sort(np.array([s for s,_ in heap]))
  gap.append(float(np.max(np.abs(true-got))))
  argset.append(len(set(-d for _,d in heap)&set(np.argsort(-fs)[:k])))
 res[str(size)]={'max_absolute_topk_score_difference':max(gap),'mean_exact_id_overlap_at5':float(np.mean(argset)/5),'queries':len(W),'all_scores_correct_at_1e-5':all(g<1e-5 for g in gap)}
print(json.dumps(res,indent=2))
(p/'round4_validation_results.json').write_text(json.dumps(res,indent=2))
