#!/usr/bin/env python3
"""Diversity stress test: does CDG fetch batching reward redundant search results?"""
import io,contextlib,json,statistics,random,time,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
 import round8_batch_fetch as b
r=b.r

def select(i,k,cap):
    ids=[];counts={}
    for x in r.full_orders[i]:
        x=int(x);path=r.PATHS[x]
        if counts.get(path,0)>=cap:continue
        ids.append(x);counts[path]=counts.get(path,0)+1
        if len(ids)>=k:break
    return ids

res={'experiment':'Diversified BM25 candidates with controlled same-path cap. Same source version store and exact query-conditioned passage selection.',
     'evaluated_queries':len(r.test),'conditions':{},'notes':['Version-specific qrels are exact selected commit-after version; a different revision of same file is NOT a hit.','All methods use the same unmodified BM25 ranking, with a post-ranking same-file-path cap.','This is not a production diversity reranker; highlights correctness/redundancy tradeoff.','Cache and decode counts measured as full per-query batches in warm in-memory source; no SSD or LLM.']}
for k in (5,10):
 for cap in (1,2,1000):
    name=f'top{k}_pathcap{cap}'
    numpaths=[];hits=[];cache_counts=[];bytes_read=[];decode_time=[];baseline=[]
    for i in r.test:
        selected=select(i,k,cap)
        numpaths.append(len(set(r.PATHS[j] for j in selected)))
        hits.append(i in selected)
        req=[b.choose_window(i,j) for j in selected]
        _,batch_meta=b.cdc.read(req,cache=True)
        _,ind_meta=b.ind.read(req,cache=False)
        cache_counts.append(batch_meta['frames_decoded'])
        bytes_read.append(batch_meta['payload_bytes'])
        baseline.append(ind_meta['payload_bytes'])
    res['conditions'][name]={
      'mean_unique_paths':round(statistics.mean(numpaths),2),
      'exact_revision_hit_at_k':round(statistics.mean(hits),4),
      'mean_shared_frames_decoded':round(statistics.mean(cache_counts),2),
      'mean_shared_payload_bytes':round(statistics.mean(bytes_read),1),
      'mean_independent_payload_bytes':round(statistics.mean(baseline),1),
      'batch_saved_payload_percent':round(100*(1-statistics.mean(bytes_read)/statistics.mean(baseline)),1)
    }
(HERE/'round8_diversity_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
