#!/usr/bin/env python3
"""Passage-level physical cost audit on same heldout queries and methods.
No I/O timing; payload-union estimate; real revision source excerpts.
"""
import json,statistics,re,contextlib,io,random
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):
 import round9_multi_intent as m
r=m.r
lines=[doc.splitlines(keepends=True) for doc in r.DOCS]
termsets=[[set(r.toks_bytes(line)) for line in ls] for ls in lines]
ends=[r.boundaries(ls) for ls in lines]
ranges=[]
for i in range(r.N):
 ranges.append([(a,b,cid) for a,b,cid in zip([0]+ends[i][:-1],ends[i],r.doc_maps[i])])

def win(task,di):
 arr=termsets[di]
 if not arr:return (0,0)
 qt=task['qt']
 best=max(range(len(arr)),key=lambda j: (len(arr[j].intersection(qt)),-j))
 start=max(0,min(max(0,len(arr)-5),best-2))
 return start,min(start+5,len(arr))

out={}
for mode in ['combined','round_robin','rrf','costaware']:
 cost=[];nunique=[];tokens=[];countdup=[];full_source=[]
 for t in m.test_tasks:
  ds=m.select(t,mode,m.best if mode=='costaware' else 0)
  pids=set();seen=set();prompt=[]
  for di in ds:
   a,b=win(t,di)
   for lo,hi,cid in ranges[di]:
    if lo<b and hi>a:pids.add(cid)
   data=b''.join(lines[di][a:b]);prompt.append(data);seen.add(data)
  cost.append(sum(m.corpus_lengths[cid] for cid in pids))
  nunique.append(len(pids));tokens.append(sum(map(len,prompt)));countdup.append(sum(map(len,seen)))
  full_source.append(sum(m.base_doc_cost[d] for d in ds))
 out[mode]={
  'mean_exact_passage_payload_union_bytes':round(statistics.mean(cost),1),
  'mean_unique_passage_chunks':round(statistics.mean(nunique),2),
  'mean_passage_raw_text_bytes':round(statistics.mean(tokens),1),
  'mean_dedup_passage_text_bytes':round(statistics.mean(countdup),1),
  'mean_selected_independent_full_docs_bytes':round(statistics.mean(full_source),1)}
result={'dataset':'75 paired commit-message tasks','method':'query-term-matched five-line windows; common content-defined compressed block references','result':out,'caveats':['Top10 selection uses entire-document cost proxy; these measurements use only five-line windows', 'No SSD read timings, no model-token counts, no independently labeled QA'],}
Path('/mnt/data/cdg_round9/round9_passage_costs.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
