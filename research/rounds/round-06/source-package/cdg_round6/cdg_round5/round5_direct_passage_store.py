"""Experimental direct passage access over versioned, losslessly shared source.
Uses 32-line independent seekable base frames + per-version compressed literal payload + compact piece map.
This implementation verifies all source bytes and random 5-line windows, not an ANN/RAG model.
"""
import sys,struct,json,time,bisect,random,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_snippet_access as r
from revision_storage_benchmark import Z

BASE_BLOCK=32
base_frames={}
base_bytes=0
for path,lines in r.base_lines.items():
  frames=[]
  for i in range(0,len(lines),BASE_BLOCK):
    raw=b''.join(lines[i:i+BASE_BLOCK]);z=Z.compress(raw,3)
    frames.append((z,len(raw)))
    base_bytes+=len(z)+4
  base_frames[path]=frames

# direct seek version payload metadata
version=[]
piece_meta_bytes=0;literal_compressed_bytes=0
for path,(pieces,ends) in zip(r.paths,r.piece_tables):
   data=bytearray();meta=[];raw=bytearray()
   for a,e in zip(pieces,ends):
     if a[0]=='ref':
       # kind, a=original first line, b=original last line (exclusive), n_lines, output end
       rec=(0,a[1],a[2],a[-1],e)
     else:
       b=a[1];offset=len(raw);raw.extend(b)
       rec=(1,offset,len(b),a[-1],e)
     meta.append(rec)
     data+=struct.pack('<BIIII',*rec)
   zm=Z.compress(bytes(data),3);zl=Z.compress(bytes(raw),3) if raw else b''
   piece_meta_bytes+=len(zm)+4
   literal_compressed_bytes+=len(zl)+4
   version.append({'path':path,'meta':meta,'ends':ends,'zmeta':zm,'literal':zl,'lit_len':len(raw)})

def base_slice(path,i,j):
  frames=base_frames[path];output=[]
  for block in range(i//BASE_BLOCK,(j-1)//BASE_BLOCK+1):
    zz,n=frames[block]
    txt=Z.decompress(zz,n).splitlines(keepends=True)
    off=block*BASE_BLOCK
    output.extend(txt[max(i-off,0):min(j-off,BASE_BLOCK)])
  return b''.join(output)

def direct_passage(i,start,stop,cache_base=False):
  e=version[i];idx=bisect.bisect_right(e['ends'],start)
  output=[];rawlit=None
  while idx<len(e['meta']):
    kind,x,y,nlines,until=e['meta'][idx]
    preceding=e['ends'][idx-1] if idx else 0
    if preceding>=stop:break
    a=max(0,start-preceding);b=min(nlines,stop-preceding)
    if a<b:
      if kind==0:
        if cache_base:piece=b''.join(r.base_lines[e['path']][x+a:x+b])
        else:piece=base_slice(e['path'],x+a,x+b)
      else:
        if rawlit is None:rawlit=Z.decompress(e['literal'],e['lit_len'])
        lines=rawlit[x:x+y].splitlines(keepends=True)
        piece=b''.join(lines[a:b])
      output.append(piece)
    idx+=1
  return b''.join(output)

assert len(version)==len(r.files)
for i,b in enumerate(r.files):
  lines=b.splitlines(keepends=True)
  assert direct_passage(i,0,len(lines))==b,(i,'whole file')
  for start in [0,max(0,len(lines)//2-2),max(0,len(lines)-5)]:
    assert direct_passage(i,start,min(len(lines),start+5))==b''.join(lines[start:start+5])
for i,a,b in r.windows:
 assert direct_passage(i,a,b)==r.piece_slice(i,a,b)

rng=random.Random(198)
times={m:[] for m in ['direct_cold_base','direct_cached_base','independent_full','seekable_own']}
for repeat in range(6):
 modes=list(times);rng.shuffle(modes)
 for mode in modes:
  windows=list(r.windows);rng.shuffle(windows)
  for i,a,b in windows:
   t0=time.perf_counter_ns()
   if mode=='direct_cold_base':res=direct_passage(i,a,b,False)
   elif mode=='direct_cached_base':res=direct_passage(i,a,b,True)
   elif mode=='independent_full':res=r.read('independent_full',i,a,b)
   else:res=r.read('seekable_zstd32',i,a,b)
   times[mode].append((time.perf_counter_ns()-t0)/1000)

storage=base_bytes+piece_meta_bytes+literal_compressed_bytes
res={'corpus':'250 genuine noVNC file revisions, five-line queries','correctness':'all 250 full documents reconstructed byte-exact from compressed pieces; all sampled windows exact',
 'compressed_source_bytes':{'base_seekable_frames':base_bytes,'piece_maps_compressed':piece_meta_bytes,
  'per_version_literal_payloads_compressed':literal_compressed_bytes,'combined_direct_passage_store':storage,
  'independent_zstd':r.sizes['independent_zstd3'],'independent_32line_seekable':r.sizes['independent_seekable_32_lines_zstd3_plus_4byte_offsets'],
  'base_star_patch':r.sizes['base_star_patches_zstd3']},
 'median_latency_microseconds':{m:round(float(np.median(t)),2) for m,t in times.items()},
 'p95_latency_microseconds':{m:round(float(np.percentile(t,95)),2) for m,t in times.items()},
 'notes':['Physical storage includes independent compressed base frames, compressed piece-map per version, and literal data per version.',
  'Search index and vocabulary not included.','Piece map decoded from disk before query and held as Python objects; exclude RAM and index-loading cost.',
  'Two direct retrieval modes: base frames decoded on demand; or base original lines cached in RAM.',
  'Every version full reconstruction is checked; no real RAG semantic evaluation.','Base frame metadata counts 4 bytes per frame, actual offsets and file catalog not fully persisted.']}
(ROOT/'round5_direct_passage_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
