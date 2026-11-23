import pytest
from anchor_bench import *

@pytest.mark.parametrize("policy",POLICIES)
def test_archive(tmp_path,policy):
    start=b"abc def ghi "*1000
    revisions=[start+b"x"*i for i in range(12)]+[b"",b"hello"*100]
    r=benchmark(tmp_path/"test.sqlite",[("a",revisions),("b",[start,start+b"!"])],policy)
    assert r["all_exact"] and r["versions"]==16
    assert r["max_dependency_depth"]<=(1 if "anchor" in policy else 8)
    if policy=="bounded_anchor":
        assert r["max_activation_relative_to_snapshot_frame"]<=1.5
        assert r["max_decode_relative_to_requested_nonempty_revision"]<=2.5

def test_corruption(tmp_path):
    db=setup(tmp_path/"bad.sqlite")
    raw=b"hello"*10
    with db:
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",("x",0,len(raw),sha(raw),0,None,C.compress(raw)))
    with db:
        db.execute("UPDATE versions SET digest=zeroblob(32)")
    with pytest.raises(ValueError,match="receipt"):
        recover(db,"x",0)
    db.close()

def test_parent_guard(tmp_path):
    db=setup(tmp_path/"bad.sqlite")
    with pytest.raises(Exception):
        with db:
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",("x",1,1,sha(b"a"),1,0,b"x"))
    db.close()

def test_bound_falls_back():
    base=b"x"*10000
    raw=b"a"
    assert choose(raw,1,[(base,len(C.compress(base)),0)],"bounded_anchor")[0] is None
