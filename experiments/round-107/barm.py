"""Experimental two-part dyadic-scale integer coding for CDG.

This is an independent research implementation inspired by Neri Merhav (2026).
It is NOT an optimized SIMD codec, a production index, or a test of the
Riemann Hypothesis. BARM-R uses 2-byte (r,count) headers and three bit planes.
Values are unsigned integers in [1, 2**64-1].
"""
from __future__ import annotations
import math
from typing import Iterable

MAX_INT = (1 << 64) - 1
GAMMA = 0.5772156649015329
BLOCK_SIZE = 128

class BitWriter:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.used = 0

    def bit(self, value: int):
        self.acc = (self.acc << 1) | (value & 1)
        self.used += 1
        if self.used == 8:
            self.out.append(self.acc)
            self.acc = self.used = 0

    def bits(self, value: int, width: int):
        if width < 0 or value < 0 or value >= (1 << width):
            raise ValueError("invalid fixed-width bit value")
        for j in range(width - 1, -1, -1):
            self.bit((value >> j) & 1)

    def finish(self) -> bytes:
        if self.used:
            self.out.append(self.acc << (8 - self.used))
        return bytes(self.out)

class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def bit(self):
        if self.pos >= len(self.data) * 8:
            raise ValueError("truncated bitstream")
        result = (self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return result

    def bits(self, n: int):
        result = 0
        for _ in range(n):
            result = (result << 1) | self.bit()
        return result

    def check_padding(self):
        remaining = len(self.data) * 8 - self.pos
        if remaining >= 8:
            raise ValueError("trailing unused bytes")
        if any(self.bit() for _ in range(remaining)):
            raise ValueError("nonzero padding bits")


def _validate(data: Iterable[int]) -> list[int]:
    vals = list(data)
    if not (1 <= len(vals) <= BLOCK_SIZE):
        raise ValueError("block length must be 1..128")
    if any(type(x) is not int or x < 1 or x > MAX_INT for x in vals):
        raise ValueError("values must be unsigned positive 64-bit integers")
    return vals


def estimate_beta(data: Iterable[int]) -> float:
    vals = _validate(data)
    avglog = sum(math.log(x) for x in vals) / len(vals)
    # Laurent approximation near beta=1. Not exact zeta MLE.
    return 1.0 + 1.0 / max(1e-4, avglog + GAMMA)


def select_r(data: Iterable[int]) -> int:
    beta = estimate_beta(data)
    m = max(1, math.ceil(1 / (beta - 1)))
    return min(5, max(0, math.floor(math.log2(max(1.0, m * math.log(2))))))


def encode_block(data: Iterable[int], r: int | None = None) -> bytes:
    vals = _validate(data)
    if r is None:
        r = select_r(vals)
    if type(r) is not int or not 0 <= r <= 5:
        raise ValueError("r must be between 0 and 5")
    count = len(vals)
    hdr = ((r << 13) | count).to_bytes(2, "big")
    scales = [v.bit_length() - 1 for v in vals]
    w = BitWriter()
    # Plane 1, unary q = floor(k/2**r).
    for k in scales:
        q = k >> r
        for _ in range(q):
            w.bit(1)
        w.bit(0)
    # Plane 2, Rice remainders.
    for k in scales:
        w.bits(k & ((1 << r) - 1), r)
    # Plane 3, raw dyadic offsets.
    for k, x in zip(scales, vals):
        w.bits(x - (1 << k), k)
    return hdr + w.finish()


def decode_block(blob: bytes) -> list[int]:
    if len(blob) < 3:
        raise ValueError("truncated header / payload")
    hdr = int.from_bytes(blob[:2], "big")
    n, r = hdr & 0x1FFF, hdr >> 13
    if not 1 <= n <= BLOCK_SIZE or not 0 <= r <= 5:
        raise ValueError("invalid header")
    rd = BitReader(blob[2:])
    scales = []
    for _ in range(n):
        q = 0
        while rd.bit():
            q += 1
            if q > 63:  # all valid unsigned 64-bit dyadic scales are <=63
                raise ValueError("unary quotient overflow")
        scales.append(q << r)
    for j in range(n):
        scales[j] |= rd.bits(r)
        if scales[j] > 63:
            raise ValueError("decoded scale out of range")
    out = []
    for k in scales:
        x = (1 << k) + rd.bits(k)
        if x > MAX_INT:
            raise ValueError("decoded integer overflow")
        out.append(x)
    rd.check_padding()
    return out


def framed_encode_series(data: Iterable[int]) -> bytes:
    vals = list(data)
    out = bytearray()
    for i in range(0, len(vals), BLOCK_SIZE):
        b = encode_block(vals[i:i+BLOCK_SIZE])
        out += len(b).to_bytes(4, "big") + b
    return bytes(out)


def framed_decode_series(blob: bytes) -> list[int]:
    pos, out = 0, []
    while pos < len(blob):
        if len(blob) - pos < 4:
            raise ValueError("truncated frame size")
        size = int.from_bytes(blob[pos:pos+4], "big")
        pos += 4
        if size < 3 or size > len(blob) - pos:
            raise ValueError("invalid frame size")
        out.extend(decode_block(blob[pos:pos+size]))
        pos += size
    return out


def encode_elias(data: Iterable[int], delta: bool = False) -> bytes:
    vals = _validate(data)
    w = BitWriter()
    for x in vals:
        n = x.bit_length()
        if delta:
            # Gamma-code the integer bit-width.
            nn = n.bit_length()
            for _ in range(nn-1):
                w.bit(0)
            w.bits(n, nn)
            w.bits(x ^ (1 << (n-1)), n-1)
        else:
            for _ in range(n-1):
                w.bit(0)
            w.bits(x, n)
    return len(vals).to_bytes(2, "big") + w.finish()


def encode_varint(data: Iterable[int]) -> bytes:
    vals = _validate(data)
    out = bytearray(len(vals).to_bytes(2, "big"))
    for x in vals:
        while x > 127:
            out.append((x & 0x7f) | 0x80)
            x >>= 7
        out.append(x)
    return bytes(out)


def encode_block_bitpack(data: Iterable[int]) -> bytes:
    vals = _validate(data)
    width = max(x.bit_length() for x in vals)
    w = BitWriter()
    for x in vals:
        w.bits(x, width)
    return len(vals).to_bytes(2, "big") + bytes([width]) + w.finish()


def encode_golomb_block(data: Iterable[int], m: int) -> bytes:
    """Explicit arbitrary-m Golomb for dyadic scale k; not a SIMD implementation.

    Distinct self-describing 7-byte header = marker, n(u16), m(u32).
    """
    vals = _validate(data)
    if type(m) is not int or not 1 <= m <= (1 << 20):
        raise ValueError("m must be in 1..2**20")
    hdr = b"G" + len(vals).to_bytes(2, "big") + m.to_bytes(4,"big")
    w = BitWriter()
    k_list = [x.bit_length() - 1 for x in vals]
    for k in k_list:
        q, rem = divmod(k, m)
        for _ in range(q):
            w.bit(1)
        w.bit(0)
        b = (m - 1).bit_length()
        threshold = (1 << b) - m
        if rem < threshold:
            w.bits(rem, b - 1)
        else:
            w.bits(rem + threshold, b)
    for k, x in zip(k_list, vals):
        w.bits(x - (1 << k), k)
    return hdr + w.finish()


def decode_golomb_block(blob: bytes) -> list[int]:
    if len(blob) < 8 or blob[0] != 71:
        raise ValueError("invalid Golomb block")
    n = int.from_bytes(blob[1:3], "big")
    m = int.from_bytes(blob[3:7], "big")
    if not 1 <= n <= BLOCK_SIZE or not 1 <= m <= 1 << 20:
        raise ValueError("invalid Golomb header")
    rd = BitReader(blob[7:])
    k_list = []
    b = (m-1).bit_length()
    threshold = (1 << b)-m
    for _ in range(n):
        q = 0
        while rd.bit():
            q += 1
            if q > 63:
                raise ValueError("Golomb unary overflow")
        if m == 1:
            rem = 0
        else:
            rem = rd.bits(b-1)
            if rem >= threshold:
                rem = ((rem << 1) | rd.bit()) - threshold
        k = q*m + rem
        if k > 63:
            raise ValueError("scale overflow")
        k_list.append(k)
    out = [(1 << k) + rd.bits(k) for k in k_list]
    rd.check_padding()
    return out

def decode_elias(blob: bytes, delta: bool = False) -> list[int]:
    if len(blob) < 2:
        raise ValueError("truncated Elias header")
    n = int.from_bytes(blob[:2],"big")
    if not 1 <= n <= BLOCK_SIZE:
        raise ValueError("invalid Elias block count")
    rd = BitReader(blob[2:])
    result=[]
    def gamma():
        z=0
        while not rd.bit():
            z+=1
            if z > 64:
                raise ValueError("invalid Elias unary")
        return (1 << z) + rd.bits(z)
    for _ in range(n):
        if delta:
            bit_len=gamma()
            if bit_len > 64:
                raise ValueError("invalid Elias width")
            result.append((1 << (bit_len-1)) + rd.bits(bit_len-1))
        else:
            result.append(gamma())
    rd.check_padding()
    return result


def decode_varint(blob: bytes) -> list[int]:
    if len(blob) < 2:
        raise ValueError("truncated varint header")
    n = int.from_bytes(blob[:2], "big")
    if not 1 <= n <= BLOCK_SIZE:
        raise ValueError("invalid varint block count")
    pos, out = 2, []
    for _ in range(n):
        x = 0
        sh = 0
        while True:
            if pos >= len(blob):
                raise ValueError("truncated varint")
            b = blob[pos]
            pos += 1
            x |= (b & 127) << sh
            if x > MAX_INT or sh > 63:
                raise ValueError("varint overflow")
            if not b & 128:
                break
            sh += 7
        if x <= 0:
            raise ValueError("zero is invalid")
        out.append(x)
    if pos != len(blob):
        raise ValueError("trailing bytes in varint")
    return out


def decode_block_bitpack(blob: bytes) -> list[int]:
    if len(blob) < 4:
        raise ValueError("truncated bitpack header")
    n = int.from_bytes(blob[:2], "big")
    width = blob[2]
    if not 1 <= n <= BLOCK_SIZE or not 1 <= width <= 64:
        raise ValueError("invalid bitpack header")
    rd = BitReader(blob[3:])
    vals = [rd.bits(width) for _ in range(n)]
    if not all(vals):
        raise ValueError("zero is invalid")
    rd.check_padding()
    return vals