#!/usr/bin/env python3
"""Multi-intent retrieval stress test on real commit subjects, synthetic pairing.
No neural model, no LLM QA: qrels are exact associated Git revisions.
"""
import contextlib,io,sys,json,random,statistics,hashlib,math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
 import run_round8 as r

rng=random.Random(9042)
# Distinct-path pairs, training and test separate

def form_pairs(ids):
 ids=list(ids);random.Random(123).shuffle(ids);out=[]
 while len(ids)>1:
  i=ids.pop(0)
  jj=next((x for x,v in enumerate(ids) if r.PATHS[v]!=r.PATHS[i]),None)
  if jj is not None:out.append((i,ids.pop(jj)))
 return out

train=form_pairs(r.train);test=form_pairs(r.test)
corpus_lengths=[len(r.Z.compress(x,3)) for x in r.all_chunks]
base_chunksets=[set(seq) for seq in r.doc_maps]
base_doc_cost=[sum(corpus_lengths[x] for x in set(seq)) for seq in r.doc_maps]

# Exact conventional document-level BM25

def score(q):
 return r.flat_score(sorted({r.vocab[t] for t in r.toks_query(q) if t in r.vocab}))

def prepare(pair):
 i,j=pair
 s1,s2,sc=score(r.QUERIES[i]),score(r.QUERIES[j]),score(r.QUERIES[i]+' '+r.QUERIES[j])
 o1=np.argsort(-s1,kind='stable');o2=np.argsort(-s2,kind='stable');oc=np.argsort(-sc,kind='stable')
 p1=np.empty(r.N,dtype=np.int32);p2=p1.copy()
 p1[o1]=np.arange(r.N);p2[o2]=np.arange(r.N)
 rrf=1.0/(20+p1)+1.0/(20+p2)
 orrf=np.argsort(-rrf,kind='stable')
 return {'targets':(i,j),'s':(s1,s2,sc),'o':(o1,o2,oc,orrf),'qt':set(r.toks_query(r.QUERIES[i]+' '+r.QUERIES[j]))}

def select(task,mode,penalty=0):
 o1,o2,oc,orrf=task['o']
 if mode=='combined': return list(map(int,oc[:10]))
 if mode=='rrf':return list(map(int,orrf[:10]))
 if mode=='round_robin':
  out=[]
  for x,y in zip(o1,o2):
   for z in (x,y):
    if int(z) not in out:out.append(int(z))
    if len(out)==10:return out
  return out
 if mode=='costaware':
  # Fixed branch quota, choose candidate based on branch-relative relevance vs
  # new compressed source blocks. No knowledge of qrels at query time.
  s1,s2,_=task['s'];norm1=max(float(s1.max()),1e-8);norm2=max(float(s2.max()),1e-8)
  sources=[list(map(int,o1[:20])),list(map(int,o2[:20]))]
  used=set();chunks=set();counts=[0,0]
  for turn in range(10):
   branch=0 if counts[0]<=counts[1] else 1
   avail=[d for d in sources[branch] if d not in used]
   if not avail:avail=[d for d in sources[1-branch] if d not in used]
   def utility(doc):
    s=(s1[doc]/norm1 if branch==0 else s2[doc]/norm2)
    cost=sum(corpus_lengths[c] for c in base_chunksets[doc]-chunks)/1024
    return float(s-penalty*cost)
   d=max(avail,key=utility)
   used.add(d);chunks.update(base_chunksets[d]);counts[branch]+=1
  return list(used)
 raise ValueError(mode)

# We retain the source order in results except costaware where ordering does
# not matter for set-based retrieval completeness.

def evaluate(tasks,mode,penalty=0):
 correct=[];partial=[];bytes_read=[];distinct_paths=[]
 for t in tasks:
  selected=select(t,mode,penalty);targets=set(t['targets'])
  n=len(targets.intersection(selected))
  correct.append(n==2);partial.append(n/2)
  unique=set().union(*(base_chunksets[d] for d in selected))
  bytes_read.append(sum(corpus_lengths[c] for c in unique))
  distinct_paths.append(len(set(r.PATHS[d] for d in selected)))
 return {'pairs':len(tasks),'both_revisions_recall_at10':round(statistics.mean(correct),4),
  'mean_revision_fraction_at10':round(statistics.mean(partial),4),
  'mean_union_compressed_chunk_bytes':round(statistics.mean(bytes_read),1),
  'mean_distinct_paths':round(statistics.mean(distinct_paths),2)}

train_tasks=[prepare(x) for x in train];test_tasks=[prepare(x) for x in test]
lams=[0,0.0005,0.002,0.01,0.05]
sweep={str(lam):evaluate(train_tasks,'costaware',lam) for lam in lams}
best=max(lams,key=lambda lam:(sweep[str(lam)]['both_revisions_recall_at10'],-sweep[str(lam)]['mean_union_compressed_chunk_bytes']))
methods={'combined':evaluate(test_tasks,'combined'), 'round_robin':evaluate(test_tasks,'round_robin'),
         'rrf':evaluate(test_tasks,'rrf'),'costaware':evaluate(test_tasks,'costaware',best)}

# paired bootstrap CI for differences in complete-revision recovery
base=[int(set(t['targets']).issubset(set(select(t,'combined')))) for t in test_tasks]
boot=random.Random(8764)
ci={}
for mode in ['round_robin','rrf','costaware']:
 vals=[int(set(t['targets']).issubset(set(select(t,mode,best if mode=='costaware' else 0)))) for t in test_tasks]
 delta=[v-b for v,b in zip(vals,base)]; n=len(delta)
 dist=sorted(sum(delta[boot.randrange(n)] for _ in range(n))/n for _ in range(1200))
 ci[mode]={'delta':round(statistics.mean(delta),4),'paired_bootstrap_95pct':[round(dist[29],4),round(dist[1170],4)]}

res={'setup':{'real_git_revisions':r.N,'train_multi_intent_pairs':len(train_tasks),'heldout_multi_intent_pairs':len(test_tasks),'synthetic_paired_queries':True,
      'pretrained_encoder':False,'label':'exact Git commit-after revision'},'heldout':methods,'selected_cost_parameter_train_only':best,
      'training_sweep':sweep,'paired_bootstrap':ci,'important_limitations':[
       'Queries are two concatenated real commit titles; they are not real multi-hop QA questions.',
       'Cost model counts unique *whole-document* shared compressed chunks, not requested source windows or measured SSD latency.',
       'The completeness metric is exact two-revision retrieval, not factual sufficiency or LLM answer accuracy.',
       'Comparing query-decomposed methods to one un-decomposed query is an established algorithmic advantage, not a new compression method.']}
(HERE/'round9_multi_intent.json').write_text(json.dumps(res,indent=2));print(json.dumps(res,indent=2))
