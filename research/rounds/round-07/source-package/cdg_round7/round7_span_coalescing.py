#!/usr/bin/env python3
"""Round 7: lossless span coalescing vs fragment-wise compression.

Reuses noVNC genuine version bytes, independently sampled synthetic access traces
from Round 6. The shared compression tree and decoding are implemented in Python.
Everything is accounted as source payload + compact persisted piece metadata.
"""
from __future__ import annotations
import bisect, contextlib, io, json, random, statistics, struct, sys, time
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cdg_round6'))
with contextlib.redirect_stdout(io.StringIO()):
 import round6_access_policy as a
Z=a.Z

class Layout:
 def __init__(self, bridge):
  self.bridge=bridge;self.vs=[];self.lit_store={};self.bytes=a.base_disk;self.merged=0;self.bridged_lines=0
  for idx,(path,(orig,ends)) in enumerate(zip(a.r.paths,a.r.piece_tables)):
   lines=a.r.files[idx].splitlines(keepends=True)
   new=[];j=0
   while j<len(orig):
    cur=orig[j]
    if cur[0]!='lit':
     new.append(cur);j+=1;continue
    st=j; en=j+1
    while en<len(orig):
     p=orig[en]
     if p[0]=='lit': en+=1;continue
     # Cross a small unchanged reference ONLY if another changed piece follows.
     if (p[0]=='ref' and p[-1]<=bridge and en+1<len(orig) and orig[en+1][0]=='lit'):
      en+=2;continue
     break
    if en>j+1:
     begin=ends[st-1] if st else 0;stop=ends[en-1]
     text=b''.join(lines[begin:stop]);new.append(('lit',text,0,stop-begin))
     self.merged+=(en-st-1)
     self.bridged_lines+=sum(p[-1] for p in orig[st:en] if p[0]=='ref')
    else: new.append(cur)
    j=en
   meta=bytearray();until=[];litkeys=[];pos=0
   for k,p in enumerate(new):
    pos+=p[-1];until.append(pos)
    if p[0]=='ref':
     rec=(0,p[1],p[2],p[-1],pos)
     litkeys.append(None)
    else:
     raw=p[1];z=Z.compress(raw,3)
     israw=len(raw)<=256 or len(raw)<=len(z)
     packed=raw if israw else z
     key=(idx,k)
     self.lit_store[key]=(packed,len(raw),israw)
     self.bytes+=len(packed)+5
     rec=(1,0,len(raw),p[-1],pos)
     litkeys.append(key)
    meta.extend(struct.pack('<BIIII',*rec))
   assert pos==len(lines),(idx,pos,len(lines))
   self.bytes+=len(Z.compress(bytes(meta),3))+4
   self.vs.append((path,meta,until,litkeys))
  self.piece_count=sum(len(v[2]) for v in self.vs)
 def read(self,i,start,stop):
  path,metadata,ends,litkeys=self.vs[i]
  out=[];k=bisect.bisect_right(ends,start)
  while k<len(ends) and (ends[k-1] if k else 0)<stop:
   kind,x,y,n,_=struct.unpack_from('<BIIII',metadata,17*k)
   before=ends[k-1] if k else 0
   lo=max(0,start-before);hi=min(n,stop-before)
   if lo<hi:
    if kind==0:
     out.append(a.base_slice(path,x+lo,x+hi))
    else:
     z,rawlen,israw=self.lit_store[litkeys[k]]
     raw=z if israw else Z.decompress(z,rawlen)
     out.append(b''.join(raw.splitlines(keepends=True)[lo:hi]))
   k+=1
  return b''.join(out)

layouts={v:Layout(v) for v in [0,1,2,4,8,16,32]}
# Exact whole-version and changed/unchanged evidence checks
for bridge,layout in layouts.items():
 for i,v in enumerate(a.r.files):
  ln=len(v.splitlines(keepends=True))
  assert layout.read(i,0,ln)==v,(bridge,i,'whole')
 for i,s,t in a.test_same+a.test_shift:
  assert layout.read(i,s,t)==b''.join(a.r.files[i].splitlines(keepends=True)[s:t]),(bridge,i,s,t)

rng=random.Random(7007)
def benchmark(qs,repeat=3):
 readers={f'bridge_{k}':lay.read for k,lay in layouts.items()}
 readers['independent_zstd']=a.read_ind
 readers['seekable_zstd32']=a.read_frames
 # Fixed 256B baseline from round 6
 readers['original_threshold256']=lambda i,s,t:a.read_policy(a.policies['threshold256'],i,s,t)
 times={name:[] for name in readers}
 for rep in range(repeat):
  names=list(readers);rng.shuffle(names)
  for name in names:
   qq=list(qs);rng.shuffle(qq)
   for i,s,t in qq:
    now=time.perf_counter_ns();readers[name](i,s,t)
    times[name].append((time.perf_counter_ns()-now)/1000)
 return {k:{'median_us':round(float(np.median(v)),2),'p95_us':round(float(np.percentile(v,95)),2)} for k,v in times.items()}

metrics={}
for name,trace in [('train',a.train[:700]),('heldout_same',a.test_same),('heldout_shift',a.test_shift)]:
 metrics[name]=benchmark(trace)

out={'data':'250 real noVNC file revisions, synthetic access traces, original Round6 pipeline',
 'intervention':'Coalesce adjacent edited pieces across unchanged bridges of at most K lines. Encode as one literal, raw if <=256 bytes, else Zstd. Keep shared bases and lossless line maps.',
 'storage_bytes':{f'bridge_{k}':v.bytes for k,v in layouts.items()}|{'original_threshold256':a.storage(a.policies['threshold256']),'independent_zstd':a.ind_size,'seekable_zstd32':a.frame_size},
 'piece_count':{f'bridge_{k}':v.piece_count for k,v in layouts.items()},
 'merged_piece_boundaries':{f'bridge_{k}':v.merged for k,v in layouts.items()},
 'duplicated_shared_lines':{f'bridge_{k}':v.bridged_lines for k,v in layouts.items()},
 'timings':metrics,
 'exactness':'Each of 250 versions and 2000 independently generated held-out windows reconstructed byte-for-byte for every bridge threshold',
 'limitations':['All query requests are synthetic over genuine version bytes','Codec, piece traversal, and splitlines occur in warm Python CPU','No SSD I/O or neural retrieval','Metadata in each compact piece map included in source disk bytes; memory allocated by Python excluded','Only same-family coalescing; no global grammar algorithm','Train and heldout have related generative distributions, shifted uses rotated popularity/changed fraction','No normalized p95 CI or external corpus testing yet']}
(ROOT/'round7_span_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))

# Independent query-length stress test: real source, synthetic span requests.
# Probe whether a small merged region is still useful for larger evidence windows.
def length_requests(base_qs,nlines=5):
 result=[]
 for i,s,t in base_qs:
  num=len(a.r.files[i].splitlines(keepends=True))
  center=(s+t)//2
  first=max(0,min(center-nlines//2,max(num-nlines,0)))
  result.append((i,first,min(num,first+nlines)))
 return result

stress={}
readers={
 'original_threshold256':lambda i,s,t:a.read_policy(a.policies['threshold256'],i,s,t),
 'bridge_2':layouts[2].read,'bridge_8':layouts[8].read,
 'bridge_16':layouts[16].read,
 'independent_zstd':a.read_ind,'seekable_zstd32':a.read_frames,
}
for n in [1,5,20,40]:
 qs=length_requests(a.test_same[:450]+a.test_shift[:450],n)
 for i,s,t in qs:
  expected=b''.join(a.r.files[i].splitlines(keepends=True)[s:t])
  for name,reader in readers.items():assert reader(i,s,t)==expected,(n,name,i,s,t)
 times={name:[] for name in readers};rnd=random.Random(1000+n)
 for rep in range(3):
  names=list(readers);rnd.shuffle(names)
  for name in names:
   rr=list(qs);rnd.shuffle(rr)
   for i,s,t in rr:
    start=time.perf_counter_ns();readers[name](i,s,t)
    times[name].append((time.perf_counter_ns()-start)/1000)
 stress[str(n)]={name:{'median_us':round(float(np.median(vals)),2),'p95_us':round(float(np.percentile(vals,95)),2)} for name,vals in times.items()}
obj2={'query_length_stress':stress,'resident_map_payload_bytes':{f'bridge_{k}':sum(len(v[1])+4*len(v[2]) for v in lay.vs.values()) if isinstance(lay.vs,dict) else sum(len(v[1])+4*len(v[2]) for v in lay.vs) for k,lay in layouts.items()},
 'notes':'Combined held-out streams are half matched and half shifted popularity; warm CPU; 900 queries per span length, three runs each.'}
(ROOT/'round7_span_stress.json').write_text(json.dumps(obj2,indent=2))
print('\nSPAN STRESS:')
print(json.dumps(obj2,indent=2))
