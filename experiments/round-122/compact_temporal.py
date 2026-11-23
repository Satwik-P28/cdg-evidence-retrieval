"""R122: compact local-ordinal temporal TF postings and shared term blocks.
Offline term-only index; identical source-free metadata and query contract to R121.
"""
import argparse, bisect, collections, json, random, sqlite3, statistics, sys, tempfile, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-121"))
from temporal_postings import (extract,metadata,postings,setup,build,active,query_plan,
    counts as old_counts,read_all_term,active_oracle,native,score,verify,
    order,load,select,SALT,PIN,sha,C,D)

MODES=("global_varint","local_varint","local_adaptive","shared4k","shared16k","shared4k_time")
BUCKET=512
LIMIT=16*1024*1024

def vint(x):
    if not 0<=x<=0xffffffff:raise ValueError("uint32")
    out=bytearray()
    while x>=128:
        out.append((x&127)|128);x>>=7
    out.append(x)
    return bytes(out)

def readv(data,p):
    x=0
    for i in range(5):
        if p>=len(data):raise ValueError("truncated varint")
        b=data[p];p+=1;x|=(b&127)<<(7*i)
        if b<128:
            if x>0xffffffff or (i and b==0):raise ValueError("noncanonical varint")
            return x,p
    raise ValueError("oversize varint")

def pack_postings(records):
    out=bytearray(vint(len(records)));prev=0
    for a,s,e,tf in sorted(records):
        if a<1 or s<0 or e<=s or tf<1:raise ValueError("bad interval")
        out+=vint(a-prev)+vint(s)+vint(e-s)+vint(tf);prev=a
    return bytes(out)

def unpack_postings(data):
    n,p=readv(data,0)
    if n>(len(data)-p)//4:raise ValueError("impossible count")
    out=[];a=0
    for _ in range(n):
        da,p=readv(data,p);s,p=readv(data,p);span,p=readv(data,p);tf,p=readv(data,p);a+=da
        if not a or not span or not tf or s+span>0xffffffff or a>0xffffffff:raise ValueError("invalid posting")
        r=(a,s,s+span,tf)
        if out and (a<out[-1][0] or (a==out[-1][0] and s<out[-1][2])):raise ValueError("overlap or order")
        out.append(r)
    if p!=len(data):raise ValueError("trailing bytes")
    return out

def frame(raw,adaptive):
    if adaptive:
        z=C.compress(raw)
        if len(z)<len(raw):return b"\x01"+z
    return b"\x00"+raw

def unframe(data):
    if not data:raise ValueError("empty frame")
    if data[0]==0:return data[1:]
    if data[0]==1:
        raw=D.decompress(data[1:],max_output_size=LIMIT)
        if len(raw)>LIMIT:raise ValueError("oversize frame")
        return raw
    raise ValueError("unknown frame")

def block(items):
    out=bytearray(vint(len(items)));prev=b""
    for word,payload in items:
        raw=word.encode("utf8");prefix=0
        while prefix<min(len(prev),len(raw)) and prev[prefix]==raw[prefix]:prefix+=1
        suffix=raw[prefix:]
        out+=vint(prefix)+vint(len(suffix))+suffix+vint(len(payload))+payload;prev=raw
    return bytes(out)

def unblock(data):
    n,p=readv(data,0);out=[];prev=b""
    if n>(len(data)-p)//3:raise ValueError("block count")
    for _ in range(n):
        pre,p=readv(data,p);size,p=readv(data,p)
        if pre>len(prev) or p+size>len(data):raise ValueError("bad suffix")
        raw=prev[:pre]+data[p:p+size];p+=size
        length,p=readv(data,p)
        if p+length>len(data) or (out and raw<=prev):raise ValueError("bad block order")
        out.append((raw.decode("utf8"),data[p:p+length]));p+=length;prev=raw
    if p!=len(data):raise ValueError("trailing block bytes")
    return out

def maps(rows):
    by=collections.defaultdict(list);ord_by_g={}
    for g,a,i,e,dl,d in rows:
        if i!=len(by[a]):raise ValueError("ordinal mismatch")
        by[a].append(g);ord_by_g[g]=i
    return by,ord_by_g

def local_records(records,by,ord_by_g,final):
    out=[]
    for a,s,e,tf in records:
        start=ord_by_g[s]
        end=len(by[a]) if e==final else ord_by_g[e]
        if by[a][start]!=s or (e!=final and by[a][end]!=e):raise ValueError("cross article interval")
        out.append((a,start,end,tf))
    return sorted(out)

def global_records(records,by,final):
    return sorted((a,by[a][s],by[a][e] if e<len(by[a]) else final,tf) for a,s,e,tf in records)

def group_items(items,target):
    group=[];size=0
    for word,payload in items:
        estimate=len(word.encode("utf8"))+len(payload)+8
        # Oversize/frequent terms retain independent frames.
        if group and size+estimate>target:
            yield group;group=[];size=0
        group.append((word,payload));size+=estimate
        if size>=target:
            yield group;group=[];size=0
    if group:yield group

def create(path,rows,ids,coal,mode,by,ord_by_g):
    db=setup(path,rows,ids)
    db.execute("CREATE TABLE blocks(first TEXT PRIMARY KEY,payload BLOB NOT NULL) WITHOUT ROWID")
    db.execute("CREATE TABLE segments(word TEXT NOT NULL,bucket INTEGER NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(word,bucket)) WITHOUT ROWID")
    final=len(rows)+1
    items=[];segments=0;duplicate_records=0
    for t,rs in sorted(coal.items()):
        local=mode!="global_varint"
        values=local_records(rs,by,ord_by_g,final) if local else sorted(rs)
        if mode=="shared4k_time" and len(rs)>=128:
            buckets=collections.defaultdict(list)
            for g_record in rs:
                a,s,e,tf=g_record
                for b in range((s-1)//BUCKET,(e-2)//BUCKET+1):
                    buckets[b].append(g_record)
            for b,rs2 in sorted(buckets.items()):
                rec=local_records(rs2,by,ord_by_g,final)
                db.execute("INSERT INTO segments VALUES(?,?,?)",(t,b,frame(pack_postings(rec),True)))
                segments+=1;duplicate_records+=len(rec)
            payload=b"\x02"
        else:
            payload=b"\x00"+pack_postings(values)
        items.append((t,payload))
    if mode.startswith("shared"):
        target=16384 if mode=="shared16k" else 4096
        groups=group_items(items,target)
    else:groups=([item] for item in items)
    block_count=stored=0
    for group in groups:
        payload=frame(block(group),mode not in ("global_varint","local_varint"))
        db.execute("INSERT INTO blocks VALUES(?,?)",(group[0][0],payload))
        block_count+=1;stored+=len(payload)
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    segbytes=db.execute("SELECT coalesce(sum(length(payload)),0) FROM segments").fetchone()[0]
    return db,dict(sqlite_bytes=path.stat().st_size,blocks=block_count,segments=segments,
        block_payload_bytes=stored,segment_payload_bytes=segbytes,segment_record_copies=duplicate_records)

def read_term(db,t,mode,c=None):
    r=db.execute("SELECT payload FROM blocks WHERE first<=? ORDER BY first DESC LIMIT 1",(t,)).fetchone()
    if not r:return [],0,0
    raw=unframe(r[0]);activated=len(r[0]);decoded=len(raw)
    for word,payload in unblock(raw):
        if word!=t:continue
        if not payload:raise ValueError("empty entry")
        if payload[0]==0:return unpack_postings(payload[1:]),activated,decoded
        if payload==b"\x02" and mode=="shared4k_time":
            if c is None:
                chunks=db.execute("SELECT payload FROM segments WHERE word=? ORDER BY bucket",(t,))
            else:
                chunks=db.execute("SELECT payload FROM segments WHERE word=? AND bucket=?",(t,(c-1)//BUCKET))
            values=set()
            for (blob,) in chunks:
                data=unframe(blob);activated+=len(blob);decoded+=len(data)
                values.update(unpack_postings(data))
            return sorted(values),activated,decoded
        raise ValueError("invalid entry tag")
    return [],activated,decoded

def verify_store(db,coal,mode,by,ord_by_g,final):
    observed=set();total=0
    for first,payload in db.execute("SELECT first,payload FROM blocks ORDER BY first"):
        group=unblock(unframe(payload))
        if not group or group[0][0]!=first:raise AssertionError("directory mismatch")
        for t,entry in group:
            if t in observed or t not in coal:raise AssertionError("unexpected term")
            observed.add(t)
            rs=read_term(db,t,mode)[0]
            got=rs if mode=="global_varint" else global_records(rs,by,final)
            if sorted(got)!=sorted(coal[t]):raise AssertionError("persisted intervals mismatch")
            total+=len(rs)
            if entry==b"\x02":
                for b,blob in db.execute("SELECT bucket,payload FROM segments WHERE word=?",(t,)):
                    want=[r for r in coal[t] if r[1]<=min(final-1,(b+1)*BUCKET) and r[2]>b*BUCKET+1]
                    if sorted(unpack_postings(unframe(blob)))!=local_records(want,by,ord_by_g,final):raise AssertionError("segment mismatch")
    if observed!=set(coal):raise AssertionError("missing terms")
    return total

def get_counts(db,t,mode,c,act,ord_by_g):
    records,activated,decoded=read_term(db,t,mode,c)
    out={}
    for a,s,e,tf in records:
        g=act.get(a)
        if g is None:continue
        q=c if mode=="global_varint" else ord_by_g[g]
        if s<=q<e:
            if g in out:raise AssertionError("duplicate active posting")
            out[g]=tf
    return out,activated,decoded,len(records)

def run_experiment(folder,events,ext,repeats):
    freqs=extract(events);rows,ids=metadata(events,freqs);coal=postings(rows,freqs,True)
    by,ord_by_g=maps(rows);final=len(rows)+1
    dbs={};stats={}
    for m in MODES:
        dbs[m],stats[m]=create(folder/(m+".sqlite"),rows,ids,coal,m,by,ord_by_g)
        stats[m]["persisted_intervals_checked"]=verify_store(dbs[m],coal,m,by,ord_by_g,final)
    for m in ("packed_coalesced","native_history"):
        dbs[m],stats[m]=build(folder/(m+".sqlite"),rows,ids,events,coal,m,ext)
    methods=MODES+("packed_coalesced","native_history","native_active")
    lens=[0]+[r[4] for r in rows]
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,common=query_plan(freqs,active(rows,cuts[0]));rng=random.Random(122);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values());ref=active_oracle(events,c)
        metrics={m:{"activated_encoded_bytes":0,"decoded_block_bytes":0,"intervals_examined":0} for m in MODES}
        maxerr={m:0.0 for m in methods};checked=0;hits=0
        def ranked(m,terms,op,account=False):
            if m=="native_active":return native(ref,terms,op)
            freq=[]
            for t in terms:
                if m in MODES:
                    f,a,d,n=get_counts(dbs[m],t,m,c,act,ord_by_g)
                    if account:
                        z=metrics[m];z["activated_encoded_bytes"]+=a;z["decoded_block_bytes"]+=d;z["intervals_examined"]+=n
                        want={g:freqs[g][t] for g in act.values() if t in freqs[g]}
                        if f!=want:raise AssertionError("active exact TF mismatch")
                else:f=old_counts(dbs[m],t,c,act,lens,m)
                freq.append(f)
            return score(freq,op,len(act),total,lens)[0]
        for terms,op in qs:
            expected=native(ref,terms,op);hits+=len(expected)
            for m in methods:maxerr[m]=max(maxerr[m],verify(ranked(m,terms,op,True),expected))
            checked+=1
        timings={m:[] for m in methods};high={m:[] for m in methods}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for terms,op in req:
                ms=list(methods);rng.shuffle(ms)
                for m in ms:
                    t=time.perf_counter_ns();ranked(m,terms,op);us=(time.perf_counter_ns()-t)/1000
                    timings[m].append(us)
                    if len(terms)==1 and terms[0] in common:high[m].append(us)
        results.append(dict(cutoff=c,queries=checked,hits=hits,max_score_error=maxerr,logical_read=metrics,
            median_us={m:statistics.median(v) for m,v in timings.items()},
            p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timings.items()},
            common_median_us={m:statistics.median(v) for m,v in high.items() if v}))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),vocabulary=len(coal),intervals=sum(map(len,coal.values())),policies=stats,cutoffs=results,repetitions=repeats)

def run(root,ext,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=run_experiment(Path(tmp),order(cohort),ext,repeats)
    return dict(round=122,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
        limits=["same corpus and query plan as R121, not independent data",
                "term-only, no positions or phrase support; native full FTS5 richer",
                "offline final immutable layout, no updates or WAL measured",
                "source payload excluded; metadata included except native active oracle",
                "logical decoded/activated block bytes not device I/O; no cross-query block cache",
                "temporal buckets duplicate overlapping intervals; prepared active maps excluded from timings",
                "warm one-runner randomized rank-only timing, no latency guarantee",
                "varints, front coding, block compression and temporal buckets are established techniques"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
