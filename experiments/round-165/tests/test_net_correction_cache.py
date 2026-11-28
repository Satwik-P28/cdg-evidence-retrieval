import collections,os
from pathlib import Path
import signed_phrase as sp
from net_correction_cache import candidates_capture,measure_candidates,install_cache,cache_reader,digest,key,pack,MODE
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_cache_matches_and_fallback(tmp_path):
    # Ensure enough long unchanged context for index-delta admission.
    ev=[]
    for i in range(16):
        raw=("alpha beta alpha gamma "*80+" ".join("tok"+str(i*1000+j) for j in range(300))).encode()
        ev.append((str(i),0,raw))
    for i in range(16):ev.append((str(i),1,ev[i][2].replace(b"alpha beta",b"alpha delta",1)))
    path=tmp_path/"archive";db,_=sp.f.build(path,EXT,ev,"marginal",False);qs=[]
    stats=sp.build_delta(db,path,ev,MODE,candidates_capture(qs));assert stats["delta_contents"]>0
    rows=measure_candidates(db,qs);base=path.stat().st_size
    r=install_cache(db,path,base,rows,"cancellation",1000);assert r["cache_entries"]>0
    assert path.stat().st_size<=base*2
    # Ensure explicit empty cached correction is actually exercised.
    k=key((b"alpha",));body=pack([],True)
    db.execute("INSERT OR REPLACE INTO net_cache VALUES(?,?,?)",(k,body,digest(k,body)));db.commit()
    rd=cache_reader(db);w=collections.Counter();assert rd(db,[b"alpha"],{},collections.Counter(),w)
    assert w["cache_hits"]==1
    mapping=sp.load_patch_map(db)
    for cut in (1,16,24,32):
        prep=sp.prepare_delta(db,cut,mapping);ref=sp.h.active_oracle(ev,cut)
        for p,o in [(("alpha",),"AND"),(("alpha beta",),"AND"),(("alpha delta",),"AND"),
                    (("alpha","gamma"),"OR"),(("alpha beta","alpha delta"),"AND"),(("absent",),"AND")]:
            a=[];b=[];want,df,_=sp.rank_delta(db,p,o,prep,frequency_sink=a)
            got,df2,_=sp.rank_delta(db,p,o,prep,frequency_sink=b,patch_cache=rd)
            assert (want,df,a)==(got,df2,b);sp.h.verify(got,sp.h.native(ref,p,o))
        ref.close()
    db.execute("UPDATE net_cache SET tag=zeroblob(16) WHERE k=?",(k,));db.commit()
    w=collections.Counter();assert not rd(db,[b"alpha"],{},collections.Counter(),w)
    assert w["cache_bad_tag"]==1
    db.close()
