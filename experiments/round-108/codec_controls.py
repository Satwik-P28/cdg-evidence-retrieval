"""R108 reference codecs for logical positive docID gaps (not SQLite native bytes).

All formats include independently recoverable per-list metadata. They are
Python reference implementations. StreamVByte is wire-format compatible in
layout concept, but these loops are NOT optimized SIMD. The Elias-Fano
partitioner is a measured variable-size DP reference, not a production PEF.
"""
from __future__ import annotations
from functools import lru_cache
import math
import sys
from pathlib import Path
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'round-107'))
from barm import (encode_block, decode_block, encode_golomb_block,
                  decode_golomb_block, encode_varint, decode_varint,
                  encode_block_bitpack, decode_block_bitpack,
                  estimate_beta, BLOCK_SIZE)

MAX_UINT = (1 << 32) - 1
CANDIDATE_PARTITIONS = (32, 64, 128, 256)


def validate(gaps: list[int]):
    if not gaps or any(type(x) is not int or not (1 <= x <= MAX_UINT) for x in gaps):
        raise ValueError('positive uint32 gap list required')
    if sum(gaps) > MAX_UINT:
        raise ValueError('cumulative docID beyond uint32 reference implementation')


def pack_bits(items: list[tuple[int, int]]) -> bytes:
    acc = 0
    total = 0
    out = bytearray()
    for x, width in items:
        if width < 0 or x < 0 or x >= 1 << width:
            raise ValueError('bit pack width/value mismatch')
        acc = (acc << width) | x
        total += width
        while total >= 8:
            total -= 8
            out.append((acc >> total) & 255)
            acc &= (1 << total) - 1
    if total:
        out.append(acc << (8 - total))
    return bytes(out)


def unpack_bits(blob: bytes, widths: list[int]) -> list[int]:
    bits = int.from_bytes(blob, 'big')
    used = len(blob)*8
    out=[]
    for w in widths:
        used -= w
        if used < 0: raise ValueError('truncated bitplane')
        out.append((bits >> used) & ((1 << w) - 1))
    if used >= 8 or bits & ((1 << used) - 1):
        raise ValueError('nonzero padding / trailing data')
    return out


def streamvbyte_encode(gaps:list[int]) -> bytes:
    """4-gap control bytes followed by little-endian payload, size self-described."""
    validate(gaps)
    controls=bytearray()
    data=bytearray()
    for start in range(0,len(gaps),4):
        ctrl=0
        for j,x in enumerate(gaps[start:start+4]):
            n=max(1,(x.bit_length()+7)//8)
            ctrl |= (n-1) << (2*j)
            data += x.to_bytes(n,'little')
        controls.append(ctrl)
    return len(gaps).to_bytes(2,'little') + bytes(controls)+bytes(data)


def streamvbyte_decode(blob:bytes) -> list[int]:
    if len(blob)<3: raise ValueError('truncated StreamVByte header')
    n=int.from_bytes(blob[:2],'little')
    if not 1<=n<=256:raise ValueError('bad value count')
    control_bytes=(n+3)//4
    if len(blob)<2+control_bytes:raise ValueError('missing control')
    ctrls=blob[2:2+control_bytes]
    p=2+control_bytes
    result=[]
    for j in range(n):
        width=1+((ctrls[j//4] >> (2*(j%4))) & 3)
        if p+width>len(blob):raise ValueError('truncated integer')
        result.append(int.from_bytes(blob[p:p+width],'little'))
        p+=width
    if p!=len(blob) or any(x<1 for x in result):
        raise ValueError('trailing payload / zero posting gap')
    return result


def _ef_params(gaps:list[int]):
    validate(gaps)
    n=len(gaps)
    u=sum(gaps)
    low=max(0,(u//n).bit_length()-1)
    return n,u,low


def ef_size(gaps:list[int]) -> int:
    n,u,low=_ef_params(gaps)
    high_max=u>>low
    return 7+(n*low+7)//8+(high_max+n+1+7)//8


def ef_encode(gaps:list[int]) -> bytes:
    """ELIAS-FANO store prefix sums, invert them to positive gaps on decoding."""
    n,u,low=_ef_params(gaps)
    if n>256:raise ValueError('EF partition too large')
    vals=[]
    cum=0
    for x in gaps:
        cum+=x
        vals.append(cum)
    low_data=pack_bits([(v & ((1<<low)-1), low) for v in vals])
    high_bits=bytearray(( (u>>low) + n + 1 + 7)//8)
    for j,v in enumerate(vals):
        pos=(v>>low)+j
        high_bits[pos//8] |= 1 << (7-pos%8)
    return (n.to_bytes(2,'little')+u.to_bytes(4,'little')+bytes([low])
            +low_data+bytes(high_bits))


def ef_decode(blob:bytes) -> list[int]:
    if len(blob)<7: raise ValueError('truncated EF header')
    n=int.from_bytes(blob[:2],'little');u=int.from_bytes(blob[2:6],'little');low=blob[6]
    if not 1<=n<=256 or not n<=u<=MAX_UINT or low>31:
        raise ValueError('bad EF header')
    low_n=(n*low+7)//8
    high_n=((u>>low)+n+1+7)//8
    if len(blob)!=7+low_n+high_n:raise ValueError('EF payload size mismatch')
    low_vals=unpack_bits(blob[7:7+low_n],[low]*n)
    highs=blob[7+low_n:]
    pos=[]
    for j in range(len(highs)*8):
        if (highs[j//8]>>(7-j%8))&1:pos.append(j)
    if len(pos)!=n:raise ValueError('EF high-plane count mismatch')
    vals=[((p-i)<<low)+lv for i,(p,lv) in enumerate(zip(pos,low_vals))]
    if vals[-1]!=u or any(a>=b for a,b in zip(vals,vals[1:])):
        raise ValueError('invalid decoded EF sequence')
    return [vals[0]]+[b-a for a,b in zip(vals,vals[1:])]


def ef_partitioned_encode(gaps:list[int], *, candidates=CANDIDATE_PARTITIONS) -> bytes:
    """Variable 32/64/128/256-value block DP on known current posting list.

    This is an in-sample oracle for partition boundaries, NOT a model
    selecting partitions without seeing the list. Charged full frame metadata.
    """
    validate(gaps)
    n=len(gaps)
    sums=[0]
    for x in gaps:sums.append(sums[-1]+x)
    dp=[float('inf')]*(n+1)
    plan=[0]*n
    dp[n]=0
    for i in range(n-1,-1,-1):
        rem=n-i
        ks=set(min(rem,k) for k in candidates)
        # Only a partial terminal block is allowed, otherwise full sizes.
        ks={k for k in ks if k in candidates or k==rem}
        for k in sorted(ks):
            total=sums[i+k]-sums[i]
            l=max(0,(total//k).bit_length()-1)
            byte_cost=4+7+(k*l+7)//8+((total>>l)+k+1+7)//8
            cost=byte_cost+dp[i+k]
            if cost<dp[i]:dp[i]=cost;plan[i]=k
    out=bytearray(n.to_bytes(4,'little'))
    i=0
    while i<n:
        k=plan[i]
        if not k:raise AssertionError('no partition')
        part=ef_encode(gaps[i:i+k]);out+=len(part).to_bytes(4,'little')+part
        i+=k
    if len(out)!=4+dp[0]:raise AssertionError('DP cost mismatch')
    return bytes(out)


def ef_partitioned_decode(blob:bytes) -> list[int]:
    if len(blob)<4: raise ValueError('missing EF total')
    n=int.from_bytes(blob[:4],'little')
    if not n:raise ValueError('empty list')
    p=4;out=[]
    while p<len(blob):
        if p+4>len(blob):raise ValueError('truncated frame')
        size=int.from_bytes(blob[p:p+4],'little');p+=4
        if size<7 or size>len(blob)-p:raise ValueError('bad frame size')
        out.extend(ef_decode(blob[p:p+size]));p+=size
    if len(out)!=n:raise ValueError('EF decoded count mismatch')
    return out


def _frame_series(gaps:list[int],codec:str) -> bytes:
    output=bytearray(len(gaps).to_bytes(4,'little'))
    for i in range(0,len(gaps),128):
        b=gaps[i:i+128]
        if codec=='barm_r':part=encode_block(b)
        elif codec=='barm_g':
            beta=estimate_beta(b)
            m=max(1,min(1<<20,math.ceil(1/(beta-1))))
            part=encode_golomb_block(b,m)
        elif codec=='varint':part=encode_varint(b)
        elif codec=='bitpack':part=encode_block_bitpack(b)
        elif codec=='streamvbyte':part=streamvbyte_encode(b)
        elif codec=='zlib_varint':part=zlib.compress(encode_varint(b),9)
        else:raise ValueError(codec)
        output+=len(part).to_bytes(4,'little')+part
    return bytes(output)


def _frame_decode(blob:bytes,codec:str) -> list[int]:
    if len(blob)<4:raise ValueError('missing series header')
    n=int.from_bytes(blob[:4],'little')
    p=4;out=[]
    while p<len(blob):
        if p+4>len(blob):raise ValueError('missing frame length')
        size=int.from_bytes(blob[p:p+4],'little');p+=4
        if not size or size>len(blob)-p:raise ValueError('bad frame length')
        frame=blob[p:p+size];p+=size
        if codec=='barm_r':vals=decode_block(frame)
        elif codec=='barm_g':vals=decode_golomb_block(frame)
        elif codec=='varint':vals=decode_varint(frame)
        elif codec=='bitpack':vals=decode_block_bitpack(frame)
        elif codec=='streamvbyte':vals=streamvbyte_decode(frame)
        elif codec=='zlib_varint':vals=decode_varint(zlib.decompress(frame))
        else:raise ValueError(codec)
        out.extend(vals)
    if len(out)!=n:raise ValueError('series length mismatch')
    return out


CODECS=('barm_r','barm_g','varint','streamvbyte','bitpack','zlib_varint','ef_partitioned')


def encode(gaps:list[int],codec:str) -> bytes:
    validate(gaps)
    if codec=='ef_partitioned':return ef_partitioned_encode(gaps)
    if len(gaps)>MAX_UINT:raise ValueError('series too long')
    return _frame_series(gaps,codec)


def decode(blob:bytes,codec:str) -> list[int]:
    if codec=='ef_partitioned':return ef_partitioned_decode(blob)
    return _frame_decode(blob,codec)