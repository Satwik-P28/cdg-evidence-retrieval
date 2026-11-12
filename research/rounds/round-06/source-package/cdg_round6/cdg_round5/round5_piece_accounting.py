"""Accounting for cached versus uncached piece tables, includes construction time.
Runs prior access benchmark on import; all times CPU-only, warm memory.
"""
import json,sys,statistics,time,random,bisect,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_snippet_access as r
from revision_storage_benchmark import Z

def deep_size(o,seen=None):
 if seen is None:seen=set()
 ix=id(o)
 if ix in seen:return 0
 seen.add(ix)
 z=sys.getsizeof(o)
 if isinstance(o,dict):return z+sum(deep_size(k,seen)+deep_size(v,seen) for k,v in o.items())
 if isinstance(o,(tuple,list,set)):return z+sum(deep_size(x,seen) for x in o)
 return z

cached_piece_ram=deep_size(r.piece_tables)
rawbase_ram=deep_size(r.base_lines)
# Serialize structural metadata only, not literal content, and include per-version prefix lengths.
# Representation exercise, not an operational persistent index: literal content still in compressed patches.
metadata=[]
for pts,ends in r.piece_tables:
  buf=bytearray();buf.extend(struct.pack('<I',len(pts)))
  for a,e in zip(pts,ends):
    if a[0]=='ref':buf.extend(struct.pack('<BIII',0,a[1],a[2],e))
    else:buf.extend(struct.pack('<BIII',1,len(a[1]),a[-1],e))
  metadata.append(bytes(buf))
metadata_raw=sum(map(len,metadata));metadata_zstd=sum(len(Z.compress(x,3)) for x in metadata)

def ondemand_piece_read(i,start,stop):
 p=r.paths[i];z,n=r.patches[i]
 ops=json.loads(Z.decompress(z,n))
 pts=[];ends=[];pos=0
 for i0,i1,new in ops:
  if pos<i0:pts.append(('ref',pos,i0,i0-pos))
  if new:
   raw=new.encode();pts.append(('lit',raw,0,len(raw.splitlines(keepends=True))))
  pos=i1
 if pos<len(r.base_lines[p]):pts.append(('ref',pos,len(r.base_lines[p]),len(r.base_lines[p])-pos))
 s=0
 for a in pts:s+=a[-1];ends.append(s)
 k=bisect.bisect_right(ends,start)
 selected=[]
 while k<len(pts) and (ends[k-1] if k>0 else 0)<stop:
  a=pts[k];out0=ends[k-1] if k>0 else 0;lo=max(start-out0,0);hi=min(stop-out0,a[-1]);
  if a[0]=='ref':selected.extend(r.base_lines[p][a[1]+lo:a[1]+hi])
  else:selected.extend(a[1].splitlines(keepends=True)[lo:hi])
  k+=1
 return b''.join(selected)

rng=random.Random(429)
t=[]
for rep in range(4):
  ww=list(r.windows);rng.shuffle(ww)
  for i,a,b in ww:
   t0=time.perf_counter_ns();got=ondemand_piece_read(i,a,b);t.append((time.perf_counter_ns()-t0)/1e3)
   assert got==r.piece_slice(i,a,b)
results={'cached_piece_tables_python_heap_bytes':cached_piece_ram,
'cached_base_lines_python_heap_bytes':rawbase_ram,
'serialized_piece_mapping_bytes_uncompressed':metadata_raw,
'compressed_piece_mapping_zstd3_bytes':metadata_zstd,
'compressed_source_star_zstd3_bytes':r.sizes['base_star_patches_zstd3'],
'combined_compressed_source_and_piece_mapping_bytes':r.sizes['base_star_patches_zstd3']+metadata_zstd,
'benchmark':{'on_demand_piece_median_us':round(float(np.median(t)),2),'on_demand_piece_p95_us':round(float(np.percentile(t,95)),2),
 'cached_piece_median_us':r.res['latency_microseconds']['indexed_piece_slice']['median'],
 'independent_seekable_zstd_median_us':r.res['latency_microseconds']['seekable_zstd32']['median']},
'cautions':['Serialized metadata is a size estimate, not an implemented on-disk lazy piece extractor.',
 'Serialized map lacks literal byte offsets into compressed patch, so direct partial decoding of literals is NOT implemented.',
 'Cached piece-table timing assumes all relevant literal bytes already available in RAM.',
 'On-demand requires full patch decoding but no full version reconstruction.']}
(ROOT/'round5_piece_accounting_results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
