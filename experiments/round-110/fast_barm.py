"""R110: wire-compatible packed-integer decoder for R107 BARM-R.

Experimental scalar Python optimization, not SIMD or native-code proof of speed.
The input framing and encoding remain exactly as R107; R110 adds no new codec.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'round-107'))
from barm import MAX_INT, BLOCK_SIZE

MAX_PAYLOAD_BYTES=4096  # encoder output worst case below 2.1 KiB per 128 u64 values

class FastBits:
    __slots__=('data','total','pos')
    def __init__(self,buffer:bytes):
        self.data=int.from_bytes(buffer,'big')
        self.total=len(buffer)*8
        self.pos=0

    def take(self,width:int)->int:
        if width<0 or self.pos+width>self.total:
            raise ValueError('truncated bitstream')
        if width==0:return 0
        shift=self.total-self.pos-width
        self.pos+=width
        return (self.data>>shift)&((1<<width)-1)

    def unary(self)->int:
        remaining=self.total-self.pos
        if remaining<=0:raise ValueError('truncated unary scale')
        mask=(1<<remaining)-1
        inverted=mask^(self.data&mask)
        if not inverted:raise ValueError('missing unary terminator')
        quotient=remaining-inverted.bit_length()
        if quotient>63:raise ValueError('unary quotient exceeds maximum BARM scale')
        self.pos+=quotient+1
        return quotient

    def check_padding(self):
        remaining=self.total-self.pos
        if remaining>=8:raise ValueError('extra payload bytes')
        if self.data&((1<<remaining)-1):
            raise ValueError('nonzero padding')


def fast_decode_block(blob:bytes)->list[int]:
    if not isinstance(blob,(bytes,bytearray)) or not 3<=len(blob)<=MAX_PAYLOAD_BYTES:
        raise ValueError('invalid BARM block length')
    header=int.from_bytes(blob[:2],'big')
    n=header&0x1FFF
    r=header>>13
    if not 1<=n<=BLOCK_SIZE or not 0<=r<=5:
        raise ValueError('invalid BARM count or Rice selector')
    rd=FastBits(blob[2:])
    scales=[rd.unary()<<r for _ in range(n)]
    for i in range(n):
        scales[i]|=rd.take(r)
        if scales[i]>63:raise ValueError('decoded scale out of range')
    output=[]
    for k in scales:
        x=(1<<k)+rd.take(k)
        if x>MAX_INT:raise ValueError('decoded unsigned overflow')
        output.append(x)
    rd.check_padding()
    return output


def fast_decode_series(blob:bytes)->list[int]:
    if not isinstance(blob,bytes) or len(blob)<4:
        raise ValueError('series framing truncated')
    expected=int.from_bytes(blob[:4],'little')
    if expected==0:raise ValueError('empty series unsupported')
    out=[];p=4
    while p<len(blob):
        if len(blob)-p<4:raise ValueError('missing frame size')
        size=int.from_bytes(blob[p:p+4],'little');p+=4
        if not 3<=size<=MAX_PAYLOAD_BYTES or size>len(blob)-p:
            raise ValueError('bad frame size')
        out.extend(fast_decode_block(blob[p:p+size]));p+=size
        if len(out)>expected:raise ValueError('series length overflow')
    if len(out)!=expected:raise ValueError('series length mismatch')
    return out