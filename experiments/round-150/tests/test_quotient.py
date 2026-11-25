import os
from pathlib import Path
from quotient_index import build,prepare,rank,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_duplicate_multiplicity_and_ties(tmp_path):
    ev=[("a",0,b"alpha beta alpha beta"),("b",0,b"alpha beta alpha beta"),("c",0,b"alpha gamma"),("a",1,b"gamma beta"),("d",0,b"gamma beta")]
    for q in (False,True):
        db,s=build(tmp_path/str(q),EXT,ev,q)
        assert s["index_rows"]==(3 if q else 5)
        for c in (2,3,4,5):
            ref=h.active_oracle(ev,c);prep=prepare(db,c)
            for p,o in [(("alpha beta",),"AND"),(("alpha","gamma"),"OR"),(("gamma","beta"),"AND")]:
                expected=h.native(ref,p,o)
                expanded,df,_=rank(db,p,o,prep)
                grouped,df2,_=rank(db,p,o,prep,True)
                h.verify(expanded,expected);assert expanded==grouped and df==df2
            ref.close()
        db.close()
def test_topk_duplicate_ties(tmp_path):
    ev=[(str(i),0,b"common token") for i in range(30)]
    db,_=build(tmp_path/"ties",EXT,ev,True)
    hits,df,work=rank(db,("common",),"AND",prepare(db,30),True)
    assert [g for g,_ in hits]==list(range(1,11)) and df==[30] and work==1
    db.close()
