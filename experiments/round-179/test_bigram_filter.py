import os,random
from pathlib import Path
from bigram_filter import build_filter,load_filter,rejector,mask_for,f,h,connect,tt,sp,prepare
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_no_false_negative_random():
    rng=random.Random(179)
    for m in (256,512,1024,2048,4096):
        for _ in range(500):
            ts=[str(rng.randrange(30)).encode() for _ in range(rng.randrange(2,100))]
            i=rng.randrange(len(ts)-1);n=rng.randrange(2,min(8,len(ts)-i)+1)
            q=ts[i:i+n];mask=mask_for(ts,m)
            assert rejector({1:(m,mask)})(q,{1,2})=={1,2}

def test_native_and_corruption(tmp_path):
    ev=[("a",0,b"alpha beta alpha beta"),("b",0,b"beta x alpha"),("a",1,b"alpha x beta"),("c",0,"CAFÉ 中文 café".encode()),("d",0,b"")]
    path=tmp_path/"archive.sqlite";db,_=f.build(path,EXT,ev,"marginal",False)
    tt.build_tape(db,path,ev,"frequency");build_filter(db,path,ev,"512");db.close()
    db=connect(path,EXT);masks,bad=load_filter(db);assert not bad
    db.execute("UPDATE adjacency SET body=zeroblob(length(body)) WHERE cid=1");db.commit()
    masks,bad=load_filter(db);assert bad==1 and 1 not in masks
    ids,_=tt.vocabulary(db);flt=rejector(masks)
    for c in range(1,len(ev)+1):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha beta",),"AND"),(("beta alpha",),"AND"),(("cafe 中文","alpha"),"OR"),(("alpha x beta",),"AND"),(("absent",),"AND")]:
            hits,_,_=sp.rank_selective(db,p,o,prepare(db,c),ids,set(),flt)
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()
