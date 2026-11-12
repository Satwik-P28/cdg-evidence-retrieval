#!/usr/bin/env python3
"""CDG Round 6: storage-byte-budgeted edited-fragment policies on real Git revisions.

Train on a synthetic access log and evaluate separate held-out queries, including a shift.
No learned encoder or claims of real RAG. Includes exact byte verification.
"""
from __future__ import annotations
import sys, os, time, random, json, bisect, struct, collections, statistics, math, array, zlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'cdg_round5'))
sys.path.insert(0,str(HERE/'cdg_round4'/'prev'/'cdg_round3'))
# Import the prior corpus generator while silencing its verbose initial benchmark output.
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
 import round5_snippet_access as r
Z=r.Z
rng=random.Random(526426)
N=len(r.files)

# Base storage and piece mapping are identical for all candidates.
base_frames={};base_disk=0
for path,arr in r.base_lines.items():
 frames=[]
 for t in range(0,len(arr),32):
  raw=b''.join(arr[t:t+32]);packed=Z.compress(raw,3)
  frames.append((packed,len(raw)))
  base_disk+=len(packed)+4
 base_frames[path]=frames

# Build literal pieces and compact, persistable 17-byte piece metadata per version.
metas=[];mapped_disk=0;resident_meta=0
literal_data={};literal_disk=0
by_version=[]
for version,(path,(pieces,ends)) in enumerate(zip(r.paths,r.piece_tables)):
 raw_meta=b'';items=[]
 for idx, (piece,end) in enumerate(zip(pieces,ends)):
  if piece[0]=='ref':
   rec=(0,piece[1],piece[2],piece[-1],end)
   items.append(None)
  else:
   raw=piece[1];z=Z.compress(raw,3)
   ident=(version,idx)
   literal_data[ident]=(raw,z)
   literal_disk+=len(z)+5
   rec=(1,0,len(raw),piece[-1],end)
   items.append(ident)
  raw_meta+=struct.pack('<BIIII',*rec)
 zmeta=Z.compress(raw_meta,3)
 mapped_disk+=len(zmeta)+4
 resident_meta+=len(raw_meta)+4*len(ends)
 metas.append((raw_meta,array.array('I',ends),path,items))
 by_version.append([x for x in items if x is not None])

# Queries select five-line windows centered on a changed (or stable) piece.
version_edits={};version_stable={}
for i, (pieces,ends) in enumerate(r.piece_tables):
 ed=[];st=[]
 for k,piece in enumerate(pieces):
  if piece[-1]==0:continue
  (ed if piece[0]=='lit' else st).append(k)
 version_edits[i]=ed;version_stable[i]=st

# Version popularity deliberately skewed. We use different random draw for held-out windows.
# The rank is a permutation so popularity is not tied to order of corpus extraction.
rank=list(range(N));rng.shuffle(rank)
weights=np.empty(N,dtype=float)
for pos,i in enumerate(rank): weights[i]=1/(pos+1)**.80
weights/=weights.sum()
rotated_weights=np.roll(weights,N//2);rotated_weights/=rotated_weights.sum()

def make_trace(seed, size, popularity, edit_fraction=.75):
 rrr=random.Random(seed)
 # use random.choices to avoid numpy RNG dependence.
 out=[]
 for i in rrr.choices(range(N),weights=popularity,k=size):
  use_edit=rrr.random()<edit_fraction
  pool=version_edits[i] if use_edit else version_stable[i]
  if not pool:pool=version_stable[i] or version_edits[i]
  if not pool:continue
  k=rrr.choice(pool);pts,ends=r.piece_tables[i];p=pts[k]
  lo=ends[k-1] if k else 0
  mid=lo+rrr.randrange(max(p[-1],1));total=ends[-1]
  start=max(0,min(mid-rrr.randrange(5),max(0,total-5)))
  out.append((i,start,min(start+5,total)))
 return out

train=make_trace(991, 3000, weights, .80)
test_same=make_trace(992, 1000, weights, .80)
test_shift=make_trace(993, 1000, rotated_weights, .35)

# Training counts: actual literal pieces touched, not entire versions, using the chosen windows.
counts=collections.Counter()
for i,a,b in train:
 raw,ends,path,items=metas[i]
 k=bisect.bisect_right(ends,a)
 while k<len(ends) and (ends[k-1] if k else 0)<b:
  item=items[k]
  if item is not None:counts[item]+=1
  k+=1

# All comparisons account for identical immutable base frames and persisted piece maps.
# Encode as an independent zstd frame for each literal; 'raw' means direct access to the literal.
# Header is identical length in either format, so it cancels from differences.
all_ids=list(literal_data)
free_raw={ident for ident,(raw,z) in literal_data.items() if len(raw)<=len(z)}
base_extra=base_disk+mapped_disk+literal_disk - sum(len(z)-len(raw) for ident,(raw,z) in literal_data.items() if ident in free_raw)

# Budget is the extra storage beyond a size-optimal raw-versus-zstd decision.
budget64=sum(max(0,len(raw)-len(z)) for (raw,z) in literal_data.values() if len(raw)<=64)
budget256=sum(max(0,len(raw)-len(z)) for (raw,z) in literal_data.values() if len(raw)<=256)
# Optional: extra budget equal to 64B threshold policy.
budget=budget64

def threshold_policy(t):return set(free_raw)|{ident for ident,(raw,z) in literal_data.items() if len(raw)<=t}

def demand_policy(budget, counts, stochastic=False):
 selected=set(free_raw)
 items=[]
 for ident,(raw,z) in literal_data.items():
  d=len(raw)-len(z)
  if d<=0:continue
  f=counts[ident]
  # Estimated saved decompression calls per extra stored byte, with mild workload-independent prior.
  util=(f+.05)*(4+len(raw)/5000)/d
  if stochastic:util=random.Random(ident[0]*100000+ident[1]*17+42).random()
  items.append((util,ident,d))
 items.sort(reverse=True)
 remaining=budget
 for util,ident,d in items:
  if d<=remaining:
   selected.add(ident);remaining-=d
 return selected

policies={
 'all_compressed':set(),
 'size_minimal':set(free_raw),
 'threshold64':threshold_policy(64),
 'threshold256':threshold_policy(256),
 'demand_budget64':demand_policy(budget,counts),
 'random_budget64':demand_policy(budget,counts,True),
 'demand_budget256':demand_policy(budget256,counts),
 'random_budget256':demand_policy(budget256,counts,True),
}

def storage(sets):
 lit=sum((len(raw) if ident in sets else len(z))+5 for ident,(raw,z) in literal_data.items())
 return base_disk+mapped_disk+lit

# Separate independent baselines, all byte exact.
ind={i:(Z.compress(v,3),len(v)) for i,v in enumerate(r.files)}
ind_size=sum(len(c) for c,n in ind.values())
frames={};frame_size=0
for i,v in enumerate(r.files):
 lines=v.splitlines(keepends=True)
 arr=[]
 for j in range(0,len(lines),32):
  raw=b''.join(lines[j:j+32]);c=Z.compress(raw,3)
  arr.append((c,len(raw)));frame_size+=len(c)+4
 frames[i]=arr

def base_slice(path,i,j):
 output=[];store=base_frames[path]
 for block in range(i//32,(j-1)//32+1):
  z,n=store[block];lines=Z.decompress(z,n).splitlines(keepends=True)
  offset=block*32
  output.extend(lines[max(i-offset,0):min(j-offset,32)])
 return b''.join(output)

def read_policy(selected,i,start,stop):
 metadata,ends,path,items=metas[i]
 out=[];k=bisect.bisect_right(ends,start)
 while k<len(ends):
  before=ends[k-1] if k else 0
  if before>=stop:break
  kind,x,y,n,_=struct.unpack_from('<BIIII',metadata,17*k)
  a=max(0,start-before);b=min(n,stop-before)
  if a<b:
   if kind==0:piece=base_slice(path,x+a,x+b)
   else:
    ident=items[k];raw,z=literal_data[ident]
    piece=raw if ident in selected else Z.decompress(z,len(raw))
    piece=b''.join(piece.splitlines(keepends=True)[a:b])
   out.append(piece)
  k+=1
 return b''.join(out)

def read_ind(i,start,stop):
 z,n=ind[i];return b''.join(Z.decompress(z,n).splitlines(keepends=True)[start:stop])

def read_frames(i,start,stop):
 chunks=frames[i];out=[]
 for chunk in range(start//32,(stop-1)//32+1):
  z,n=chunks[chunk];lines=Z.decompress(z,n).splitlines(keepends=True)
  off=chunk*32
  out.extend(lines[max(0,start-off):min(stop-off,32)])
 return b''.join(out)

readers={'independent_full':read_ind,'seekable_frames32':read_frames}
for name,selected in policies.items():readers[name]=lambda i,a,b,selected=selected:read_policy(selected,i,a,b)

# Entire-corpus reconstruction for each policy and every sampled window.
for name,fn in readers.items():
 for i,source in enumerate(r.files):
  goal=source
  nlines=len(source.splitlines(keepends=True))
  assert fn(i,0,nlines)==goal,(name,i,'whole')
 for i,a,b in test_same+test_shift:
  expected=b''.join(r.files[i].splitlines(keepends=True)[a:b])
  assert fn(i,a,b)==expected,(name,i,a,b)

results={}
for trace_name,qs in [('heldout_same',test_same),('heldout_shift',test_shift)]:
 durations={name:[] for name in readers}
 rnd=random.Random(8872)
 for rep in range(5):
  names=list(readers);rnd.shuffle(names)
  for name in names:
   qq=list(qs);rnd.shuffle(qq)
   reader=readers[name]
   for i,a,b in qq:
    t0=time.perf_counter_ns();reader(i,a,b)
    durations[name].append((time.perf_counter_ns()-t0)/1000)
 results[trace_name]={name:{'median_us':round(float(np.median(v)),2),'p95_us':round(float(np.percentile(v,95)),2)} for name,v in durations.items()}

sizes={**{n:storage(s) for n,s in policies.items()},'independent_full':ind_size,'seekable_frames32':frame_size}
obj={
 'study':'Holdout adaptive literal storage selection, real noVNC revision bytes, synthetic query traces',
 'source_versions':N,
 'source_raw_bytes':sum(len(v) for v in r.files),
 'literal_piece_count':len(all_ids),
 'free_raw_count':len(free_raw),
 'shared_base_frame_bytes':base_disk,
 'compressed_piece_map_disk_bytes':mapped_disk,
 'resident_piece_map_metadata_bytes':resident_meta,
 'training':{'queries':len(train),'skew':'Zipf-like permuted popularity, 80% change-oriented windows', 'test_same_queries':len(test_same),'test_shift_queries':len(test_shift),'shift':'version popularity rotated, only 35% change-oriented windows'},
 'budget64_extra_bytes':budget,
 'budget256_extra_bytes':budget256,
 'storage_bytes':sizes,
 'raw_fragment_counts':{n:len(s) for n,s in policies.items()},
 'timings':results,
 'verified':'All 250 full original byte streams reconstruct exactly for every policy and both independently-compressed baselines; all 2000 held-out 5-line windows exact.',
 'limits':['Warm CPU Python microbenchmark, no SSD reads, no neural retrieval or LLM.', 'Source frames and metadata are preloaded;  resident piece-map size counted separately.', 'Access traces synthetically generated from real source revisions, not real user query logs.', 'Policies select fragments using 3000 training synthetic accesses only, test queries independently generated.', 'Selected policy based on synthetic access popularity may fail under distribution shift.', 'No proof of novel algorithm; caching and tiering are established techniques.'],
}
(HERE/'round6_results.json').write_text(json.dumps(obj,indent=2))
print(json.dumps(obj,indent=2))
