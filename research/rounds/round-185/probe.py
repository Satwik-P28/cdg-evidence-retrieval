"""R185: exact signed suffix basis vs window pair and native FTS patch controls.
Synthetic patch subsystem only; source, anchors and revision mappings excluded equally.
"""
import collections, itertools, json, random, sqlite3, struct, tempfile, time, zlib
from pathlib import Path
from bisect import bisect_left
L=8

def count(w,q):
    return sum(w[i:i+len(q)]==q for i in range(len(w)-len(q)+1))

def residual(a,b):
    c=collections.Counter(b[i:i+L] for i in range(len(b)))
    c.subtract(a[i:i+L] for i in range(len(a)))
    return {k:v for k,v in c.items() if v}

def common(a,b):
    p=0
    while p<min(len(a),len(b)) and a[p]==b[p]:p+=1
    s=0
    while s<min(len(a),len(b))-p and a[-s-1]==b[-s-1]:s+=1
    return p,s

def affected(w,p,s,q):
    return sum(w[i:i+len(q)]==q for i in range(max(0,p-len(q)+1),min(len(w)-len(q)+1,len(w)-s)))

def pack_tokens(ts):return struct.pack('<'+'H'*len(ts),*ts)
def unpack_tokens(raw):return tuple(x[0] for x in struct.iter_unpack('<H',raw))
def packed_pair(a,b,mode):
    if mode=='joint':return zlib.compress(struct.pack('<H',len(a))+pack_tokens(a+b),6)
    p,s=common(a,b);middle=b[p:len(b)-s]
    return zlib.compress(struct.pack('<HHH',len(a),p,s)+pack_tokens(a+middle),6)

def decode_pair(blob,mode):
    raw=zlib.decompress(blob);n=struct.unpack_from('<H',raw)[0]
    if mode=='joint':ts=unpack_tokens(raw[2:]);return ts[:n],ts[n:]
    p,s=struct.unpack_from('<HH',raw,2);ts=unpack_tokens(raw[6:]);a=ts[:n];return a,a[:p]+ts[n:]+a[n-s:]

def pack_basis(c):
    # Lexically ordered residual suffixes, common-prefix front coding,
    # signed 16-bit coefficient. Full metadata included in each payload.
    prev=();buf=bytearray()
    for k,v in sorted(c.items()):
        p,_=common(prev,k);tail=k[p:];buf.extend(struct.pack('<BBh',p,len(tail),v));buf.extend(pack_tokens(tail));prev=k
    return zlib.compress(buf,6)

def decode_basis(blob):
    raw=zlib.decompress(blob);i=0;prev=();keys=[];sums=[0]
    while i<len(raw):
        p,n,c=struct.unpack_from('<BBh',raw,i);i+=4;key=prev[:p]+unpack_tokens(raw[i:i+2*n]);i+=2*n
        assert p<=len(prev) and 0<len(key)<=L and c and (not keys or key>prev)
        keys.append(key);sums.append(sums[-1]+c);prev=key
    return keys,sums

def basis_count(decoded,q):
    keys,sums=decoded
    # All keys starting with q lie in [q, q+(65536,)); tokens <65536.
    return sums[bisect_left(keys,q+(65536,))]-sums[bisect_left(keys,q)]

def verify():
    seqs=[tuple(w) for n in range(6) for w in itertools.product(range(2),repeat=n)]
    qs=[tuple(w) for n in range(1,5) for w in itertools.product(range(2),repeat=n)]
    n=0
    for a in seqs:
        for b in seqs:
            c=residual(a,b);d=decode_basis(pack_basis(c));p,s=common(a,b)
            for q in qs:
                want=count(b,q)-count(a,q)
                assert basis_count(d,q)==want==affected(b,p,s,q)-affected(a,p,s,q);n+=1
    return n

def experiment(regime):
    rng=random.Random(185);pairs=[];qs=set();raw=before=after=0
    for _ in range(1800):
        a=tuple(rng.choices(range(256),weights=[32 if i<8 else 1 for i in range(256)],k=31));i=15
        if regime=='substitution':b=a[:i]+(rng.randrange(256),)+a[i+1:]
        elif regime=='insertion':b=a[:i]+tuple(rng.randrange(256) for _ in range(3))+a[i:]
        elif regime=='deletion':b=a[:i]+a[i+3:]
        else:b=a[:8]+tuple(rng.randrange(256) for _ in range(15))+a[23:]
        pairs.append((a,b));before+=len(a)+len(b);after+=len(residual(a,b));raw+=len(a)+len(b)
        k=rng.randrange(len(a)-7);qs.add(a[k:k+rng.randrange(1,9)])
        k=rng.randrange(len(b)-7);qs.add(b[k:k+rng.randrange(1,9)])
    qs=sorted(qs);rng.shuffle(qs);qs=qs[:120]
    want=[{i:d for i,(a,b) in enumerate(pairs,1) if (d:=count(b,q)-count(a,q))} for q in qs]
    results={}
    with tempfile.TemporaryDirectory() as temp:
        for mode in ('fts','joint','factored','suffix_basis'):
            path=Path(temp)/(mode+'.db');db=sqlite3.connect(path);db.execute('PRAGMA page_size=4096')
            if mode=='fts':
                db.execute("CREATE VIRTUAL TABLE patches USING fts5(body,content='')")
                db.executemany('INSERT INTO patches(rowid,body) VALUES(?,?)',[(2*i+sgn,' '.join('t'+str(t) for t in w)) for i,(a,b) in enumerate(pairs,1) for sgn,w in ((0,a),(1,b))])
                db.execute("INSERT INTO patches(patches) VALUES('optimize')")
                # Exact TF from native FTS5 vocab offsets; query FTS MATCH then compute counts from positions.
                # This is Python position joining, not the CDG native count extension.
                db.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,patches,'instance')")
            else:
                db.execute('CREATE TABLE patches(cid INTEGER PRIMARY KEY,body BLOB NOT NULL)')
                db.executemany('INSERT INTO patches VALUES(?,?)',[(i,pack_basis(residual(a,b)) if mode=='suffix_basis' else packed_pair(a,b,mode)) for i,(a,b) in enumerate(pairs,1)])
            db.commit();db.execute('VACUUM');size=path.stat().st_size;db.close();db=sqlite3.connect(path)
            # Report persistent bytes; resident decode setup separately. Query evaluation uses resident structures in all arms.
            t=time.perf_counter_ns()
            if mode=='fts':
                db.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,patches,'instance')")
                postings=collections.defaultdict(lambda:collections.defaultdict(set))
                for term,doc,off in db.execute('SELECT term,doc,offset FROM temp.vocab'):postings[int(term[1:])][doc].add(off)
            elif mode=='suffix_basis':
                data=[(i,decode_basis(blob)) for i,blob in db.execute('SELECT cid,body FROM patches')]
            else:
                data=[]
                for i,blob in db.execute('SELECT cid,body FROM patches'):
                    a,b=decode_pair(blob,mode);assert (a,b)==pairs[i-1];p,s=common(a,b);data.append((i,a,b,p,s))
            setup=(time.perf_counter_ns()-t)/1e6;times=[];checks=0
            for q,expected in zip(qs,want):
                t=time.perf_counter_ns();got=collections.Counter()
                if mode=='fts':
                    cand=set.intersection(*(set(postings[x]) for x in set(q)))
                    for rid in cand:
                        starts=postings[q[0]][rid].copy()
                        for j,x in enumerate(q[1:],1):starts.intersection_update(p-j for p in postings[x][rid])
                        got[rid//2]+=len(starts)*(1 if rid&1 else -1)
                elif mode=='suffix_basis':
                    for i,d in data:got[i]=basis_count(d,q)
                else:
                    for i,a,b,p,s in data:got[i]=affected(b,p,s,q)-affected(a,p,s,q)
                got={i:d for i,d in got.items() if d};times.append((time.perf_counter_ns()-t)/1000)
                assert got==expected,(mode,q);checks+=len(pairs)
            times.sort();results[mode]=dict(bytes=size,setup_ms=setup,median_us=times[len(times)//2],p95_us=times[int(.95*(len(times)-1))],checks=checks);db.close()
    return dict(regime=regime,pairs=len(pairs),queries=len(qs),suffixes_before=before,suffixes_after=after,policies=results)
if __name__=='__main__':
    out=dict(exhaustive=verify(),sqlite=sqlite3.sqlite_version,regimes=[experiment(r) for r in ('substitution','insertion','deletion','rewrite')]);print(json.dumps(out,indent=2));Path(__file__).with_name('results.json').write_text(json.dumps(out,indent=2)+'\n')
