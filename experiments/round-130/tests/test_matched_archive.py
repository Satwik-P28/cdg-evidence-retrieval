"""Policy-specific tests, plus an integrated synthetic control using real FTS."""
import hashlib,os,random
from pathlib import Path
import pytest
from matched_archive import (POLICIES,DEPTHS,BOUNDED,integrated_setup,append_policy,
    fixture_origin,recover,C,choose_previous_budget,experiment,sha)

@pytest.mark.parametrize("policy",POLICIES)
def test_exact_and_bounds(tmp_path,policy):
    ext=Path(os.environ["CDG_FTS_EXTENSION"])
    db=integrated_setup(tmp_path/"test.sqlite",ext,{"fixture":True})
    rng=random.Random(130)
    base=" ".join(f"token{rng.randrange(100000)}" for _ in range(600)).encode()
    versions=[base+f" edit{i}".encode() for i in range(15)]+[b"tiny",b"",base]
    for i,raw in enumerate(versions):
        assert append_policy(db,"doc",raw,fixture_origin(raw,str(i)),policy)==(i+1,i)
    for i,raw in enumerate(versions):
        got,a,d,depth=recover(db,"doc",i)
        assert got==raw and depth<=DEPTHS[policy]
        if policy in BOUNDED:
            assert 2*a<=3*len(C.compress(raw)) and 2*d<=5*len(raw)
    db.close()

def test_budget_previous_refuses_nonliteral():
    assert choose_previous_budget(b"hello",1,[(b"hello",10,1)])[1]==0

def test_integrated(tmp_path):
    ext=Path(os.environ["CDG_FTS_EXTENSION"])
    events=[];origins=[]
    rng=random.Random(130)
    bases={a:("common " + " ".join(f"word{rng.randrange(500)}" for _ in range(300))).encode()
           for a in ("a","b","c","d")}
    for i in range(5):
        for a,base in bases.items():
            raw=base+f" update{i}".encode();events.append((a,i,raw))
            c,t,b=fixture_origin(raw,str(len(events)))
            origins.append(dict(g=len(events),commit=c,committer_unix=t,blob_sha1=b))
    manifest=dict(cutoffs=[4,12,20],origins=origins,retained_paths=list(bases),changed_paths=4)
    result=experiment(tmp_path,events,manifest,ext,1)
    assert set(result["policies"])==set(POLICIES)
    assert result["pareto_policies"]
    assert all(x["source_reads"]==20 and x["max_score_error"]<1e-11 for x in result["policies"].values())
