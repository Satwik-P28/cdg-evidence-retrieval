#!/usr/bin/env python3
"""Round 27 local-storage benchmark, NOT a HotpotQA RAG or SSD benchmark.

Fixed-size versus line-aligned independently compressed Zstandard frames.
Workload is deterministic and synthetic, sampled from genuine research-report text.
Every candidate includes actual sidecar storage and a reversible raw-byte mapping.
"""
from __future__ import annotations
import argparse, ctypes, ctypes.util, hashlib, json, random, statistics, time
from pathlib import Path

class Zstd:
    def __init__(self, level=3):
        path=ctypes.util.find_library('zstd')
        if not path: raise RuntimeError('libzstd is required')
        self.lib=ctypes.CDLL(path); self.level=level
        l=self.lib
        l.ZSTD_compressBound.argtypes=[ctypes.c_size_t];l.ZSTD_compressBound.restype=ctypes.c_size_t
        l.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];l.ZSTD_compress.restype=ctypes.c_size_t
        l.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];l.ZSTD_decompress.restype=ctypes.c_size_t
        l.ZSTD_isError.argtypes=[ctypes.c_size_t];l.ZSTD_isError.restype=ctypes.c_uint
    def compress(self,b):
        if not b:return b''
        dst=ctypes.create_string_buffer(self.lib.ZSTD_compressBound(len(b)))
        src=ctypes.create_string_buffer(b)
        n=self.lib.ZSTD_compress(dst,len(dst),src,len(b),self.level)
        if self.lib.ZSTD_isError(n):raise RuntimeError('compress failed')
        return dst.raw[:n]
    def decompress(self,b,n):
        if n==0:return b''
        dst=ctypes.create_string_buffer(n);src=ctypes.create_string_buffer(b)
        actual=self.lib.ZSTD_decompress(dst,n,src,len(b))
        if self.lib.ZSTD_isError(actual) or actual!=n:raise RuntimeError('decode failed')
        return dst.raw[:n]

def lines(raw):
    out=[];i=0
    for line in raw.splitlines(keepends=True):
        end=i+len(line)
        if len(line.rstrip(b'\r\n')) >= 40:
            out.append((i,end))
        i=end
    assert i==len(raw)
    return out

def fixed(raw,size):
    return [(i,min(i+size,len(raw))) for i in range(0,len(raw),size)]

def line_aligned(raw,span,size):
    """Greedy no-line-split frames except where one line itself exceeds cap.
    This is defined on the raw line grid, including whitespace-only lines.
    """
    frames=[];cur=0
    all_lines=[];i=0
    for l in raw.splitlines(keepends=True):
        all_lines.append((i,i+len(l)));i+=len(l)
    assert i==len(raw)
    for a,b in all_lines:
        while b-a>size:
            if cur<a:frames.append((cur,a));cur=a
            frames.append((a,a+size));a+=size;cur=a
        if a==b:continue
        if a-cur>size:
            raise AssertionError('gap')
        if b-cur>size and a>cur:
            frames.append((cur,a));cur=a
        if b-cur>size:
            frames.append((a,b));cur=b
    if cur<len(raw):frames.append((cur,len(raw)))
    if frames:
        assert frames[0][0]==0 and frames[-1][1]==len(raw)
        assert all(x[1]==y[0] for x,y in zip(frames,frames[1:]))
        assert all(0<b-a<=size for a,b in frames)
    return frames

def activation(frames,spans):
    return [i for i,(a,b) in enumerate(frames) if any(start<end and a<end and start<b for start,end in spans)]

def record_one(raw,spans,layout,codec):
    packed=[codec.compress(raw[a:b]) for a,b in layout]
    for (a,b),p in zip(layout,packed):
        assert codec.decompress(p,b-a)==raw[a:b]
    selected=activation(layout,spans)
    materialized=b''.join(raw[a:b] for a,b in spans)
    touched={i:codec.decompress(packed[i],layout[i][1]-layout[i][0]) for i in selected}
    for a,b in spans:
        recreated=b''.join(touched[i][max(a,layout[i][0])-layout[i][0]:min(b,layout[i][1])-layout[i][0]]
                           for i in selected if layout[i][0]<b and a<layout[i][1])
        assert recreated==raw[a:b]
    return packed,selected,len(materialized)

def run(paths,queries=250,seed=27026,span_style="whole_line"):
    codec=Zstd();corpus=[p.read_bytes() for p in paths]
    candidates=[(i,a,b) for i,raw in enumerate(corpus) for a,b in lines(raw)]
    if not candidates: raise ValueError("No qualifying source lines")
    rng=random.Random(seed); workload=[]
    for n in range(queries):
        ia,a,b=candidates[rng.randrange(len(candidates))]
        if n%3==0:
            other=[(j,c,d) for j,c,d in candidates if j==ia and abs(c-a)<=1024 and c!=a]
            if other:ib,c,d=other[rng.randrange(len(other))]
            else:ib,c,d=candidates[rng.randrange(len(candidates))]
        else:ib,c,d=candidates[rng.randrange(len(candidates))]
        if span_style == "subspan":
            def crop(start, end):
                length=end-start
                n=min(60,max(12,length//3))
                n=min(n,length)
                pos=start+rng.randrange(length-n+1)
                return (pos,pos+n)
            a,b=crop(a,b);c,d=crop(c,d)
        elif span_style != "whole_line":
            raise ValueError(span_style)
        per={ia:[(a,b)]};per.setdefault(ib,[]).append((c,d));workload.append(per)
    results={}
    for mode in ('whole','fixed','line_aligned'):
        for size in ([0] if mode=='whole' else [128,256,512,1024,2048,4096]):
            key=f'{mode}:{size}'
            layouts=[];packs=[]
            for raw in corpus:
                fr=([(0,len(raw))] if mode=='whole' else fixed(raw,size) if mode=='fixed' else line_aligned(raw,None,size))
                compressed=[codec.compress(raw[a:b]) for a,b in fr]
                for (a,b),frame in zip(fr,compressed): assert codec.decompress(frame,b-a)==raw[a:b]
                layouts.append(fr);packs.append(compressed)
            frame_count=sum(len(x) for x in layouts)
            frame_storage=sum(sum(len(q) for q in a) for a in packs)
            # 16 bytes per frame: 64-bit raw start, 32-bit compressed offset, 32-bit packed length.
            # Sidecar is hypothetical; no serialization/API implementation is timed.
            sidecar=16*frame_count
            raw_reads=[];compressed_reads=[];decoded_frame_counts=[];times=[]
            selected_raw=[]
            for per in workload:
                selected=[]; raw_ct=0; compressed_ct=0;frag_count=0
                for i,spans in per.items():
                    ids=activation(layouts[i],spans)
                    for j in ids:
                        a,b=layouts[i][j];raw_ct+=b-a;compressed_ct+=len(packs[i][j]);selected.append((i,j))
                    frag_count+=len(ids)
                    for a,b in spans:selected_raw.append(b-a)
                raw_reads.append(raw_ct);compressed_reads.append(compressed_ct);decoded_frame_counts.append(frag_count)
                # Warm in-memory decompression timing only; no file reads and no indexing.
                st=time.perf_counter_ns()
                dec={(i,j):codec.decompress(packs[i][j],layouts[i][j][1]-layouts[i][j][0]) for i,j in selected}
                for i,spans in per.items():
                    for a,b in spans:
                        got=b''.join(dec[(i,j)][max(a,layouts[i][j][0])-layouts[i][j][0]:min(b,layouts[i][j][1])-layouts[i][j][0]]
                                     for _,j in selected if _==i and layouts[i][j][0]<b and a<layouts[i][j][1])
                        assert got==corpus[i][a:b]
                times.append((time.perf_counter_ns()-st)/1000)
            ordered=sorted(times)
            results[key]={'layout':mode,'frame_limit':size,'n_frames':frame_count,'compressed_payload_bytes':frame_storage,
                          'modeled_frame_table_bytes':sidecar,'total_compressed_plus_frame_table_bytes':frame_storage+sidecar,
                          'mean_compressed_read_bytes':round(statistics.mean(compressed_reads),1),
                          'mean_uncompressed_activated_bytes':round(statistics.mean(raw_reads),1),
                          'mean_frames_decoded':round(statistics.mean(decoded_frame_counts),2),
                          'median_warm_decode_plus_extract_us':round(statistics.median(times),2),
                          'p95_warm_decode_plus_extract_us':round(ordered[min(len(ordered)-1,int(.95*len(ordered)))],2)}
    return {'benchmark':'local CDG report text, synthetic sentence-span queries',
            'source_files':[{'name':p.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for p,raw in zip(paths,corpus)],
            'workload':{'seed':seed,'queries':queries,'mix':'every third query draws nearby second span; other queries random','span_style':span_style,'mean_requested_source_bytes':round(statistics.mean([sum(b-a for spans in q.values() for a,b in spans) for q in workload]),1)},
            'limits':['Not HotpotQA','Not SSD reads','No query engine, title-index, answer model, external verification or update maintenance','Frame tables modeled at 16B per frame','Warm Python-level call timings include extraction; host dependent','All archive sizes are compressed with actual libzstd level 3'],
            'layouts':results}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--files',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--queries',type=int,default=250);p.add_argument('--span-style',choices=('whole_line','subspan'),default='whole_line')
    a=p.parse_args();r=run(a.files,a.queries,span_style=a.span_style);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'workload':r['workload'],'layouts':r['layouts']},indent=2))