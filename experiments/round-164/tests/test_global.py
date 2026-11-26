import itertools,random
from global_facilities import value,expansion,bound,exact_mip

def brute(w,o,a,access):
    names=sorted(access);options=[[-1]+[j for j,ws in enumerate(w) if n in ws] for n in names]
    return max(value({n:j for n,j in zip(names,labels) if j!=-1},w,o,a,access)
               for labels in itertools.product(*options))

def test_exact_expansions():
    rng=random.Random(164)
    for _ in range(40):
        access={str(i):rng.randrange(8) for i in range(5)}
        w=[{n:rng.randrange(1,30) for n in access if rng.randrange(4)} for _ in range(3)]
        o=[rng.randrange(10) for _ in w];a=[rng.randrange(10) for _ in w]
        x={n:rng.choice(js) for n in access if (js:=[j for j,ws in enumerate(w) if n in ws]) and rng.randrange(2)}
        for target in (-1,0,1,2):
            can=[n for n in access if x.get(n,-1)!=target and (target==-1 or n in w[target])]
            best=value(x,w,o,a,access)
            for mask in range(1<<len(can)):
                y=dict(x)
                for i,n in enumerate(can):
                    if mask>>i&1:
                        if target==-1:y.pop(n,None)
                        else:y[n]=target
                best=max(best,value(y,w,o,a,access))
            y,gain=expansion(x,target,w,o,a,access)
            assert value(y,w,o,a,access)==best==value(x,w,o,a,access)+gain
        ub,_=bound(w,o,a,access);assert ub>=brute(w,o,a,access)

def test_greedy_unbounded_gap():
    # k disjoint facilities each yield 1, distractor takes one client from
    # each group for gain 2, after which all remaining groups lose money.
    k=12;w=[{"a"+str(i):10,"b"+str(i):10} for i in range(k)]
    w.append({"a"+str(i):1 for i in range(k)})
    o=[19]*k+[k-2];a=[0]*(k+1);access={n:1 for ws in w for n in ws}
    greedy={n:k for n in w[k]};optimal={n:j for j in range(k) for n in w[j]}
    assert value(greedy,w,o,a,access)==2
    assert value(optimal,w,o,a,access)==k
    x,res=exact_mip(w,o,a,access,1,10)
    assert res["status"]==0 and value(x,w,o,a,access)==k
