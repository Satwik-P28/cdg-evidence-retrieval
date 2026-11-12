#!/usr/bin/env python3
"""Local real-zstd independent-frame experiment on *research-report text*, not SciFact.
No SSD read timings; source positions are sampled by a deterministic synthetic workload.
"""
import ctypes, ctypes.util, hashlib, json, random, statistics, time
from pathlib import Path
L=ctypes.CDLL(ctypes.util.find_library('zstd'))
L.ZSTD_compressBound.argtypes=[ctypes.c_size_t]; L.ZSTD_compressBound.restype=ctypes.c_size_t
L.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]; L.ZSTD_compress.restype=ctypes.c_size_t
L.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]; L.ZSTD_decompress.restype=ctypes.c_size_t
L.ZSTD_isError.argtypes=[ctypes.c_size_t]; L.ZSTD_isError.restype=ctypes.c_uint

def compress(x):
    dst=ctypes.create_string_buffer(L.ZSTD_compressBound(len(x)))
    src=ctypes.create_string_buffer(x,len(x))
    k=L.ZSTD_compress(dst,len(dst),src,len(x),3)
    if L.ZSTD_isError(k):raise ValueError('zstd compress')
    return dst.raw[:k]
def decompress(x,n):
    dst=ctypes.create_string_buffer(n)
    src=ctypes.create_string_buffer(x,len(x))
    k=L.ZSTD_decompress(dst,n,src,len(x))
    if L.ZSTD_isError(k) or k!=n:raise ValueError('zstd decompress')
    return dst.raw[:n]

def main():
    data=Path('/mnt/data/CDG_Living_Research_Record_Rounds_19_20_2026-11-11.md').read_bytes()
    rng=random.Random(20261112)
    spans=[(a,a+rng.randrange(50,350)) for a in [rng.randrange(0,len(data)-350) for _ in range(250)]]
    rows=[]
    for b in (128,256,512,1024,2048,4096,8192):
        raw=[data[i:i+b] for i in range(0,len(data),b)]
        compressed=[compress(c) for c in raw]
        assert b''.join(decompress(c,len(r)) for c,r in zip(compressed,raw))==data
        query_comp=[];query_decomp=[];query_frames=[]
        for a,z in spans:
            chosen=set(range(a//b,(z-1)//b+1))
            query_comp.append(sum(len(compressed[j]) for j in chosen))
            query_decomp.append(sum(len(raw[j]) for j in chosen))
            query_frames.append(len(chosen))
        rows.append(dict(frame_bytes=b,frame_count=len(raw),actual_zstd_payload_bytes=sum(map(len,compressed)),
          modeled_seek_table_bytes=8*len(raw)+17, total_with_modeled_table_bytes=sum(map(len,compressed))+8*len(raw)+17,
          ratio_with_table=round((sum(map(len,compressed))+8*len(raw)+17)/len(data),4),
          sampled_mean_compressed_activation_bytes=round(statistics.mean(query_comp),1),
          sampled_mean_decompressed_activation_bytes=round(statistics.mean(query_decomp),1),
          sampled_mean_frames=round(statistics.mean(query_frames),2)))
    obj={'protocol':'round21-local-zstd-independent-frames-v1','source':'user-provided Round 19-20 research Markdown, not SciFact','source_bytes':len(data),'source_sha256':hashlib.sha256(data).hexdigest(),'compression_level':3,'n_synthetic_source_spans':len(spans),'tables':rows,'limitations':['Frame payloads use libzstd individually; 8 bytes per frame + 17 seek-table overhead is a modeled no-checksum table, not a serialized official seekable archive.','No measured SSD reads, cache behavior, p95 latency, neural model, or real query offsets.','Document is a single research report; storage ratios cannot generalize to SciFact or heterogeneous corpora.']}
    print(json.dumps(obj,indent=2))
if __name__=='__main__':main()
