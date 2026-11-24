import os
import pytest
from native_compact import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
DEC=Path(os.environ["CDG_NATIVE_DECODER"]).resolve()

def test_native_lookup():
    d=Decoder(DEC);state=d.prepare({1:7,3:9},{7:1,9:2},4)
    raw=block([("alpha",b"\x00"+pack_postings([(1,0,2,3),(3,0,2,1),(3,2,4,5)])),
               ("alphabet",b"\x00"+pack_postings([(3,0,4,2)])),
               ("école",b"\x00"+pack_postings([(1,1,2,7)]))])
    assert d.lookup(raw,"alpha",state)==({7:3,9:5},3)
    assert d.lookup(raw,"alphabet",state)==({9:2},1)
    assert d.lookup(raw,"école",state)==({7:7},1)
    assert d.lookup(raw,"missing",state)==({},0)
    for bad in (raw[:-1],b"\x80",raw+b"x"):
        with pytest.raises(ValueError):d.lookup(bad,"alpha",state)
    bad=block([("x",b"\x00"+pack_postings([(4,0,2,1)]))])
    with pytest.raises(ValueError):d.lookup(bad,"x",state)

def test_full_fixture(tmp_path):
    events=[("a",0,b"x x one"),("b",0,b"x two"),("a",1,b"x x three"),("a",2,b""),("b",1,b"two"),("a",3,b"x one")]
    r=experiment(tmp_path,events,EXT,DEC,1)
    assert all(max(c["max_score_error"].values())<=1e-11 for c in r["cutoffs"])
    assert all(c["native_exhaustive_term_checks"]==2*r["vocabulary"] for c in r["cutoffs"])
    assert all(x["peak_decoded_bytes"]<=x["budget"] for c in r["cutoffs"] for x in c["cache"].values())

def test_native_invalid_overlap():
    d=Decoder(DEC);state=d.prepare({1:7},{7:1},2)
    bad=block([("x",b"\x00"+pack_postings([(1,0,3,1),(1,1,2,2)]))])
    with pytest.raises(ValueError):d.lookup(bad,"x",state)
