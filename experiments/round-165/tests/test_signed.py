import itertools,random,os
from pathlib import Path
import pytest
from signed_phrase import windows,count,L,build_delta,rank_delta,prepare_delta,f,h
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

@pytest.mark.parametrize("mode",["aligned_single","aligned_multi","independent_multi"])
def test_native_signed_index(tmp_path,mode):
    text=(b"alpha beta gamma delta epsilon theta "*150)
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
