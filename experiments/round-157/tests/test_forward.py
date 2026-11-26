import os
from pathlib import Path
import pytest
from forward_index import build,recover,rank_presence,prepare,phrase_count,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_overlap():
    assert phrase_count(b"a a a a",[b"a",b"a"])==3
    assert phrase_count(b"ab a ba",[b"a"])==1
    assert phrase_count(b"a b a b",[b"a",b"b"])==2
@pytest.mark.parametrize("mode",["marginal","forward"])
def test_presence(tmp_path,mode):
    ev=[("a",0,b"ALPHA alpha alpha beta! "*100),("b",0,b"ALPHA alpha alpha beta! "*100),("a",1,b"beta alpha beta "*80),("c",0,b""),("d",0,"CAFÉ, café 中文!".encode())]
    db,_=build(tmp_path/"db",EXT,ev,mode,True)
    for g,(_,_,want) in enumerate(ev,1):
        raw,dd,ab=recover(db,g);assert raw==want
        assert 2*dd<=5*len(want) and 2*ab<=3*len(h.C.compress(want))
    for c in range(1,6):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha alpha",),"AND"),(("beta alpha","cafe"),"OR"),(("alpha","beta"),"AND"),(("missing",),"AND")]:
            hits,_,_,_=rank_presence(db,p,o,prepare(db,c));h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()
