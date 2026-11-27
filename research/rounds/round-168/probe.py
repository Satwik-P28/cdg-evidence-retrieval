"""Independent local synthetic private-row codec probe, R168."""
import sqlite3,tempfile,pathlib,collections,bisect

def run(path,terms,weighted):
    db=sqlite3.connect(path)
    db.executescript("CREATE VIRTUAL TABLE patch_fts USING fts5(body,content=''); CREATE TABLE patch_run(last_ordinal INTEGER PRIMARY KEY,cid INTEGER NOT NULL);")
    ordinal=0;indexed={};exceptions=0
    for cid,cs in terms:
        for w,k in cs.items():
            for _ in range(1 if weighted else abs(k)):
                ordinal+=1;r=2*ordinal+int(k>0);indexed[r]=w
                db.execute('INSERT INTO patch_fts(rowid,body) VALUES(?,?)',(r,' '.join(w)))
                if weighted and abs(k)>1:
                    if not exceptions:db.execute('CREATE TABLE patch_coeff(rid INTEGER PRIMARY KEY,magnitude INTEGER NOT NULL CHECK(magnitude>1))')
                    db.execute('INSERT INTO patch_coeff VALUES(?,?)',(r,abs(k)));exceptions+=1
        db.execute('INSERT INTO patch_run VALUES(?,?)',(ordinal,cid))
    db.execute("INSERT INTO patch_fts(patch_fts) VALUES('optimize')");db.commit();db.execute('VACUUM');db.close()
    db=sqlite3.connect(path);rows=list(db.execute('SELECT last_ordinal,cid FROM patch_run ORDER BY last_ordinal'))
    ends=[r[0] for r in rows];cids=[r[1] for r in rows];ex=dict(db.execute('SELECT rid,magnitude FROM patch_coeff')) if exceptions else {}
    def resolve(r):return cids[bisect.bisect_left(ends,r//2)],ex.get(r,1)*(1 if r&1 else -1)
    got=collections.defaultdict(collections.Counter)
    for r, in db.execute('SELECT rowid FROM patch_fts'):
        cid,k=resolve(r);got[cid][indexed[r]]+=k
    assert got=={cid:collections.Counter(cs) for cid,cs in terms}
    checks=0
    for p in [('old',),('new',),('left1','left2'),('right1','right2'),('group3',),('absent',)]:
        def tf(w):return sum(w[i:i+len(p)]==p for i in range(len(w)-len(p)+1))
        hits={r[0] for r in db.execute('SELECT rowid FROM patch_fts WHERE patch_fts MATCH ?',('"'+ ' '.join(p)+'"',))}
        assert hits=={r for r,w in indexed.items() if tf(w)}
        for cutoff in (0,250,500,1000):
            got=collections.Counter()
            for r in hits:
                cid,k=resolve(r)
                if cid<=cutoff:got[cid]+=k*tf(indexed[r])
            want=collections.Counter({cid:sum(k*tf(w) for w,k in cs.items()) for cid,cs in terms if cid<=cutoff})
            assert got==want;checks+=1
    db.close();return path.stat().st_size,ordinal,exceptions,checks

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as d:
        for mag in (1,2,4,16):
            terms=[]
            for cid in range(1,1001):
                prefix=[f'group{cid}']+[f'left{i}' for i in range(6)];suffix=[f'right{i}' for i in range(7)]
                terms.append((cid,{tuple(prefix+['old']+suffix):-mag,tuple(prefix+['new']+suffix):mag}))
            print(mag,[run(pathlib.Path(d)/f'{mag}-{w}.db',terms,w) for w in (False,True)],flush=True)
