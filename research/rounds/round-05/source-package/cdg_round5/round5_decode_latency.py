"""CPU-only decode latency on same real noVNC version corpus, roundtrip verified.
Independent zstd vs star patch with/without uncompressed base cache.
"""
import sys,json,time,collections,hashlib,random,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'cdg_round4'/'prev'/'cdg_round3'))
from git_history_retrieval import create
from revision_storage_benchmark import patch,apply_patch,Z
samples=create(250)
base_by_path={};basez_by_path={};ind=[];deltas=[]
for s in samples:
  b=s['after'].encode();p=s['path']
  if p not in base_by_path:
   base_by_path[p]=b;basez_by_path[p]=Z.compress(b,3)
  bz=Z.compress(b,3);ind.append((bz,len(b)))
  payload=patch(base_by_path[p],b)
  deltas.append((Z.compress(payload,3),len(payload),p,hashlib.sha256(b).digest()))

def recon(mode,i):
  if mode=='independent':
    z,ln=ind[i];return Z.decompress(z,ln)
  z,ln,p,sha=deltas[i]
  base=base_by_path[p] if mode=='cached_base' else Z.decompress(basez_by_path[p],len(base_by_path[p]))
  return apply_patch(base,Z.decompress(z,ln))
for i in range(len(samples)):
  assert recon('independent',i)==recon('uncached_base',i)==recon('cached_base',i)
rng=random.Random(400)
modes=('independent','uncached_base','cached_base');times={m:[] for m in modes}
for run in range(6):
  modeorder=list(modes);rng.shuffle(modeorder)
  for mode in modeorder:
    ix=list(range(len(samples)));rng.shuffle(ix)
    for i in ix:
      t0=time.perf_counter_ns();b=recon(mode,i);t1=time.perf_counter_ns()
      times[mode].append((t1-t0)/1e3)
out={'samples':len(samples),'repeats':6,'unit':'microseconds per random version read, CPU only, warm OS cache',
 'decode':{m:{'median_us':round(float(np.median(t)),2),'p95_us':round(float(np.percentile(t,95)),2),'mean_us':round(float(np.mean(t)),2)} for m,t in times.items()},
 'roundtrip_verified':True,
 'limitations':['Per-read Python patch reconstruction, no C/Rust optimized implementation.','Caching base as raw data consumes extra RAM, not included in compressed bytes.', 'No SSD read or end-to-end RAG latency measured.']}
(ROOT/'round5_decode_latency_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
