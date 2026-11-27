"""R166 local frequency and physical patch-subsystem falsification probe."""
from collections import Counter
from itertools import product
import random
import sqlite3
import tempfile
from pathlib import Path
from signed_phrase import windows,signed_terms,L

def ngrams(a,m):
    return Counter(tuple(a[i:i+m]) for i in range(len(a)-m+1))

def check(a,b):
    for m in range(1,L+1):
        expected=ngrams(b,m);got=ngrams(a,m)
        for w,coef in signed_terms(windows(a,b,True,m)).items():
            for p,n in ngrams(w,m).items():got[p]+=coef*n
        assert got==expected,(a,b,m)
    return L

def main():
    ss=[list(p) for n in range(7) for p in product(range(2),repeat=n)]
    checks=sum(check(a,b) for a in ss for b in ss)
    rng=random.Random(166)
    for _ in range(1000):
        a=[rng.randrange(7) for _ in range(rng.randrange(100))];b=a[:]
        for _ in range(10):
            i=rng.randrange(len(b)+1)
            b[i:i+rng.randrange(5)]=[rng.randrange(7) for _ in range(rng.randrange(5))]
        checks+=check(a,b)
    print("pair_length_checks",checks,"pairs",len(ss)**2+1000)
    with tempfile.TemporaryDirectory() as temp:
        for group_count in (1,10,100,1000,5000):
            pairs=[]
            for cid in range(1,5001):
                group=cid%group_count
                prefix=[f"group{group}"]+[f"left{i}" for i in range(6)]
                suffix=[f"right{i}" for i in range(7)]
                pairs.append((prefix+["old"]+suffix,prefix+["new"]+suffix))
            sizes=[]
            for mode in ("sparse","dense","quotient"):
                path=Path(temp)/f"{group_count}-{mode}.db";db=sqlite3.connect(path)
                db.execute("CREATE VIRTUAL TABLE patch_fts USING fts5(body,content='')")
                if mode=="quotient":
                    db.execute("CREATE TABLE patch_use(wid INTEGER NOT NULL,cid INTEGER NOT NULL,coeff INTEGER NOT NULL CHECK(coeff<>0),PRIMARY KEY(wid,cid)) WITHOUT ROWID")
                ids={}
                for cid,(old,new) in enumerate(pairs,1):
                    if mode!="quotient":
                        for i,w in enumerate((old,new)):
                            rid=((cid<<16) if mode=="sparse" else (cid<<1))|i
                            db.execute("INSERT INTO patch_fts(rowid,body) VALUES(?,?)",(rid," ".join(w)))
                    else:
                        for w,coeff in signed_terms([(old,new)]).items():
                            if w not in ids:
                                ids[w]=len(ids)+1
                                db.execute("INSERT INTO patch_fts(rowid,body) VALUES(?,?)",(ids[w]," ".join(w)))
                            db.execute("INSERT INTO patch_use VALUES(?,?,?)",(ids[w],cid,coeff))
                db.execute("INSERT INTO patch_fts(patch_fts) VALUES('optimize')")
                db.commit();db.execute("VACUUM")
                assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
                db.close();sizes.append(path.stat().st_size)
            print("groups",group_count,"sparse_bytes",sizes[0],"dense_bytes",sizes[1],
                "quotient_bytes",sizes[2],"saving_vs_dense_pct",round(100*(1-sizes[2]/sizes[1]),3))

if __name__=="__main__":main()
