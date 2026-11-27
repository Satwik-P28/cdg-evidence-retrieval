import os,random
from pathlib import Path
import pytest
from selective_positions import pack_positions,unpack_positions,shifted_count,build_positions,rank_selective,f,h,prepare,connect,tt
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_position_codec_and_upper_bound():
    rng=random.Random(172)
    for _ in range(1000):
        docs=[(i*3+1,sorted(rng.sample(range(1000),rng.randrange(1,100)))) for i in range(rng.randrange(1,20))]
        assert list(unpack_positions(pack_positions(docs)))==docs
        seq=[rng.randrange(5) for _ in range(rng.randrange(1,100))]
        q=[rng.randrange(5) for _ in range(rng.randrange(2,9))]
        lists=[(i,[j for j,t in enumerate(seq) if t==x]) for i,x in enumerate(q)]
        exact=sum(seq[j:j+len(q)]==q for j in range(len(seq)-len(q)+1))
        assert shifted_count(lists,len(seq),len(q))==exact
        part=rng.sample(lists,rng.randrange(1,len(lists)+1))
        assert shifted_count(part,len(seq),len(q))>=exact
    with pytest.raises(ValueError):list(unpack_positions(b"\x80"))
    with pytest.raises(ValueError):list(unpack_positions(b"\x01\x01\x00"))

@pytest.mark.parametrize("limit",[2,3,None])
def test_native_selective_positions(tmp_path,limit):
    ev=[("a",0,b"alpha beta x alpha beta alpha beta rare"),
        ("b",0,b"alpha alpha x beta alpha gamma"),
        ("a",1,b"alpha beta x alpha alpha gamma"),
        ("c",0,"CAFÉ 中文 alpha beta café".encode()),
        ("d",0,b"")]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    build_positions(db,limit);tt.build_tape(db,path,ev,"frequency");db.close()
    db=connect(path,EXT);ids,_=tt.vocabulary(db)
    selected={tid for tid, in db.execute("SELECT tid FROM term_positions")}
    assert ids[b"alpha"] in selected and ids[b"beta"] in selected
    for cutoff in range(1,len(ev)+1):
        ref=h.active_oracle(ev,cutoff)
        for p,o in [(("alpha beta",),"AND"),(("alpha alpha",),"AND"),(("alpha beta rare",),"AND"),(("alpha gamma beta",),"AND"),(("cafe 中文","alpha beta"),"OR"),(("absent",),"AND")]:
            hits,_,work=rank_selective(db,p,o,prepare(db,cutoff),ids,selected)
            h.verify(hits,h.native(ref,p,o))
            if limit is None:assert work.get("source_reads",0)==0
        ref.close()
    hits,_,work=rank_selective(db,("alpha beta",),"AND",prepare(db,2),ids,selected)
    assert hits and work["position_exact"]==1 and work["position_rejections"]==1
    db.close()
