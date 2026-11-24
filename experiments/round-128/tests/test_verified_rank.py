import random
from verified_rank import exact_rank,MODES,score

def test_ties_bad_draft():
    lens=[0]+[10]*80;aid={g:g for g in range(1,81)}
    freq=[{g:2 for g in aid}]
    want=score(freq,"AND",80,800,lens)[0]
    for m in MODES:
        got,w=exact_rank(freq,"AND",80,800,lens,aid,m,tuple(range(80,60,-1)),True)
        assert got==want
        assert [g for g,s in got]==list(range(1,11))

def test_randomized():
    r=random.Random(128)
    for _ in range(100):
        n=r.randint(1,200);lens=[0]+[r.randint(1,1000) for i in range(n)]
        aid={g:g for g in range(1,n+1)}
        freq=[{g:r.randint(1,lens[g]) for g in aid if r.random()<.65} for j in range(r.randint(1,6))]
        for op in ("AND","OR"):
            want=score(freq,op,n,sum(lens),lens)[0]
            for m in MODES:
                got,z=exact_rank(freq,op,n,sum(lens),lens,aid,m,tuple(reversed(list(aid)))[:10],True)
                assert got==want
