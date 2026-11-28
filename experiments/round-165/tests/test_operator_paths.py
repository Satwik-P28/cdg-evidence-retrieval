import os,random
from pathlib import Path
import signed_phrase as sp
from operator_paths import path_builder,load_paths,path_prepare,MODE
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_operator_paths_native(tmp_path):
    rng=random.Random(191);ev=[]
    for a in range(6):
        ts=["tok"+str(rng.randrange(1000000)) for _ in range(500)]
        ev.append((str(a),0," ".join(ts).encode()))
        for v in range(1,7):
            ts[50*v]="changed"+str(v)
            ev.append((str(a),v," ".join(ts).encode()))
    for limit in (2,4,8):
        path=tmp_path/str(limit);db,_=sp.f.build(path,EXT,ev,"marginal",False)
        size=sp.build_delta(db,path,ev,MODE,path_builder(ev,limit))
        assert size["operator_parent_rows"]>0 and size["operator_max_depth"]<=limit
        paths=load_paths(db,limit);mapping=sp.load_patch_map(db)
        for c in (3,7,15,len(ev)):
            ref=sp.h.active_oracle(ev,c);prep=path_prepare(db,c,mapping,paths)
            for p,o in [(("changed1",),"AND"),(("changed2",),"AND"),(("changed1","changed3"),"OR"),
                        (("absent",),"AND"),(("changed1 changed2",),"AND")]:
                hits,_,_=sp.rank_delta(db,p,o,prep)
                sp.h.verify(hits,sp.h.native(ref,p,o))
            ref.close()
        db.close()
