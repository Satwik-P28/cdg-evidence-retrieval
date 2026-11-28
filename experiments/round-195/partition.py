"""Contiguous block DP with exact codec costs and logical decode constraints."""

def candidates(parts,cap,encode,limit=16):
    for i in range(len(parts)):
        raw=b''
        for j in range(i+1,min(len(parts),i+limit)+1):
            raw+=parts[j-1]
            if len(raw)>cap and j>i+1:break
            blob=encode(raw)
            yield i,j,len(raw),len(blob)
            if len(raw)>cap:break

def greedy(parts,cap,limit=16):
    out=[];i=0
    while i<len(parts):
        j=i+1;n=len(parts[i])
        while j<len(parts) and j-i<limit and n+len(parts[j])<=cap:
            n+=len(parts[j]);j+=1
        out.append((i,j));i=j
    return out

def optimize(parts,cap,encode,penalty=0,overhead=64,limit=16):
    # Integer objective: 64*(encoded bytes + block proxy) + penalty*(uniform excess decode bytes).
    # Excess decode sums per-source requests, not a measured query workload.
    n=len(parts);edges=[[] for _ in range(n)]
    for i,j,raw,enc in candidates(parts,cap,encode,limit):
        score=64*(enc+overhead)+penalty*(j-i-1)*raw
        edges[i].append((j,score))
    best=[None]*(n+1);best[n]=(0,0,())
    for i in range(n-1,-1,-1):
        best[i]=min((score+best[j][0],1+best[j][1],(j,)+best[j][2]) for j,score in edges[i])
    start=0;out=[]
    for end in best[0][2]:out.append((start,end));start=end
    assert start==n
    return out,best[0][0]

def measure(parts,spans,encode):
    raw=enc=excess=0;maximum=0;position=0
    for i,j in spans:
        assert i==position and i<j<=len(parts);position=j
        block=b''.join(parts[i:j]);n=len(block);raw+=n;enc+=len(encode(block));excess+=(j-i-1)*n;maximum=max(maximum,n)
    assert position==len(parts)
    return dict(blocks=len(spans),payload=enc,raw=raw,excess=excess,max_block=maximum)
