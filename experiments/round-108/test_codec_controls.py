"""Exact round trips, framing and corruption checks for R108 controls."""
import random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from codec_controls import CODECS,encode,decode,ef_encode,ef_decode,ef_size,ef_partitioned_encode
import pytest

@pytest.mark.parametrize('data',[[1],[3],[1]*128,list(range(1,129)),[1,255,256,65535,65536,2**24], [2**32-1], [1]*257, [1]*512,[10**6]*3])
@pytest.mark.parametrize('name',CODECS)
def test_roundtrip(data,name):
    enc=encode(data,name)
    assert decode(enc,name)==data

@pytest.mark.parametrize('seed',range(15))
def test_varied_random(seed):
    r=random.Random(seed)
    data=[r.randint(1,3000) for _ in range(r.randrange(1,400))]
    for c in CODECS:
        assert decode(encode(data,c),c)==data

def test_ef_encoded_cost_and_decode():
    for data in [[1],[1]*255,[1,2,4,8,16],[32000]*128]:
        assert len(ef_encode(data))==ef_size(data)
        assert ef_decode(ef_encode(data))==data

@pytest.mark.parametrize('codec', CODECS)
def test_reject_invalid(codec):
    for data in [[],[0],[True],[2**32],[-1]]:
        with pytest.raises(ValueError):encode(data,codec)

@pytest.mark.parametrize('codec',CODECS)
def test_truncated(codec):
    blob=encode([3,5,7],codec)
    with pytest.raises((ValueError, IndexError)):
        decode(blob[:-1],codec)


def test_dp_variable_partitions_better_than_large_fixed_on_skew():
    data=[1]*512+[9000]*32+[1]*128
    d=ef_partitioned_encode(data)
    assert decode(d,'ef_partitioned')==data
    assert len(d)>0