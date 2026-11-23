"""R121: exact temporal TF coalescing, matched term-only retrieval.
Offline index-only study. Not a reproduction of TimIR or TTIX.
"""
import argparse, collections, json, random, sqlite3, statistics, struct, sys, tempfile, time
from pathlib import Path
import zstandard as zstd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-120"))
from active_rank import active_oracle,native,score
from rank_replay import expression,quote,verify
from native_compare import extension
from versioned_evidence import order,load,select,SALT,PIN,sha

POLICIES=("rel_version","rel_coalesced","packed_version","packed_coalesced","native_history")
METHODS=POLICIES+("native_active",)
RECORD=struct.Struct("<IIII")  # article ID, inclusive start, exclusive end, tf
C=zstd.ZstdCompressor(level=6)
D=zstd.ZstdDecompressor()

def extract(events):
    ref=sqlite3.connect(":memory:")
    ref.execute("CREATE VIRTUAL TABLE docs USING fts5(body,content='')")
    ref.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)",
        ((g,raw.decode("utf8")) for g,(_,_,raw) in enumerate(events,1)))
    ref.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(docs,'instance')")
    freqs=[{} for _ in range(len(events)+1)]
    for t,g,tf in ref.execute("SELECT term,doc,count(*) FROM vocab GROUP BY term,doc"):
        freqs[g][t]=tf
    ref.close()
    return freqs

def metadata(events,freqs):
    ids={a:i for i,a in enumerate(sorted({a for a,_,_ in events}),1)}
    end=len(events)+1;last={}
    rows=[]
    for g,(a,i,raw) in enumerate(events,1):
        aid=ids[a]
        if aid in last:
            old=last[aid]
            if rows[old-1][2]+1!=i:raise ValueError("noncontiguous revision")
            rows[old-1][3]=g
        elif i!=0:raise ValueError("missing initial revision")
        last[aid]=g
        rows.append([g,aid,i,end,sum(freqs[g].values()),sha(raw)])
    return rows,ids

def postings(rows,freqs,coalesce):
    """One interval per nonzero TF run, split at every frequency change,
    including disappearance and later reappearance. No term positions."""
    out=collections.defaultdict(list)
    previous={};opened={}
    for g,aid,i,end,dl,digest in rows:
        curr=freqs[g]
        if not coalesce:
            for t,tf in curr.items():out[t].append((aid,g,end,tf))
            continue
        old=previous.get(aid,{})
        for t in old.keys()|curr.keys():
            before,after=old.get(t,0),curr.get(t,0)
            if before==after:continue
            key=(aid,t)
            if before:
                start,tf=opened.pop(key)
                out[t].append((aid,start,g,tf))
            if after:opened[key]=(g,after)
        previous[aid]=curr
    for (aid,t),(start,tf) in opened.items():
        out[t].append((aid,start,len(rows)+1,tf))
    return out

def pack(records):
    raw=b"".join(RECORD.pack(*r) for r in records)
    return C.compress(raw)

def unpack(payload,n):
    if not 0<=n<=10000000:raise ValueError("unsafe record count")
    raw=D.decompress(payload,max_output_size=n*RECORD.size+1)
    if len(raw)!=n*RECORD.size:raise ValueError("record length mismatch")
    for a,s,e,tf in RECORD.iter_unpack(raw):
        if not a or not s<e or not tf:raise ValueError("invalid posting interval")
        yield a,s,e,tf

def setup(path,rows,ids):
    db=sqlite3.connect(path)
    db.execute("PRAGMA page_size=4096")
    db.executescript("""
    CREATE TABLE article(aid INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
    CREATE TABLE versions(g INTEGER PRIMARY KEY,aid INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,end_g INTEGER NOT NULL,dl INTEGER NOT NULL,
        digest BLOB NOT NULL);
    """)
    db.executemany("INSERT INTO article VALUES(?,?)",((i,a) for a,i in ids.items()))
    db.executemany("INSERT INTO versions VALUES(?,?,?,?,?,?)",rows)
    db.commit()
    return db

def build(path,rows,ids,events,records,policy,ext):
    start=time.perf_counter()
    db=setup(path,rows,ids)
    if policy=="native_history":
        extension(db,ext)
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(body,content='')")
        db.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)",
            ((g,raw.decode("utf8")) for g,(_,_,raw) in enumerate(events,1)))
        db.execute("INSERT INTO docs(docs) VALUES('optimize')")
        entries=None
    else:
        db.execute("CREATE TABLE term(tid INTEGER PRIMARY KEY,word TEXT UNIQUE NOT NULL)")
        terms=sorted(records)
        db.executemany("INSERT INTO term VALUES(?,?)",enumerate(terms,1))
        entries=sum(map(len,records.values()))
        if policy=="rel_version":
            db.execute("CREATE TABLE postings(tid INTEGER,g INTEGER,tf INTEGER NOT NULL,PRIMARY KEY(tid,g)) WITHOUT ROWID")
            db.executemany("INSERT INTO postings VALUES(?,?,?)",
                ((tid,s,tf) for tid,t in enumerate(terms,1) for a,s,e,tf in sorted(records[t],key=lambda x:x[1])))
        elif policy=="rel_coalesced":
            db.execute("CREATE TABLE postings(tid INTEGER,aid INTEGER,start_g INTEGER,end_g INTEGER NOT NULL,tf INTEGER NOT NULL,PRIMARY KEY(tid,start_g,aid)) WITHOUT ROWID")
            db.executemany("INSERT INTO postings VALUES(?,?,?,?,?)",
                ((tid,a,s,e,tf) for tid,t in enumerate(terms,1) for a,s,e,tf in sorted(records[t],key=lambda x:(x[1],x[0]))))
        else:
            db.execute("CREATE TABLE packed(tid INTEGER PRIMARY KEY,n INTEGER NOT NULL,payload BLOB NOT NULL)")
            db.executemany("INSERT INTO packed VALUES(?,?,?)",
                ((tid,len(records[t]),pack(sorted(records[t],key=lambda x:(x[1],x[0])))) for tid,t in enumerate(terms,1)))
    db.commit();db.execute("VACUUM")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("SQLite integrity")
    return db,dict(sqlite_bytes=path.stat().st_size,logical_postings=entries,build_seconds_exploratory=time.perf_counter()-start)

def active(rows,c):
    return {a:g for g,a,i,e,dl,d in rows if g<=c<e}

def read_all_term(db,t,policy):
    if policy=="rel_version":
        return db.execute("""SELECT v.aid,v.g,v.end_g,p.tf FROM term t JOIN postings p ON p.tid=t.tid
            JOIN versions v ON v.g=p.g WHERE t.word=?""",(t,)).fetchall()
    if policy=="rel_coalesced":
        return db.execute("SELECT p.aid,p.start_g,p.end_g,p.tf FROM term t JOIN postings p ON p.tid=t.tid WHERE t.word=?",(t,)).fetchall()
    n=db.execute("SELECT p.n,p.payload FROM term t JOIN packed p ON p.tid=t.tid WHERE t.word=?",(t,)).fetchone()
    return list(unpack(n[1],n[0])) if n else []

def verify_all(db,policy,expected):
    checked=0
    for term,records in expected.items():
        got=read_all_term(db,term,policy)
        if sorted(got)!=sorted(records):raise AssertionError("persisted posting mismatch")
        checked+=len(got)
    return checked

def counts(db,t,c,act,lens,policy):
    if policy=="native_history":
        rows=db.execute("""SELECT docs.rowid,cdg_count(docs),cdg_length(docs) FROM docs
          JOIN versions v ON v.g=docs.rowid WHERE docs MATCH ? AND docs.rowid<=? AND v.end_g>?""",(quote(t),c,c))
        out={}
        for g,tf,dl in rows:
            if dl!=lens[g]:raise ValueError("native length")
            out[g]=tf
        return out
    if policy=="rel_version":
        return dict(db.execute("""SELECT p.g,p.tf FROM term t JOIN postings p ON p.tid=t.tid
          JOIN versions v ON v.g=p.g WHERE t.word=? AND p.g<=? AND v.end_g>?""",(t,c,c)))
    if policy=="rel_coalesced":
        records=db.execute("""SELECT p.aid,p.start_g,p.end_g,p.tf FROM term t JOIN postings p ON p.tid=t.tid
          WHERE t.word=? AND p.start_g<=? AND p.end_g>?""",(t,c,c))
    else:records=read_all_term(db,t,policy)
    out={}
    for a,s,e,tf in records:
        if s<=c<e:
            g=act[a]
            if g in out:raise ValueError("overlapping term intervals")
            out[g]=tf
    return out

def query_plan(freqs,act):
    df=collections.Counter(t for g in act.values() for t in freqs[g])
    key=lambda t:sha(("CDG-R121-query-v1|"+t).encode())
    ts=[]
    for lo,hi in ((1,2),(3,10),(11,10000000)):
        ts+=sorted((t for t,f in df.items() if lo<=f<=hi),key=key)[:24]
    common=[t for t,_ in sorted(df.items(),key=lambda p:(-p[1],p[0]))[:8]]
    ts=list(dict.fromkeys(ts+common))
    qs=[((t,),"AND") for t in ts]
    for i in range(min(12,len(ts)//2)):
        a,b=ts[i],ts[-1-i]
        if a!=b:qs.extend([((a,b),"AND"),((a,b),"OR")])
    return qs,common

def rank(db,terms,op,c,act,lens,total,policy,ref):
    if policy=="native_active":return native(ref,terms,op)
    freq=[counts(db,t,c,act,lens,policy) for t in terms]
    return score(freq,op,len(act),total,lens)[0]

def experiment(folder,events,ext,repeats):
    freqs=extract(events);rows,ids=metadata(events,freqs)
    ordinary=postings(rows,freqs,False);coal=postings(rows,freqs,True)
    # Independent exhaustive interval expansion against original TF maps.
    by_article=collections.defaultdict(list)
    for g,a,i,e,dl,d in rows:by_article[a].append(g)
    checked=0
    expanded=[{} for _ in freqs]
    for t,rs in coal.items():
        for a,s,e,tf in rs:
            for g in by_article[a]:
                if s<=g<e:
                    if t in expanded[g]:raise AssertionError("overlap")
                    expanded[g][t]=tf;checked+=1
    if expanded!=freqs:raise AssertionError("coalesced full expansion differs from native TF")
    del expanded
    dbs={};stats={}
    for p in POLICIES:
        rec=coal if p.endswith("coalesced") else ordinary
        dbs[p],stats[p]=build(folder/(p+".sqlite"),rows,ids,events,rec,p,ext)
        if p!="native_history":stats[p]["persisted_postings_verified"]=verify_all(dbs[p],p,rec)
    lens=[0]+[r[4] for r in rows]
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,common=query_plan(freqs,active(rows,cuts[0]))
    if not qs:raise ValueError("empty queries")
    rng=random.Random(121);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values())
        path=folder/("active-"+str(c)+".sqlite");ref=active_oracle(events,c,path)
        unique=sorted({t for terms,_ in qs for t in terms})
        countchecks=0;maxerr={p:0.0 for p in METHODS};hits=0
        for t in unique:
            want={g:freqs[g][t] for g in act.values() if t in freqs[g]}
            for p in POLICIES:
                if counts(dbs[p],t,c,act,lens,p)!=want:raise AssertionError("active count mismatch")
            countchecks+=len(want)
        for terms,op in qs:
            want=native(ref,terms,op);hits+=len(want)
            for p in POLICIES:
                got=rank(dbs[p],terms,op,c,act,lens,total,p,ref)
                maxerr[p]=max(maxerr[p],verify(got,want))
        timings={p:[] for p in METHODS};high={p:[] for p in METHODS}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for terms,op in req:
                methods=list(METHODS);rng.shuffle(methods)
                for p in methods:
                    st=time.perf_counter_ns()
                    rank(dbs.get(p),terms,op,c,act,lens,total,p,ref)
                    us=(time.perf_counter_ns()-st)/1000
                    timings[p].append(us)
                    if len(terms)==1 and terms[0] in common:high[p].append(us)
        results.append(dict(cutoff=c,active_documents=len(act),query_checks=len(qs),
            ranked_hits=hits,active_integer_count_checks=countchecks,max_error=maxerr,
            native_active_index_bytes=path.stat().st_size,
            warm_median_us={p:statistics.median(v) for p,v in timings.items()},
            warm_p95_us={p:sorted(v)[int(.95*(len(v)-1))] for p,v in timings.items()},
            common_median_us={p:statistics.median(v) for p,v in high.items() if v}))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),vocabulary=len(ordinary),expanded_postings_checked=checked,
        ordinary_postings=sum(map(len,ordinary.values())),coalesced_postings=sum(map(len,coal.values())),
        policies=stats,cutoffs=results,repetitions=repeats,queries_per_cutoff=len(qs))

def run(root,ext,repeats):
    articles,manifest=load(root);cohort=select(articles,len(articles),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,repeats)
    return dict(round=121,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),
        sqlite_version=sqlite3.sqlite_version,result=r,limits=[
        "same processed Versions corpus; synthetic cross-article order; no fresh holdout",
        "term-only distinct AND/OR, no positions, phrase or NEAR support in external stores",
        "native full-detail FTS5 is richer than external TF-only indexes",
        "all index files include identical version and article metadata except active-only oracle files",
        "source payload excluded; offline bulk builds, no update WAL or atomic integration measured",
        "prepared active mapping shared outside timed rank calls; warm one-machine timing",
        "packed arms decode entire term list, no skips or temporal partitions",
        "TimIR-style relational baseline uses shared SQLite scoring/tokenizer, not executed MonetDB/Lucene or TTIX"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
