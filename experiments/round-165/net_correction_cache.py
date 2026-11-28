"""R190: materialize exact net corrections on the existing signed FTS index.
No suffix residual index. Fixed corpus-derived candidates and physical size caps.
"""
import argparse,collections,hashlib,json,random,shutil,tempfile,time
from pathlib import Path
import signed_phrase as sp
from signed_phrase import f,h,si,nr,ar,connect,prepare,recover
from real_residuals import key,pack,unpack,plans,quant,MODE
HERE=Path(__file__).resolve().parent

def candidates_capture(out):
    def capture(db,pending,stats):
        # Count unique windows once, weight by number of distinct child uses.
        # Independent of evaluation queries.
        uses=collections.Counter(w for _,m in pending for w in m)
        tokens=collections.Counter()
        for w,n in uses.items():
            for t in set(w):tokens[t]+=n
        common={t for t,_ in sorted(tokens.items(),key=lambda x:(-x[1],x[0]))[:128]}
        support=collections.Counter()
        for w,n in uses.items():
            for q in {w[i:i+l] for i in range(len(w)) for l in (2,3)
                      if i+l<=len(w) and all(t in common for t in w[i:i+l])}:
                support[q]+=n
        out.extend((t,) for t in sorted(common))
        out.extend(q for q,_ in sorted(support.items(),key=lambda x:(-x[1],x[0]))[:512])
        stats["cache_candidates"]=len(out)
        return pending
    return capture

def measure_candidates(db,candidates):
    mapping=sp.load_patch_map(db);rows=[]
    for q in candidates:
        text=b" ".join(q).decode("utf8")
        if tuple(sp.tokens(db,text))!=q:raise ValueError("token roundtrip")
        counts=collections.Counter();visits=hits=0
        for rid,tf in db.execute("SELECT rowid,cdg_count(patch_fts) FROM patch_fts WHERE patch_fts MATCH ?",(ar.quote(text),)):
            hits+=1
            for cid,c in mapping.get(rid,()):
                visits+=1;counts[cid]+=c*tf
        postings=sorted((cid,c) for cid,c in counts.items() if c)
        k=key(q);body=pack(postings,True)
        # Explicit empty posting lists are valid cached zero corrections.
        # Charge key, digest, encoded body and row-overhead proxy.
        cost=len(k)+len(body)+16+12
        gain=hits+visits-len(postings)
        rows.append(dict(k=k,body=body,hits=hits,visits=visits,net=len(postings),
                         cost=cost,gain=gain))
    return rows

def digest(k,body):
    return hashlib.blake2b(k+body,digest_size=16).digest()

def install_cache(db,path,base_bytes,rows,mode,permille=10):
    cap=base_bytes*permille//1000;start=time.perf_counter_ns()
    # Structural score, not workload frequency. Compare against native row
    # frequency under the same physical archive increment cap.
    if mode=="cancellation":
        order=sorted((r for r in rows if r["gain"]>0),key=lambda r:(-r["gain"]/r["cost"],r["k"]))
    else:
        order=sorted((r for r in rows if r["hits"]>0),key=lambda r:(-r["hits"],r["k"]))
    if not order or cap<4096:return dict(cache_budget_bytes=cap,cache_entries=0)
    db.execute("CREATE TABLE net_cache(k BLOB PRIMARY KEY,body BLOB NOT NULL,tag BLOB NOT NULL) WITHOUT ROWID")
    chosen=[];spent=0
    for r in order:
        if spent+r["cost"]>cap:continue
        db.execute("INSERT INTO net_cache VALUES(?,?,?)",(r["k"],r["body"],digest(r["k"],r["body"])))
        chosen.append(r);spent+=r["cost"]
    db.commit();db.execute("VACUUM")
    # Real measured file cap, not just a payload proxy. Remove lowest
    # priority entries and compact until the actual archive fits.
    while path.stat().st_size>base_bytes+cap and chosen:
        n=max(1,len(chosen)//8)
        for r in chosen[-n:]:db.execute("DELETE FROM net_cache WHERE k=?",(r["k"],))
        del chosen[-n:];db.commit();db.execute("VACUUM")
    if not chosen:
        db.execute("DROP TABLE net_cache");db.commit();db.execute("VACUUM")
    assert path.stat().st_size<=base_bytes+cap
    return dict(cache_budget_bytes=cap,cache_entries=len(chosen),
        cache_empty=sum(r["net"]==0 for r in chosen),
        cache_candidate_count=len(rows),cache_proxy_bytes=sum(r["cost"] for r in chosen),
        cache_estimated_saved_work=sum(r["gain"] for r in chosen),
        cache_physical_increment=path.stat().st_size-base_bytes,
        cache_build_us=(time.perf_counter_ns()-start)/1000)

def cache_reader(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='net_cache'").fetchone():return None
    def read(db,q,active,counts,work):
        if len(q)>3:return False
        k=key(q);row=db.execute("SELECT body,tag FROM net_cache WHERE k=?",(k,)).fetchone()
        if row is None:work["cache_misses"]+=1;return False
        body,tag=row
        if digest(k,body)!=tag:
            work["cache_bad_tag"]+=1;return False
        # Fully decode before updating counts, so malformed records can
        # safely fall back without a partial signed correction.
        try:entries=list(unpack(body))
        except (ValueError,IndexError,OverflowError):work["cache_bad_body"]+=1;return False
        for cid,c in entries:
            if cid in active:counts[cid]+=c;work["cache_active_postings"]+=1
        work["cache_hits"]+=1;work["cache_postings"]+=len(entries);work["cache_bytes"]+=len(body)
        return True
    return read

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts};groups=plans(events,cuts,refs,ext)
    expected={(c,p,o):h.native(refs[c],p,o) for c in cuts for qs in groups.values() for p,o in qs}
    for ref in refs.values():ref.close()
    root=folder/"source.sqlite";db,size0=f.build(root,ext,events,"marginal",False);db.close()
    signed=folder/"signed.sqlite";shutil.copyfile(root,signed);db=connect(signed,ext)
    candidates=[];ss=sp.build_delta(db,signed,events,MODE,candidates_capture(candidates))
    t=time.perf_counter_ns();rows=measure_candidates(db,candidates);candidate_us=(time.perf_counter_ns()-t)/1000
    db.close();base_bytes=signed.stat().st_size
    sigs={};freq_sigs={};results={}
    for mode,policy,cap in (("positional",None,0),("signed",None,0),
                            ("frequency_1pct","frequency",10),("cancellation_1pct","cancellation",10),
                            ("cancellation_halfpct","cancellation",5)):
        path=folder/(mode+"-eval.sqlite")
        shutil.copyfile(root if mode=="positional" else signed,path);db=connect(path,ext)
        size=dict(size0 if mode=="positional" else ss)
        if policy:size.update(install_cache(db,path,base_bytes,rows,policy,cap))
        db.close();db=connect(path,ext)
        size.update(sqlite_bytes=path.stat().st_size,table_bytes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name")))
        for g,(_,_,raw) in enumerate(events,1):
            got,dd,ab=recover(db,g);assert got==raw and 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        t=time.perf_counter_ns()
        mapping=sp.load_patch_map(db) if mode!="positional" else None
        rd=cache_reader(db) if policy else None
        setup=(time.perf_counter_ns()-t)/1000;preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns();preps[c]=prepare(db,c) if mode=="positional" else sp.prepare_delta(db,c,mapping)
            pt.append((time.perf_counter_ns()-t)/1000)
        splits={}
        for group,qs in groups.items():
            if not qs:continue
            plan=[(c,p,o) for c in cuts for p,o in qs];rng=random.Random(190);times=[];work=collections.Counter();err=0.
            for _ in range(3):
                rng.shuffle(plan)
                for c,p,o in plan:
                    sink=[];t=time.perf_counter_ns()
                    if mode=="positional":hits,df=si.rank(db,1,p,o,preps[c])
                    else:hits,df,w=sp.rank_delta(db,p,o,preps[c],frequency_sink=sink,patch_cache=rd)
                    times.append((time.perf_counter_ns()-t)/1000)
                    if mode!="positional":work.update(w)
                    err=max(err,h.verify(hits,expected[c,p,o]));k=(c,p,o)
                    if mode=="positional":sigs[k]=(hits,df)
                    else:
                        assert sigs[k]==(hits,df)
                        signature=h.sha(h.canonical([sorted(m.items()) for m in sink])).hex()
                        if mode=="signed":freq_sigs[k]=signature
                        else:assert freq_sigs[k]==signature
            splits[group]=dict(query=quant(times),rank_checks=len(times),max_score_error=err,work=dict(work))
        results[mode]=dict(**size,source_checks=len(events),setup_us=setup,prepare=quant(pt),splits=splits)
        print("ARM_JSON="+json.dumps(dict(mode=mode,**results[mode])),flush=True);db.close();path.unlink()
    return dict(round=190,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_counts={k:len(v) for k,v in groups.items()},query_hashes={k:h.sha(h.canonical(v)).hex() for k,v in groups.items()},
        candidate_measure_us=candidate_us,policies=results,
        limitations=["same finalized signed source/index archive; no transactional append",
        "candidate pool from corpus statistics, not evaluation queries; same R188 workload",
        "physical file increment capped after VACUUM; no guaranteed cold device IO",
        "checksum detects accidental cache corruption; missing/invalid cache falls back to native patch index",
        "cache entries derived from immutable signed archive, not independently authenticated",
        "sequential arm timings, three shuffled warm passes, no peak RSS or RH theorem application"])

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
