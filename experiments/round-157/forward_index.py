"""R157: presence postings plus bounded materialized token predictor.
Finalized source/index subset. No transactional provenance claim.
"""
import argparse,collections,json,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-156"))
import self_index as si
from self_index import connect,h,nr,ar,tokens,query_plan,D,delta_decode,prepare

def build(path,ext,events,mode,presence):
    block=0
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
      CREATE TABLE contents(cid INTEGER PRIMARY KEY,shard INTEGER NOT NULL);
      CREATE TABLE source(g INTEGER PRIMARY KEY,digest BLOB NOT NULL,n INTEGER NOT NULL,
        kind INTEGER NOT NULL,parent INTEGER NOT NULL,fid INTEGER NOT NULL);
      CREATE TABLE frames(fid INTEGER PRIMARY KEY,body BLOB NOT NULL);
      CREATE TABLE predictors(cid INTEGER PRIMARY KEY,n INTEGER NOT NULL,body BLOB NOT NULL);
    """)
    known={};heads={};hist=collections.defaultdict(list);frames={};recipes=[None]
    total=0;shards=0;stats=collections.Counter();start=time.perf_counter_ns()
    for g,(a,i,raw) in enumerate(events,1):
        digest=h.sha(raw);known_row=known.get(digest)
        if known_row is None:
            ts=tokens(db,raw.decode("utf8"));dl=len(ts)
            canonical=b" ".join(ts);cid=g;shard=len(known)//block if block else 0
            if shard==shards:
                detail=",detail=none,columnsize=0" if presence else ""
                db.execute(f"CREATE VIRTUAL TABLE docs_{shard} USING fts5(body,content=''{detail})");shards+=1
            db.execute(f"INSERT INTO docs_{shard}(rowid,body) VALUES(?,?)",(cid,raw.decode("utf8")))
            db.execute("INSERT INTO contents VALUES(?,?)",(cid,shard))
            known[digest]=(cid,dl,shard)
        else:
            cid,dl,shard=known_row;assert events[cid-1][2]==raw
            canonical=None
        full=h.C.compress(raw);local=hist[a];assert len(local)==i
        def frame_cost(frame):
            row=frames.get(h.sha(frame))
            if row is not None:
                assert row[1]==frame;return 0
            return len(frame)+48
        if mode=="marginal":
            # Same source encoding decision as R149, including 48 B catalog proxy.
            choices=[(0,0,full,len(raw),len(full))]
            for j in [j for j in reversed(local) if recipes[j][0]==0][:4]:
                parent=events[j-1][2];encoded=recipes[j][2]
                if 2*(len(parent)+len(raw))>5*len(raw):continue
                diff=h.delta_encode(raw,parent)
                if diff is not None and 5*len(diff)<=4*len(full) and 2*(len(encoded)+len(diff))<=3*len(full):
                    choices.append((1,j,diff,len(parent)+len(raw),len(encoded)+len(diff)))
            kind,parent,frame,_,_=min(choices,key=lambda x:(frame_cost(x[2]),x[3],x[4],len(x[2]),-x[1]))
        elif known_row is not None:
            kind,parent,frame=recipes[cid]
        else:
            kind,parent,frame=0,0,full
            if canonical and 2*(len(canonical)+len(raw))<=5*len(raw):
                diff=h.delta_encode(raw,canonical);pred=h.C.compress(canonical)
                if diff is not None and 5*len(diff)<=4*len(full) and 2*(len(pred)+len(diff))<=3*len(full):
                    kind,parent,frame=2,0,diff
                    assert delta_decode(frame,canonical,len(raw))==raw
                    db.execute('INSERT INTO predictors VALUES(?,?,?)',(cid,len(canonical),pred))
        key=h.sha(frame)
        if key not in frames:
            fid=len(frames)+1;frames[key]=(fid,frame)
            db.execute("INSERT INTO frames VALUES(?,?)",(fid,frame))
        else:
            fid,old=frames[key];assert old==frame
        db.execute("INSERT INTO source VALUES(?,?,?,?,?,?)",(g,digest,len(raw),kind,parent,fid))
        recipes.append((kind,parent,frame));local.append(g);stats["kind_"+str(kind)]+=1
        if a in heads:
            old_g,old_i,old_dl=heads[a];assert i==old_i+1
            db.execute("UPDATE revisions SET end_g=? WHERE g=?",(g,old_g));total-=old_dl
        else:assert i==0
        db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,NULL)",(g,a,i,cid,dl))
        heads[a]=(g,i,dl);total+=dl
        db.execute("INSERT INTO active_stats VALUES(?,?,?)",(g,len(heads),total))
    db.execute("CREATE INDEX revision_cid ON revisions(cid,g)")
    db.commit()
    for shard in range(shards):db.execute(f"INSERT INTO docs_{shard}(docs_{shard}) VALUES('optimize')")
    db.commit();db.execute("VACUUM")
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    pred_bytes=db.execute('SELECT coalesce(sum(length(body)),0) FROM predictors').fetchone()[0]
    return db,dict(predictor_bytes=pred_bytes,sqlite_bytes=path.stat().st_size,frame_payload_bytes=sum(len(x[1]) for x in frames.values()),
        unique_frames=len(frames),unique_contents=len(known),shards=shards,
        max_shard_rows=db.execute("SELECT max(n) FROM (SELECT count(*) n FROM contents GROUP BY shard)").fetchone()[0],
        fts_bytes=sum(v for k,v in sizes.items() if k.startswith("docs_")),table_bytes=sizes,
        build_us=(time.perf_counter_ns()-start)/1000,**stats)


def predictor(db,cid):
    row=db.execute("SELECT n,body FROM predictors WHERE cid=?",(cid,)).fetchone()
    if row is None:return None,0
    n,frame=row
    raw=D.decompress(frame,max_output_size=n+1)
    assert len(raw)==n
    return raw,len(frame)

def recover(db,g):
    digest,n,kind,parent,frame,cid=db.execute("""
      SELECT s.digest,s.n,s.kind,s.parent,f.body,r.cid FROM source s
      JOIN frames f ON f.fid=s.fid JOIN revisions r ON r.g=s.g WHERE s.g=?""",(g,)).fetchone()
    if kind==0:raw=D.decompress(frame,max_output_size=n+1);dd=n;ab=len(frame)
    elif kind==1:
        assert parent<g
        old_n,old_kind,old_frame=db.execute("SELECT s.n,s.kind,f.body FROM source s JOIN frames f ON f.fid=s.fid WHERE s.g=?",(parent,)).fetchone()
        assert old_kind==0
        old=D.decompress(old_frame,max_output_size=old_n+1)
        raw=delta_decode(frame,old,n);dd=n+old_n;ab=len(frame)+len(old_frame)
    else:
        assert kind==2 and parent==0
        pred,cost=predictor(db,cid);assert pred is not None
        raw=delta_decode(frame,pred,n);dd=n+len(pred);ab=len(frame)+cost
    assert len(raw)==n and h.sha(raw)==digest
    return raw,dd,ab

def phrase_count(canonical,query):
    # unicode61 token sequence joined by one ASCII space. Match both
    # token boundaries; advance one byte to preserve overlapping starts.
    assert query and all(q and b" " not in q for q in query)
    needle=b" "+b" ".join(query)+b" ";hay=b" "+canonical+b" ";n=0;pos=0
    while True:
        at=hay.find(needle,pos)
        if at<0:return n
        n+=1;pos=at+1

def rank_presence(db,p,o,prepared):
    ar.expression(p,o);active,lens,n,total=prepared;freq=[];cache={};candidates=0;read_bytes=0
    for phrase in p:
        qs=tokens(db,phrase);assert qs
        expr=" AND ".join(ar.quote(t.decode("utf8")) for t in dict.fromkeys(qs))
        matches={}
        for cid, in db.execute("SELECT rowid FROM docs_0 WHERE docs_0 MATCH ?",(expr,)):
            if cid not in active:continue
            candidates+=1
            if cid not in cache:
                pred,cost=predictor(db,cid)
                if pred is None:
                    raw,_,cost=recover(db,cid);pred=b" ".join(tokens(db,raw.decode("utf8")))
                cache[cid]=pred;read_bytes+=cost
            tf=phrase_count(cache[cid],qs)
            if tf:
                for g in active[cid]:
                    assert 1<=tf<=lens[g];matches[g]=tf
        freq.append(matches)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,candidates,read_bytes

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(157);results={};sig={}
    for name,mode,presence in [("marginal_positional","marginal",False),("marginal_presence","marginal",True),("forward_positional","forward",False),("forward_presence","forward",True)]:
        path=folder/(name+".sqlite");db,size=build(path,ext,events,mode,presence);db.close();db=connect(path,ext)
        rawbytes=decoded=activated=0;maxd=maxa=0.;start=time.perf_counter_ns()
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g);assert raw==want
            f=len(h.C.compress(want))
            assert 2*dd<=5*len(want) and 2*ab<=3*f
            rawbytes+=len(raw);decoded+=dd;activated+=ab
            if raw:maxd=max(maxd,dd/len(raw))
            maxa=max(maxa,ab/f)
        audit_us=(time.perf_counter_ns()-start)/1000
        sample=random.Random(157).sample(range(1,len(events)+1),min(64,len(events)))
        reads=[]
        for g in sample:
            t=time.perf_counter_ns();raw,_,_=recover(db,g);reads.append((time.perf_counter_ns()-t)/1000)
            assert raw==events[g-1][2]
        prep={c:prepare(db,c) for c in cuts};times=[];err=0.;cand=io=0
        plan=list(expected);rng.shuffle(plan)
        for c,p,o in plan:
            t=time.perf_counter_ns()
            if presence:
                hits,df,k,b=rank_presence(db,p,o,prep[c]);cand+=k;io+=b
            else:hits,df=si.rank(db,1,p,o,prep[c])
            times.append((time.perf_counter_ns()-t)/1000)
            err=max(err,h.verify(hits,expected[c,p,o]))
            if (c,p,o) in sig:assert sig[c,p,o]==(hits,df)
            else:sig[c,p,o]=(hits,df)
        if corpus=="ap" and mode=="marginal":
            old=json.loads((HERE.parent/"round-149"/("results-"+str(len(events))+"-original.json")).read_text())
            assert size["frame_payload_bytes"]==old["policies"]["marginal"]["payload_bytes"]
        results[name]=dict(**size,source_checks=len(events),audit_us=audit_us,read=h.quant(reads),
            mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
            activated_source_bytes=activated,query=h.quant(times),rank_checks=len(times),max_score_error=err,
            candidate_content_occurrences=cand,query_activated_frame_bytes=io)
        print("ARM_JSON="+json.dumps(results[name]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=157,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(queries),policies=results,limitations=[
        "finalized matched source/index subset, no provenance or transaction integration",
        "presence index filters exact token conjunction, exact overlapping phrase counts verified in forward stream or reconstructed raw",
        "forward predictor and residual both charged in source activation bound, logical bytes only, no physical page/CPU bound",
        "one warm shuffled query pass and 64 uniform reads; query cache only within one request",
        "forward admission compares source byte bounds, not total optimal storage; no novel indexing primitive claim",
        "AP synthetic global schedule"])

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
