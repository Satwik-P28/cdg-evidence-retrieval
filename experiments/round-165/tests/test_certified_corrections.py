import os,random
from pathlib import Path
import signed_phrase as sp
from certified_corrections import rank_certified,native_one,native_counts

EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_certificates_native(tmp_path):
    rng=random.Random(184)
    ev=[]
    for a in range(20):
        base=("alpha beta alpha gamma "*50+" ".join("tok"+str(rng.randrange(99999)) for _ in range(200))).encode()
        ev.append((str(a),0,base))
    for a in range(20):
        old=ev[a][2]
        ev.append((str(a),1,old.replace(b"alpha beta",b"alpha delta",1)))
    path=tmp_path/"archive";db,_=sp.f.build(path,EXT,ev,"marginal",False)
    size=sp.build_delta(db,path,ev,"independent_adaptive_weighted_adjusted_multi")
    assert size["delta_contents"]>0
    mapping=sp.load_patch_map(db)
    for q in ("alpha","alpha beta","alpha delta","gamma alpha","alpha alpha"):
        allrows=native_counts(db,"patch_fts",q)
        for rid, in db.execute("SELECT rowid FROM patch_fts"):
            assert native_one(db,rid,q)==allrows.get(rid,0)
    for c in (1,20,25,40):
        ref=sp.h.active_oracle(ev,c);prep=sp.prepare_delta(db,c,mapping)
        for p,o in [(("alpha beta",),"AND"),(("alpha delta",),"AND"),(("alpha alpha",),"OR"),
                    (("alpha beta","alpha delta"),"OR"),(("alpha","gamma"),"AND"),(("absent",),"AND")]:
            expected,df,_=sp.rank_delta(db,p,o,prep)
            for prune in (False,True):
                hits,d,_=rank_certified(db,p,o,prep,prune)
                assert (hits,d)==(expected,df)
                sp.h.verify(hits,sp.h.native(ref,p,o))
        ref.close()
    db.close()
