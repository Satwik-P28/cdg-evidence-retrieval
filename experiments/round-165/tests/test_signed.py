import itertools,random,os
from pathlib import Path
import pytest
from signed_phrase import windows,count,L,build_delta,rank_delta,prepare_delta,f,h,signed_terms,load_patch_map,PatchRuns,share_window,write_runs
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

@pytest.mark.parametrize("mode",["independent_runs_multi","independent_adaptive_multi","independent_quotient_global_multi","independent_runs_weighted_multi","independent_adaptive_weighted_multi","independent_adaptive_weighted_adjusted_multi"])
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


@pytest.mark.parametrize("adaptive,adjusted",[(False,False),(True,False),(True,True)])
def test_weighted_private_and_shared(tmp_path,adaptive,adjusted):
    import collections
    import sqlite3
    path=tmp_path/"coeff.db"
    db=sqlite3.connect(path)
    db.execute("CREATE VIRTUAL TABLE patch_fts USING fts5(body,content='')")
    db.execute("CREATE TABLE patch_run(last_ordinal INTEGER PRIMARY KEY,cid INTEGER NOT NULL)")
    db.execute("CREATE TABLE patch_use(wid INTEGER NOT NULL,cid INTEGER NOT NULL,coeff INTEGER NOT NULL CHECK(coeff<>0),PRIMARY KEY(wid,cid)) WITHOUT ROWID")
    repeated=tuple(["shared"]*15)
    a=("a","a","b");b=("b","c");c=("c","a")
    terms=[(1,{a:-17,b:3,repeated:4}),(4,{c:-2,repeated:-5}),(9,{("unique",):1})]
    materialized={}
    def insert(table,rid,w):
        assert rid not in materialized
        materialized[rid]=tuple(w)
        db.execute(f"INSERT INTO {table}(rowid,body) VALUES(?,?)",(rid," ".join(w)))
    stats=collections.Counter()
    write_runs(db,terms,insert,stats,adaptive,True,adjusted)
    assert stats["coefficient_exceptions"]>=3 and stats["avoided_rows"]>=19
    db.commit();db.close()
    db=sqlite3.connect(path)
    mapping=load_patch_map(db)
    got=collections.defaultdict(collections.Counter)
    for (rid,) in db.execute("SELECT rowid FROM patch_fts"):
        for cid,coef in mapping.get(rid,()):got[cid][materialized[rid]]+=coef
    assert got=={cid:collections.Counter(cs) for cid,cs in terms}
    for p in [("a",),("a","a"),("shared","shared"),("unique",)]:
        hits={r[0] for r in db.execute("SELECT rowid FROM patch_fts WHERE patch_fts MATCH ?",('"'+ ' '.join(p)+'"',))}
        for active in ({1},{4},{1,4,9},set()):
            observed=collections.Counter()
            for rid in hits:
                tf=count(list(materialized[rid]),list(p))
                for cid,coef in mapping.get(rid,()):
                    if cid in active:observed[cid]+=tf*coef
            want={cid:sum(coef*count(list(w),list(p)) for w,coef in cs.items()) for cid,cs in terms if cid in active}
            assert observed==collections.Counter(want)
    db.close()

def test_adjusted_sharing():
    w=tuple(range(4))
    uses=[(1,20),(2,-20)]
    assert share_window(w,uses)
    assert not share_window(w,uses,True)

def test_native_repeated_private_coefficients(tmp_path):
    rng=random.Random(168)
    # The same 15-token window is repeated with disjoint contexts, ensuring non-unit signed coefficients.
    unit=b" one two three four five six seven OLD eight nine ten eleven twelve thirteen fourteen "
    sep=b" ".join(("sep"+str(i)).encode() for i in range(20))
    base=b" ".join(("tok"+str(rng.randrange(1000000))).encode() for _ in range(1200))+unit+sep+unit+sep+unit
    child=base.replace(b"OLD",b"NEW")
    ev=[("a",0,base),("a",1,child)]
    path=tmp_path/"db";db,_=f.build(path,EXT,ev,"marginal",False)
    size=build_delta(db,path,ev,"independent_runs_weighted_multi")
    assert size["coefficient_exceptions"]>0 and size["avoided_rows"]>0
    for cutoff in (1,2):
        ref=h.active_oracle(ev,cutoff)
        for p,o in [(("seven old eight",),"AND"),(("seven new eight",),"AND"),(("old","new"),"OR")]:
            hits,_,_=rank_delta(db,p,o,prepare_delta(db,cutoff))
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    db.close()


def test_shared_alignment_native_offsets():
    from signed_phrase import alignment
    from shared_alignment import offsets,make_script,decode_script
    from frequency_index import connect,tokens
    db=connect(":memory:",EXT)
    pairs=[("  CAFÉ, old! 中文. ","\nCafe new? 中文!"),
        ("a b a b a b","a b a c a b"),("","new"),("old",""),
        ("!!!","???"),("A\u0301 a","á A"),("alpha beta","ALPHA   BETA")]
    for a,b in pairs:
        old,raw=a.encode(),b.encode()
        aa,bb=tokens(db,a),tokens(db,b)
        ops=alignment(aa,bb)
        script=make_script(old,raw,offsets(db,old,aa),offsets(db,raw,bb),ops)
        assert decode_script(old,script,len(raw))==raw
        assert windows(aa,bb,True,ops=ops)==windows(aa,bb,True)
    db.close()

def test_shared_alignment_random_native():
    from signed_phrase import alignment
    from shared_alignment import offsets,make_script,decode_script
    from frequency_index import connect,tokens
    db=connect(":memory:",EXT);rng=random.Random(169)
    words=["A","a","B","b","café","CAFE","中文","x","!","é","e\u0301"]
    seps=[" ","  ",", ","!","\n","-"]
    for _ in range(300):
        a=[rng.choice(words) for _ in range(rng.randrange(40))]
        b=a[:]
        for _ in range(4):
            i=rng.randrange(len(b)+1);b[i:i+rng.randrange(3)]=[rng.choice(words) for _ in range(rng.randrange(3))]
        def render(x):return rng.choice(seps)+''.join(w+rng.choice(seps) for w in x)
        old,raw=render(a).encode(),render(b).encode()
        aa,bb=tokens(db,old.decode()),tokens(db,raw.decode())
        ops=alignment(aa,bb)
        script=make_script(old,raw,offsets(db,old,aa),offsets(db,raw,bb),ops)
        assert decode_script(old,script,len(raw))==raw
    db.close()

def test_shared_script_malformed():
    from shared_alignment import decode_script
    for script in (b"\x02",b"\x00",b"\x01"+b"\x00"*8,b"\x00\x00\x00\x00\x04x",b"\x01\x00\x00\x00\x05\x00\x00\x00\x01"):
        with pytest.raises(ValueError):decode_script(b"abc",script,1)
