import os
from pathlib import Path
from frequency_index import f,h,frequency_index,rank_frequency,prepare,recover,get
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_frequency_exact(tmp_path):
    ev=[("a",0,b"alpha alpha beta alpha "*100),("b",0,b"alpha alpha beta alpha "*100),("a",1,b"beta gamma alpha "*100),("c",0,b""),("d",0,"CAFÉ café 中文!".encode())]
    path=tmp_path/"db.sqlite";db,_=f.build(path,EXT,ev,"marginal",False);frequency_index(db,path)
    assert get(db,b"alpha")[0][1]==300
    assert get(db,b"missing")==({},0)
    for g,(_,_,raw) in enumerate(ev,1):assert recover(db,g)[0]==raw
    for c in range(1,len(ev)+1):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha",),"AND"),(("alpha alpha",),"AND"),(("alpha","beta"),"OR"),(("beta alpha","cafe"),"OR"),(("missing",),"AND")]:
            hits,df,work=rank_frequency(db,p,o,prepare(db,c));h.verify(hits,h.native(ref,p,o))
            if p==("alpha",):assert work["source_reads"]==0
        ref.close()
    db.close()
