import random
from anchor_oracle import solve,greedy

def brute(full,edge,t=0,anchor=None):
    if t==len(full):return 0
    best=full[t]+brute(full,edge,t+1,t)
    if anchor is not None:
        d=edge(anchor,t)
        if d is not None:best=min(best,d+brute(full,edge,t+1,anchor))
    return best

def test_random():
    rng=random.Random(133)
    for _ in range(200):
        n=rng.randrange(1,9);full=[rng.randrange(10,100) for _ in range(n)]
        edges={(j,t):rng.choice([None,rng.randrange(1,full[t])]) for t in range(n) for j in range(t)}
        f=lambda j,t:edges[j,t]
        assert solve(full,f)==brute(full,f)<=greedy(full,f)

def test_counterexample():
    full=[100,100,100,100];edges={(0,1):10,(1,2):1,(1,3):1}
    f=lambda j,t:edges.get((j,t))
    assert solve(full,f)==202<greedy(full,f)==310
