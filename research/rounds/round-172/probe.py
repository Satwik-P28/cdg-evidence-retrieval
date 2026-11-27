import collections,itertools,random,sqlite3

def varint(n):
    if n<0:raise ValueError('negative')
    b=bytearray()
    while n>=128:b.append((n&127)|128);n>>=7
    b.append(n);return bytes(b)

def pack_positions(rows):
    out=bytearray();prev=0
    for cid,positions in rows:
        if cid<=prev or not positions:raise ValueError('position posting order')
        out.extend(varint(cid-prev));out.extend(varint(len(positions)));prev=cid;last=-1
        for pos in positions:
            if pos<=last:raise ValueError('position order')
            out.extend(varint(pos-last));last=pos
    return bytes(out)

def unpack_positions(raw):
    i=0;cid=0
    def get():
        nonlocal i
        n=shift=0
        while i<len(raw) and shift<=63:
            b=raw[i];i+=1;n|=(b&127)<<shift
            if b<128:return n
            shift+=7
        raise ValueError('truncated position varint')
    while i<len(raw):
        step=get();n=get()
        if not step or not n or n>len(raw)-i:raise ValueError('invalid position posting')
        cid+=step;last=-1;positions=[]
        for _ in range(n):
            step=get()
            if not step:raise ValueError('nonincreasing position')
            last+=step;positions.append(last)
        yield cid,positions

def shifted_count(covered,dl,length):
    if not covered:raise ValueError('empty coverage')
    i,positions=min(covered,key=lambda x:len(x[1]));starts={p-i for p in positions if 0<=p-i<=dl-length}
    for j,ps in covered:
        if j!=i:starts.intersection_update(p-j for p in ps)
        if not starts:break
    return len(starts)

def main():
    rng=random.Random(172)
    for _ in range(10000):
        seq=[rng.randrange(5) for _ in range(rng.randrange(100))];q=[rng.randrange(5) for _ in range(rng.randrange(2,9))]
        lists=[(i,[j for j,t in enumerate(seq) if t==x]) for i,x in enumerate(q)]
        exact=sum(seq[j:j+len(q)]==q for j in range(len(seq)-len(q)+1))
        assert shifted_count(lists,len(seq),len(q))==exact
        part=rng.sample(lists,rng.randrange(1,len(lists)+1));assert shifted_count(part,len(seq),len(q))>=exact
        docs=[(i*3+1,sorted(rng.sample(range(1000),rng.randrange(1,40)))) for i in range(rng.randrange(1,9))]
        assert list(unpack_positions(pack_positions(docs)))==docs
    print('random codec/full/partial checks: 10000 each')
    rng=random.Random(172);db=sqlite3.connect(':memory:');db.execute('CREATE VIRTUAL TABLE docs USING fts5(body)')
    docs={i:[f'common{rng.randrange(16)}' if rng.random()<.6 else f'rare{rng.randrange(1000)}' for _ in range(250)] for i in range(1,401)}
    db.executemany('INSERT INTO docs(rowid,body) VALUES(?,?)',[(i,' '.join(ts)) for i,ts in docs.items()]);db.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(docs,'instance')")
    postings={}
    for term,rows in itertools.groupby(db.execute('SELECT term,doc,offset FROM vocab ORDER BY term,doc,offset'),key=lambda r:r[0]):
        vals=[(cid,[p for _,_,p in rs]) for cid,rs in itertools.groupby(rows,key=lambda r:r[1])];postings[term]=dict(unpack_positions(pack_positions(vals)))
    queries=[]
    for i in range(8):
        queries.append(('common',(f'common{i}',f'common{(i+1)%16}')))
        queries.append(('mixed',(f'common{i}',f'rare{i}',f'common{(i+2)%16}')))
        queries.append(('rare',(f'rare{i}',f'rare{i+1}')))
    for limit in (0,8,16,32,len(postings)):
        selected=set(sorted(postings,key=lambda t:(-len(postings[t]),t))[:limit]);total=collections.Counter();checks=0
        for group,q in queries:
            candidates=set.intersection(*(set(postings.get(t,{})) for t in set(q)));covered=[(i,t) for i,t in enumerate(q) if t in selected];complete=len(covered)==len(q);got={}
            total[(group,'candidates')]+=len(candidates)
            for cid in candidates:
                if len(covered)>=2:
                    upper=shifted_count([(i,postings[t][cid]) for i,t in covered],len(docs[cid]),len(q))
                    if not upper:total[(group,'rejected')]+=1;continue
                    if complete:got[cid]=upper;total[(group,'exact')]+=1;continue
                total[(group,'source_reads')]+=1;ts=docs[cid];tf=sum(tuple(ts[j:j+len(q)])==q for j in range(len(ts)-len(q)+1))
                if tf:got[cid]=tf
            expected={cid:sum(tuple(ts[j:j+len(q)])==q for j in range(len(ts)-len(q)+1)) for cid,ts in docs.items()};expected={cid:tf for cid,tf in expected.items() if tf}
            native={cid for cid, in db.execute('SELECT rowid FROM docs WHERE docs MATCH ?',('"'+ ' '.join(q)+'"',))}
            assert got==expected and set(got)==native;checks+=1
        print(limit,checks,{g:{k:total[g,k] for k in ('candidates','rejected','exact','source_reads')} for g in ('common','mixed','rare')})
    db.close()
if __name__=='__main__':main()
