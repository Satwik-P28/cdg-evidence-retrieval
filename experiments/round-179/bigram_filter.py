"""Independent R179: query-independent adjacency rejection, exact source fallback."""
import argparse,collections,hashlib,json,random,struct,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-165"))
import selective_positions as sp
from frequency_index import f,h,si,connect,nr,tokens,query_plan,prepare,recover
import token_tape as tt
import signed_phrase as signed

def pairmask(a,b,m):
    digest=hashlib.blake2b(struct.pack(">I",len(a))+a+b,digest_size=16).digest()
    x,y=struct.unpack(">QQ",digest);y|=1
    out=0
    for i in range(3):out|=1<<((x+i*y)%m)
    return out

def mask_for(ts,m):
    mask=0
    for a,b in zip(ts,ts[1:]):mask|=pairmask(a,b,m)
    return mask

def checksum(cid,m,digest,blob):
    return hashlib.blake2b(struct.pack(">QI",cid,m)+digest+blob,digest_size=16).digest()

def build_filter(db,path,events,mode):
    db.execute("CREATE TABLE adjacency(cid INTEGER PRIMARY KEY,m INTEGER NOT NULL,body BLOB NOT NULL,tag BLOB NOT NULL)")
    rawbytes=0;distribution=collections.Counter();t=time.perf_counter_ns()
    for cid,digest in db.execute("SELECT c.cid,s.digest FROM contents c JOIN source s ON s.g=c.cid ORDER BY c.cid"):
        ts=tokens(db,events[cid-1][2].decode("utf8"))
        n=len(set(zip(ts,ts[1:])))
        if mode=="adaptive":
            m=min(4096,max(256,1<<(max(1,8*n)-1).bit_length()))
        else:m=int(mode)
        blob=mask_for(ts,m).to_bytes(m//8,"little")
        db.execute("INSERT INTO adjacency VALUES(?,?,?,?)",(cid,m,blob,checksum(cid,m,digest,blob)))
        rawbytes+=len(blob);distribution[m]+=1
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return dict(sqlite_bytes=path.stat().st_size,table_bytes=sizes,filter_table_bytes=sizes["adjacency"],
                filter_payload_bytes=rawbytes,filter_width_counts=dict(distribution),filter_build_us=(time.perf_counter_ns()-t)/1000)

def load_filter(db):
    masks={};invalid=0
    for cid,m,blob,tag,digest in db.execute("""SELECT a.cid,a.m,a.body,a.tag,s.digest FROM adjacency a
        JOIN contents c ON c.cid=a.cid JOIN source s ON s.g=c.cid"""):
        if (m not in (256,512,1024,2048,4096) or not isinstance(blob,bytes) or
            len(blob)!=m//8 or checksum(cid,m,digest,blob)!=tag):
            invalid+=1;continue
        masks[cid]=(m,int.from_bytes(blob,"little"))
    return masks,invalid

def rejector(masks):
    def filter_candidates(qs,candidates):
        needs={};passed=set()
        for cid in candidates:
            row=masks.get(cid)
            if row is None:passed.add(cid);continue
            m,mask=row
            if m not in needs:needs[m]=mask_for(qs,m)
            need=needs[m]
            if mask&need==need:passed.add(cid)
        return passed
    return filter_candidates

def extended_plan(events,db,old):
    rng=random.Random(179);seen=set(old);extra=[]
    # Fixed workload independent of filter representation or query performance.
    late=list(range(len(events)//2,len(events)));rng.shuffle(late)
    for j in late:
        ts=tokens(db,events[j][2].decode("utf8"))
        if len(ts)<2:continue
        n=rng.randint(2,min(8,len(ts)));i=rng.randrange(len(ts)-n+1)
        q=((b" ".join(ts[i:i+n]).decode(),),"AND")
        if q not in seen and '"' not in q[0][0]:
            seen.add(q);extra.append(q)
        if len(extra)>=96:break
    # Frequent-token combinations likely to have large unigram intersections.
    df=collections.Counter()
    for _,_,raw in events[:min(2000,len(events))]:
        df.update(set(tokens(db,raw.decode("utf8"))))
    common=[t for t,_ in df.most_common(32)]
    for _ in range(2000):
        if len(common)<2 or len(extra)>=160:break
        q=((b" ".join(rng.choices(common,k=rng.randint(2,8))).decode(),),"AND")
        if q not in seen and '"' not in q[0][0]:
            seen.add(q);extra.append(q)
    return extra

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    checker=connect(":memory:",ext)
    old=[(p,o) for p,o in query_plan(events,cuts[0],refs[cuts[0]]) if all(1<=len(tokens(checker,x))<=8 for x in p)]
    new=extended_plan(events,checker,old);checker.close()
    groups={"legacy":old,"extended":new};expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in old+new}
    results={};sigs={}
    for mode in ("positional","signed","frequency","512","1024","adaptive"):
        path=folder/(mode+".sqlite");db,size=f.build(path,ext,events,"marginal",False)
        if mode=="signed":size.update(signed.build_delta(db,path,events,"independent_adaptive_multi"))
        elif mode!="positional":
            size.update(tt.build_tape(db,path,events,"frequency"))
            if mode!="frequency":size.update(build_filter(db,path,events,mode))
        db.close();db=connect(path,ext);ids={};mapping=None;masks={};flt=None
        start=time.perf_counter_ns()
        if mode=="signed":mapping=signed.load_patch_map(db)
        elif mode!="positional":
            ids,_=tt.vocabulary(db)
            if mode!="frequency":
                masks,bad=load_filter(db);assert not bad and len(masks)==db.execute("SELECT count(*) FROM contents").fetchone()[0]
                flt=rejector(masks)
        setup=(time.perf_counter_ns()-start)/1000
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g);assert raw==want
            assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        preps={c:signed.prepare_delta(db,c,mapping) if mode=="signed" else prepare(db,c) for c in cuts}
        stats={}
        for label,queries in groups.items():
            plan=[(c,p,o) for c in cuts for p,o in queries];rng=random.Random(179);times=[];work=collections.Counter();err=0.
            for _ in range(2):
                rng.shuffle(plan)
                for c,p,o in plan:
                    t=time.perf_counter_ns()
                    if mode=="positional":hits,df=si.rank(db,1,p,o,preps[c])
                    elif mode=="signed":hits,df,w=signed.rank_delta(db,p,o,preps[c]);work.update(w)
                    else:hits,df,w=sp.rank_selective(db,p,o,preps[c],ids,set(),flt);work.update(w)
                    times.append((time.perf_counter_ns()-t)/1000)
                    err=max(err,h.verify(hits,expected[c,p,o]))
                    if (c,p,o) in sigs:assert sigs[c,p,o]==(hits,df)
                    else:sigs[c,p,o]=(hits,df)
            ordered=sorted(times);quant=h.quant(times)
            quant["p99_us"]=ordered[int(.99*(len(ordered)-1))];quant["max_us"]=ordered[-1]
            stats[label]=dict(query=quant,rank_checks=len(times),score_error=err,work=dict(work))
        results[mode]=dict(**size,setup_us=setup,source_checks=len(events),
            resident_mask_payload_bytes=sum(m//8 for m,_ in masks.values()),splits=stats)
        print("ARM_JSON="+json.dumps(dict(mode=mode,**results[mode])),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=179,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_counts={k:len(v) for k,v in groups.items()},query_hashes={k:h.sha(h.canonical(v)).hex() for k,v in groups.items()},policies=results,
        limitations=["finalized source/index subset, no transaction or receipt integration","legacy and extended synthetic query workloads, not human search logs",
        "filter masks resident after measured setup; payload bytes not peak memory","complete SQLite file includes source and frequency postings, filter bytes included",
        "checksums detect accidental corruption, not adversarial replacement; no physical IO claim","all remaining candidate phrase frequencies verified from original source"])

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
