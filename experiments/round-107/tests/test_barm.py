import random
import pytest
from barm import (
  encode_block, decode_block, estimate_beta, select_r,
  encode_golomb_block, decode_golomb_block,
  framed_encode_series, framed_decode_series,
  encode_elias, encode_varint, encode_block_bitpack,
)

@pytest.mark.parametrize('a',[
 [1], [2], [3], [2**31-1], [2**64-1],
 [1]*128, [2**64-1]*128, list(range(1,129)),
 [2**k for k in range(64)]])
def test_exact_round_trip(a):
    assert decode_block(encode_block(a)) == a
    assert framed_decode_series(framed_encode_series(a*2)) == a*2

@pytest.mark.parametrize('r',list(range(6)))
def test_explicit_r(r):
    vals = [1,2,3,17,59,2**31,2**63,2**64-1]
    assert decode_block(encode_block(vals,r)) == vals

@pytest.mark.parametrize('m',[1,2,3,4,7,16,51,1000,1048576])
def test_golomb(m):
    vals=[1,2,3,8,19,2**63,2**64-1]
    assert decode_golomb_block(encode_golomb_block(vals,m)) == vals

def test_random_property():
    rng = random.Random(42)
    for _ in range(600):
        vals=[rng.randint(1,2**rng.randint(1,64)-1) for _ in range(rng.randint(1,128))]
        assert decode_block(encode_block(vals)) == vals
        m=rng.randint(1,512)
        assert decode_golomb_block(encode_golomb_block(vals,m)) == vals

def test_mutations_fail_closed():
    b=encode_block([1,3,15,31,127])
    for j in range(1,len(b)):
        with pytest.raises(ValueError):
            decode_block(b[:j])
    with pytest.raises(ValueError):
        decode_block(b+b'\x00')
    with pytest.raises(ValueError):
        decode_block(b+b'\xff')
    with pytest.raises(ValueError):
        decode_block(b'\xff\xff\xff')
    with pytest.raises(ValueError):
        framed_decode_series(framed_encode_series([1,2,3])[:-1])

def test_invalid_values():
    for vals in ([], [0],[-2],[2**64], [1.3], [True], list(range(1,130))):
        with pytest.raises(ValueError): encode_block(vals)

def test_baseline_encoders_basic():
    vals=[1,2,3,7,19]
    assert all(len(f(vals)) > 2 for f in [encode_elias, lambda x: encode_elias(x,True),encode_varint,encode_block_bitpack])
    assert select_r(vals) in range(6)
    assert estimate_beta(vals) > 1

def test_all_baseline_round_trips():
    from barm import decode_elias, decode_varint, decode_block_bitpack
    rng=random.Random(1928)
    for _ in range(150):
        vals=[rng.randint(1,2**rng.randint(1,64)-1) for _ in range(rng.randint(1,128))]
        assert decode_elias(encode_elias(vals)) == vals
        assert decode_elias(encode_elias(vals, True), True) == vals
        assert decode_varint(encode_varint(vals)) == vals
        assert decode_block_bitpack(encode_block_bitpack(vals)) == vals

def test_empty_framed_series():
    assert framed_decode_series(framed_encode_series([])) == []

def test_frame_corruption_length():
    data = framed_encode_series(list(range(1,130)))
    for corrupt in [b'\x00'+data, data[:-1], b'\xff\xff\xff\xff' + data[4:]]:
        with pytest.raises(ValueError):
            framed_decode_series(corrupt)