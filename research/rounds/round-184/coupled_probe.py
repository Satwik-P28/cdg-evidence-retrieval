import collections, itertools, random, json

def common(a,b):
    p=0
    while p<min(len(a),len(b)) and a[p]==b[p]:p+=1
    s=0
    while s<min(len(a),len(b))-p and a[len(a)-1-s]==b[len(b)-1-s]:s+=1
    return p,s

def starts(w,p,s,q):
    # Valid phrase starts not wholly inside common prefix or suffix.
    l=len(q)
    return range(max(0,p-l+1),min(len(w)-l+1,len(w)-s))

def envelope(w,p,s,q):
    # At least one middle token must agree with a corresponding query offset,
    # except if the middle is empty (a gap whose crossing can break adjacency).
    l=len(q);middle=w[p:len(w)-s];possible=starts(w,p,s,q)
    if not middle:return len(possible)
    valid=set(possible)
    supported={i-j for i in range(p,len(w)-s) for j,t in enumerate(q) if w[i]==t}
    return len(valid & supported)

def exact(w,p,s,q):return sum(w[i:i+len(q)]==q for i in starts(w,p,s,q))
def count(w,q):return sum(w[i:i+len(q)]==q for i in range(len(w)-len(q)+1))

def verify():
    seqs=[tuple(w) for n in range(6) for w in itertools.product(range(2),repeat=n)]
    qs=[tuple(w) for n in range(1,5) for w in itertools.product(range(2),repeat=n)]
    checks=0
    for a in seqs:
        for b in seqs:
            p,s=common(a,b)
            for q in qs:
                x,y=exact(a,p,s,q),exact(b,p,s,q);u,v=envelope(a,p,s,q),envelope(b,p,s,q)
                assert y-x==count(b,q)-count(a,q) and x<=u and y<=v
                checks+=1
    rng=random.Random(184)
    for _ in range(20000):
        a=tuple(rng.randrange(8) for _ in range(rng.randrange(0,45)));i=rng.randrange(len(a)+1);j=rng.randrange(i,len(a)+1);b=a[:i]+tuple(rng.randrange(8) for _ in range(rng.randrange(0,20)))+a[j:];q=tuple(rng.randrange(8) for _ in range(rng.randrange(1,9)))
        p,s=common(a,b);x,y=exact(a,p,s,q),exact(b,p,s,q);u,v=envelope(a,p,s,q),envelope(b,p,s,q)
        assert y-x==count(b,q)-count(a,q) and x<=u and y<=v;checks+=1
    return checks

def test(regime):
    rng=random.Random(184);pairs=[];queries=set()
    for _ in range(2000):
        w=tuple(rng.choices(range(40),weights=[20 if i<4 else 1 for i in range(40)],k=31));i=15
        if regime=='substitution':v=w[:i]+(rng.randrange(40),)+w[i+1:]
        elif regime=='insertion':v=w[:i]+tuple(rng.randrange(40) for _ in range(3))+w[i:]
        else:v=w[:i]+w[i+3:]
        pairs.append((w,v));k=rng.randrange(25);queries.add(w[k:k+rng.randrange(2,7)])
    queries=sorted(queries,key=lambda q: (len(q),q));rng.shuffle(queries);queries=queries[:120]
    work=collections.Counter()
    for q in queries:
        for a,b in pairs:
            p,s=common(a,b);delta=count(b,q)-count(a,q)
            u0=min([max(0,len(a)-len(q)+1)]+[a.count(x) for x in set(q)]);v0=min([max(0,len(b)-len(q)+1)]+[b.count(x) for x in set(q)])
            u,v=envelope(a,p,s,q),envelope(b,p,s,q)
            assert -u<=delta<=v
            work['pairs']+=1;work['unigram_zero']+=int(u0==v0==0);work['coupled_zero']+=int(u==v==0);work['true_zero']+=int(delta==0);work['unigram_width']+=u0+v0;work['coupled_width']+=u+v;work['combined_zero']+=int(min(u,u0)==min(v,v0)==0);work['combined_width']+=min(u,u0)+min(v,v0)
    return dict(regime=regime,queries=len(queries),**work)
if __name__=='__main__':print(json.dumps({'checks':verify(),'regimes':[test(r) for r in ('substitution','insertion','deletion')]},indent=2))
