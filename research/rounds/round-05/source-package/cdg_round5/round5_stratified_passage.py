"""Unchanged vs edited passage access. Avoid favorable random-window distribution.
Compares same version snippet windows selected to overlap changed vs stable pieces.
"""
import sys,json,time,random,bisect
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_compact_metadata as c
r=c.src.r
rng=random.Random(651)
windows={'stable':[], 'changed':[]}
for i,(pts,ends) in enumerate(r.piece_tables):
  total=ends[-1]
  for kind,label in [('ref','stable'),('lit','changed')]:
    options=[(j,a) for j,a in enumerate(pts) if a[0]==kind and a[-1]>0]
    if not options:continue
    j,a=rng.choice(options)
    piece_start=ends[j-1] if j else 0
    middle=piece_start+(a[-1]//2)
    start=min(max(0,middle-2),max(0,total-5))
    stop=min(total,start+5)
    windows[label].append((i,start,stop))

means={}
for label,ww in windows.items():
 times={m:[] for m in ['compact','independent','seekable']}
 for rep in range(6):
  modes=list(times);rng.shuffle(modes)
  for m in modes:
   selected=list(ww);rng.shuffle(selected)
   for i,start,stop in selected:
    t0=time.perf_counter_ns()
    if m=='compact':got=c.compact_read(i,start,stop)
    elif m=='independent':got=r.read('independent_full',i,start,stop)
    else:got=r.read('seekable_zstd32',i,start,stop)
    times[m].append((time.perf_counter_ns()-t0)/1000)
    assert got==b''.join(r.files[i].splitlines(keepends=True)[start:stop])
 means[label]={'versions_with_window':len(ww),
  'median_us':{m:round(float(np.median(x)),2) for m,x in times.items()},
  'p95_us':{m:round(float(np.percentile(x,95)),2) for m,x in times.items()}}
res={'experiment':'Five-line windows selected to overlap one stable or changed piece per real source version, 6 repeated randomized passes',
'correctness':'All checked byte-exact', 'results':means,'limitations':['Window selection is by structural piece, not by natural language retrieval relevance.',
'As before, metadata and compressed payloads are loaded/warm; no real SSD latency.',
'Changed windows may overlap unchanged lines; they are selected to contain a change.',
'Not a neural retrieval benchmark.']}
(ROOT/'round5_stratified_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
