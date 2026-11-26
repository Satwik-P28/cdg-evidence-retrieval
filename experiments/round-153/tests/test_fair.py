import os
from pathlib import Path
from fair_receipt import j,tp,bv,h,rank_body,verify_batch
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_fast_control(tmp_path):
    ev=[("a",0,b"alpha beta "*100),("b",0,b"alpha beta "*100),("a",1,b"gamma beta "*100)]
    path=tmp_path/"archive";db=j.setup(path,EXT,{},False);fd=os.open(tp.side(path),os.O_RDWR)
    req=[]
    for g,(a,i,raw) in enumerate(ev,1):
        j.append(db,fd,a,raw,tp.fixture(raw,str(g)),"marginal",quotient=False)
        db.execute("BEGIN");manifest,roots,_=bv.prefix_set(db,[g]);req.append(j.issue(db,fd,("beta",),"AND",g,manifest,roots[g],False));db.rollback()
    db.execute("BEGIN")
    for c in range(1,4):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha beta",),"AND"),(("alpha","gamma"),"OR"),(("missing",),"AND")]:
            a=rank_body(db,fd,p,o,c,"legacy");b=rank_body(db,fd,p,o,c,"fast_revision");assert a==b
            h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in b["hits"]],h.native(ref,p,o))
        ref.close()
    assert verify_batch(db,fd,req,"fast_revision")==3
    db.rollback();db.close();os.close(fd)
