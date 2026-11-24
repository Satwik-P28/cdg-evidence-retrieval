"""R123: native wire-compatible filtering, page layout and bounded block cache."""
import argparse,collections,ctypes,json,random,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-122"))
from compact_temporal import (extract,metadata,postings,maps,local_records,global_records,
    pack_postings,unpack_postings,block,unblock,frame,unframe,group_items,read_term,
    get_counts,build,old_counts,active,query_plan,active_oracle,native,score,verify,
    order,load,select,SALT,PIN)

# Fixed layouts, no query-frequency training. Page sizes and schema differ only
# for the 16KiB control. Hybrid isolates high-cardinality terms.
LAYOUTS={
 "direct4":(0,4096,False,0),
 "shared4":(4096,4096,False,0),
 "shared16":(16384,4096,False,0),
 "shared16_rowid":(16384,4096,True,0),
 "shared16_page8":(16384,8192,False,0),
 "shared16_page16":(16384,16384,False,0),
 "hybrid4":(4096,4096,True,128),
 "hybrid16":(16384,4096,True,128),
}
METHODS=("direct_python","direct_c","shared16_python","shared16_c",
         "shared4_c","shared16_rowid_c","shared16_page8_c","shared16_page16_c",
         "hybrid4_c","hybrid16_c","packed_coalesced","native_history","native_active")

class Decoder:
    def __init__(self,path):
        self.lib=ctypes.CDLL(str(Path(path).resolve()))
        self.fn=self.lib.cdg_lookup
        u=ctypes.POINTER(ctypes.c_uint32)
        self.fn.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_size_t,
                           u,u,ctypes.c_size_t,u,ctypes.POINTER(ctypes.c_size_t)]
        self.fn.restype=ctypes.c_int
    def prepare(self,act,ord_by_g,cap):
        a=(ctypes.c_uint32*cap)();o=(ctypes.c_uint32*cap)();out=(ctypes.c_uint32*(2*cap))()
        for aid,g in act.items():a[aid]=g;o[aid]=ord_by_g[g]
        return a,o,out,cap
    def lookup(self,raw,term,state):
        a,o,out,cap=state;t=term.encode("utf8");seen=ctypes.c_size_t()
        n=self.fn(raw,len(raw),t,len(t),a,o,cap,out,ctypes.byref(seen))
        if n<0:raise ValueError("native decode "+str(n))
        return {out[2*i]:out[2*i+1] for i in range(n)},seen.value

def groups(items,target,threshold):
    if not target:
        yield from ([item] for item in items);return
    pending=[]
    for word,payload,n in items:
        if threshold and n>=threshold:
            yield from group_items(pending,target);pending=[]
            yield [(word,payload)]
        else:pending.append((word,payload))
    yield from group_items(pending,target)

def page_stats(db):
    # dbstat is optional on some SQLite builds; do not invent page accounting.
    try:
        rows=db.execute("""SELECT name,pagetype,count(*),sum(pgsize),sum(payload),sum(unused)
             FROM dbstat GROUP BY name,pagetype ORDER BY name,pagetype""").fetchall()
        return [dict(name=n,type=t,pages=c,page_bytes=b,payload=p,unused=u) for n,t,c,b,p,u in rows]
    except sqlite3.OperationalError:return None

def make(path,rows,ids,coal,by,og,layout):
    target,page,rowid,threshold=LAYOUTS[layout]
    db=sqlite3.connect(path);db.execute("PRAGMA page_size="+str(page))
    db.executescript("""
      CREATE TABLE article(aid INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
      CREATE TABLE versions(g INTEGER PRIMARY KEY,aid INTEGER NOT NULL,ordinal INTEGER NOT NULL,
         end_g INTEGER NOT NULL,dl INTEGER NOT NULL,digest BLOB NOT NULL);
      CREATE TABLE segments(word TEXT NOT NULL,bucket INTEGER NOT NULL,payload BLOB NOT NULL,
         PRIMARY KEY(word,bucket)) WITHOUT ROWID;
    """)
    db.executemany("INSERT INTO article VALUES(?,?)",((i,a) for a,i in ids.items()))
    db.executemany("INSERT INTO versions VALUES(?,?,?,?,?,?)",rows)
    db.execute("CREATE TABLE blocks(first TEXT PRIMARY KEY,payload BLOB NOT NULL)"+("" if rowid else " WITHOUT ROWID"))
    final=len(rows)+1;items=[]
    for t,rs in sorted(coal.items()):
        items.append((t,b"\x00"+pack_postings(local_records(rs,by,og,final)),len(rs)))
    groups_iter=groups(items,target,threshold) if target else ([(t,p)] for t,p,n in items)
    for group in groups_iter:
        db.execute("INSERT INTO blocks VALUES(?,?)",(group[0][0],frame(block(group),True)))
    db.commit();db.execute("VACUUM")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("SQLite integrity")
    seen=set();count=0
    for first,blob in db.execute("SELECT first,payload FROM blocks ORDER BY first"):
        entries=unblock(unframe(blob))
        if not entries or entries[0][0]!=first:raise ValueError("block directory")
        for t,p in entries:
            if t in seen or p[:1]!=b"\x00":raise ValueError("duplicate or invalid tag")
            seen.add(t);rs=unpack_postings(p[1:])
            if global_records(rs,by,final)!=sorted(coal[t]):raise ValueError("persisted intervals")
            count+=len(rs)
    if seen!=set(coal):raise ValueError("missing terms")
    return db,dict(sqlite_bytes=path.stat().st_size,page_size=page,blocks=db.execute("SELECT count(*) FROM blocks").fetchone()[0],
       encoded_block_bytes=db.execute("SELECT sum(length(payload)) FROM blocks").fetchone()[0],
       persisted_intervals_checked=count,dbstat=page_stats(db))

def raw_lookup(db,t):
    row=db.execute("SELECT payload FROM blocks WHERE first<=? ORDER BY first DESC LIMIT 1",(t,)).fetchone()
    if row is None:return None,0
    return unframe(row[0]),len(row[0])

class BlockCache:
    """LRU budget accounts decoded wire bytes only, not Python object overhead."""
    def __init__(self,db,budget):
        self.db=db;self.budget=budget;self.items=collections.OrderedDict();self.used=0
        self.hits=0;self.misses=0;self.activated=0;self.decoded=0;self.peak=0
    def get(self,t):
        row=self.db.execute("SELECT first FROM blocks WHERE first<=? ORDER BY first DESC LIMIT 1",(t,)).fetchone()
        if row is None:return None
        key=row[0]
        if key in self.items:
            self.hits+=1;self.items.move_to_end(key);return self.items[key]
        self.misses+=1
        blob=self.db.execute("SELECT payload FROM blocks WHERE first=?",(key,)).fetchone()[0]
        raw=unframe(blob);self.activated+=len(blob);self.decoded+=len(raw)
        if len(raw)<=self.budget:
            while self.used+len(raw)>self.budget:
                _,v=self.items.popitem(last=False);self.used-=len(v)
            self.items[key]=raw;self.used+=len(raw);self.peak=max(self.peak,self.used)
        return raw

def c_counts(db,t,decoder,state,cache=None):
    raw=cache.get(t) if cache is not None else raw_lookup(db,t)[0]
    return decoder.lookup(raw,t,state)[0] if raw is not None else {}

def experiment(folder,events,ext,decoder_path,repeats):
    decoder=Decoder(decoder_path);freqs=extract(events);rows,ids=metadata(events,freqs)
    coal=postings(rows,freqs,True);by,og=maps(rows);cap=len(ids)+1
    dbs={};stats={}
    for name in LAYOUTS:dbs[name],stats[name]=make(folder/(name+".sqlite"),rows,ids,coal,by,og,name)
    for name in ("packed_coalesced","native_history"):
        dbs[name],stats[name]=build(folder/(name+".sqlite"),rows,ids,events,coal,name,ext)
    lens=[0]+[r[4] for r in rows]
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,common=query_plan(freqs,active(rows,cuts[0]));rng=random.Random(123);results=[]
    # Exhaustive selected-list C/Python differential at every sampled generation
    # on direct and shared16 wire layouts, including empty matches.
    for c in cuts:
        act=active(rows,c);state=decoder.prepare(act,og,cap);total=sum(lens[g] for g in act.values())
        ref=active_oracle(events,c);native_checks=0;positive=0
        expected_by_term=collections.defaultdict(dict)
        for g in act.values():
            for t,tf in freqs[g].items():expected_by_term[t][g]=tf
        for t in sorted(coal):
            want=expected_by_term.get(t,{})
            for layout in ("direct4","shared16"):
                if c_counts(dbs[layout],t,decoder,state)!=want:raise AssertionError("native exhaustive TF differential")
            native_checks+=2;positive+=len(want)
        def ranked(method,terms,op,cache=None):
            if method=="native_active":return native(ref,terms,op)
            freq=[]
            for t in terms:
                if method in ("packed_coalesced","native_history"):
                    f=old_counts(dbs[method],t,c,act,lens,method)
                elif method.endswith("_python"):
                    layout="direct4" if method=="direct_python" else "shared16"
                    f=get_counts(dbs[layout],t,"local_adaptive",c,act,og)[0]
                else:
                    layout="direct4" if method=="direct_c" else method[:-2]
                    f=c_counts(dbs[layout],t,decoder,state,cache)
                freq.append(f)
            return score(freq,op,len(act),total,lens)[0]
        maxerr={m:0.0 for m in METHODS};hits=0
        for terms,op in qs:
            want=native(ref,terms,op);hits+=len(want)
            for m in METHODS:maxerr[m]=max(maxerr[m],verify(ranked(m,terms,op),want))
        # Timings do not include exhaustive audit or prepared metadata/state.
        timings={m:[] for m in METHODS};high={m:[] for m in METHODS}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for terms,op in req:
                ms=list(METHODS);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns();ranked(m,terms,op);us=(time.perf_counter_ns()-st)/1000
                    timings[m].append(us)
                    if len(terms)==1 and terms[0] in common:high[m].append(us)
        # Separate synthetic repeated stream, same randomized order for all
        # cache budgets. Zero-budget cache is the two-lookup matched control.
        stream=[]
        for _ in range(3):
            req=list(qs);rng.shuffle(req);stream+=req
        cache_results={}
        for layout in ("shared16","hybrid16"):
            for budget in (0,65536,262144):
                cache=BlockCache(dbs[layout],budget);ts=[]
                for terms,op in stream:
                    st=time.perf_counter_ns();got=ranked(layout+"_c",terms,op,cache);ts.append((time.perf_counter_ns()-st)/1000)
                    verify(got,native(ref,terms,op))
                cache_results[layout+"_"+str(budget)]=dict(budget=budget,hits=cache.hits,misses=cache.misses,
                    encoded_bytes=cache.activated,decoded_bytes=cache.decoded,peak_decoded_bytes=cache.peak,
                    median_us=statistics.median(ts),p95_us=sorted(ts)[int(.95*(len(ts)-1))])
        results.append(dict(cutoff=c,queries=len(qs),ranked_hits=hits,native_exhaustive_term_checks=native_checks,
            positive_active_pairs_per_layout=positive,max_score_error=maxerr,
            median_us={m:statistics.median(v) for m,v in timings.items()},
            p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timings.items()},
            common_median_us={m:statistics.median(v) for m,v in high.items() if v},cache=cache_results))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),vocabulary=len(coal),intervals=sum(map(len,coal.values())),layouts=stats,
        cutoffs=results,repetitions=repeats)
def run(root,ext,decoder,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,decoder,repeats)
    return dict(round=123,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
      limits=["same Versions data and query plan, not independent corpus",
       "term-only, no positions/phrase support; full native FTS5 richer",
       "offline immutable index, no source payload or update WAL",
       "C selected-list validation; no adversarial full-file authentication",
       "warm one-runner timings, prepared active maps, no I/O guarantees",
       "cache repeats synthetic query stream; budget counts decoded wire bytes only",
       "page accounting via dbstat when supported; no new compression primitive"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--decoder",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.decoder.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
