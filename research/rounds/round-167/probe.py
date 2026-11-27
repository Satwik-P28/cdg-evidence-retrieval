"""R167 synthetic patch-subsystem probe. Requires R167 dependencies."""
import collections
import pathlib
import random
import sqlite3
import sys
import tempfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/"experiments"/"round-165"))
from signed_phrase import write_runs,PatchRuns

def run(path,terms,mode):
    db=sqlite3.connect(path)
    db.execute("CREATE VIRTUAL TABLE patch_fts USING fts5(body,content='')")
    db.execute("CREATE TABLE patch_use(wid INTEGER NOT NULL,cid INTEGER NOT NULL,coeff INTEGER NOT NULL CHECK(coeff<>0),PRIMARY KEY(wid,cid)) WITHOUT ROWID")
    materialized={}
    def insert(table,rid,w):
        assert rid not in materialized
        materialized[rid]=tuple(w)
        db.execute(f"INSERT INTO {table}(rowid,body) VALUES(?,?)",(rid," ".join(w)))
    stats=collections.Counter()
    if mode in ("runs","adaptive"):
        db.execute("CREATE TABLE patch_run(last_ordinal INTEGER PRIMARY KEY,cid INTEGER NOT NULL)")
        write_runs(db,terms,insert,stats,mode=="adaptive")
    else:
        ids={}
        for cid,cs in terms:
            for w,coeff in cs.items():
                if w not in ids:
                    ids[w]=len(ids)+1;insert("patch_fts",ids[w],w)
                db.execute("INSERT INTO patch_use VALUES(?,?,?)",(ids[w],cid,coeff))
    db.execute("INSERT INTO patch_fts(patch_fts) VALUES('optimize')")
    db.commit();db.execute("VACUUM")
    shared=collections.defaultdict(list)
    for wid,cid,coef in db.execute("SELECT wid,cid,coeff FROM patch_use"):
        shared[wid].append((cid,coef))
    mapping=PatchRuns(list(db.execute("SELECT last_ordinal,cid FROM patch_run ORDER BY last_ordinal")),shared) if mode in ("runs","adaptive") else shared
    recovered=collections.defaultdict(collections.Counter)
    for (rid,) in db.execute("SELECT rowid FROM patch_fts"):
        for cid,coef in mapping.get(rid,()):recovered[cid][materialized[rid]]+=coef
    assert recovered=={cid:collections.Counter(cs) for cid,cs in terms if cs}
    checks=0
    for p in [("old",),("new",),("left1","left2"),("right1","right2"),("group0",),("group3",)]:
        def tf(w):return sum(w[i:i+len(p)]==p for i in range(len(w)-len(p)+1))
        hits={r[0] for r in db.execute("SELECT rowid FROM patch_fts WHERE patch_fts MATCH ?",('"'+ ' '.join(p)+'"',))}
        assert hits=={r for r,w in materialized.items() if tf(w)}
        for cutoff in (1000,2500,5000):
            got=collections.Counter();expected=collections.Counter()
            for rid in hits:
                for cid,coef in mapping.get(rid,()):
                    if cid<=cutoff:got[cid]+=coef*tf(materialized[rid])
            for cid,cs in terms:
                if cid<=cutoff:expected[cid]=sum(coef*tf(w) for w,coef in cs.items())
            assert got==expected;checks+=1
    db.close()
    return path.stat().st_size,checks,dict(stats)

def main():
    with tempfile.TemporaryDirectory() as d:
        for group_count in (1,10,100,1000,5000):
            terms=[]
            for cid in range(1,5001):
                group=cid%group_count
                prefix=[f"group{group}"]+[f"left{i}" for i in range(6)]
                suffix=[f"right{i}" for i in range(7)]
                terms.append((cid,{tuple(prefix+["old"]+suffix):-1,tuple(prefix+["new"]+suffix):1}))
            print(group_count,[(mode,run(pathlib.Path(d)/f"{group_count}-{mode}.db",terms,mode)) for mode in ("quotient","runs","adaptive")])
        rng=random.Random(167);terms=[]
        for cid in range(1,5001):
            cs=collections.Counter()
            for _ in range(rng.randrange(1,7)):
                w=tuple(["group"+str(rng.randrange(20)),"left1","left2","old","right1","right2"]+[str(rng.randrange(3)) for _ in range(9)])
                cs[w]+=rng.choice((-3,-2,-1,1,2,3))
            terms.append((cid,{w:c for w,c in cs.items() if c}))
        print("mixed_coeff",[(mode,run(pathlib.Path(d)/f"mixed-{mode}.db",terms,mode)) for mode in ("quotient","runs","adaptive")])

if __name__=="__main__":main()
