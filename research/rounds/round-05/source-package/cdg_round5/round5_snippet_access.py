"""Compare snippet retrieval from version compressed source without full reconstruction.
Exact 5-line windows of real noVNC historical files. CPU warm cache only.
"""
import sys,json,time,random,bisect,collections,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'cdg_round4'/'prev'/'cdg_round3'))
from git_history_retrieval import create
from revision_storage_benchmark import patch,apply_patch,Z
samples=create(250)
files=[s['after'].encode() for s in samples];paths=[s['path'] for s in samples]
base={};base_lines={};bases_z={};ind=[];patches=[];piece_tables=[]
for p,v in zip(paths,files):
 if p not in base:
  base[p]=v; base_lines[p]=v.splitlines(keepends=True);bases_z[p]=Z.compress(v,3)
 ind.append((Z.compress(v,3),len(v)))
 pp=patch(base[p],v)
 patches.append((Z.compress(pp,3),len(pp)))
 # construct pieces for indexed representation; total storage measure for in-memory piece metadata
 ops=json.loads(pp)
 pts=[];pos=0;outlines=0
 for i0,i1,new in ops:
  if pos<i0:
   pts.append(('ref',pos,i0, i0-pos))
  if new:
   dat=new.encode();pts.append(('lit',dat,0,len(dat.splitlines(keepends=True))))
  pos=i1
 if pos<len(base_lines[p]):pts.append(('ref',pos,len(base_lines[p]),len(base_lines[p])-pos))
 ends=[];s=0
 for a in pts:
  s+=a[-1];ends.append(s)
 assert s==len(v.splitlines(keepends=True)),('line mismatch',p)
 piece_tables.append((pts,ends))

# Strong baseline: independent seekable line-aligned Zstd frames (32 lines/frame)
chunks=[];chunk_offsets=[];frame_bytes=0
for v in files:
 arr=v.splitlines(keepends=True)
 blocks=[]
 for i in range(0,len(arr),32):
  raw=b''.join(arr[i:i+32]);blocks.append((Z.compress(raw,3),len(raw)))
  frame_bytes+=len(blocks[-1][0])+4
 chunks.append(blocks)

def piece_slice(idx,start,stop):
  p=paths[idx];pts,ends=piece_tables[idx];k=bisect.bisect_right(ends,start)
  selected=[]
  while k<len(pts) and (ends[k-1] if k>0 else 0)<stop:
   a=pts[k];out0=ends[k-1] if k>0 else 0; lo=max(start-out0,0);hi=min(stop-out0,a[-1]);
   if a[0]=='ref':selected.extend(base_lines[p][a[1]+lo:a[1]+hi])
   else:selected.extend(a[1].splitlines(keepends=True)[lo:hi])
   k+=1
  return b''.join(selected)

def read(mode,i,start,stop):
 if mode=='independent_full':
  z,n=ind[i];return b''.join(Z.decompress(z,n).splitlines(keepends=True)[start:stop])
 if mode=='patch_full_cached_base':
  z,n=patches[i];raw=Z.decompress(z,n);v=apply_patch(base[paths[i]],raw)
  return b''.join(v.splitlines(keepends=True)[start:stop])
 if mode=='indexed_piece_slice':return piece_slice(i,start,stop)
 if mode=='seekable_zstd32':
  selected=[]
  first=start//32;last=(stop-1)//32
  for blockid in range(first,last+1):
   z,n=chunks[i][blockid]
   lines=Z.decompress(z,n).splitlines(keepends=True)
   off=blockid*32
   selected.extend(lines[max(start-off,0):min(stop-off,32)])
  return b''.join(selected)
 raise ValueError(mode)

rng=random.Random(998)
windows=[]
for i,v in enumerate(files):
  n=len(v.splitlines(keepends=True));j=rng.randrange(max(1,n-5)) if n>5 else 0
  windows.append((i,j,min(j+5,n)))
for i,a,b in windows:
  true=b''.join(files[i].splitlines(keepends=True)[a:b])
  for mode in ['independent_full','patch_full_cached_base','indexed_piece_slice','seekable_zstd32']:
    assert read(mode,i,a,b)==true,(mode,i,a,b)

modes=['independent_full','patch_full_cached_base','indexed_piece_slice','seekable_zstd32']
times={m:[] for m in modes}
for rep in range(6):
  rng.shuffle(modes)
  for mode in modes:
    ww=list(windows);rng.shuffle(ww)
    for i,a,b in ww:
      t0=time.perf_counter_ns();out=read(mode,i,a,b)
      times[mode].append((time.perf_counter_ns()-t0)/1000)
# metadata is Python (RAM) and not disk, report counts instead of claiming negligible
sizes={'independent_zstd3':sum(len(z) for z,_ in ind),
 'base_star_patches_zstd3':sum(len(z) for z in bases_z.values())+sum(len(z)+4 for z,_ in patches),
 'independent_seekable_32_lines_zstd3_plus_4byte_offsets':frame_bytes,
 'piece_table_num_pieces':sum(len(x[0]) for x in piece_tables),
 'piece_table_python_objects_not_counted_on_disk':True}
res={'dataset':'250 noVNC real source revisions, 250 fixed random 5-line windows, 6 repeated randomized-order measurements',
'roundtrip':'All 5-line samples match original bytes for all methods','compressed_storage_bytes':sizes,
 'latency_microseconds':{mode:{'median':round(float(np.median(t)),2),'p95':round(float(np.percentile(t,95)),2)} for mode,t in times.items()},
 'limitations':['Indexed piece tables are already constructed in RAM before timing, so their preprocessing and RAM cost is excluded from lookup latency.',
 'Patch full method assumes uncompressed family bases cached in RAM.',
 'All access CPU warm cache; no SSD cost, no actual RAG model.',
 'Frames are 32 lines per independently compressed version, not cross-version deduplication.',
 'Piece table is an established text-editor/data-structure idea, not a new method.']}
(ROOT/'round5_snippet_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
