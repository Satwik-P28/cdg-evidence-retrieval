"""Reproducible preliminary size/correctness microbenchmarks for BARM.

Synthetic zeta samples use a finite truncated distribution, NOT Merhav's
unbounded zeta distribution. Audit-report word positions are a local proxy,
NOT an authentic QASPER, SciFact, or Lean index.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import os
import re
import time
import zlib
from pathlib import Path
import numpy as np
from barm import (
  encode_block, decode_block, encode_golomb_block, decode_golomb_block,
  encode_elias, decode_elias, encode_varint, decode_varint,
  encode_block_bitpack, decode_block_bitpack, estimate_beta, select_r,
)

B=128

def sample_truncated_zeta(beta: float, n: int, rng, cap: int=65536) -> list[int]:
    x=np.arange(1, cap+1, dtype=np.float64)
    weights=np.power(x, -beta)
    cum=np.cumsum(weights)
    cum /= cum[-1]
    return (np.searchsorted(cum, rng.random(n), side='left')+1).tolist()


def audit_word_gaps(path: str):
    text=Path(path).read_text(encoding='utf-8')
    toks=re.findall(r"[a-z][a-z0-9]{1,30}", text.lower())
    d=collections.defaultdict(list)
    for j,t in enumerate(toks):
        d[t].append(j)
    streams=[]
    for _,locations in sorted(d.items()):
        if len(locations)>=3:
            streams.extend(b-a for a,b in zip(locations,locations[1:]))
    return streams[:25000], {"raw_word_count":len(toks),"repeated_terms":sum(len(v)>=3 for v in d.values()),"path_sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def per_block_methods(v):
    beta = estimate_beta(v)
    # BARM-G uses approximation-derived m, not exact distribution maximum likelihood.
    m = max(1, min(1<<20, math.ceil(1 / (beta - 1))))
    methods = {
      'barm_r': (lambda:encode_block(v),decode_block),
      'barm_g': (lambda:encode_golomb_block(v,m),decode_golomb_block),
      'gamma': (lambda:encode_elias(v),decode_elias),
      'delta': (lambda:encode_elias(v, True),lambda x:decode_elias(x, True)),
      'varint': (lambda:encode_varint(v),decode_varint),
      'fixed_bitpack': (lambda:encode_block_bitpack(v),decode_block_bitpack),
    }
    return methods


def bench_case(vals: list[int], label: str) -> dict:
    start = time.perf_counter()
    sizes=collections.Counter()
    barm_decode_time=0.0
    oracle_r_bytes=0
    frames=0
    for i in range(0,len(vals),B):
        block=vals[i:i+B]
        methods=per_block_methods(block)
        for name,(encoder,decoder) in methods.items():
            encoded=encoder()
            if decoder(encoded) != block:
                raise AssertionError(f"{name} round-trip mismatch")
            # 4-byte frame-length cost to allow random-access block boundaries.
            sizes[name] += len(encoded)+4
            if name=='barm_r':
                t0=time.perf_counter()
                decoder(encoded)
                barm_decode_time+=time.perf_counter()-t0
        # Strong in-sample choice of optimal r in same 0..5 code family.
        oracle_r_bytes += 4 + min(len(encode_block(block,r=r)) for r in range(6))
        # Compress a serialized, independently decodable varint block.
        vb = encode_varint(block)
        sizes['zlib_varint_block'] += 4 + len(zlib.compress(vb,9))
        frames+=1
    sizes['barm_oracle_r'] = oracle_r_bytes
    # Nonrandom access cross-block compressor, deliberately separate comparison.
    all_varints = bytearray()
    for i in range(0,len(vals),B):
        all_varints.extend(encode_varint(vals[i:i+B]))
    sizes['zlib_varint_global'] = len(zlib.compress(bytes(all_varints),9))
    return {
        'case': label, 'n': len(vals), 'min': min(vals),'max':max(vals),
        'p1': round(sum(v == 1 for v in vals)/len(vals),5),
        'frames':frames,
        'sizes_bytes':dict(sizes),
        'bits_per_integer':{name:round(8*s/len(vals),4) for name,s in sizes.items()},
        'barm_decoding_seconds_warm_python':round(barm_decode_time,6),
        'elapsed_seconds':round(time.perf_counter()-start,3),
    }


def run(audit_path: str|None=None, n:int=20000):
    rng=np.random.default_rng(42)
    cases = [(f'truncated_zeta_beta_{beta:g}_cap_65536',sample_truncated_zeta(beta,n,rng)) for beta in [1.001,1.01,1.1,1.5,2.0,3.0]]
    # Non-zeta clustered gap case, deliberately hard for heavy-tail universal coding.
    r=np.random.default_rng(443)
    mix=np.where(r.random(n)<0.8,r.integers(1,5,n),r.integers(256,32768,n))
    cases.append(('clustered_mixture_80pct_gaps_1to4',mix.tolist()))
    audit_meta=None
    if audit_path:
        g,audit_meta=audit_word_gaps(audit_path)
        if g:cases.append(('audit_report_word_position_gaps_not_fts',g))
    output = {
      'contract':'CDG BARM CPU-only pilot; not published CDG results',
      'created_date':'2026-11-23',
      'seed':42,'synthetic_distribution':'finite truncated discrete power law on [1,65536], not full zeta',
      'block_size':128,
      'frame_accounting':'each independently decodable block includes 4B byte-length; global zlib does not support block random access',
      'notes':'No QASPER, SciFact, Lean corpus tested. Python reference decoders, not SIMD. No FTS/WAL/archive integration. No LLM/RAG claims.',
      'audit_corpus':audit_meta,
      'cases':[]
    }
    for label,vals in cases:
        output['cases'].append(bench_case(vals,label))
    return output

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--audit-text')
    ap.add_argument('--n',type=int,default=20000)
    ap.add_argument('--out',default='results.json')
    args=ap.parse_args()
    result=run(args.audit_text, args.n)
    Path(args.out).write_text(json.dumps(result,indent=2))
    for c in result['cases']:
        name=c['case']; n=c['n']; s=c['sizes_bytes']; v=s['varint']; print(f'{name} n={n}  BARM={s["barm_r"]}B ({s["barm_r"]/v:.3f}× varint), oracle={s["barm_oracle_r"]}, delta={s["delta"]}, bitpack={s["fixed_bitpack"]}, zlib_global={s["zlib_varint_global"]}')