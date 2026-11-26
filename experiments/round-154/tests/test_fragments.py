import os
from pathlib import Path
import pytest
from fragment_index import build,rank,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
@pytest.mark.parametrize("mode",["fixed32","cdc32","cdc64"])
def test_boundary_and_multiplicity(tmp_path,mode):
    # Repeated token run forces duplicate fragments and overlapping phrases.
    ev=[("a",0,b"alpha "*95+b"beta gamma delta epsilon zeta eta theta iota"),
        ("b",0,b"alpha "*95+b"beta gamma delta epsilon zeta eta theta iota"),
        ("a",1,b"alpha "*94+b"beta gamma delta epsilon zeta eta theta iota"),
        ("c",0,b"")]
    db,_=build(tmp_path/"a.sqlite",EXT,ev,mode)
    for c in (1,2,3,4):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha alpha alpha alpha alpha alpha alpha alpha",),"AND"),
                    (("alpha beta gamma delta",),"AND"),(("beta","alpha alpha"),"OR"),
                    (("beta gamma","alpha alpha"),"AND"),(("missing",),"AND")]:
            hits,_=rank(db,p,o,c);h.verify(hits,h.native(ref,p,o))
        ref.close()
    with pytest.raises(ValueError):rank(db,("alpha "*9,), "AND",4)
    db.close()
def test_exact_boundary_start(tmp_path):
    ev=[("a",0,b"pad "*31+b"unique second third fourth fifth sixth seventh eighth"),
        ("b",0,b"unique second third fourth fifth sixth seventh eighth")]
    db,_=build(tmp_path/"b.sqlite",EXT,ev,"fixed32")
    ref=h.active_oracle(ev,2)
    p=("unique second third fourth fifth sixth seventh eighth",)
    hits,df=rank(db,p,"AND",2);h.verify(hits,h.native(ref,p,"AND"));assert df==[2]
    ref.close();db.close()
