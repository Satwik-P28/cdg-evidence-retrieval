import os,random
from pathlib import Path
from self_index import build,recover,batch_predictors,rank,prepare,h,normalized
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def test_reversible_native_postings(tmp_path):
    raw=("CAFÉ, "+" ".join(random.Random(156).choices(["alpha","beta","gamma","delta","epsilon","omega"],k=400))+"!\n").encode()
    ev=[("a",0,raw),("b",0,raw),("a",1,raw+b" extra\0data"),("c",0,b""),("d",0,"中文 naïve!".encode())]
    for mode,block in [("marginal",0),("self",0),("self",2)]:
        path=tmp_path/(mode+str(block));db,size=build(path,EXT,ev,mode,block)
        for g,(_,_,want) in enumerate(ev,1):assert recover(db,g)==want
        for cid,pred in batch_predictors(db,size["shards"]):
            shard,dl=db.execute("SELECT c.shard,r.dl FROM contents c JOIN revisions r ON r.g=c.cid WHERE c.cid=?",(cid,)).fetchone()
            assert normalized(db,shard,cid,dl)==pred
        for c in range(1,6):
            ref=h.active_oracle(ev,c)
            for p,o in [(("alpha beta",),"AND"),(("gamma","extra"),"OR"),(("cafe",),"AND")]:
                hits,_=rank(db,size["shards"],p,o,prepare(db,c));h.verify(hits,h.native(ref,p,o))
            ref.close()
        db.close()
