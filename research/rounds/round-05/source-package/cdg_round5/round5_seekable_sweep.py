"""Strong compression/access baseline: independently compressed frames with varied line count.
Compare frame sizes on SAME changed-evidence query windows as the hybrid piece store.
"""
import sys,random,time,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_literal_hybrid as h
r=h.r;qs=h.queries;Z=h.Z
results={}
rng=random.Random(874)
for blocksize in [8,16,32,64,128,256,512,1024]:
  frames=[];stored=0
  for raw in r.files:
   lines=raw.splitlines(keepends=True)
   fl=[]
   for b in range(0,len(lines),blocksize):
    part=b''.join(lines[b:b+blocksize]);z=Z.compress(part,3)
    fl.append((z,len(part)));stored+=len(z)+4
   frames.append(fl)
  def fetch(i,a,b):
   accum=[]
   for fid in range(a//blocksize,(b-1)//blocksize+1):
    z,n=frames[i][fid];lines=Z.decompress(z,n).splitlines(keepends=True)
    offset=fid*blocksize
    accum.extend(lines[max(a-offset,0):min(b-offset,blocksize)])
   return b''.join(accum)
  times=[]
  for repeat in range(4):
   shuffled=list(qs);rng.shuffle(shuffled)
   for i,a,b in shuffled:
    t0=time.perf_counter_ns();got=fetch(i,a,b);times.append((time.perf_counter_ns()-t0)/1000)
    assert got==b''.join(r.files[i].splitlines(keepends=True)[a:b])
  results[str(blocksize)]={'source_bytes':stored,'median_us':round(float(np.median(times)),2),
                          'p95_us':round(float(np.percentile(times,95)),2)}
  print(blocksize,results[str(blocksize)],flush=True)
out={'task':'192 5-line windows selected to overlap changed pieces in 250 actual noVNC version histories',
 'baseline':'Independent Zstd-3 compressed per-version line frames; varying 8-1024 lines per frame',
 'frame_index_bytes':'4-byte per-frame offset included; full global document directory omitted',
 'results':results,'limits':['CPU warm cache and Python code; no SSD I/O.','All queries correct by byte-exact comparisons.',
 'Frame size in number of lines produces uneven byte sizes.','No vector-search or LLM inference included.']}
(ROOT/'round5_seekable_sweep_results.json').write_text(json.dumps(out,indent=2))
