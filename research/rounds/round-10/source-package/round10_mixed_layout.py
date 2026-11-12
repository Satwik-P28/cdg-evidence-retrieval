#!/usr/bin/env python3
"""Train-selected per-source-family CDC granularity, held-out exact passage access.
All source versions are byte-exact; no neural RAG or SSD I/O.
"""
import contextlib,io,hashlib,collections,statistics,json,random
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):import run_round8 as r
HERE=Path(__file__).resolve().parent
TARGETS=(8,16,32,64)
LINES=[d.splitlines(keepends=True) for d in r.DOCS]
TOK_LINES=[[set(r.toks_bytes(line)) for line in ls] for ls in LINES]
PATHS=sorted(set(r.PATHS));GROUPS={path:[i for i,p in enumerate(r.PATHS) if p==path] for path in PATHS}

def varint(n):
 out=bytearray();n=int(n)
 while n>127:out.append((n&127)|128);n>>=7
 out.append(n);return bytes(out)

def window(doc,query_idx):
 lines=LINES[doc];terms=set(r.toks_query(r.QUERIES[query_idx]))
 if not lines:return (doc,0,0)
 best=max(range(len(lines)),key=lambda j:(len(terms&TOK_LINES[doc][j]),-j))
 a=max(0,min(max(len(lines)-5,0),best-2));return (doc,a,min(a+5,len(lines)))

REQUESTS={lab:[[window(int(d),q) for d in r.full_orders[q][:10]] for q in ids] for lab,ids in [('train',r.train),('heldout',r.test)]}

# Build all-family, all-granularity chunk lists; hash identifies losslessly shared bytes.
precomp={}
for path,docids in GROUPS.items():
 for size in TARGETS:
  docs={};unique={};pieces=[]
  for di in docids:
   lines=LINES[di];ends=r.boundaries(lines,target=size);start=0;spans=[]
   for end in ends:
    data=b''.join(lines[start:end]);h=hashlib.blake2b(data,digest_size=16).digest()
    if h in unique:
     assert unique[h][0]==data
    else:unique[h]=(data,r.Z.compress(data,3))
    spans.append((start,end,h));start=end
   assert b''.join(unique[h][0] for a,b,h in spans)==r.DOCS[di]
   docs[di]=spans
  # independent family cost approximates global: count unique chunks within family and compact manifests.
  local_ids={h:i for i,h in enumerate(unique)}
  manifest=b''.join(varint(len(docs[di]))+b''.join(varint(local_ids[h])+varint(b-a) for a,b,h in docs[di]) for di in docids)
  local_size=sum(len(z) for _,z in unique.values())+len(r.Z.compress(manifest,3))+sum(len(varint(len(z)))+len(varint(len(raw))) for raw,z in unique.values())+32
  precomp[(path,size)]={'docs':docs,'unique':unique,'size':local_size}
print('built family structures',len(precomp),flush=True)

# Workload cost per family based on training requests, with dedup within each query.
def query_cost_family(path,size,requests):
 data=precomp[(path,size)];docs=data['docs'];unique=data['unique'];cost=0
 for qreq in requests:
  hashes=set()
  for di,a,b in qreq:
   if di not in docs:continue
   hashes.update(h for lo,hi,h in docs[di] if lo<b and hi>a)
  cost+=sum(len(unique[h][1]) for h in hashes)
 return cost/len(requests)

family_stats={}
for path in PATHS:
 family_stats[path]={}
 for size in TARGETS:
  data=precomp[(path,size)]
  family_stats[path][str(size)]={'storage_bytes':data['size'],
    'train_mean_query_payload_bytes':query_cost_family(path,size,REQUESTS['train']),
    'heldout_mean_query_payload_bytes':query_cost_family(path,size,REQUESTS['heldout'])}

# Train-only decisions, no knowledge of heldout query distribution.
chosen={}
for horizon in (50,200,1000,5000):
 chosen[str(horizon)]={path:min(TARGETS,key=lambda size:family_stats[path][str(size)]['storage_bytes']/horizon+family_stats[path][str(size)]['train_mean_query_payload_bytes']) for path in PATHS}

# Compute the true global compressed shared-chunk payload and static metadata for selected sizes.
def evaluate(layout, measure_decode=False):
 unique={};doc_spans={};manifest=b''
 for di in range(r.N):
  path=r.PATHS[di];spans=precomp[(path,layout[path])]['docs'][di];doc_spans[di]=spans
  for _,_,h in spans:
   if h not in unique:unique[h]=precomp[(path,layout[path])]['unique'][h]
 # stable IDs by first encounter; use a global chunk catalog
 ids={h:i for i,h in enumerate(unique)}
 for di in range(r.N):
  spans=doc_spans[di]
  manifest+=varint(len(spans))+b''.join(varint(ids[h])+varint(b-a) for a,b,h in spans)
 offsets=b''.join(varint(len(z))+varint(len(raw)) for raw,z in unique.values())
 total=sum(len(z) for raw,z in unique.values())+len(r.Z.compress(manifest,3))+len(r.Z.compress(offsets,3))+32
 # Exact original-byte reconstruction verification.
 for di in range(r.N):
  assert b''.join(unique[h][0] for _,_,h in doc_spans[di])==r.DOCS[di]
 if measure_decode:
  for h,(raw,z) in unique.items():
   assert r.Z.decompress(z,len(raw))==raw
 ret={'total_source_bytes':total,'unique_chunks':len(unique),'exact_reconstructions':r.N}
 for label,qreqs in REQUESTS.items():
  vals=[];cnt=[]
  for reqs in qreqs:
   need=set()
   for di,a,b in reqs:need.update(h for lo,hi,h in doc_spans[di] if lo<b and hi>a)
   vals.append(sum(len(unique[h][1]) for h in need));cnt.append(len(need))
  ret[label]={'queries':len(qreqs),'mean_passage_payload_bytes':round(statistics.mean(vals),1),'median_passage_payload_bytes':round(statistics.median(vals),1),'mean_chunks_per_query':round(statistics.mean(cnt),2),'passage_payload_per_query_bytes':vals}
  if measure_decode and label=='heldout':
   import time
   times=[];check=0
   for rep in range(5):
    order=list(range(len(qreqs)));random.Random(19001+rep).shuffle(order)
    for qi in order:
     need=set()
     for di,a,b in qreqs[qi]:need.update(h for lo,hi,h in doc_spans[di] if lo<b and hi>a)
     t0=time.perf_counter_ns()
     for h in need:
      raw,z=unique[h];check+=len(r.Z.decompress(z,len(raw)))
     times.append((time.perf_counter_ns()-t0)/1000.)
   assert check>0
   ret[label]['median_warm_payload_decode_us']=round(statistics.median(times),2)
   ret[label]['p95_warm_payload_decode_us']=round(sorted(times)[int(.95*(len(times)-1))],2)
 return ret

results={}
for size in TARGETS:
 key=f'global_{size}';results[key]=evaluate({path:size for path in PATHS})
 print(key,results[key]['total_source_bytes'],results[key]['heldout']['mean_passage_payload_bytes'],flush=True)
for horizon,layout in chosen.items():
 key=f'mixed_h{horizon}';results[key]=evaluate(layout)
 results[key]['family_target_counts']=dict(collections.Counter(layout.values()))
 print(key,results[key]['total_source_bytes'],results[key]['heldout']['mean_passage_payload_bytes'],results[key]['family_target_counts'],flush=True)


# Stronger controls for the family-specific learned layout. Neither uses
# family-specific learned compression-vs-access cost models.
storage_only={path:min(TARGETS,key=lambda size:family_stats[path][str(size)]['storage_bytes']) for path in PATHS}
results['family_storage_only']=evaluate(storage_only)
results['family_storage_only']['family_target_counts']=dict(collections.Counter(storage_only.values()))
print('family_storage_only',results['family_storage_only']['total_source_bytes'],results['family_storage_only']['heldout']['mean_passage_payload_bytes'],flush=True)

# Popularity-only heuristic: top-k most retrieved source paths get small chunks,
# everyone else gets one fixed coarse target. Tune k and coarse size on train.
frequency=collections.Counter(r.PATHS[di] for reqs in REQUESTS['train'] for di,_,_ in reqs)
ranked=sorted(PATHS,key=lambda path:(-frequency[path],path))
popularity_choices={}
for horizon in (50,200):
 vals=[]
 for hot in (0,5,10,20,30,40,56):
  for cold_size in (16,32,64):
   layout={path:(8 if path in set(ranked[:hot]) else cold_size) for path in PATHS}
   measured=evaluate(layout)
   obj=measured['total_source_bytes']/horizon+measured['train']['mean_passage_payload_bytes']
   vals.append((obj,hot,cold_size,layout,measured))
 objective,hot,cold_size,layout,measured=min(vals,key=lambda item:item[0])
 key=f'popularity_h{horizon}'
 results[key]=measured
 results[key]['hot_families']=hot
 results[key]['cold_chunk_lines']=cold_size
 popularity_choices[str(horizon)]={'hot_families':hot,'cold_chunk_lines':cold_size,'train_objective':objective}
 print(key,measured['total_source_bytes'],measured['heldout']['mean_passage_payload_bytes'],hot,cold_size,flush=True)

# Held-out stress tests for access-pattern shift. These are not retrieval queries.
# They sample real source passages from random/cold families independent of BM25.
rand=random.Random(700001)
cold_paths=set(sorted(PATHS,key=lambda pa:(frequency[pa],pa))[:max(1,len(PATHS)//4)])
cold_docs=[di for di in range(r.N) if r.PATHS[di] in cold_paths]
for name,pool in [('uniform_random_access',list(range(r.N))),('cold_family_access',cold_docs)]:
 qsets=[]
 for qi in range(150):
  ids=rand.sample(pool,min(10,len(pool)))
  spans=[]
  for di in ids:
   n=len(LINES[di]);a=rand.randrange(max(1,n-4));spans.append((di,a,min(a+5,n)))
  qsets.append(spans)
 REQUESTS[name]=qsets

# Robust mixed layouts: keep reasonable direct-access granularity for families
# rarely observed during training; fixed thresholds, not tuned on heldout data.
robust_choices={}
for max_training_requests in (0,1,3):
 layout={pa:(min(32,chosen['50'][pa]) if frequency[pa]<=max_training_requests else chosen['50'][pa]) for pa in PATHS}
 key=f'robust_unseen_le{max_training_requests}'
 robust_choices[key]=layout
 results[key]=evaluate(layout)
 results[key]['changed_families']=sum(layout[pa]!=chosen['50'][pa] for pa in PATHS)
 print(key,results[key]['total_source_bytes'],results[key]['heldout']['mean_passage_payload_bytes'],results[key]['cold_family_access']['mean_passage_payload_bytes'],flush=True)

# Perform actual warm decoding for main comparisons, matched retrieval windows.
for key,layout in [('global_8',{path:8 for path in PATHS}),('global_32',{path:32 for path in PATHS}),
                   ('mixed_h50',chosen['50']),('mixed_h200',chosen['200']),
                   ('family_storage_only',storage_only),('robust_unseen_le1',robust_choices['robust_unseen_le1']),('popularity_h50',{path:(8 if path in set(ranked[:popularity_choices['50']['hot_families']]) else popularity_choices['50']['cold_chunk_lines']) for path in PATHS})]:
 results[key]=evaluate(layout,measure_decode=True) | {k:v for k,v in results[key].items() if k not in ('train','heldout','total_source_bytes','unique_chunks','exact_reconstructions')}
 print('decode',key,results[key]['heldout']['median_warm_payload_decode_us'],results[key]['heldout']['p95_warm_payload_decode_us'],flush=True)

# Paired query bootstrap on byte reductions; avoids treating source bytes as independent samples.
bootstrap={}
random_boot=random.Random(20261109)
for method,baseline,condition in [('mixed_h50','global_32','heldout'),('mixed_h50','family_storage_only','heldout'),('mixed_h50','popularity_h50','heldout'),('mixed_h50','global_32','cold_family_access'),('robust_unseen_le1','mixed_h50','cold_family_access')]:
 a=results[method][condition]['passage_payload_per_query_bytes']
 b=results[baseline][condition]['passage_payload_per_query_bytes']
 differences=[x-y for x,y in zip(a,b)];n=len(differences)
 draws=sorted(sum(differences[random_boot.randrange(n)] for _ in range(n))/n for _ in range(3000))
 bootstrap[f'{method}_vs_{baseline}_{condition}']={'mean_byte_difference':round(statistics.mean(differences),1), 'paired_bootstrap95_mean_byte_difference':[round(draws[74],1),round(draws[2924],1)]}

out={'bootstrap_comparisons':bootstrap,'dataset':{'real_versions':r.N,'families':len(PATHS),'train_queries':len(r.train),'heldout_queries':len(r.test),'task':'fixed BM25 top-ten passage access','neural_retriever':False},'results':results,'train_selected_family_layouts':chosen,'popularity_baselines':popularity_choices,
     'methodology':'Family granularity minimizes family encoded size/horizon + train average physical passage payload, using actual shared chunk bytes; evaluated on separate queries with real source exact reconstructions.',
     'limitations':['No SSD I/O, actual RAG generator, or dense neural search','One repository, query distribution may differ markedly in real deployments','Serialized metadata costs included; Python runtime/RAM excluded','Mixed granularity may lose cross-family dedup; actual globally deduplicated source size counted','Amortization horizon is a hypothetical source-byte/read-byte equivalence, not an economic cost model','Queries use BM25-selected top-ten versions and five-line passages, not independently labeled answer support']}
(HERE/'round10_mixed_layout_results.json').write_text(json.dumps(out,indent=2))
print('finish',flush=True)
