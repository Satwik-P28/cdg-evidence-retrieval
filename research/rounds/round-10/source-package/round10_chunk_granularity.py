#!/usr/bin/env python3
"""Controlled retrieval-workload-sensitive CDC chunk-size sweep.
Real noVNC Git source versions; human commit titles select query-matched five-line windows.
Each source version reconstructed exactly from independently decodable shared chunks.
The study measures compressed bytes and warm decode time, not SSD or LLM latency.
"""
import io,contextlib,json,hashlib,collections,statistics,time,random
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):import run_round8 as r
HERE=Path(__file__).resolve().parent
LINES=[d.splitlines(keepends=True) for d in r.DOCS]
TOKEN_LINES=[[set(r.toks_bytes(line)) for line in ls] for ls in LINES]

def request(di,qi):
    terms=set(r.toks_query(r.QUERIES[qi]));ls=LINES[di]
    if not ls:return (di,0,0)
    best=max(range(len(ls)),key=lambda j:(len(terms&TOKEN_LINES[di][j]),-j))
    lo=max(0,min(len(ls)-5,best-2));return (di,lo,min(lo+5,len(ls)))

train_queries=list(r.train);test_queries=list(r.test)
# Retrieval fixed across layouts; excludes differences from reranking.
requests={}
for label,ids in [('train',train_queries),('heldout',test_queries)]:
 for k in (5,10):requests[(label,k)]=[[request(int(d),qi) for d in r.full_orders[qi][:k]] for qi in ids]

# Compact variable-length integer encoding for static manifests.
def vi(n):
 n=int(n);arr=[]
 while n>=128:arr.append((n&127)|128);n>>=7
 arr.append(n);return bytes(arr)

results={}
for target in (8,16,32,64,128):
    print('build',target,flush=True)
    chunks=[];compressed=[];table={};doc_spans=[];raw_refs=0
    manifests=[]
    for di,ls in enumerate(LINES):
        ends=r.boundaries(ls,target=target);start=0;spans=[];ids=[]
        for end in ends:
            raw=b''.join(ls[start:end]);digest=hashlib.blake2b(raw,digest_size=16).digest()
            if digest not in table:
                table[digest]=len(chunks);chunks.append(raw);compressed.append(r.Z.compress(raw,3))
            ci=table[digest]
            if chunks[ci]!=raw:raise AssertionError('hash collision')
            spans.append((start,end,ci));ids.append(ci);start=end;raw_refs+=1
        assert b''.join(chunks[ci] for _,_,ci in spans)==r.DOCS[di]
        doc_spans.append(spans)
        # per-doc content ID, start/end exact line boundaries
        record=vi(len(spans))
        for a,b,ci in spans:record+=vi(ci)+vi(b-a)
        manifests.append(record)
    payload=sum(map(len,compressed))
    index=r.Z.compress(b''.join(manifests),3)
    # Include independently-addressable compressed chunk offsets and raw lengths,
    # plus a static header and chunk count. Excludes allocator/OS caches.
    offsets=bytearray();offset=0
    for raw,comp in zip(chunks,compressed):
        offsets.extend(vi(offset));offset+=len(comp)
        offsets.extend(vi(len(comp)));offsets.extend(vi(len(raw)))
    offset_bytes=r.Z.compress(bytes(offsets),3)
    storage=payload+len(index)+len(offset_bytes)+32

    def info_one_query(q):
        selected=set()
        for di,a,b in q:
            selected.update(ci for lo,hi,ci in doc_spans[di] if lo<b and hi>a)
        return selected

    agg={}
    for (label,k),qsets in requests.items():
        by_req=[info_one_query(q) for q in qsets]
        vals=[sum(len(compressed[ci]) for ci in x) for x in by_req]
        cnt=[len(x) for x in by_req]
        # warm CPU: randomized repetitions of actual zstd decoding
        times=[];check=0
        for rep in range(5):
            order=list(range(len(qsets)));random.Random(1984+rep).shuffle(order)
            for ix in order:
                t0=time.perf_counter_ns()
                for ci in by_req[ix]:
                    data=r.Z.decompress(compressed[ci],len(chunks[ci]));check+=len(data)
                times.append((time.perf_counter_ns()-t0)/1e3)
        assert check>0
        agg[f'{label}_k{k}']={
            'queries':len(qsets),'mean_compressed_payload_bytes':round(statistics.mean(vals),1),
            'median_compressed_payload_bytes':round(statistics.median(vals),1),
            'mean_unique_chunks_decompressed':round(statistics.mean(cnt),2),
            'median_warm_decode_us':round(statistics.median(times),2),
            'p95_warm_decode_us':round(sorted(times)[int(.95*(len(times)-1))],2)
        }
    results[str(target)]={'target_lines_per_chunk':target,'raw_bytes':sum(map(len,r.DOCS)),
        'unique_chunks':len(chunks),'logical_references':raw_refs,'payload_bytes':payload,
        'compressed_manifest_bytes':len(index),'compressed_seek_table_bytes':len(offset_bytes),
        'total_storage_bytes':storage,'lossless_verified_versions':len(r.DOCS),'access':agg}
    print('  done', target,'storage',storage,'payload',agg['heldout_k10']['mean_compressed_payload_bytes'], 'decode',agg['heldout_k10']['median_warm_decode_us'],flush=True)

# Train-only choose under objective; scalar trade-off is illustrative, not an absolute value measure.
# 100 queries x cost per query; storage valued as bytes per queried corpus over a chosen amortization horizon.
choices={}
for amortization in (100,1000,10000):
    target=min(results,key=lambda x:results[x]['total_storage_bytes']/amortization+results[x]['access']['train_k10']['mean_compressed_payload_bytes'])
    choices[str(amortization)]={'chosen_target':int(target),'heldout':results[target]['access']['heldout_k10']}
res={'dataset':{'corpus':'real noVNC commit revisions','versions':r.N,'human_commit_queries':len(r.QUERIES),'train':len(train_queries),'heldout':len(test_queries),'task':'fixed BM25 top-k exact five-line passage retrieval','encoder':'none'},'chunk_sweep':results,'train_chosen_by_amortization':choices,
 'limitations':['Repetitive one-repository Git history, not real RAG QA data','Warm CPU zstd decode, no SSD fetch, no tokenizer or generation','Compression ratios include manifest and compressed seek-table payloads but exclude Python allocator memory and search index','Predictive selection uses fixed BM25 retrieval; it does not improve evidence relevance','No trained codec or model, no pretrained neural retriever','The amortization term is an illustrative workload weighting, not observed economic cost']}
(HERE/'round10_chunk_granularity_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps({'summary':{t:{'total_kb':round(v['total_storage_bytes']/1024,1),'heldout_payload_kb':round(v['access']['heldout_k10']['mean_compressed_payload_bytes']/1024,2),'heldout_decode_us':v['access']['heldout_k10']['median_warm_decode_us']} for t,v in results.items()},'train_chosen':choices},indent=2),flush=True)
