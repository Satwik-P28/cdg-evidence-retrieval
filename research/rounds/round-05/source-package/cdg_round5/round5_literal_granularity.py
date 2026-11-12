"""Selective changed-evidence decoding: compress each literal hunk separately instead of whole-version literal payload.
This is a storage-latency tradeoff, evaluated on real source histories with stable/edited windows.
"""
import sys,json,time,random,bisect,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_compact_metadata as c
r=c.src.r
zlib=c.src.Z
frames=[];frame_payload=0;litcount=0
for i,(pts,ends) in enumerate(r.piece_tables):
 arr=[]
 for j,a in enumerate(pts):
  if a[0]=='lit':
   raw=a[1];zz=zlib.compress(raw,3)
   frame_payload+=len(zz)+4;arr.append((zz,len(raw)));litcount+=1
  else:arr.append(None)
 frames.append(arr)

def read_piece(i,start,stop):
  records,ends,path,lit,litlen=c.compact[i];k=bisect.bisect_right(ends,start);output=[]
  while k<len(ends):
   prev=ends[k-1] if k>0 else 0
   if prev>=stop:break
   kind,x,y,nlines,ending=struct.unpack_from('<BIIII',records,17*k)
   a=max(0,start-prev);b=min(nlines,stop-prev)
   if a<b:
    if kind==0:piece=c.src.base_slice(path,x+a,x+b)
    else:
     zz,n=frames[i][k]
     piece=b''.join(zlib.decompress(zz,n).splitlines(keepends=True)[a:b])
    output.append(piece)
   k+=1
  return b''.join(output)

for i,raw in enumerate(r.files):
 assert read_piece(i,0,len(raw.splitlines(keepends=True)))==raw

rng=random.Random(73)
windows={'random':r.windows,'stable':[],'changed':[]}
for i,(pieces,ends) in enumerate(r.piece_tables):
  total=ends[-1]
  for kind,label in [('ref','stable'),('lit','changed')]:
   choices=[j for j,x in enumerate(pieces) if x[0]==kind and x[-1]>0]
   if not choices:continue
   j=rng.choice(choices);startpiece=ends[j-1] if j else 0
   middle=startpiece+pieces[j][-1]//2;start=min(max(0,middle-2),max(0,total-5))
   windows[label].append((i,start,min(total,start+5)))
res={}
for label,qs in windows.items():
 timings={'per_piece':[],'per_version':[],'independent_seekable':[]}
 for rep in range(6):
  methods=list(timings);rng.shuffle(methods)
  for method in methods:
   qq=list(qs);rng.shuffle(qq)
   for i,a,b in qq:
    t0=time.perf_counter_ns()
    if method=='per_piece':got=read_piece(i,a,b)
    elif method=='per_version':got=c.compact_read(i,a,b)
    else:got=r.read('seekable_zstd32',i,a,b)
    timings[method].append((time.perf_counter_ns()-t0)/1000)
    assert got==b''.join(r.files[i].splitlines(keepends=True)[a:b])
 res[label]={'n':len(qs),'median_us':{k:round(float(np.median(v)),2) for k,v in timings.items()},
  'p95_us':{k:round(float(np.percentile(v,95)),2) for k,v in timings.items()}}

storage=c.src.base_bytes+c.src.piece_meta_bytes+frame_payload
out={'corpus':'250 noVNC real versions','literal_frames':litcount,'source_bytes':{
  'original_per_version_literal':c.src.storage,'selective_per_literal':storage,
  'independent_32_line_seekable':r.sizes['independent_seekable_32_lines_zstd3_plus_4byte_offsets']},
 'piece_payload_zstd3_and_length_metadata':frame_payload,'latency':res,
 'checks':'whole source reconstructs exactly; every tested five-line window identical to original',
 'limitations':['Source only; no real neural retrieval or generation.',
  'Metadata for all piece records is resident; compressed blocks warm in memory/OS cache.',
  'Per-literal blocks trade increased overhead for selective changed-region decoding.',
  'Literal frame pointers and complete file catalog costs not separately serialized.']}
(ROOT/'round5_literal_granularity_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
