#!/usr/bin/env python3
"""Negative control: prime-length chunk scheduling vs near-equal fixed lengths.

This does not apply the Riemann hypothesis. Prime scheduling is merely a
number-theoretic arbitrary deterministic schedule and should not help on text.
"""
import ctypes,ctypes.util,hashlib,json,random,statistics
from pathlib import Path
L=ctypes.CDLL(ctypes.util.find_library('zstd'))
L.ZSTD_compressBound.argtypes=[ctypes.c_size_t];L.ZSTD_compressBound.restype=ctypes.c_size_t
L.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];L.ZSTD_compress.restype=ctypes.c_size_t
L.ZSTD_isError.argtypes=[ctypes.c_size_t];L.ZSTD_isError.restype=ctypes.c_uint

def compressed_len(data):
    b=L.ZSTD_compressBound(len(data));dest=ctypes.create_string_buffer(b);src=ctypes.create_string_buffer(data)
    n=L.ZSTD_compress(dest,b,src,len(data),3)
    if L.ZSTD_isError(n):raise ValueError('zstd failure')
    return int(n)

def partitions(blob,schedule):
    out=[];pos=0;i=0
    while pos<len(blob):
        end=min(len(blob),pos+schedule[i%len(schedule)])
        out.append((pos,end,compressed_len(blob[pos:end])))
        pos=end;i+=1
    return out

def query_bytes(parts,start,end):
    return sum(n for a,b,n in parts if start<b and end>a)

def run(paths):
    rng=random.Random(33116)
    hashes={}
    # Average scheduled length 509: compare fixed 509, also fixed 512.
    schedules={'fixed_509':[509],'fixed_512':[512],'prime_schedule':[487,503,509,521,523,511]}
    # 511 is NOT prime. Remove it deliberately to avoid pretending prime schedule.
    schedules['prime_schedule']=[487,503,509,521,523]
    # Share the exact same sample queries across layouts.
    stats={k:{'archive_bytes':0,'frame_entries':0,'read_bytes':[]} for k in schedules}
    rng=random.Random(33116)
    hashes={}
    for index,p in enumerate(paths):
        blob=Path(p).read_bytes();hashes[f'report_{index+1:02d}.md']=hashlib.sha256(blob).hexdigest();spans=[];pos=0
        for line in blob.splitlines(keepends=True):
            if line.strip():spans.append((pos,pos+len(line)))
            pos+=len(line)
        requests=[rng.sample(spans,2) for _ in range(50)]
        for typ,sched in schedules.items():
            frames=partitions(blob,sched)
            stats[typ]['archive_bytes']+=sum(z for a,b,z in frames)
            stats[typ]['frame_entries']+=len(frames)
            for selection in requests:stats[typ]['read_bytes'].append(sum(query_bytes(frames,a,b) for a,b in selection))
    result={'scope':'real text, synthetic sampled whole-line queries, compressed payload without metadata/CPU; prime schedule is arbitrary, no RH theorem','files':hashes,'queries':250,'methods':{}}
    for typ,row in stats.items():
        result['methods'][typ]={'compressed_payload_bytes':row['archive_bytes'],'frames':row['frame_entries'],'modeled_16B_entry_table':row['frame_entries']*16,'mean_compressed_bytes_per_query':round(statistics.mean(row['read_bytes']),2),'median_compressed_bytes_per_query':round(statistics.median(row['read_bytes']),2)}
    return result

if __name__=='__main__':
    import sys
    out=run([Path(p) for p in sys.argv[1:]])
    print(json.dumps(out,indent=2))
