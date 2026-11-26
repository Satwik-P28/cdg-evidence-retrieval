import os
from pathlib import Path
import pytest
from compact_fragments import pack,unpack,bridge_build,compact,prepare,rank,h,fi
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_packed():
    rows=[(1,1),(2,3),(10000,1),(10001,300)]
    assert list(unpack(pack(rows)))==rows
    assert list(unpack(b""))==[]
    with pytest.raises(ValueError):list(unpack(b"\x80"))
    with pytest.raises(ValueError):pack([(1,1),(1,1)])
@pytest.mark.parametrize("layout",["halo","bridge"])
def test_boundary(tmp_path,layout):
    ev=[("a",0,b"alpha "*63+b"unique second third fourth fifth sixth seventh eighth"),
        ("b",0,b"alpha "*63+b"unique second third fourth fifth sixth seventh eighth"),
        ("a",1,b"alpha "*62+b"unique second third fourth fifth sixth seventh eighth"),
        ("c",0,b"")]
    path=tmp_path/"a.sqlite"
    db,_=(fi.build(path,EXT,ev,"fixed64") if layout=="halo" else bridge_build(path,EXT,ev,"fixed64"))
    compact(db,path,layout)
    for c in (1,2,3,4):
        ref=h.active_oracle(ev,c)
        for p,o in [(("unique second third fourth fifth sixth seventh eighth",),"AND"),
                    (("alpha alpha alpha alpha alpha alpha alpha alpha",),"AND"),
                    (("alpha unique","eighth"),"OR"),(("missing",),"AND")]:
            hits,df=rank(db,p,o,prepare(db,c),layout);h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()
