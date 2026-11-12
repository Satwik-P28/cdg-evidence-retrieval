"""Compact 17-byte packed piece maps, 32-bit prefix-search arrays, source range access.
No Python list of piece records retained during lookup. Base frames decoded on demand.
"""
import sys,struct,json,bisect,time,random,array
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import round5_direct_passage_store as src

compact=[];resident_meta_bytes=0
for e in src.version:
    raw=b''.join(struct.pack('<BIIII',*rec) for rec in e['meta'])
    ends=array.array('I',e['ends'])
    compact.append((raw,ends,e['path'],e['literal'],e['lit_len']))
    resident_meta_bytes+=len(raw)+len(ends)*4

def compact_read(i,start,stop):
    records,ends,path,lit,litlen=compact[i]
    k=bisect.bisect_right(ends,start)
    output=[];literals=None
    while k<len(ends):
        previous=ends[k-1] if k>0 else 0
        if previous>=stop:break
        kind,x,y,nlines,ending=struct.unpack_from('<BIIII',records,k*17)
        a=max(0,start-previous);b=min(nlines,stop-previous)
        if a<b:
            if kind==0:piece=src.base_slice(path,x+a,x+b)
            else:
                if literals is None:literals=src.Z.decompress(lit,litlen)
                piece=b''.join(literals[x:x+y].splitlines(keepends=True)[a:b])
            output.append(piece)
        k+=1
    return b''.join(output)

for i,original in enumerate(src.r.files):
    assert compact_read(i,0,len(original.splitlines(keepends=True)))==original
for i,a,b in src.r.windows:
    assert compact_read(i,a,b)==src.r.piece_slice(i,a,b)

rng=random.Random(10021)
t=[]
for repeat in range(6):
    ww=list(src.r.windows);rng.shuffle(ww)
    for i,a,b in ww:
        t0=time.perf_counter_ns();compact_read(i,a,b);t.append((time.perf_counter_ns()-t0)/1e3)
res={'corpus_versions':len(compact),'packed_piece_map_record_bytes':17,'piece_count':sum(len(x[1]) for x in compact),
  'resident_compact_piece_map_bytes':resident_meta_bytes,
  'median_5line_read_microseconds':round(float(np.median(t)),2),
  'p95_5line_read_microseconds':round(float(np.percentile(t,95)),2),
  'source_compressed_disk_bytes':src.storage,
  'correctness':'250 byte exact full reconstruction and 250 byte exact random 5-line windows',
  'comparators':{'full_document_zstd_median_us':src.res['median_latency_microseconds']['independent_full'],
                 'independent_seekable_32line_median_us':src.res['median_latency_microseconds']['seekable_own'],
                 'independent_seekable_disk_bytes':src.res['compressed_source_bytes']['independent_32line_seekable'],
                 'independent_zstd_disk_bytes':src.res['compressed_source_bytes']['independent_zstd']},
  'limitations':['Resident metadata and compressed base/literal payloads are assumed warm in RAM / OS cache.',
                 'Disk I/O and on-demand metadata load not timed.',
                 'Only source access; excludes retrieval engine and LLM.']}
(ROOT/'round5_compact_metadata_results.json').write_text(json.dumps(res,indent=2))
print(json.dumps(res,indent=2))
