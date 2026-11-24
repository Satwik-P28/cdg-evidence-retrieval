"""R124: exact temporal position vectors, bounded edit patches, phrase parity.
Offline source-free index; Unicode61 exact quoted phrases and distinct AND/OR.
"""
import argparse,collections,json,random,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-123"))
from native_compact import groups,page_stats
from compact_temporal import (vint,readv,block,unblock,frame,unframe,active,metadata,maps,
    build,old_counts,query_plan,active_oracle,native,score,verify,order,load,select,SALT,PIN)
from rank_replay import quote
from native_compare import extension

LAYOUTS={
    "version_hybrid4":(False,False,4096,128),
    "coalesced_direct":(True,False,0,0),
    "coalesced_hybrid4":(True,False,4096,128),
    "coalesced_hybrid16":(True,False,16384,128),
    "patch_hybrid4":(True,True,4096,128),
    "patch_hybrid16":(True,True,16384,128),
}
MAX_POS=0xffffffff

def extract_positions(events):
    db=sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(body,content='')")
    db.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)",((g,r.decode("utf8")) for g,(_,_,r) in enumerate(events,1)))
    db.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(docs,'instance')")
    out=[collections.defaultdict(list) for _ in range(len(events)+1)]
    for t,g,p in db.execute("SELECT term,doc,offset FROM vocab ORDER BY doc,term,offset"):
        out[g][t].append(p)
    db.close()
    return [{t:tuple(v) for t,v in m.items()} for m in out]

def intervals(rows,pos,coalesce):
    """Local ordinal intervals, half-open; changed/absent vectors close runs."""
    result=collections.defaultdict(list);prior={};opened={}
    for g,a,i,e,dl,d in rows:
        cur=pos[g]
        if not coalesce:
            for t,v in cur.items():result[t].append((a,i,i+1,v))
            continue
        old=prior.get(a,{})
        for t in old.keys()|cur.keys():
            before,after=old.get(t),cur.get(t)
            if before==after:continue
            key=(a,t)
            if before is not None:
                start,v=opened.pop(key);result[t].append((a,start,i,v))
            if after is not None:opened[key]=(i,after)
        prior[a]=cur
    ends={a:i+1 for g,a,i,e,dl,d in rows}
    for (a,t),(s,v) in opened.items():result[t].append((a,s,ends[a],v))
    return {t:sorted(v) for t,v in result.items()}

def gaps(v):
    if not v or v[0]<0 or v[-1]>MAX_POS or any(x>=y for x,y in zip(v,v[1:])):raise ValueError("invalid vector")
    return (v[0],)+tuple(y-x for x,y in zip(v,v[1:]))

def ungap(v):
    if not v or any(x<=0 for x in v[1:]):raise ValueError("invalid gaps")
    out=[];p=0
    for x in v:
        p+=x
        if p>MAX_POS:raise ValueError("position overflow")
        out.append(p)
    return tuple(out)

def full(v):
    return b"\x00"+vint(len(v))+b"".join(map(vint,v))

def patch(base,v):
    """Common prefix/suffix of position gaps; splice literal middle.
    A shifted suffix often has identical internal gaps.
    """
    pre=0
    while pre<min(len(base),len(v)) and base[pre]==v[pre]:pre+=1
    suf=0
    while suf<min(len(base),len(v))-pre and base[-1-suf]==v[-1-suf]:suf+=1
    mid=v[pre:len(v)-suf if suf else len(v)]
    return b"\x01"+vint(pre)+vint(suf)+vint(len(mid))+b"".join(map(vint,mid))

def read_vector(data,p,base):
    if p>=len(data):raise ValueError("missing vector tag")
    tag=data[p];p+=1
    if tag==0:
        n,p=readv(data,p)
        if not n or n>len(data)-p:raise ValueError("impossible vector")
        v=[]
        for _ in range(n):x,p=readv(data,p);v.append(x)
        v=tuple(v);return ungap(v),v,p,False
    if tag!=1 or base is None:raise ValueError("invalid patch anchor")
    pre,p=readv(data,p);suf,p=readv(data,p);n,p=readv(data,p)
    if pre+suf>len(base) or n>len(data)-p:raise ValueError("bad splice")
    mid=[]
    for _ in range(n):x,p=readv(data,p);mid.append(x)
    v=base[:pre]+tuple(mid)+(base[len(base)-suf:] if suf else ())
    return ungap(v),base,p,True

def encode(rs,patches):
    out=bytearray(vint(len(rs)));last_a=0;anchor=None;stats=[0,0,0]
    for a,s,e,positions in rs:
        if a!=last_a:anchor=None
        v=gaps(positions);literal=full(v);chosen=literal
        if patches and anchor is not None:
            delta=patch(anchor,v)
            if len(delta)<len(literal):chosen=delta
        if chosen[0]==0:anchor=v
        else:stats[0]+=1;stats[1]+=len(literal)-len(chosen)
        stats[2]+=len(literal)
        out+=vint(a-last_a)+vint(s)+vint(e-s)+chosen;last_a=a
    return bytes(out),stats

def decode(data,allow_patch):
    n,p=readv(data,0);a=0;anchor=None;last_end=0;out=[]
    if n>(len(data)-p)//6:raise ValueError("impossible records")
    for _ in range(n):
        da,p=readv(data,p);s,p=readv(data,p);span,p=readv(data,p)
        if da:anchor=None;last_end=0
        a+=da
        if not a or a>MAX_POS or not span or s+span>MAX_POS or s<last_end:raise ValueError("invalid interval")
        v,anchor,p,patched=read_vector(data,p,anchor)
        if patched and not allow_patch:raise ValueError("unexpected patch")
        out.append((a,s,s+span,v));last_end=s+span
    if p!=len(data):raise ValueError("trailing bytes")
    return out

def setup(path,rows,ids):
    db=sqlite3.connect(path);db.execute("PRAGMA page_size=4096")
    db.executescript("""CREATE TABLE article(aid INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
    CREATE TABLE versions(g INTEGER PRIMARY KEY,aid INTEGER NOT NULL,ordinal INTEGER NOT NULL,end_g INTEGER NOT NULL,dl INTEGER NOT NULL,digest BLOB NOT NULL);
    CREATE TABLE segments(word TEXT NOT NULL,bucket INTEGER NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(word,bucket)) WITHOUT ROWID;
    CREATE TABLE blocks(first TEXT PRIMARY KEY,payload BLOB NOT NULL);""")
    db.executemany("INSERT INTO article VALUES(?,?)",((i,a) for a,i in ids.items()))
    db.executemany("INSERT INTO versions VALUES(?,?,?,?,?,?)",rows)
    return db

def make(path,rows,ids,rs,by,pos,mode):
    coalesced,patches,target,threshold=LAYOUTS[mode]
    db=setup(path,rows,ids);items=[];patch_count=patch_saved=literal_bytes=wire=0
    for t,records in sorted(rs.items()):
        p,s=encode(records,patches);patch_count+=s[0];patch_saved+=s[1];literal_bytes+=s[2];wire+=len(p)
        items.append((t,p,len(records)))
    batches=groups(items,target,threshold) if target else ([(t,p)] for t,p,n in items)
    for group in batches:db.execute("INSERT INTO blocks VALUES(?,?)",(group[0][0],frame(block(group),True)))
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    seen=set();vectors=tokens=records_checked=0
    # Every persisted vector expanded to every covered original revision.
    # Exact record equality to construction is a separate check.
    for first,payload in db.execute("SELECT first,payload FROM blocks ORDER BY first"):
        entries=unblock(unframe(payload))
        if not entries or entries[0][0]!=first:raise AssertionError("directory")
        for t,p in entries:
            if t in seen:raise AssertionError("duplicate term")
            seen.add(t);records=decode(p,patches)
            if records!=rs[t]:raise AssertionError("position records")
            records_checked+=len(records)
            for a,s,e,v in records:
                if not 0<=s<e<=len(by[a]):raise AssertionError("local validity")
                for g in by[a][s:e]:
                    if pos[g].get(t)!=v:raise AssertionError("expanded position vector")
                    vectors+=1;tokens+=len(v)
    if seen!=set(rs) or vectors!=sum(map(len,pos)) or tokens!=sum(len(v) for m in pos for v in m.values()):raise AssertionError("coverage")
    return db,dict(sqlite_bytes=path.stat().st_size,blocks=db.execute("SELECT count(*) FROM blocks").fetchone()[0],
      encoded_block_bytes=db.execute("SELECT sum(length(payload)) FROM blocks").fetchone()[0],raw_posting_wire_bytes=wire,
      interval_records=records_checked,expanded_vectors=vectors,expanded_positions=tokens,
      patch_records=patch_count,patch_raw_bytes_saved=patch_saved,full_vector_wire_bytes=literal_bytes,dbstat=page_stats(db))

def term_positions(db,t,mode,act,og):
    row=db.execute("SELECT payload FROM blocks WHERE first<=? ORDER BY first DESC LIMIT 1",(t,)).fetchone()
    if row is None:return {}
    for word,p in unblock(unframe(row[0])):
        if word!=t:continue
        out={}
        for a,s,e,v in decode(p,LAYOUTS[mode][1]):
            g=act.get(a)
            if g is not None and s<=og[g]<e:
                if g in out:raise ValueError("overlap")
                out[g]=v
        return out
    return {}

def phrase_freq(phrase,lookup):
    words=phrase.split(" ")
    maps=[lookup(w) for w in words]
    if len(maps)==1:return {g:len(v) for g,v in maps[0].items()}
    candidates=set.intersection(*(set(m) for m in maps));out={}
    for g in candidates:
        starts=set(maps[0][g])
        for j,m in enumerate(maps[1:],1):
            starts.intersection_update(p-j for p in m[g])
            if not starts:break
        if starts:out[g]=len(starts)
    return out

def queries(pos,freqs,act):
    qs,common=query_plan(freqs,act)
    df=collections.Counter()
    for g in act.values():
        at={p:t for t,vs in pos[g].items() for p in vs}
        found=set()
        for p in at:
            for length in (2,3):
                if all(p+i in at for i in range(length)):
                    found.add(" ".join(at[p+i] for i in range(length)))
        df.update(found)
    from versioned_evidence import sha
    key=lambda p:sha(("CDG-R124-phrase-v1|"+p).encode())
    selected=[]
    for length in (2,3):
        subset=[p for p in df if len(p.split())==length]
        selected+=sorted(subset,key=key)[:16]
        selected+=sorted(subset,key=lambda p:(-df[p],p))[:4]
    selected=list(dict.fromkeys(selected))
    qs.extend(((p,),"AND") for p in selected)
    for p in selected[:8]:
        qs.extend([((p,p.split()[0]),"AND"),((p,p.split()[0]),"OR")])
    return qs,common,selected

def experiment(folder,events,ext,repeats):
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);by,og=maps(rows)
    full_records=intervals(rows,pos,False);coal=intervals(rows,pos,True)
    dbs={};stats={}
    for mode,(coalesced,*_) in LAYOUTS.items():
        dbs[mode],stats[mode]=make(folder/(mode+".sqlite"),rows,ids,coal if coalesced else full_records,by,pos,mode)
    dbs["native_history"],stats["native_history"]=build(folder/"native_history.sqlite",rows,ids,events,{},"native_history",ext)
    lens=[0]+[r[4] for r in rows];cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,common,selected=queries(pos,freqs,active(rows,cuts[0]))
    methods=tuple(LAYOUTS)+("native_history","native_active")
    rng=random.Random(124);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values());ref=active_oracle(events,c);extension(ref,ext)
        unique=sorted({p for ps,_ in qs for p in ps})
        # Independent native FTS5 phrase occurrence count from rebuilt snapshot.
        expected_counts={p:dict(ref.execute("SELECT rowid,cdg_count(fulltext) FROM fulltext WHERE fulltext MATCH ?",(quote(p),))) for p in unique}
        checked=0
        for p,want in expected_counts.items():
            for m in LAYOUTS:
                got=phrase_freq(p,lambda t:term_positions(dbs[m],t,m,act,og))
                if got!=want:raise AssertionError("native phrase frequency differential "+repr((m,p,c)))
            if old_counts(dbs["native_history"],p,c,act,lens,"native_history")!=want:raise AssertionError("historical count")
            checked+=len(want)
        def ranked(m,ps,op):
            if m=="native_active":return native(ref,ps,op)
            if m=="native_history":freq=[old_counts(dbs[m],p,c,act,lens,m) for p in ps]
            else:
                cache={}
                def lookup(t):
                    if t not in cache:cache[t]=term_positions(dbs[m],t,m,act,og)
                    return cache[t]
                freq=[phrase_freq(p,lookup) for p in ps]
            return score(freq,op,len(act),total,lens)[0]
        maxerr={m:0.0 for m in methods};hits=0
        for ps,op in qs:
            expected=native(ref,ps,op);hits+=len(expected)
            for m in methods:maxerr[m]=max(maxerr[m],verify(ranked(m,ps,op),expected))
        timings={m:[] for m in methods};phrases={m:[] for m in methods}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for ps,op in req:
                ms=list(methods);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns();ranked(m,ps,op);us=(time.perf_counter_ns()-st)/1000
                    timings[m].append(us)
                    if any(" " in p for p in ps):phrases[m].append(us)
        results.append(dict(cutoff=c,queries=len(qs),phrase_queries=sum(any(" " in p for p in ps) for ps,op in qs),
          ranked_hits=hits,unique_phrase_or_term_counts=len(unique),positive_native_frequency_pairs=checked,max_error=maxerr,
          median_us={m:statistics.median(v) for m,v in timings.items()},
          phrase_median_us={m:statistics.median(v) for m,v in phrases.items() if v},
          p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timings.items()}))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),vocabulary=len(coal),per_version_vectors=sum(map(len,full_records.values())),
      coalesced_vectors=sum(map(len,coal.values())),position_occurrences=sum(len(v) for m in pos for v in m.values()),
      layouts=stats,cutoffs=results,repetitions=repeats)
def run(root,ext,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,repeats)
    return dict(round=124,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
      limits=["same processed Versions corpus; synthetic order; not independent validation",
      "exact Unicode61 token positions, quoted phrases and distinct phrase AND/OR only; no NEAR, prefix, NOT, weights or arbitrary grammar",
      "one-step gap splice patch to latest literal in same term/article; no chain; offline immutable index",
      "native full-detail FTS5 richer; source bytes and online update/WAL excluded",
      "Python query decoding versus native FTS5; prepared active maps; warm one-runner timing",
      "no general novelty claim for gap coding, temporal coalescing or prefix/suffix delta coding"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
