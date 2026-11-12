"""Same-run, randomized benchmark of literal-storage policies against independently seekable source.
Focus on edited evidence windows, RAG likely to need changed facts.
"""
import sys,time,random,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_literal_hybrid as h
r=h.r;queries=h.queries
frames64,n64=h.encode(64);frames256,n256=h.encode(256)
modes=['independent_full','independent_seekable','per_version_literals','raw_under_64','raw_under_256']
times={m:[] for m in modes};rng=random.Random(17771)
for rep in range(9):
 methods=list(modes);rng.shuffle(methods)
 for mode in methods:
  qs=list(queries);rng.shuffle(qs)
  for i,a,b in qs:
   t0=time.perf_counter_ns()
   if mode=='independent_full':got=r.read('independent_full',i,a,b)
   elif mode=='independent_seekable':got=r.read('seekable_zstd32',i,a,b)
   elif mode=='per_version_literals':got=h.c.compact_read(i,a,b)
   elif mode=='raw_under_64':got=h.read(i,a,b,frames64)
   else:got=h.read(i,a,b,frames256)
   times[mode].append((time.perf_counter_ns()-t0)/1000)
   assert got==b''.join(r.files[i].splitlines(keepends=True)[a:b])
result={'query_type':'192 actual edited-piece-centered 5-line windows, 9 randomized repeats per method',
 'source_bytes':{'independent_full':r.sizes['independent_zstd3'],
 'independent_seekable':r.sizes['independent_seekable_32_lines_zstd3_plus_4byte_offsets'],
 'per_version_literals':h.c.src.storage,
 'raw_under_64':h.c.src.base_bytes+h.c.src.piece_meta_bytes+n64,
 'raw_under_256':h.c.src.base_bytes+h.c.src.piece_meta_bytes+n256},
 'median_latency_us':{k:round(float(np.median(v)),2) for k,v in times.items()},
 'p95_latency_us':{k:round(float(np.percentile(v,95)),2) for k,v in times.items()},
 'all_results_exact':True,
 'limits':['Warm CPU and resident metadata.','No read from disk or natural-language retrieval loop.','Compression source sizes exclude lexical index, shared code and model.','Python prototype, not compiled engine.']}
(ROOT/'round5_head_to_head_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
