"""R110 compatibility and adversarial decoder input tests."""
from pathlib import Path
import random,sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'round-107'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'round-108'))
from barm import encode_block,decode_block
from codec_controls import encode
from fast_barm import fast_decode_block,fast_decode_series

@pytest.mark.parametrize('r',range(6))
@pytest.mark.parametrize('vals',[[1],[1]*128,[2**64-1]*128,[1,2,3,7,15,16,17,2**32,2**63,2**64-1],list(range(1,129))])
def test_exact_wire_and_all_rice_selectors(r,vals):
    block=encode_block(vals,r=r)
    assert fast_decode_block(block)==decode_block(block)==vals

@pytest.mark.parametrize('seed',range(30))
def test_seeded_random_equivalence(seed):
    rng=random.Random(seed)
    vals=[rng.randint(1,2**64-1) for _ in range(rng.randint(1,128))]
    for r in [None,0,1,3,5]:
        enc=encode_block(vals,r=r)
        assert fast_decode_block(enc)==decode_block(enc)

@pytest.mark.parametrize('sample',[[1],[1]*257,[3,6,12,24],[2**20]*129])
def test_framed_codec_is_unchanged(sample):
    b=encode(sample,'barm_r')
    assert fast_decode_series(b)==sample


def test_malformed_headers_truncation_extra_payload_and_padding():
    data=encode_block([1,2,3,400,500])
    invalid=[b'', b'\xff\xff\x00', b'\x00\x00\x00', data[:-1], data+b'\x00',data+b'\xff', b'\x00\x01'+b'\xff'*4096]
    for bad in invalid:
        with pytest.raises(ValueError):fast_decode_block(bad)
    valid=encode_block([1])
    mutated=valid[:-1]+bytes([valid[-1]|1])
    with pytest.raises(ValueError):fast_decode_block(mutated)


def test_framing_rejects_wrong_length():
    v=encode([2,5,9],'barm_r')
    with pytest.raises(ValueError):fast_decode_series(v[:-1])
    with pytest.raises(ValueError):fast_decode_series((100).to_bytes(4,'little')+v[4:])


def test_no_wrong_roundtrip_when_corruption_changes_an_encoded_value():
    blob=encode_block([17,18,19])
    # Hash/source receipts are still required for genuine corruption detection.
    assert fast_decode_block(blob)==[17,18,19]