import collections,os,random,sqlite3
from pathlib import Path
import signed_phrase as sp
from real_residuals import key,upper,residual,pack,unpack,blocks,block_decode,builder,reader,MODE

EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_residual_codec_and_prefix():
    rng=random.Random(188)
    vocab=[b"a",b"ab",b"b","中文".encode(),"café".encode(),b"x"*400]
    for _ in range(1000):
        a=tuple(rng.choices(vocab,k=rng.randrange(1,30)));b=tuple(rng.choices(vocab,k=rng.randrange(1,30)))
        w=collections.Counter({a:-1});w[b]+=1
        r=residual(w)
        for _ in range(8):
            q=tuple(rng.choices(vocab,k=rng.randrange(1,9)));k=key(q)
            assert sum(c for s,c in r.items() if k<=key(s)<upper(k))==sp.count(b,q)-sp.count(a,q)
    rows=[(1,-3),(2,2),(65536,10000),(65540,-20000)]
    for z in (False,True):assert list(unpack(pack(rows,z)))==rows
    items=sorted((key((t,)),pack(rows)) for t in vocab)
    assert [(k,b) for _,block,_ in blocks(items) for k,b in block_decode(block)]==items

def test_zero_net_and_absent_cache():
    db=sqlite3.connect(":memory:")
    # Two keys contribute opposite signed corrections to prefix a.
    pending=[(1,{(b"a",b"b"):-1,(b"a",b"c"):1})]
    stats=collections.Counter();assert not builder("residual_cache")(db,pending,stats)
    # Explicit cached zero vs absent cache row must behave differently.
    db.execute("INSERT OR REPLACE INTO residual_cache VALUES(?,?)",(key((b"a",)),b"\0"))
    r=reader(db);counts=collections.Counter();work=collections.Counter()
    r(db,[b"a"],{1:[1]},counts,work)
    assert not counts and work["residual_cache_hits"]==1
    r(db,[b"a",b"c"],{1:[1]},counts,work)
    assert counts[1]==1

def test_native_snapshots(tmp_path):
    rng=random.Random(188);ev=[]
    for i in range(15):
        raw=("alpha beta alpha gamma "*30+" ".join("tok"+str(rng.randrange(100000)) for _ in range(200))+" CAFÉ 中文 ").encode()
        ev.append((str(i),0,raw))
    for i in range(15):ev.append((str(i),1,ev[i][2].replace(b"alpha beta",b"alpha delta",1)))
    for mode in ("signed","residual","residual_cache","hybrid_cache"):
        path=tmp_path/mode;db,_=sp.f.build(path,EXT,ev,"marginal",False)
        stats=sp.build_delta(db,path,ev,MODE,None if mode=="signed" else builder(mode))
        assert stats["delta_contents"]>0
        db.close();db=sp.connect(path,EXT);mapping=sp.load_patch_map(db);rd=reader(db)
        for c in (1,15,22,30):
            ref=sp.h.active_oracle(ev,c);prep=sp.prepare_delta(db,c,mapping)
            for p,o in [(("alpha beta",),"AND"),(("alpha delta",),"AND"),(("alpha alpha",),"AND"),
                        (("cafe 中文","alpha delta"),"OR"),(("alpha","gamma"),"AND"),(("absent",),"AND")]:
                got,_,_=sp.rank_delta(db,p,o,prep,rd)
                sp.h.verify(got,sp.h.native(ref,p,o))
            ref.close()
        db.close()
