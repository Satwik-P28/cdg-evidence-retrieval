"""R125: fragment-relative positions and exact historical phrase retrieval.

Baseline inspired by He/Suel SIGIR 2012, not their full system reproduction.
Fragments are normalized token sequences, not original byte-exact source chunks.
"""
import argparse,collections,hashlib,json,random,sqlite3,statistics,struct,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-124"))
from positional_temporal import (extract_positions,phrase_freq,queries,metadata,maps,active,
    active_oracle,native,score,verify,build,old_counts,extension,quote,order,load,select,SALT,PIN)
from native_compact import page_stats

LAYOUTS={
 "fixed32_version":("fixed",32,False),
 "fixed32_coalesced":("fixed",32,True),
 "min32_version":("minima",16,False),
 "min32_coalesced":("minima",16,True),
 "min64_coalesced":("minima",32,True),
}

def tokens(pos):
    seq=[()]
    for m in pos[1:]:
        n=sum(len(v) for v in m.values());out=[None]*n
        for t,vs in m.items():
            for p in vs:
                if not 0<=p<n or out[p] is not None:raise ValueError("non-dense Unicode61 offsets")
                out[p]=t
        if any(t is None for t in out):raise ValueError("missing token")
        seq.append(tuple(out))
    return seq

def partitions(seq,mode,size):
    n=len(seq)
    if not n:return []
    if mode=="fixed":return [(i,seq[i:i+size]) for i in range(0,n,size)]
    if mode!="minima" or size<1:raise ValueError("partition mode")
    # Strict local minima of a four-token hash within radius size.
    # Maximum fragment length 4*radius is a deterministic forced fallback.
    # This is a simple 2MIN-inspired heuristic, not the paper's optimizer.
    hashes=[int.from_bytes(hashlib.blake2b(struct.pack("<IIII",*seq[i:i+4]),digest_size=8).digest(),"little") for i in range(max(0,n-3))]
    boundaries=[0]
    for i,h in enumerate(hashes):
        if i==0:continue
        lo=max(0,i-size);hi=min(len(hashes),i+size+1)
        if h<min(hashes[lo:i],default=2**64) and h<min(hashes[i+1:hi],default=2**64):
            boundaries.append(i)
    boundaries.append(n)
    out=[]
    for a,b in zip(boundaries,boundaries[1:]):
        for i in range(a,b,4*size):out.append((i,seq[i:min(b,i+4*size)]))
    if tuple(t for _,p in out for t in p)!=seq:raise AssertionError("partition coverage")
    return out

def fragmentize(rows,seq,mode,size,coalesce):
    ids={};frags=[()];apps=[];prior={};opened={}
    end=len(rows)+1
    for g,a,i,e,dl,d in rows:
        cur=set()
        for off,part in partitions(seq[g],mode,size):
            fid=ids.get(part)
            if fid is None:fid=len(frags);ids[part]=fid;frags.append(part)
            cur.add((fid,off))
        if not coalesce:
            apps.extend((fid,a,g,e,off) for fid,off in cur);continue
        old=prior.get(a,set())
        for fid,off in old-cur:
            start=opened.pop((a,fid,off));apps.append((fid,a,start,g,off))
        for fid,off in cur-old:opened[(a,fid,off)]=g
        prior[a]=cur
    for (a,fid,off),start in opened.items():apps.append((fid,a,start,end,off))
    return frags,sorted(apps)

def create(path,rows,ids,seq,words,mode,ext,posext):
    method,size,coalesce=LAYOUTS[mode]
    fragments,apps=fragmentize(rows,seq,method,size,coalesce)
    db=sqlite3.connect(path);db.execute("PRAGMA page_size=4096")
    extension(db,ext);extension(db,posext)
    db.executescript("""CREATE TABLE article(aid INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
    CREATE TABLE versions(g INTEGER PRIMARY KEY,aid INTEGER NOT NULL,ordinal INTEGER NOT NULL,end_g INTEGER NOT NULL,dl INTEGER NOT NULL,digest BLOB NOT NULL);
    CREATE VIRTUAL TABLE docs USING fts5(body,content='');
    CREATE TABLE fragment_length(fid INTEGER PRIMARY KEY,n INTEGER NOT NULL);
    CREATE TABLE applications(fid INTEGER NOT NULL,aid INTEGER NOT NULL,start_g INTEGER NOT NULL,end_g INTEGER NOT NULL,
       off INTEGER NOT NULL,PRIMARY KEY(fid,start_g,aid,off)) WITHOUT ROWID;
    """)
    db.executemany("INSERT INTO article VALUES(?,?)",((i,a) for a,i in ids.items()))
    db.executemany("INSERT INTO versions VALUES(?,?,?,?,?,?)",rows)
    db.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)",
        ((fid," ".join(words[t] for t in part)) for fid,part in enumerate(fragments[1:],1)))
    db.executemany("INSERT INTO fragment_length VALUES(?,?)",((fid,len(part)) for fid,part in enumerate(fragments[1:],1)))
    db.executemany("INSERT INTO applications VALUES(?,?,?,?,?)",apps)
    db.execute("INSERT INTO docs(docs) VALUES('optimize')")
    db.commit();db.execute("VACUUM")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("SQLite integrity")
    # Re-tokenization can be non-idempotent for arbitrary tokenizers.
    # Audit every fragment posting against the actual original native tokens.
    db.execute("CREATE VIRTUAL TABLE temp.frag_vocab USING fts5vocab(main,docs,'instance')")
    wordids={t:i for i,t in enumerate(words) if i}
    restored=[[] for _ in fragments]
    for t,fid,off in db.execute("SELECT term,doc,offset FROM temp.frag_vocab ORDER BY doc,offset"):
        if off!=len(restored[fid]) or t not in wordids:raise AssertionError("fragment re-tokenization drift")
        restored[fid].append(wordids[t])
    if [tuple(v) for v in restored]!=fragments:raise AssertionError("fragment posting mismatch")
    persisted=db.execute("SELECT fid,aid,start_g,end_g,off FROM applications ORDER BY fid,aid,start_g,end_g,off").fetchall()
    if persisted!=apps:raise AssertionError("stored application mismatch")
    by,_=maps(rows);cover=[[] for _ in seq];expanded=0
    for fid,a,s,e,off in persisted:
        part=fragments[fid]
        for g in by[a]:
            if s<=g<e:
                cover[g].append((off,part));expanded+=1
    for g in range(1,len(seq)):
        off=0;decoded=[]
        for start,part in sorted(cover[g]):
            if start!=off:raise AssertionError("application coverage or overlap")
            decoded.extend(part);off+=len(part)
        if tuple(decoded)!=seq[g]:raise AssertionError("token reconstruction mismatch")
    return db,dict(sqlite_bytes=path.stat().st_size,unique_fragments=len(fragments)-1,
        unique_fragment_tokens=sum(map(len,fragments)),application_intervals=len(apps),
        expanded_applications=expanded,verified_original_tokens=sum(map(len,seq)),dbstat=page_stats(db))

def term_positions(db,t,c,act):
    # Native FTS5 fragment index joined to exact application intervals.
    rows=db.execute("""SELECT a.aid,a.off,cdg_offsets(docs) FROM docs
         JOIN applications a ON a.fid=docs.rowid
         WHERE docs MATCH ? AND a.start_g<=? AND a.end_g>?""",(quote(t),c,c))
    out=collections.defaultdict(list)
    for aid,off,blob in rows:
        g=act.get(aid)
        if g is None or len(blob)%4 or not blob:raise ValueError("invalid active application")
        out[g].extend(off+p for p, in struct.iter_unpack("<I",blob))
    result={}
    for g,vs in out.items():
        v=tuple(sorted(vs))
        if any(a>=b for a,b in zip(v,v[1:])):raise ValueError("duplicate position")
        result[g]=v
    return result

def experiment(folder,events,ext,posext,repeats):
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs)
    original=tokens(pos);words=[""]+sorted({t for m in pos for t in m})
    wordids={t:i for i,t in enumerate(words) if i}
    seq=[tuple(wordids[t] for t in s) for s in original]
    dbs={};stats={}
    for mode in LAYOUTS:
        dbs[mode],stats[mode]=create(folder/(mode+".sqlite"),rows,ids,seq,words,mode,ext,posext)
    dbs["native_history"],stats["native_history"]=build(folder/"native_history.sqlite",rows,ids,events,{},"native_history",ext)
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    lens=[0]+[r[4] for r in rows];qs,common,selected=queries(pos,freqs,active(rows,cuts[0]))
    methods=tuple(LAYOUTS)+("native_history","native_active");rng=random.Random(125);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values())
        ref=active_oracle(events,c);extension(ref,ext)
        uniq=sorted({p for ps,_ in qs for p in ps})
        terms=sorted({t for p in uniq for t in p.split()})
        checked=positions_checked=0
        for t in terms:
            want={g:pos[g][t] for g in act.values() if t in pos[g]}
            for m in LAYOUTS:
                if term_positions(dbs[m],t,c,act)!=want:raise AssertionError("active position mismatch")
            positions_checked+=sum(map(len,want.values()))
        for p in uniq:
            want=dict(ref.execute("SELECT rowid,cdg_count(fulltext) FROM fulltext WHERE fulltext MATCH ?",(quote(p),)))
            for m in LAYOUTS:
                got=phrase_freq(p,lambda t:term_positions(dbs[m],t,c,act))
                if got!=want:raise AssertionError("phrase occurrence mismatch")
            checked+=len(want)
        def ranked(m,ps,op):
            if m=="native_active":return native(ref,ps,op)
            if m=="native_history":freq=[old_counts(dbs[m],p,c,act,lens,m) for p in ps]
            else:
                cache={}
                def lookup(t):
                    if t not in cache:cache[t]=term_positions(dbs[m],t,c,act)
                    return cache[t]
                freq=[phrase_freq(p,lookup) for p in ps]
            return score(freq,op,len(act),total,lens)[0]
        maxerr={m:0.0 for m in methods};hits=0
        for ps,op in qs:
            want=native(ref,ps,op);hits+=len(want)
            for m in methods:maxerr[m]=max(maxerr[m],verify(ranked(m,ps,op),want))
        timings={m:[] for m in methods};pt={m:[] for m in methods}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for ps,op in req:
                ms=list(methods);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns();ranked(m,ps,op);us=(time.perf_counter_ns()-st)/1000
                    timings[m].append(us)
                    if any(" " in p for p in ps):pt[m].append(us)
        results.append(dict(cutoff=c,queries=len(qs),ranked_hits=hits,positive_phrase_frequency_pairs=checked,
            positive_term_positions_checked=positions_checked,unique_terms_checked=len(terms),max_error=maxerr,
            median_us={m:statistics.median(v) for m,v in timings.items()},
            phrase_median_us={m:statistics.median(v) for m,v in pt.items() if v},
            p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timings.items()}))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),original_tokens=sum(map(len,seq)),vocabulary=len(words)-1,layouts=stats,
         cutoffs=results,repetitions=repeats)

def run(root,ext,posext,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,posext,repeats)
    return dict(round=125,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
       limits=["same processed Versions corpus, synthetic cross-article order; no independent corpus",
        "normalized token fragments not exact source-byte fragments; source payload excluded",
        "fixed and 2MIN-inspired strict minima with maximum length cap; not He/Suel optimized partitioning",
        "global exact fragment deduplication plus optional application interval coalescing",
        "exact quoted phrase AND/OR only; no general FTS5 grammar or prefix/NEAR",
        "full active phrase frequency counts, not approximate candidate rerank",
        "offline builds; no updates/WAL or source receipt integration",
        "warm one-runner rank timings, prepared active heads; no device I/O claims"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--position-extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.position_extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
