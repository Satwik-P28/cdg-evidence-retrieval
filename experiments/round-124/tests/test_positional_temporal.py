import os
import pytest
from positional_temporal import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
def test_patch_and_anchor():
    rs=[(1,0,1,tuple(range(0,200,3))),(1,1,2,tuple(range(1,201,3))),
        (1,2,4,tuple(range(2,202,3))),(2,0,2,(1,2,3))]
    payload,s=encode(rs,True)
    assert s[0]==2 and s[1]>0
    assert decode(payload,True)==rs
    with pytest.raises(ValueError):decode(payload,False)
    with pytest.raises(ValueError):decode(payload[:-1],True)
def test_vectors_and_gaps():
    events=[("a",0,b"x x x"),("b",0,b"x y"),("a",1,b"x x x y"),("a",2,b"y"),("a",3,b"x x x")]
    pos=extract_positions(events);rows,ids=metadata(events,[{t:len(v) for t,v in m.items()} for m in pos])
    assert intervals(rows,pos,True)["x"]==[(ids["a"],0,2,(0,1,2)),(ids["a"],3,4,(0,1,2)),(ids["b"],0,1,(0,))]
    assert phrase_freq("x x",lambda t:{1:(0,1,2)})=={1:2}
    assert phrase_freq("x x x",lambda t:{1:(0,1,2)})=={1:1}
def test_fixture(tmp_path):
    events=[("a",0,b"x x one"),("b",0,"café one two".encode()),("a",1,b"x x three"),("a",2,b""),("b",1,b"two one"),("a",3,b"x one")]
    r=experiment(tmp_path,events,EXT,1)
    assert all(max(c["max_error"].values())<=1e-11 for c in r["cutoffs"])
    assert all(x["expanded_positions"]==r["position_occurrences"] for m,x in r["layouts"].items() if m in LAYOUTS)
