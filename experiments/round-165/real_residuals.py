"""R188: real-corpus signed suffix residuals on exactly matched R168 anchors."""
import argparse,collections,json,random,shutil,tempfile,time,zlib
from pathlib import Path
import signed_phrase as sp
from signed_phrase import f,h,si,nr,connect,tokens,query_plan,prepare,recover
HERE=Path(__file__).resolve().parent
MODE="independent_adaptive_weighted_adjusted_multi"

def key(q):
    if not q or any(not t or b"\0" in t for t in q):raise ValueError("invalid normalized token")
    return b"\0".join(q)+b"\0"

def upper(k):
    assert k.endswith(b"\0")
    return k[:-1]+b"\1"

def residual(windows):
    out=collections.Counter()
    for w,c in windows.items():
        for i in range(len(w)):out[w[i:i+sp.L]]+=c
    return {s:v for s,v in out.items() if v}

def put(n,buf):
    if n<0:raise ValueError("negative varint")
    while n>=128:buf.append((n&127)|128);n>>=7
    buf.append(n)

def take(raw,i):
    x=shift=0
    while i<len(raw) and shift<=63:
        b=raw[i];i+=1;x|=(b&127)<<shift
        if b<128:return x,i
        shift+=7
    raise ValueError("invalid varint")

def pack(rows,compress=False):
    buf=bytearray();prev=0
    for cid,c in rows:
        if cid<=prev or not c:raise ValueError("invalid posting")
        put(cid-prev,buf);put(2*c if c>0 else -2*c-1,buf);prev=cid
    raw=bytes(buf)
    if compress:
        z=zlib.compress(raw,6)
        if len(z)<len(raw):return b"\1"+z
    return b"\0"+raw

def unpack(blob):
    if not blob or blob[0] not in (0,1):raise ValueError("invalid posting tag")
    raw=zlib.decompress(blob[1:]) if blob[0] else blob[1:];i=cid=0
    while i<len(raw):
        d,i=take(raw,i);v,i=take(raw,i)
        if not d or not v:raise ValueError("invalid posting")
        cid+=d;yield cid,v//2 if v%2==0 else -(v+1)//2

def block_encode(rows):
    out=bytearray();prev=b""
    for k,blob in rows:
        p=0
        while p<min(len(prev),len(k)) and prev[p]==k[p]:p+=1
        put(p,out);put(len(k)-p,out);put(len(blob),out)
        out.extend(k[p:]);out.extend(blob);prev=k
    return zlib.compress(out,6)

def block_decode(blob):
    raw=zlib.decompress(blob);i=0;prev=b""
    while i<len(raw):
        p,i=take(raw,i);n,i=take(raw,i);b,i=take(raw,i)
        if p>len(prev) or i+n+b>len(raw):raise ValueError("invalid block")
        k=prev[:p]+raw[i:i+n];i+=n;body=raw[i:i+b];i+=b
        if k<=prev or not k.endswith(b"\0"):raise ValueError("invalid block key")
        yield k,body;prev=k

def blocks(items):
    # Heuristic 900B compressed-body target; oversized singleton allowed.
    i=0
    while i<len(items):
        lo=i+1;hi=min(i+128,len(items));best=lo;body=block_encode(items[i:lo])
        while lo<=hi:
            mid=(lo+hi)//2;candidate=block_encode(items[i:mid])
            if len(candidate)<=900:best=mid;body=candidate;lo=mid+1
            else:hi=mid-1
        yield items[i][0],body,best-i;i=best

def builder(mode):
    def build(db,pending,stats):
        inv=collections.defaultdict(list);native=[];potential=collections.Counter();net=collections.defaultdict(list)
        cache="cache" in mode;hybrid="hybrid" in mode
        for cid,windows in pending:
            r=residual(windows)
            n=sum(len(w)*abs(c) for w,c in windows.items())
            # Fixed R185 sparse residual proxy, not optimized on evaluation.
            if hybrid and 5*len(r)>2*n:
                native.append((cid,windows));stats["residual_native_children"]+=1;continue
            stats["residual_children"]+=1;stats["residual_distinct_entries"]+=len(r);stats["residual_original_tokens"]+=n
            pref=collections.Counter()
            for suffix,c in r.items():
                inv[key(suffix)].append((cid,c))
                if cache:
                    for l in range(1,min(3,len(suffix))+1):
                        k=key(suffix[:l]);potential[k]+=1;pref[k]+=c
            if cache:
                for k,c in pref.items():
                    if c:net[k].append((cid,c))
        if not inv:return native
        db.execute("CREATE TABLE residual_blocks(k BLOB PRIMARY KEY,body BLOB NOT NULL) WITHOUT ROWID")
        items=[(k,pack(sorted(rows))) for k,rows in sorted(inv.items())]
        for k,blob,n in blocks(items):
            db.execute("INSERT INTO residual_blocks VALUES(?,?)",(k,blob))
            stats["residual_block_rows"]+=1;stats["residual_block_payload_bytes"]+=len(blob)
            stats["residual_keys"]+=n;stats["residual_oversize_blocks"]+=int(len(blob)>900)
        if cache:
            db.execute("CREATE TABLE residual_cache(k BLOB PRIMARY KEY,body BLOB NOT NULL) WITHOUT ROWID")
            block_bytes=db.execute("SELECT COALESCE(sum(pgsize),0) FROM dbstat WHERE name='residual_blocks'").fetchone()[0]
            budget=block_bytes//10;stats["residual_cache_estimated_budget"]=budget
            candidates=[]
            for k,w in potential.items():
                rows=net[k];gain=w-len(rows)
                if gain<=0:continue
                blob=pack(sorted(rows),True);cost=len(k)+len(blob)+12
                candidates.append((gain/cost,k,blob,cost))
            spent=0
            for _,k,blob,cost in sorted(candidates,key=lambda x:(-x[0],x[1])):
                if spent+cost>budget:continue
                db.execute("INSERT INTO residual_cache VALUES(?,?)",(k,blob));spent+=cost
                stats["residual_cache_entries"]+=1;stats["residual_cache_empty"]+=int(blob==b"\0")
            stats["residual_cache_estimated_bytes"]=spent
        return native
    return build

def read_blocks(db,k):
    hi=upper(k)
    row=db.execute("SELECT body FROM residual_blocks WHERE k<=? ORDER BY k DESC LIMIT 1",(k,)).fetchone()
    if row is not None:yield row[0]
    for blob, in db.execute("SELECT body FROM residual_blocks WHERE k>? AND k<? ORDER BY k",(k,hi)):yield blob

def reader(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "residual_blocks" not in tables:return None
    cache="residual_cache" in tables
    def read(db,q,active,counts,work):
        k=key(q);hi=upper(k)
        row=db.execute("SELECT body FROM residual_cache WHERE k=?",(k,)).fetchone() if cache and len(q)<=3 else None
        if row is not None:
            work["residual_cache_hits"]+=1;payloads=[row[0]]
        else:
            def payload_iter():
                for blob in read_blocks(db,k):
                    work["residual_block_reads"]+=1;work["residual_block_bytes"]+=len(blob)
                    for kk,payload in block_decode(blob):
                        if k<=kk<hi:yield payload
            payloads=payload_iter()
        for payload in payloads:
            work["residual_key_hits"]+=1
            for cid,c in unpack(payload):
                work["residual_postings"]+=1
                if cid in active:counts[cid]+=c;work["residual_active_postings"]+=1
    return read

def plans(events,cuts,refs,ext):
    db=connect(":memory:",ext);legacy=query_plan(events,cuts[0],refs[cuts[0]])
    legacy=[(p,o) for p,o in legacy if all(1<=len(tokens(db,t))<=sp.L for t in p)]
    prior={};pool=set()
    for a,_,raw in events[:min(20000,len(events))]:
        ts=tokens(db,raw.decode("utf8"))
        if a in prior:
            for x,y in sp.windows(prior[a],ts,False):
                for w in (x,y):
                    for l in (2,4,8):
                        if len(w)>=l:
                            i=(len(w)-l)//2;pool.add(b" ".join(w[i:i+l]).decode("utf8"))
        prior[a]=ts
        if len(pool)>=2048:break
    legacy=list(dict.fromkeys(legacy+[((p,),"AND") for p in sorted(pool,key=lambda p:h.sha(("R165|"+p).encode()))[:24]]))
    rng=random.Random(188);later=list(range(len(events)//2,len(events)));rng.shuffle(later)
    extra=[];seen=set(legacy)
    for j in later:
        ts=tokens(db,events[j][2].decode("utf8"))
        if len(ts)<2:continue
        l=rng.randint(2,min(sp.L,len(ts)));i=rng.randrange(len(ts)-l+1)
        q=((b" ".join(ts[i:i+l]).decode("utf8"),),"AND")
        if q not in seen:extra.append(q);seen.add(q)
        if len(extra)>=96:break
    common=collections.Counter()
    for _,_,raw in events[:min(len(events),2000)]:common.update(set(tokens(db,raw.decode("utf8"))))
    frequent=[t for t,_ in sorted(common.items(),key=lambda x:(-x[1],x[0]))[:32]]
    for _ in range(1000):
        if not frequent or len(extra)>=160:break
        q=((b" ".join(rng.choices(frequent,k=rng.randint(2,sp.L))).decode("utf8"),),"AND")
        if q not in seen:extra.append(q);seen.add(q)
    db.close();return dict(legacy=legacy,extended=extra)

def quant(times):
    z=h.quant(times);ordered=sorted(times)
    z["p99_us"]=ordered[int(.99*(len(ordered)-1))];z["max_us"]=ordered[-1];return z

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts};groups=plans(events,cuts,refs,ext)
    expected={(c,p,o):h.native(refs[c],p,o) for c in cuts for qs in groups.values() for p,o in qs}
    for ref in refs.values():ref.close()
    root=folder/"source.sqlite";db,size0=f.build(root,ext,events,"marginal",False);db.close()
    sigs={};freq_sigs={};results={};anchor_sig=None
    for mode in ("positional","signed","residual","residual_cache","hybrid_cache"):
        path=folder/(mode+".sqlite");shutil.copyfile(root,path);db=connect(path,ext);size=dict(size0)
        if mode!="positional":
            size.update(sp.build_delta(db,path,events,MODE,None if mode=="signed" else builder(mode)))
            signature=h.sha(h.canonical(list(db.execute("SELECT cid,base FROM idx_delta ORDER BY cid")))).hex()
            if anchor_sig is None:anchor_sig=signature
            else:assert anchor_sig==signature
        db.close();db=connect(path,ext)
        for g,(_,_,raw) in enumerate(events,1):
            got,dd,ab=recover(db,g);assert got==raw and 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        t=time.perf_counter_ns()
        mapping=sp.load_patch_map(db) if mode!="positional" else None
        rd=reader(db) if mode not in ("positional","signed") else None
        setup=(time.perf_counter_ns()-t)/1000
        preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns();preps[c]=prepare(db,c) if mode=="positional" else sp.prepare_delta(db,c,mapping)
            pt.append((time.perf_counter_ns()-t)/1000)
        splits={}
        for group,qs in groups.items():
            if not qs:continue
            plan=[(c,p,o) for c in cuts for p,o in qs];rng=random.Random(188);times=[];work=collections.Counter();err=0.
            for _ in range(2):
                rng.shuffle(plan)
                for c,p,o in plan:
                    sink=[];t=time.perf_counter_ns()
                    if mode=="positional":hits,df=si.rank(db,1,p,o,preps[c])
                    else:
                        hits,df,w=sp.rank_delta(db,p,o,preps[c],rd,sink)
                    times.append((time.perf_counter_ns()-t)/1000)
                    if mode!="positional":work.update(w)
                    err=max(err,h.verify(hits,expected[c,p,o]))
                    k=(c,p,o)
                    if mode=="positional":sigs[k]=(hits,df)
                    else:
                        assert sigs[k]==(hits,df)
                        digest=h.sha(h.canonical([sorted(m.items()) for m in sink])).hex()
                        if mode=="signed":freq_sigs[k]=digest
                        else:assert freq_sigs[k]==digest
            splits[group]=dict(query=quant(times),rank_checks=len(times),max_score_error=err,work=dict(work))
        results[mode]=dict(**size,source_checks=len(events),setup_us=setup,prepare=quant(pt),splits=splits)
        print("ARM_JSON="+json.dumps(dict(mode=mode,**results[mode])),flush=True);db.close();path.unlink()
    return dict(round=188,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_counts={k:len(v) for k,v in groups.items()},query_hashes={k:h.sha(h.canonical(v)).hex() for k,v in groups.items()},
        anchors_sha256=anchor_sig,policies=results,limitations=["finalized source/index subset; no atomic receipt integration",
        "UTF-8 normalized token keys charge actual byte lengths, no uncharged lexicon",
        "identical source archive and index anchors; exact full active phrase frequency maps matched to signed control",
        "prefix cache budget estimated from encoded rows and block table pages before finalization; actual SQLite bytes charged",
        "content-derived query plans, two warm passes, no physical I/O or peak RSS",
        "no checksum for residual records, no arbitrary positional syntax, no RH proof theorem used"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="clark":
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex()
            assert manifest=="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f"
            n=len(events);cuts=[n//4,n//2,3*n//4,n]
        else:
            events,_,m=nr.load(a.source,a.target,folder);manifest=m["source_manifest_sha256"]
            n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            assert manifest==json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
