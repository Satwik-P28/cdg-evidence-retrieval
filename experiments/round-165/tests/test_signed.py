import itertools,random,os
from pathlib import Path
import pytest
from signed_phrase import windows,count,L,build_delta,rank_delta,prepare_delta,f,h,signed_terms,load_patch_map,PatchRuns,share_window
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def ngrams(seq):
    return {tuple(seq[i:i+n]) for n in range(1,L+1) for i in range(len(seq)-n+1)}

def check(a,b):
    for multi in (False,True):
        w=windows(a,b,multi)
        for p in ngrams(a)|ngrams(b):
            p=list(p)
            assert count(b,p)==count(a,p)+sum(count(y,p)-count(x,p) for x,y in w)

def test_exhaustive():
    ss=[list(x) for n in range(5) for x in itertools.product(range(2),repeat=n)]
    for a in ss:
        for b in ss:check(a,b)

def test_random_spaced_edits():
    rng=random.Random(165)
    for _ in range(150):
        a=[rng.randrange(5) for _ in range(rng.randrange(100))];b=a[:]
        for _ in range(8):
            i=rng.randrange(len(b)+1);b[i:i+rng.randrange(5)]=[rng.randrange(5) for _ in range(rng.randrange(5))]
        check(a,b)

@pytest.mark.parametrize("mode",["aligned_single","aligned_multi","independent_multi","aligned_quotient_multi","independent_quotient_multi","independent_dense_multi"])
def test_native_signed_index(tmp_path,mode):
    rng=random.Random(166)
    text=b"alpha beta gamma delta epsilon theta "+b" ".join(("word"+str(rng.randrange(1000000))).encode() for _ in range(900))
    ev=[("a",0,text),("b",0,text),("a",1,text.replace(b"gamma",b"unique",1)),
        ("a",2,text[:-30]+b"another finish"),("c",0,b""),("d",0,"CAFÉ café 中文!".encode())]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False);size=build_delta(db,path,ev,mode)
    assert size.get("delta_contents",0)>0
    for c in range(1,len(ev)+1):
        ref=h.active_oracle(ev,c)
        for p,o in [(("alpha beta unique delta",),"AND"),(("alpha","gamma"),"OR"),(("gamma delta",),"AND"),(("another finish",),"AND"),(("cafe",),"AND")]:
            hits,df,_=rank_delta(db,p,o,prepare_delta(db,c));h.verify(hits,h.native(ref,p,o))
        ref.close()
    with pytest.raises(ValueError):rank_delta(db,("alpha "*9,),"AND",prepare_delta(db,len(ev)))
    db.close()


def test_signed_multiset_cancellation():
    assert signed_terms([([1,2],[2,3]),([1,2],[2,3]),([2,3],[1,2])])=={(1,2):-1,(2,3):1}
    assert signed_terms([([1],[2]),([2],[1]),([],[])])=={}

def test_adaptive_halo():
    rng=random.Random(166)
    for _ in range(100):
        a=[rng.randrange(4) for _ in range(rng.randrange(60))]
        b=a[:]
        for _ in range(6):
            i=rng.randrange(len(b)+1)
            b[i:i+rng.randrange(4)]=[rng.randrange(4) for _ in range(rng.randrange(4))]
        for limit in range(1,L+1):
            terms=signed_terms(windows(a,b,True,limit))
            for p in ngrams(a)|ngrams(b):
                if len(p)!=limit:continue
                q=list(p)
                assert count(b,q)==count(a,q)+sum(coef*count(list(w),q) for w,coef in terms.items())

def test_native_quotient_multiplicity(tmp_path):
    rng=random.Random(166)
    context=b"left one two three four five six seven OLD eight nine ten eleven twelve thirteen right"
    def document():
        return b" ".join(("tok"+str(rng.randrange(1000000))).encode() for _ in range(900))+b" "+context
    a,b=document(),document()
    ev=[("a",0,a),("b",0,b),("a",1,a.replace(b"OLD",b"NEW")),("b",1,b.replace(b"OLD",b"NEW"))]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    size=build_delta(db,path,ev,"independent_quotient_multi")
    assert size["window_uses"]>size["distinct_windows"]
    for c in range(1,len(ev)+1):
        ref=h.active_oracle(ev,c)
        for p,o in [(("seven old eight",),"AND"),(("seven new eight",),"AND"),(("left","new"),"OR")]:
            hits,_,_=rank_delta(db,p,o,prepare_delta(db,c));h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()


def test_run_boundaries():
    runs=PatchRuns([(2,10),(5,50)],{12:[(99,-2),(100,3)]})
    assert runs.get(2)==((10,-1),)
    assert runs.get(5)==((10,1),)
    assert runs.get(6)==((50,-1),)
    assert runs.get(11)==((50,1),)
    assert runs.get(12)==[(99,-2),(100,3)]
    assert runs.get(13)==()
    assert not share_window(tuple(range(15)),[(1,1)])
    assert share_window(tuple(range(15)),[(1,1),(2,-1)])

@pytest.mark.parametrize("mode",["independent_runs_multi","independent_adaptive_multi","independent_quotient_global_multi"])
def test_global_map_native(tmp_path,mode):
    rng=random.Random(167)
    shared=b" one two three four five six seven OLD eight nine ten eleven twelve thirteen fourteen "
    def doc():
        return b" ".join(("tok"+str(rng.randrange(1000000))).encode() for _ in range(900))+shared
    a,b=doc(),doc()
    ev=[("a",0,a),("b",0,b),("a",1,a.replace(b"OLD",b"NEW")),
        ("b",1,b.replace(b"OLD",b"NEW")),("a",2,a.replace(b"OLD",b"DIFFERENT"))]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    size=build_delta(db,path,ev,mode)
    if "_runs_" in mode:assert size["direct_rows"]>0
    if "_adaptive_" in mode:
        assert size["shared_rows"]>0 and size["direct_rows"]>0
    mapping=load_patch_map(db)
    assert mapping is not None
    for c in range(1,len(ev)+1):
        ref=h.active_oracle(ev,c)
        for p,o in [(("seven old eight",),"AND"),(("seven new eight",),"AND"),
                    (("seven different eight",),"AND"),(("one","old"),"OR")]:
            hits,_,_=rank_delta(db,p,o,prepare_delta(db,c,mapping))
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()
