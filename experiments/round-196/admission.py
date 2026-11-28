"""Budget search and source identity remapping, independent of codec."""
import collections
import hashlib

def pid(doc):
    return str(doc["doc_id"]).rsplit("|",2)[0]

def priority(docs,seed,policy):
    keys=[hashlib.sha256(f"R196|{seed}|{d['doc_id']}".encode()).digest() for d in docs]
    if policy=="global":return sorted(range(len(docs)),key=lambda i:(keys[i],i))
    if policy!="balanced":raise ValueError("policy")
    groups=collections.defaultdict(list)
    for i,d in enumerate(docs):groups[pid(d)].append(i)
    ranks={}
    for members in groups.values():
        for rank,i in enumerate(sorted(members,key=lambda i:(keys[i],i))):ranks[i]=rank
    return sorted(range(len(docs)),key=lambda i:(ranks[i],keys[i],i))

def subset(docs,cases,order,n):
    indices=sorted(order[:n]);chosen=[docs[i] for i in indices]
    old_to_new={old+1:new+1 for new,old in enumerate(indices)}
    ranges={}
    for rid,doc in enumerate(chosen,1):
        p=pid(doc)
        if p in ranges:
            assert ranges[p][1]==rid-1
            ranges[p][1]=rid
        else:ranges[p]=[rid,rid]
    # Dropped gold retains a unique negative original row ID, so denominator
    # and complete-union metric cannot be inflated by source admission.
    scoped=[]
    for c in cases:
        lo,hi=ranges.get(c["paper"],(1,0))
        gold={old_to_new.get(r,-r) for r in c["gold_rowids"]}
        scoped.append(dict(c,row_start=lo,row_end=hi,gold_rowids=gold))
    assert all(len(a["gold_rowids"])==len(b["gold_rowids"]) for a,b in zip(cases,scoped))
    return chosen,scoped

def fit_prefix(n,cap,probe):
    """Feasible prefix heuristic; file sizes can be non-monotonic.
    Test full corpus first, binary search, then probe nearby larger lengths.
    No global-optimality claim. Each accepted result actually measured.
    """
    if n<1 or cap<1:raise ValueError("invalid budget")
    full=probe(n)
    if full<=cap:return n,full
    lo,hi=0,n-1
    while lo<hi:
        mid=(lo+hi+1)//2
        if probe(mid)<=cap:lo=mid
        else:hi=mid-1
    if lo==0:raise ValueError("no nonempty measured prefix fits")
    best=lo
    for k in sorted({min(n,lo+d) for d in (1,2,4,8,16,32)}):
        if probe(k)<=cap:best=max(best,k)
    size=probe(best)
    assert size<=cap
    return best,size
