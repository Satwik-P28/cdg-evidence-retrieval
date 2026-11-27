"""Independent synthetic R179 probe: Bloom adjacency vs exact source verification."""
import collections, hashlib, itertools, json, pathlib, random, sqlite3, tempfile, time, zlib

def bits(a,b,m):
    x=int.from_bytes(hashlib.blake2b(f'{a} {b}'.encode(),digest_size=16).digest(),'little')
    h1=x&((1<<64)-1);h2=(x>>64)|1
    return sum(1<<((h1+i*h2)%m) for i in range(3)) if len({(h1+i*h2)%m for i in range(3)})==3 else __import__('functools').reduce(int.__or__,(1<<((h1+i*h2)%m) for i in range(3)),0)

def run(seed,style):
    rng=random.Random(seed); docs={};heads={};snapshots=[];freq=collections.defaultdict(set);queries=set()
    for v in range(5):
        for a in range(160):
            cid=160*v+a+1
            if v:
                seq=docs[heads[a]][:]
                for j in rng.sample(range(len(seq)),12):seq[j]=rng.choice([f'c{i}' for i in range(24)]+[f'r{a%16}_{i}' for i in range(32)])
            elif style=='mixed':seq=[f'c{rng.randrange(24)}' if rng.random()<.65 else f'r{a%16}_{rng.randrange(32)}' for _ in range(160)]
            else:seq=[f'c{rng.randrange(24)}' for _ in range(160)]
            # ASCII letter/digit terms only, matching unicode61 exactly.
            seq=[s.replace('_','x') for s in seq];docs[cid]=seq;heads[a]=cid
            for t in set(seq):freq[t].add(cid)
        snapshots.append(set(heads.values()))
    for _ in range(120):
        seq=rng.choice(list(docs.values()));n=rng.randrange(2,7);i=rng.randrange(len(seq)-n+1);queries.add(tuple(seq[i:i+n]))
    for _ in range(120):queries.add(tuple(f'c{rng.randrange(24)}' for _ in range(rng.randrange(2,7))))
    qs=sorted(queries);plan=[(q,active) for q in qs for active in snapshots]
    # Native FTS oracle, plus exact candidate and full source frame independent of filter.
    oracle=sqlite3.connect(':memory:');oracle.execute('CREATE VIRTUAL TABLE docs USING fts5(body)');oracle.executemany('INSERT INTO docs(rowid,body) VALUES(?,?)',[(cid,' '.join(s)) for cid,s in docs.items()])
    frames={cid:zlib.compress(' '.join(s).encode(),6) for cid,s in docs.items()}
    records=[]
    for q,active in plan:
        native={cid for cid, in oracle.execute('SELECT rowid FROM docs WHERE docs MATCH ?',('"'+' '.join(q)+'"',)) if cid in active}
        candidates=set.intersection(*(freq[t] for t in set(q)))&active
        assert native<=candidates;records.append((q,candidates,native))
    results={}
    with tempfile.TemporaryDirectory() as td:
        for m in (0,256,512,1024,2048):
            db=sqlite3.connect(pathlib.Path(td)/f'{m}.db');db.execute('CREATE TABLE source(cid INTEGER PRIMARY KEY,body BLOB NOT NULL)');db.executemany('INSERT INTO source VALUES(?,?)',frames.items())
            masks={}
            if m:
                db.execute('CREATE TABLE filters(cid INTEGER PRIMARY KEY,body BLOB NOT NULL,checkval BLOB NOT NULL)')
                for cid,seq in docs.items():
                    mask=0
                    for a,b in set(zip(seq,seq[1:])):mask|=bits(a,b,m)
                    blob=mask.to_bytes(m//8,'little');digest=hashlib.blake2b(blob,digest_size=8).digest();db.execute('INSERT INTO filters VALUES(?,?,?)',(cid,blob,digest))
            db.commit();db.execute('VACUUM');db.close();path=pathlib.Path(td)/f'{m}.db';size=path.stat().st_size;db=sqlite3.connect(path)
            if m:
                for cid,blob,check in db.execute('SELECT cid,body,checkval FROM filters'):
                    if hashlib.blake2b(blob,digest_size=8).digest()==check and len(blob)==m//8:masks[cid]=int.from_bytes(blob,'little')
                assert len(masks)==len(docs)
            counts=collections.Counter();ts=[]
            for q,candidates,native in records:
                start=time.perf_counter_ns();need=0
                if m:
                    for a,b in zip(q,q[1:]):need|=bits(a,b,m)
                passed={cid for cid in candidates if cid not in masks or masks[cid]&need==need};assert native<=passed
                got={};needle=' '.join(q);p=tuple(q)
                for cid in passed:
                    raw=zlib.decompress(frames[cid]).decode();seq=raw.split();tf=sum(tuple(seq[i:i+len(p)])==p for i in range(len(seq)-len(p)+1))
                    if tf:got[cid]=tf
                assert set(got)==native
                # Independent direct token-string count, allowing overlap.
                for cid in native:
                    hay=' '+' '.join(docs[cid])+' ';pattern=' '+needle+' ';n=0;pos=0
                    while (j:=hay.find(pattern,pos))>=0:n+=1;pos=j+1
                    assert got[cid]==n
                ts.append((time.perf_counter_ns()-start)/1000);counts.update(candidates=len(candidates),source_reads=len(passed),true_hits=len(native),checks=1,activated_bytes=sum(len(frames[cid]) for cid in passed))
            ts.sort();results[str(m)]={**counts,'archive_bytes':size,'p95_us':ts[int(.95*(len(ts)-1))],'resident_filter_bytes':len(masks)*(m//8)};db.close()
    oracle.close();return {'style':style,'docs':len(docs),'queries':len(qs),'cutoffs':len(snapshots),'policies':results}
if __name__=='__main__':
    out=[run(179,s) for s in ('mixed','common')];print(json.dumps(out,indent=2));pathlib.Path(__file__).with_name('results.json').write_text(json.dumps(out,indent=2)+'\n')
