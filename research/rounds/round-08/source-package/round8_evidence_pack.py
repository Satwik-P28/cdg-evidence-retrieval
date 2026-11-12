#!/usr/bin/env python3
"""Measure exact evidence redundancy in BM25 candidate sets; byte/token proxy only.

Retains a provenance map from each unique passage to every retrieved version.
Does not test LLM generation or semantic correctness.
"""
import io,contextlib,statistics,hashlib,json,collections,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
 import round8_batch_fetch as b
r=b.r

result={'experiment':'Evidence packing after BM25 retrieval, exact passage-level dedup with per-version provenance.',
        'queries_heldout':len(r.test),'conditions':{},'notes':[
  'Uses the same five-line query-selected evidence windows as Round8b; generated extractive windows, not QA-gold snippets.',
  'Deduplicates only byte-identical passage content. Every original passage and version association remains represented as provenance metadata.',
  'Raw prompt bytes are a proxy for token costs; not actual LLM token counts, and provenance metadata has its own costs.',
  'No LLM generation, attention-cache reuse or measured end-to-end RAG latency.'
 ]}
for topk in (5,10):
 for how in ('BM25','random'):
  key=f'{how}_top{topk}';ratios=[];raw_len=[];uniq_len=[];uniq_count=[];same_paths=[];tok_ratio=[];prov_bytes=[]
  traces=b.traces[f'{how}_top{topk}']
  for req in traces:
   snippets,_=b.cdc.read(req,cache=True)
   combined=sum(map(len,snippets))
   unique={};prov={}
   for (doc,a,e),text in zip(req,snippets):
    digest=hashlib.sha256(text).hexdigest()
    if digest not in unique:unique[digest]=text
    prov.setdefault(digest,[]).append({'version':int(doc),'start_line':int(a),'end_line':int(e)})
   independent_tokens=sum(len(r.toks_bytes(x)) for x in snippets)
   packed_tokens=sum(len(r.toks_bytes(x)) for x in unique.values())
   packed_bytes=sum(map(len,unique.values()))
   raw_len.append(combined);uniq_len.append(packed_bytes);uniq_count.append(len(unique))
   same_paths.append(len(set(r.PATHS[d] for d,a,e in req)))
   ratios.append(1-packed_bytes/combined if combined else 0)
   tok_ratio.append(1-packed_tokens/independent_tokens if independent_tokens else 0)
   # JSON serialized provenance, only indicative; 64 hex hash per unique passage can dominate very short windows.
   prov_bytes.append(len(json.dumps(prov,separators=(',',':')).encode()))
  result['conditions'][key]={
    'mean_original_prompt_bytes':round(statistics.mean(raw_len),1),
    'mean_exact_dedup_prompt_bytes':round(statistics.mean(uniq_len),1),
    'mean_exact_dedup_percent':round(100*statistics.mean(ratios),1),
    'mean_token_count_proxy_reduction_percent':round(100*statistics.mean(tok_ratio),1),
    'mean_unique_evidence_passages':round(statistics.mean(uniq_count),2),
    'mean_source_paths':round(statistics.mean(same_paths),2),
    'mean_naive_json_provenance_bytes':round(statistics.mean(prov_bytes),1)
  }
(HERE/'round8_evidence_pack_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
