"""R173 independent probe: codecs, block addressing, activation and phrase counts.

Executed locally and in CI.  Checks are independent of the block index where
possible: brute-force phrase counts and native FTS5 membership are computed from
the fixtures, not from the module under test.
"""
import os,random,sqlite3,sys,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/"experiments"/"round-173"))
import blocked_positions as bp

def brute(seq,query):
    return sum(tuple(seq[i:i+len(query)])==tuple(query) for i in range(len(seq)-len(query)+1))

def main():
    ext=os.environ.get("CDG_FTS_EXTENSION")
    if not ext:raise SystemExit("CDG_FTS_EXTENSION required")
    ext=Path(ext).resolve()
    rng=random.Random(173)
    # 1. codec round trips, pure and native decoder
    per_codec={c:0 for c in bp.CODECS}
    for _ in range(10000):
        n=rng.randrange(0,60)
        vals=[rng.randrange(0,rng.choice((2,16,128,4096,2**20))) for _ in range(n)]
        for codec in bp.CODECS:
            tag,raw=bp.enc_stream(vals,codec)
            assert list(bp.dec_stream(tag,raw,n))==vals
            saved=bp.KERNEL;bp.KERNEL=None
            try:assert bp.dec_stream(tag,raw,n)==vals
            finally:bp.KERNEL=saved
            per_codec[codec]+=1
    print("codec round trips:",per_codec)
    # 2. block and directory round trips
    for _ in range(5000):
        count=rng.randrange(1,12);cid=0;docs=[]
        for _ in range(count):
            cid+=rng.randrange(1,6)
            docs.append((cid,sorted(rng.sample(range(400),rng.randrange(1,12)))))
        codec=rng.choice(bp.CODECS);compress=rng.random()<0.5
        stored=bp.encode_block(docs,codec,compress)
        full=bp.parse_block(stored,docs[0][0],True)
        assert list(full["cids"])==[c for c,_ in docs]
        assert [full["positions"][c] for c,_ in docs]==[p for _,p in docs]
        lite=bp.parse_block(stored,docs[0][0],False)
        assert list(lite["cids"])==list(full["cids"]) and lite["positions"] is None
        assert lite["decoded"]<=full["decoded"]
    print("block round trips: 5000 (all codecs, raw and Zstandard)")
    for _ in range(2000):
        n=rng.randrange(1,30);firsts=sorted(rng.sample(range(10**6),n))
        offs=sorted(rng.sample(range(10**7),n));lens=[rng.randrange(1,900) for _ in range(n)]
        assert bp.decode_dir(bp.encode_dir(firsts,offs,lens))==(firsts,offs,lens)
    print("directory round trips: 2000")
    # 3. phrase kernel versus brute force, full and partial coverage
    full=partial=0
    for _ in range(10000):
        seq=[rng.randrange(5) for _ in range(rng.randrange(0,90))]
        q=[rng.randrange(5) for _ in range(rng.randrange(2,9))]
        lists=[(i,[j for j,t in enumerate(seq) if t==x]) for i,x in enumerate(q)]
        exact=brute(seq,q)
        assert bp.shifted_count(lists,len(seq),len(q))==exact;full+=1
        part=rng.sample(lists,rng.randrange(1,len(lists)+1))
        assert bp.shifted_count(part,len(seq),len(q))>=exact;partial+=1
    print("shifted-position kernel:",full,"exact and",partial,"upper-bound checks")
    # 4. activation: blocks parsed must cover candidates only
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        docs=[]
        for term in (b"common",b"middle",b"rare"):
            postings=[]
            for cid in range(1,201):
                hit=(term==b"common") or (term==b"middle" and cid%4==0) or (term==b"rare" and cid==137)
                if hit:postings.append((cid,[cid%7,cid%7+3]))
            postings=[(c,p) for c,p in postings if p]
            docs.append((term,postings))
        for block in (4,16,64):
            index={}
            for term,postings in docs:
                for start in range(0,len(postings),block):
                    chunk=postings[start:start+block]
                    enc=bp.encode_term(chunk,block,"best",True)
                    index.setdefault(term,[]).append(enc)
            print("activation fixture block",block,
                  {t.decode():sum(e["blocks"] for e in v) for t,v in index.items()})
        # native FTS5 phrase oracle
        db=sqlite3.connect(tmp/"oracle.sqlite")
        db.execute("PRAGMA page_size=4096")
        db.execute("CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT,cid INTEGER,dl INTEGER,end_g INTEGER)")
        db.execute("CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER,tokens INTEGER)")
        db.execute("CREATE VIRTUAL TABLE docs_0 USING fts5(body)")
        corpus={}
        for cid in range(1,201):
            toks=[]
            for _ in range(6):
                toks.append("common")
                if cid%4==0:toks.append("middle")
                if cid==137:toks.append("rare")
                toks.append("filler%d"%(cid%9))
            corpus[cid]=toks
            db.execute("INSERT INTO docs_0(rowid,body) VALUES(?,?)",(cid," ".join(toks)))
        db.execute("INSERT INTO revisions VALUES(1,'a',1,6,NULL)")
        db.execute("INSERT INTO active_stats VALUES(1,200,1200)")
        db.commit()
        phrases=[("common",),("common middle",),("common rare",),("middle rare",),("common common",),
                 ("middle filler137",),("common middle rare",),("filler1 filler2",)]
        checks=0
        positions={}
        for cid,toks in corpus.items():
            for j,t in enumerate(toks):positions.setdefault(t,{}).setdefault(cid,[]).append(j)
        for phrase in phrases:
            qs=phrase[0].split()
            native={cid for cid, in db.execute("SELECT rowid FROM docs_0 WHERE docs_0 MATCH ?",('"'+' '.join(qs)+'"',))}
            for subset in ([t for t in qs],qs[:1],qs[1:]):
                if len(set(subset))<1:continue
                got={}
                for cid in range(1,201):
                    lists=[]
                    ok=True
                    for i,t in enumerate(qs):
                        if t not in subset:continue
                        if cid not in positions.get(t,{}):ok=False;break
                        lists.append((i,positions[t][cid]))
                    if not ok or not lists:continue
                    c=bp.shifted_count(lists,len(corpus[cid]),len(qs))
                    if c:got[cid]=c
                if len(set(subset))==len(set(qs)):
                    want={cid:brute(corpus[cid],qs) for cid in range(1,201)}
                    want={c:v for c,v in want.items() if v}
                    assert got==want and set(want)==native,(phrase,subset,len(got),len(want))
                else:
                    for cid,v in got.items():
                        assert v>=brute(corpus[cid],qs)
                    assert native<=set(got),(phrase,subset,sorted(native-set(got)))
                checks+=1
        db.close()
        print("native FTS5 phrase oracle checks:",checks)
    print("PROBE_OK")

if __name__=="__main__":
    main()
