import os
import pytest
from temporal_postings import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()

def test_coalesce_gaps_and_changes():
    events=[("a",0,b"x x"),("b",0,b"x"),("a",1,b"x x y"),("a",2,b"y"),("b",1,b"x"),("a",3,b"x")]
    f=extract(events);r,ids=metadata(events,f)
    p=postings(r,f,True)
    assert sorted(p["x"])==sorted([(ids["a"],1,4,2),(ids["a"],6,7,1),(ids["b"],2,7,1)])
    assert list(unpack(pack(p["x"]),len(p["x"])))==p["x"]

def test_pack_wrong_count():
    with pytest.raises(Exception):list(unpack(pack([(1,1,2,1)]),2))
    with pytest.raises(ValueError):list(unpack(pack([(1,2,2,1)]),1))

def test_empty_and_unicode(tmp_path):
    events=[("a",0,"café café one".encode()),("b",0,b"one two"),("a",1,b""),("b",1,b"one one"),("a",2,b"one")]
    r=experiment(tmp_path,events,EXT,1)
    assert r["expanded_postings_checked"]==r["ordinary_postings"]
    assert r["coalesced_postings"]<=r["ordinary_postings"]
    assert all(max(x["max_error"].values())<=1e-11 for x in r["cutoffs"])
