#!/usr/bin/env python3
"""Leakage-free passage-cost-aware retrieval policy test.
Queries and relevance are synthetic commit-subject pairs; source is real git.
Parameter selection on 50 train pairs, heldout on 75 pairs.
"""
import json,statistics,random,contextlib,io
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):
 import round9_multi_intent as m
r=m.r
DOC_LINES=[d.splitlines(keepends=True) for d in r.DOCS]
LTS=[[set(r.toks_bytes(line)) for line in ls] for ls in DOC_LINES]
EDGES=[]
for i,ls in enumerate(DOC_LINES):
 edges=r.boundaries(ls)
 EDGES.append(list(zip([0]+edges[:-1],edges,r.doc_maps[i])))

# Calculate actual compressed payload cost of query-matched passage for candidate
# document. This is measured against the exact CDC representation and is *not*
# a learned predictor, an important limit on external-validity.
def prepare(task):
 o1,o2,_,_=task['o'];ds=list(dict.fromkeys([*map(int,o1[:20]),*map(int,o2[:20])]))
 q=task['qt'];ids={}
 for di in ds:
  arr=LTS[di]
  if not arr:ids[di]=set();continue
  best=max(range(len(arr)),key=lambda j:(len(arr[j]&q),-j))
  a=max(0,min(max(0,len(arr)-5),best-2));b=min(a+5,len(arr))
  ids[di]={cid for lo,hi,cid in EDGES[di] if lo<b and hi>a}
 return ids

all_train=[prepare(t) for t in m.train_tasks]
all_test=[prepare(t) for t in m.test_tasks]

def select(task,pcost,penalty):
 s1,s2,_=task['s'];o1,o2,_,_=task['o']
 s1max=max(float(s1.max()),1e-8);s2max=max(float(s2.max()),1e-8)
 pools=[list(map(int,o1[:20])),list(map(int,o2[:20]))]
 selected=[];seen=set();counts=[0,0]
 for step in range(10):
  branch=0 if counts[0]<=counts[1] else 1
  avail=[d for d in pools[branch] if d not in selected]
  if not avail:avail=[d for d in pools[1-branch] if d not in selected]
  def util(d):
   score=(s1[d]/s1max if branch==0 else s2[d]/s2max)
   extra=sum(m.corpus_lengths[c] for c in pcost[d]-seen)/1024
   return float(score-penalty*extra)
  best=max(avail,key=util)
  selected.append(best);seen.update(pcost[best]);counts[branch]+=1
 return selected

def eval(tasks,pcosts,lam):
 both=[];halves=[];bytes=[];nchunks=[]
 for task,pc in zip(tasks,pcosts):
  ds=select(task,pc,lam);both.append(set(task['targets']).issubset(ds))
  halves.append(len(set(task['targets'])&set(ds))/2)
  ch=set().union(*(pc[d] for d in ds));nchunks.append(len(ch))
  bytes.append(sum(m.corpus_lengths[c] for c in ch))
 return {'both_at10':round(statistics.mean(both),4),'mean_revision_fraction':round(statistics.mean(halves),4),
         'mean_actual_passage_payload_bytes':round(statistics.mean(bytes),1),'mean_passage_chunks':round(statistics.mean(nchunks),2)}

lams=[0,0.0005,0.002,0.01,0.03,0.05,0.1,0.2]
train={str(l):eval(m.train_tasks,all_train,l) for l in lams}
# Priority to full two evidence recall and then minimized actual passage bytes
lam=max(lams,key=lambda l:(train[str(l)]['both_at10'],-train[str(l)]['mean_actual_passage_payload_bytes']))
held={str(l):eval(m.test_tasks,all_test,l) for l in lams}
res={'train':train,'test_sensitivity_not_for_tuning':held,'selected_lambda':lam,
 'heldout_selected':held[str(lam)],'setup':{'test_pairs':len(m.test_tasks),'train_pairs':len(m.train_tasks)},
 'limitations':['Passage windows selected from lexical overlap with query, not an LLM','Costs are true compressed payload unions for five-line passage chunks, not SSD I/O','Only exact selected revisions counted as correct; synthetic paired task.']}
Path('/mnt/data/cdg_round9/round9_passage_rerank.json').write_text(json.dumps(res,indent=2))
print(json.dumps({'selected_lambda':lam,'heldout':held[str(lam)],'all_test':held},indent=2))
