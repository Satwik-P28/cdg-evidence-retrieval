"""Mixed edit regimes: adaptive residual suffix basis plus native positional FTS control."""
from probe import *

def run():
    rng=random.Random(185);pairs=[];qs=set()
    for regime in ('substitution','insertion','deletion','rewrite'):
        for _ in range(600):
            a=tuple(rng.choices(range(256),weights=[32 if i<8 else 1 for i in range(256)],k=31));i=15
            if regime=='substitution':b=a[:i]+(rng.randrange(256),)+a[i+1:]
            elif regime=='insertion':b=a[:i]+tuple(rng.randrange(256) for _ in range(3))+a[i:]
            elif regime=='deletion':b=a[:i]+a[i+3:]
            else:b=a[:8]+tuple(rng.randrange(256) for _ in range(15))+a[23:]
            c=residual(a,b);pairs.append((a,b,c));j=rng.randrange(len(a)-7);qs.add(a[j:j+rng.randrange(1,9)])
    qs=sorted(qs);rng.shuffle(qs);qs=qs[:80]
    expected=[{i:d for i,(a,b,_) in enumerate(pairs,1) if (d:=count(b,q)-count(a,q))} for q in qs]
    out={}
    with tempfile.TemporaryDirectory() as tmp:
        for mode in ('fts','suffix','hybrid'):
            path=Path(tmp)/(mode+'.db');db=sqlite3.connect(path)
            if mode!='suffix':db.execute("CREATE VIRTUAL TABLE patches USING fts5(body,content='')")
            if mode!='fts':db.execute('CREATE TABLE basis(cid INTEGER PRIMARY KEY,body BLOB NOT NULL)')
            ns=nf=0
            for i,(a,b,c) in enumerate(pairs,1):
                if mode=='suffix' or (mode=='hybrid' and 5*len(c)<=2*(len(a)+len(b))):
                    db.execute('INSERT INTO basis VALUES(?,?)',(i,pack_basis(c)));ns+=1
                else:
                    db.executemany('INSERT INTO patches(rowid,body) VALUES(?,?)',[(2*i+s,' '.join('t'+str(t) for t in w)) for s,w in ((0,a),(1,b))]);nf+=1
            if mode!='suffix':db.execute("INSERT INTO patches(patches) VALUES('optimize')")
            db.commit();db.execute('VACUUM');size=path.stat().st_size;db.close();db=sqlite3.connect(path)
            t=time.perf_counter_ns();post=collections.defaultdict(lambda:collections.defaultdict(set));data=[]
            if mode!='suffix':
                db.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,patches,'instance')")
                for term,doc,off in db.execute('SELECT term,doc,offset FROM temp.vocab'):post[int(term[1:])][doc].add(off)
            if mode!='fts':data=[(i,decode_basis(blob)) for i,blob in db.execute('SELECT cid,body FROM basis')]
            setup=(time.perf_counter_ns()-t)/1e6;times=[]
            for q,want in zip(qs,expected):
                t=time.perf_counter_ns();got=collections.Counter()
                if mode!='suffix':
                    for rid in set.intersection(*(set(post[x]) for x in set(q))):
                        starts=post[q[0]][rid].copy()
                        for j,x in enumerate(q[1:],1):starts.intersection_update(p-j for p in post[x][rid])
                        got[rid//2]+=len(starts)*(1 if rid&1 else -1)
                for i,d in data:got[i]+=basis_count(d,q)
                got={i:d for i,d in got.items() if d};times.append((time.perf_counter_ns()-t)/1000);assert got==want
            times.sort();out[mode]=dict(bytes=size,basis_pairs=ns,fts_pairs=nf,setup_ms=setup,median_us=times[len(times)//2],p95_us=times[int(.95*(len(times)-1))],checks=len(pairs)*len(qs));db.close()
    return dict(pairs=len(pairs),queries=len(qs),threshold=.4,policies=out)
if __name__=='__main__':
    out=run();print(json.dumps(out,indent=2));Path(__file__).with_name('hybrid-results.json').write_text(json.dumps(out,indent=2)+'\n')
