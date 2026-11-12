"""Lossless source storage for SAME 250 revisions used in Round 5 retrieval.
Independent per-version zstd3 vs per-path star patches with exact round trips.
"""
import sys,json,collections,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'cdg_round4'/'prev'/'cdg_round3'))
from git_history_retrieval import create
from revision_storage_benchmark import patch,apply_patch,Z
start=time.perf_counter()
samples=create(250)
groups=collections.defaultdict(list)
for s in samples:groups[s['path']].append(s['after'].encode())
independent=0; shared=0; hybrid=0; recomputed=0; solid_buf=[]; family_results=[]
for path,versions in groups.items():
  iz=[Z.compress(x,3) for x in versions]; independent += sum(map(len,iz)); solid_buf.extend(versions)
  # one first version is base; compare direct patch vs independent per version; metadata 4 bytes/payload
  base=versions[0]; bz=iz[0]
  storage=len(bz)+4; count_patches=0
  for i,v in enumerate(versions[1:],1):
    raw=patch(base,v);z=Z.compress(raw,3)
    assert apply_patch(base,Z.decompress(z,len(raw)))==v
    storage+=len(z)+4;count_patches+=1
  h=min(storage,sum(map(len,iz))+4*len(versions))+1
  shared+=storage;hybrid+=h; recomputed+=count_patches
  family_results.append({'path':path,'versions':len(versions),'independent_bytes':sum(map(len,iz)),'star_patch_bytes':storage})
# zstd9 solid archive has no per-version direct access, archive is by concatenation with length metadata
import struct
all_versions=[s['after'].encode() for s in samples]
solid=Z.compress(b''.join(struct.pack('<I',len(x))+x for x in all_versions),9)
out={'versions':len(samples),'families':len(groups),'raw_bytes':sum(map(len,all_versions)),
 'compressed_source_bytes':{'independent_zstd3':independent,'base_star_patch_zstd3':shared,
 'hybrid_per_family_choose_min':hybrid,'solid_zstd9':len(solid)},
 'patch_roundtrip_verified':recomputed,'complete_versions':len(samples),'seconds':round(time.perf_counter()-start,2),
 'limitations':['Patch star uses first observed version as base, not optimized root.',
 'Source bytes only; separate lexical index and vocabulary must be counted for total system.',
 'Solid archive cannot retrieve versions without additional index and decoding work.',
 'Random access/time not measured by this experiment.']}
(ROOT/'round5_storage_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
