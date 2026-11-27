import os,random
from pathlib import Path
import pytest
from token_tape import encode_ids,decode_ids,count_ids,build_tape,vocabulary,recover_tape,rank_tape,f,h,prepare
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_integer_tape_overlap_and_alignment():
    rng=random.Random(170)
    for _ in range(1000):
        seq=[rng.choice([1,2,256,65536,16777216,0x02000100]) for _ in range(rng.randrange(80))]
        p=[rng.choice([1,2,256,65536,16777216,0x02000100]) for _ in range(rng.randrange(1,8))]
        raw=encode_ids(seq)
        assert decode_ids(raw)==seq
        assert count_ids(raw,encode_ids(p))==sum(seq[i:i+len(p)]==p for i in range(len(seq)-len(p)+1))
    assert count_ids(encode_ids([1,1,1]),encode_ids([1,1]))==2
    with pytest.raises(ValueError):decode_ids(b"x")
    with pytest.raises(ValueError):count_ids(b"x",b"1234")

@pytest.mark.parametrize("mode",["frequency","text","text_joint","text_delta","text_delta_joint","ids","ids_delta"])
def test_tape_native_and_reopen(tmp_path,mode):
    rng=random.Random(170)
    base=("Alpha CAFÉ 中文 alpha alpha beta "+ " ".join("word"+str(rng.randrange(50000)) for _ in range(250))).encode()
    child=base.replace(b"beta",b"gamma")
    ev=[("a",0,base),("b",0,base),("a",1,child),("c",0,b""),("b",1,base.replace(b"alpha",b"delta"))]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    build_tape(db,path,ev,mode);db.close()
    from frequency_index import connect,recover
    db=connect(path,EXT);ids,terms=vocabulary(db)
    for g,(_,_,want) in enumerate(ev,1):
        raw,dd,ab=recover_tape(db,g,mode,terms) if mode.endswith("_joint") else recover(db,g)
        assert raw==want
        assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
    for cutoff in range(1,len(ev)+1):
        ref=h.active_oracle(ev,cutoff)
        for p,o in [(("alpha alpha",),"AND"),(("cafe 中文",),"AND"),(("beta","gamma"),"OR"),(("absent",),"AND"),(("alpha","alpha alpha"),"OR")]:
            hits,_,_=rank_tape(db,p,o,prepare(db,cutoff),mode,ids)
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    with pytest.raises(ValueError,match="unsupported query"):
        rank_tape(db,("alpha","alpha"),"OR",prepare(db,len(ev)),mode,ids)
    db.close()


@pytest.mark.parametrize("mode",["text_delta","ids_delta"])
def test_tape_delta_one_hop(tmp_path,mode):
    from token_tape import get_tape,connect,tokens,encode_ids,payload
    rng=random.Random(171)
    a=["word"+str(rng.randrange(50000)) for _ in range(500)]
    ev=[]
    for v in range(6):
        if v:a[v]="edit"+str(v)
        ev.append(("a",v," ".join(a).encode()))
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    size=build_tape(db,path,ev,mode)
    assert size.get("tape_delta_selected",0)>0
    db.close();db=connect(path,EXT);ids,_=vocabulary(db)
    for cid,base in db.execute("SELECT cid,base FROM token_tape"):
        ts=tokens(db,ev[cid-1][2].decode())
        want=encode_ids([ids[x] for x in ts]) if mode.startswith("ids") else b" ".join(ts)
        got,ab,dd=get_tape(db,cid)
        assert got==want and 2*dd<=5*len(want) and 2*ab<=3*len(payload(want)[1])
        if base:assert db.execute("SELECT base FROM token_tape WHERE cid=?",(base,)).fetchone()==(0,)
    db.close()
