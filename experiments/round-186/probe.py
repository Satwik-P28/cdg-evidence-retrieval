"""R186/R187 exact inverted suffix residuals. Synthetic patch subsystem only."""
import collections as C, itertools, json, random, sqlite3, struct, tempfile, time, zlib
from pathlib import Path
L=8
HERE=Path(__file__).resolve().parent

def key(q):return struct.pack('>'+str(len(q))+'H',*q)
def residual(a,b):
    r=C.Counter(b[i:i+L] for i in range(len(b)));r.subtract(a[i:i+L] for i in range(len(a)))
    return {k:v for k,v in r.items() if v}
def prefixes(r,lo=1,hi=L):
    out=C.Counter()
    for s,v in r.items():
        for n in range(lo,min(hi,len(s))+1):out[s[:n]]+=v
    return {k:v for k,v in out.items() if v}
def putv(n,out):
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n)
def encode(rows,compress=True):
    buf=bytearray();prev=0
    for cid,c in rows:
        assert cid>prev and c
        putv(cid-prev,buf);putv(2*c if c>0 else -2*c-1,buf);prev=cid
    z=zlib.compress(buf,6)
    return b'\1'+z if compress and len(z)<len(buf) else b'\0'+buf
def decode(blob):
    raw=zlib.decompress(blob[1:]) if blob[0] else blob[1:];i=cid=0
    def get():
        nonlocal i
        x=s=0
        while True:
            b=raw[i];i+=1;x|=(b&127)<<s
            if b<128:return x
            s+=7
    while i<len(raw):
        d=get();c=get();assert d and c;cid+=d
        yield cid,c//2 if c%2==0 else -(c+1)//2

def block_encode(rows):
    out=bytearray();prev=b''
    for k,body in rows:
        common=0
        while common<min(len(k),len(prev)) and k[common]==prev[common]:common+=1
        suffix=k[common:];out.extend(bytes((common,len(suffix))));putv(len(body),out);out.extend(suffix);out.extend(body);prev=k
    return zlib.compress(out,6)

def block_decode(blob):
    raw=zlib.decompress(blob);i=0;prev=b''
    while i<len(raw):
        p,n=raw[i:i+2];i+=2;b=shift=0
        while True:
            x=raw[i];i+=1;b|=(x&127)<<shift
            if x<128:break
            shift+=7
        k=prev[:p]+raw[i:i+n];i+=n;body=raw[i:i+b];i+=b
        assert p<=len(prev) and k>prev and i<=len(raw)
        yield k,body;prev=k

def block_query(db,k,upper):
    first=db.execute('SELECT k,body FROM inv WHERE k<=? ORDER BY k DESC LIMIT 1',(k,)).fetchone()
    if first is not None:yield first[1]
    for _,blob in db.execute('SELECT k,body FROM inv WHERE k>? AND k<? ORDER BY k',(k,upper)):yield blob

def build_pairs(seed,n,vocab,regime):
    rng=random.Random(seed);pairs=[];qs=set();weights=[vocab//4 if i<8 else 1 for i in range(vocab)]
    for j in range(n):
        a=tuple(rng.choices(range(vocab),weights=weights,k=31));i=rng.randrange(8,23)
        r=regime if regime!='mixed' else ('sub','ins','del','rewrite')[j%4]
        if r=='sub':b=a[:i]+(rng.randrange(vocab),)+a[i+1:]
        elif r=='ins':b=a[:i]+tuple(rng.randrange(vocab) for _ in range(3))+a[i:]
        elif r=='del':b=a[:i]+a[i+3:]
        elif r=='repeat':
            a=tuple((j%4,i%4)[k%2] for k in range(31));b=a[:i]+(rng.randrange(vocab),)+a[i+1:]
        else:b=a[:8]+tuple(rng.randrange(vocab) for _ in range(15))+a[23:]
        pairs.append((a,b))
        for w in (a,b):
            k=rng.randrange(len(w));qs.add(w[k:k+rng.randrange(1,L+1)])
    plan=[]
    for l in range(1,L+1):
        candidates=sorted(q for q in qs if len(q)==l);rng.shuffle(candidates);plan.extend(candidates[:8]);plan.extend(tuple(rng.randrange(vocab) for _ in range(l)) for _ in range(2))
    return pairs,list(dict.fromkeys(plan))
def counts(a,q):return sum(a[i:i+len(q)]==q for i in range(len(a)-len(q)+1))
def measure(seed,n,vocab,regime,modes=None):
    pairs,qs=build_pairs(seed,n,vocab,regime);res=[residual(a,b) for a,b in pairs]
    expected=[{i:d for i,(a,b) in enumerate(pairs,1) if (d:=counts(b,q)-counts(a,q))} for q in qs]
    out={}
    with tempfile.TemporaryDirectory() as tmp:
      for mode in (modes or ('fts','suffix','prefix','suffix_short1','suffix_short2','hybrid','block32','block128','block128_short2','blockpage','blockpage_short2','blockpage_hybrid')):
        path=Path(tmp)/(mode+'.sqlite');db=sqlite3.connect(path);db.enable_load_extension(True);db.load_extension(str(HERE/'count.so'));db.execute('PRAGMA page_size=4096')
        t=time.perf_counter();ftsn=0;inv=C.defaultdict(list);short=C.defaultdict(list);selected=0;est=0
        if mode in ('fts','hybrid','blockpage_hybrid'):db.execute("CREATE VIRTUAL TABLE fts USING fts5(body,content='')")
        if mode!='fts':db.execute('CREATE TABLE inv(k BLOB PRIMARY KEY,body BLOB NOT NULL) WITHOUT ROWID')
        if mode.startswith('suffix_short') or mode.endswith('_short2') or mode.startswith('blockpage_cache'):db.execute('CREATE TABLE short(k BLOB PRIMARY KEY,body BLOB NOT NULL) WITHOUT ROWID')
        for cid,((a,b),r) in enumerate(zip(pairs,res),1):
            if mode=='fts' or (mode in ('hybrid','blockpage_hybrid') and 5*len(r)>2*(len(a)+len(b))):
                db.executemany('INSERT INTO fts(rowid,body) VALUES(?,?)',[(2*cid+s,' '.join('t'+str(x) for x in w)) for s,w in ((0,a),(1,b))]);ftsn+=1;continue
            v=prefixes(r) if mode=='prefix' else r
            for k,c in v.items():inv[key(k)].append((cid,c))
            if mode.startswith('suffix_short') or mode.endswith('_short2'):
                for k,c in prefixes(r,1,int(mode[-1])).items():short[key(k)].append((cid,c))
        if mode.startswith('blockpage_cache'):
            potential=C.Counter();net=C.defaultdict(list)
            for cid,r in enumerate(res,1):
                for k,c in r.items():
                    for l in range(1,min(3,len(k))+1):potential[key(k[:l])]+=1
                for k,c in prefixes(r,1,3).items():net[key(k)].append((cid,c))
            opts=[]
            for k,work0 in potential.items():
                rows=net[k];cost=len(k)+len(encode(rows))+12;gain=work0-len(rows)
                if gain>0:opts.append((gain/cost,k,cost,rows))
            budget=out['blockpage']['bytes']*int(mode.removeprefix('blockpage_cache'))/100
            for _,k,cost,rows in sorted(opts,key=lambda x:(-x[0],x[1])):
                if est+cost<=budget:short[k]=rows;est+=cost;selected+=1
        for table,m in (('inv',inv),('short',short)):
            if not m:continue
            if table=='inv' and mode.startswith('block'):
                items=[(k,encode(v,False)) for k,v in sorted(m.items())]
                if mode.startswith('blockpage'):
                    i=0;blocks=[]
                    while i<len(items):
                        lo=i+1;hi=min(i+128,len(items));best=lo;body=block_encode(items[i:lo])
                        while lo<=hi:
                            mid=(lo+hi)//2;candidate=block_encode(items[i:mid])
                            if len(candidate)<=900:best=mid;body=candidate;lo=mid+1
                            else:hi=mid-1
                        blocks.append((items[i][0],body));i=best
                    db.executemany('INSERT INTO inv VALUES(?,?)',blocks)
                else:
                    bs=32 if mode=='block32' else 128;db.executemany('INSERT INTO inv VALUES(?,?)',[(items[i][0],block_encode(items[i:i+bs])) for i in range(0,len(items),bs)])
            else:db.executemany('INSERT INTO '+table+' VALUES(?,?)',[(k,encode(rows)) for k,rows in sorted(m.items())])
        if mode in ('fts','hybrid','blockpage_hybrid'):db.execute("INSERT INTO fts(fts) VALUES('optimize')")
        db.commit();db.execute('VACUUM');size=path.stat().st_size;build=time.perf_counter()-t;db.close();db=sqlite3.connect(path);db.enable_load_extension(True);db.load_extension(str(HERE/'count.so'))
        ts=[];work=C.Counter();bylen=C.defaultdict(list);order=list(range(len(qs)));rng=random.Random(seed+100)
        for _ in range(2):
          rng.shuffle(order)
          for j in order:
            q=qs[j];k=key(q);t=time.perf_counter_ns();got=C.Counter()
            if mode in ('fts','hybrid','blockpage_hybrid'):
                expr='"'+' '.join('t'+str(x) for x in q)+'"'
                for rid,tf in db.execute('SELECT rowid,r186_count(fts) FROM fts WHERE fts MATCH ?',(expr,)):
                    got[rid//2]+=tf if rid&1 else -tf;work['fts_rows']+=1
            if mode!='fts':
                if mode=='prefix':rows=db.execute('SELECT body FROM inv WHERE k=?',(k,))
                elif (mode.startswith('suffix_short') or mode.endswith('_short2')) and len(q)<=int(mode[-1]):rows=db.execute('SELECT body FROM short WHERE k=?',(k,))
                elif mode.startswith('block'):
                    cached=db.execute('SELECT body FROM short WHERE k=?',(k,)).fetchone() if mode.startswith('blockpage_cache') and len(q)<=3 else None
                    def block_rows():
                        for blob in block_query(db,k,k+b'\xff\xff'):
                            work['block_rows']+=1;work['block_bytes']+=len(blob)
                            for kk,body in block_decode(blob):
                                if k<=kk<k+b'\xff\xff':yield (body,)
                    if cached is not None:work['cache_hits']+=1;rows=[cached]
                    else:rows=block_rows()
                else:rows=db.execute('SELECT body FROM inv WHERE k>=? AND k<?',(k,k+b'\xff\xff'))
                for blob, in rows:
                    work['key_rows']+=1;work['payload_bytes']+=len(blob)
                    for cid,c in decode(blob):got[cid]+=c;work['decoded_pairs']+=1
            got={i:c for i,c in got.items() if c};dt=(time.perf_counter_ns()-t)/1000;ts.append(dt);bylen[len(q)].append(dt);assert got==expected[j],(mode,q)
        ts.sort();out[mode]={'bytes':size,'median_us':ts[len(ts)//2],'p95_us':ts[int(.95*(len(ts)-1))],'build_s':build,'fts_pairs':ftsn,'keys':len(inv),'short_keys':len(short),'selected':selected,'cache_estimated_bytes':est,'work':dict(work),'checks':2*len(qs)*n,'bylen_median':{k:sorted(v)[len(v)//2] for k,v in bylen.items()}};db.close()
    return dict(seed=seed,n=n,vocab=vocab,regime=regime,queries=len(qs),policies=out)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=('matrix','cache','scale','smoke'),default='smoke');p.add_argument('--out',type=Path,default=HERE/'results.json');a=p.parse_args()
    if a.suite=='matrix':n=400;seeds=[186,187,188];vocabs=[32,256,2048];regimes=['sub','ins','del','rewrite','mixed','repeat'];modes=None
    elif a.suite=='cache':n=400;seeds=[189,190];vocabs=[32,256,2048];regimes=['sub','mixed','repeat'];modes=['fts','blockpage','blockpage_cache2','blockpage_cache5','blockpage_cache10']
    elif a.suite=='scale':n=2000;seeds=[191,192];vocabs=[256];regimes=['sub','mixed','repeat'];modes=['fts','blockpage','blockpage_cache5','blockpage_cache10']
    else:n=200;seeds=[193];vocabs=[32,256];regimes=['sub','mixed','repeat'];modes=['fts','suffix','prefix','blockpage','blockpage_cache5','blockpage_cache10']
    results=[]
    for seed,v,r in itertools.product(seeds,vocabs,regimes):
        x=measure(seed,n,v,r,modes);results.append(x);print(seed,v,r,{k:(z['bytes'],round(z['median_us'],1),round(z['p95_us'],1)) for k,z in x['policies'].items()},flush=True);a.out.write_text(json.dumps(results,indent=2)+'\n')
