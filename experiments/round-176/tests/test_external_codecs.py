import pytest
from external_codecs import (delta_varint_size,elias_fano_size,simdbp128_size,
                             roaring_size,tf_bytes)

def _bits(docids,universe):
    """Known-answer Elias-Fano bit count: n*L low bits plus unary high bits."""
    n=len(docids)
    if universe//n<=1:return n*2
    l=(universe//n).bit_length()-1
    high=[c>>l for c in docids]
    return ((n*l)+7)//8+((n+high[-1]+1)+7)//8

@pytest.mark.parametrize("docids,universe",[
    ([1],10),([0,1,2,3],8),([1,5,9,100],200),([2,4,8,16,32,64],65),
    (list(range(1,50)),1000),([7]*1,7)])
def test_elias_fano_matches_known_formula(docids,universe):
    assert elias_fano_size(docids,universe)==_bits(docids,universe)

def test_elias_fano_beats_dense_bitmap():
    docids=list(range(1,100))
    assert elias_fano_size(docids,1000)<1000//8

@pytest.mark.parametrize("docids",[[1],[1,2,3],[1]*130,list(range(1,300))])
def test_simdbp128_block_shape(docids):
    size=simdbp128_size(docids)
    blocks=(len(docids)+127)//128
    per_block=size-blocks
    assert 0<=per_block<=blocks*128*4

def test_simdbp128_uses_one_width_per_128_values():
    flat=list(range(1,129))            # deltas all 1 -> 1 bit each
    assert simdbp128_size(flat)==1+16
    mixed=list(range(1,128))+[10000]   # last delta needs 14 bits -> one block
    assert simdbp128_size(mixed)>1+16

def test_roaring_switches_to_bitmap_above_4096():
    dense=[1+i*3 for i in range(5000)]
    assert roaring_size(dense)==4+4+8192
    sparse=[1,500,900]
    assert roaring_size(sparse)==4+4+6

def test_delta_varint_matches_manual_encoding():
    docids=[1,2,130,16500]
    # deltas 1, 1, 128 (2 B), 16370 (2 B)
    assert delta_varint_size(docids)==1+1+2+2

def test_tf_cost_is_varint():
    assert tf_bytes([1]*128)==128
    assert tf_bytes([200])==2
    assert tf_bytes([20000])==3

def test_all_codecs_are_total_and_monotone():
    base=list(range(1,900,7))
    for f in (delta_varint_size,simdbp128_size,roaring_size):
        small=f(base);big=f(base+[10000*i for i in range(1,20)])
        assert big>=small>=0
    for n in (1,2,3,127,128,129):
        docids=list(range(1,n+1))
        assert elias_fano_size(docids,10**6)>0
        assert simdbp128_size(docids)>0
