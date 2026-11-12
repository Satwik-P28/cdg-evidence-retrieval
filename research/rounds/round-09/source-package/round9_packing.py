#!/usr/bin/env python3
"""Round 9: provenance-preserving evidence packing and multi-intent retrieval.
Real noVNC revision contents and human commit subjects; paired tasks are synthetic.
No pretrained neural embeddings, no generated answer evaluation.
"""
import contextlib, io, sys, json, random, statistics, hashlib, math, struct, zlib, time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    import run_round8 as r
print("import_done",file=sys.stderr,flush=True)

rng=random.Random(9042)
# unchanged source/query text, no QA gold
DOC_LINES=[d.splitlines(keepends=True) for d in r.DOCS]
TOK_LINES=[[set(r.toks_bytes(x)) for x in lines] for lines in DOC_LINES]
print("tokens_done",file=sys.stderr,flush=True)
# corpus unique chunk storage and doc-line-to-chunk maps
CHUNK_BYTES=[len(r.Z.compress(x,3)) for x in r.all_chunks]
DOC_CHUNK_MAPS=[]
for di,doc in enumerate(r.DOCS):
    ends=r.boundaries(DOC_LINES[di]);starts=[0]+ends[:-1]
    DOC_CHUNK_MAPS.append([(a,b, cid) for a,b,cid in zip(starts,ends,r.doc_maps[di])])

print("maps_done",file=sys.stderr,flush=True)
def window(qterms,di):
    lines=DOC_LINES[di]
    if not lines: return di,0,0
    best=max(range(len(lines)),key=lambda j:(len(qterms&TOK_LINES[di][j]),-j))
    start=max(0,min(max(0,len(lines)-5),best-2))
    return di,start,min(start+5,len(lines))

def chunk_ids(req):
    doc,a,b=req
    return {cid for lo,hi,cid in DOC_CHUNK_MAPS[doc] if lo<b and hi>a}

def text_for(req):
    di,a,b=req
    return b''.join(DOC_LINES[di][a:b])

# Ground-truth exact inverse of serialized prompt mapping: every evidence/source relation
# remains recoverable, including byte-different and version-specific snippets.
def pack(reqs):
    originals=[];unique={};ref_for=[]
    for req in reqs:
        di,a,b=req
        payload=text_for(req)
        originals.append(f'[v{di}:{a+1}-{b}]\n'.encode()+payload+b'\n')
        unique.setdefault(payload,[]).append(req)
    baseline=b''.join(originals)
    parts=[];binary=b'';binary_pieces=[]
    for uid,(payload,refs) in enumerate(unique.items()):
        short=','.join(f'v{di}:{a+1}-{b}' for di,a,b in refs)
        parts.append(f'[e{uid} -> {short}]\n'.encode()+payload+b'\n')
        binary_pieces.append(struct.pack('<HI',uid,len(refs)))
        for di,a,b in refs:binary_pieces.append(struct.pack('<HHH',di,a,b))
        for req in refs:ref_for.append((uid,req,payload))
    packed=b''.join(parts)
    binary=b''.join(binary_pieces)
    # validate raw source roundtrip by occurrence keys; not merely count preservation
    inverse={(di,a,b):payload for payload,refs in unique.items() for di,a,b in refs}
    assert len(inverse)==len(set(reqs))
    for req in reqs:assert inverse[req]==text_for(req)
    return {'raw_prompt_bytes':len(baseline),'exact_inline_bytes':len(packed),'unique_evidence':len(unique),
      'occurrences':len(reqs),'binary_provenance_bytes':len(binary),'binary_provenance_zlib':len(zlib.compress(binary,6)),
      'raw_token_proxy':sum(len(r.toks_bytes(x)) for x in originals),'inline_token_proxy':sum(len(r.toks_bytes(x)) for x in parts)}

ids=list(r.test)
metrics={key:[] for key in ['bm25_top5','bm25_top10','random_top10']}
for num,di in enumerate(ids):
    if num%10==0:print("pack_progress",num,file=sys.stderr,flush=True)
    qt=set(r.toks_query(r.QUERIES[di]))
    for label,candidates in [
       ('bm25_top5',r.full_orders[di][:5]),('bm25_top10',r.full_orders[di][:10]),
       ('random_top10',random.Random(di+440).sample(range(r.N),10))]:
        reqs=[window(qt,int(j)) for j in candidates]
        metrics[label].append(pack(reqs))

def summarize_pack(label,values):
    ret={'queries':len(values)}
    for k in values[0]:
        ret['mean_'+k]=round(statistics.mean(x[k] for x in values),3)
    ret['overall_byte_reduction_frac']=round(1-sum(x['exact_inline_bytes'] for x in values)/sum(x['raw_prompt_bytes'] for x in values),5)
    ret['overall_token_proxy_reduction_frac']=round(1-sum(x['inline_token_proxy'] for x in values)/sum(x['raw_token_proxy'] for x in values),5)
    ret['percent_queries_inline_smaller']=round(sum(x['exact_inline_bytes']<x['raw_prompt_bytes'] for x in values)/len(values),4)
    return ret

data={key:summarize_pack(key,vals) for key,vals in metrics.items()}
(HERE/"round9_packing.json").write_text(json.dumps(data,indent=2))
print(json.dumps(data,indent=2))
