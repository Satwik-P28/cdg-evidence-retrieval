"""R156: physical finalized source+index self-reconstruction feasibility.

Use native positional postings to recover normalized token bytes, then
decode a Zstd residual against that predictor. Sharding bounds the
number of indexed content rows visited, NOT physical decoded bytes.
"""
import argparse,collections,json,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-154"))
from fragment_index import connect,h,nr,ar,tokens,query_plan
from anchor_bench import D,delta_decode

def build(path,ext,events,mode,block):
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
      CREATE TABLE contents(cid INTEGER PRIMARY KEY,shard INTEGER NOT NULL);
      CREATE TABLE source(g INTEGER PRIMARY KEY,digest BLOB NOT NULL,n INTEGER NOT NULL,
        kind INTEGER NOT NULL,parent INTEGER NOT NULL,fid INTEGER NOT NULL);
      CREATE TABLE frames(fid INTEGER PRIMARY KEY,body BLOB NOT NULL);
    """)
    known={};heads={};hist=collections.defaultdict(list);frames={};recipes=[None]
    total=0;shards=0;stats=collections.Counter();start=time.perf_counter_ns()
    for g,(a,i,raw) in enumerate(events,1):
        digest=h.sha(raw);known_row=known.get(digest)
        if known_row is None:
            ts=tokens(db,raw.decode("utf8"));dl=len(ts)
            canonical=b" ".join(ts);cid=g;shard=len(known)//block if block else 0
            if shard==shards:
                db.execute(f"CREATE VIRTUAL TABLE docs_{shard} USING fts5(body,content='')");shards+=1
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
                diff=h.delta_encode(raw,canonical)
                if diff is not None and 5*len(diff)<=4*len(full) and frame_cost(diff)<frame_cost(full):
                    kind,parent,frame=2,0,diff
                    assert delta_decode(frame,canonical,len(raw))==raw
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
    return db,dict(sqlite_bytes=path.stat().st_size,frame_payload_bytes=sum(len(x[1]) for x in frames.values()),
        unique_frames=len(frames),unique_contents=len(known),shards=shards,
        max_shard_rows=db.execute("SELECT max(n) FROM (SELECT count(*) n FROM contents GROUP BY shard)").fetchone()[0],
        fts_bytes=sum(v for k,v in sizes.items() if k.startswith("docs_")),table_bytes=sizes,
        build_us=(time.perf_counter_ns()-start)/1000,**stats)

def create_vocab(db,shard):
    db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS temp.v_{shard} USING fts5vocab(main,docs_{shard},'instance')")

def normalized(db,shard,cid,dl):
    create_vocab(db,shard)
    out=[]
    for term,offset in db.execute(f"SELECT term,offset FROM temp.v_{shard} WHERE doc=? ORDER BY offset",(cid,)):
        assert offset==len(out);out.append(term.encode("utf8"))
    assert len(out)==dl
    return b" ".join(out)

def batch_predictors(db,shards):
    """One scan per shard, sorted by content/position; no raw input used."""
    for shard in range(shards):
        create_vocab(db,shard)
        dl=dict(db.execute("SELECT DISTINCT r.cid,r.dl FROM revisions r JOIN contents c ON c.cid=r.cid WHERE c.shard=?",(shard,)))
        current=None;out=[];seen=set()
        for cid,term,offset in db.execute(f"SELECT doc,term,offset FROM temp.v_{shard} ORDER BY doc,offset"):
            if cid!=current:
                if current is not None:
                    assert len(out)==dl[current];seen.add(current);yield current,b" ".join(out)
                current=cid;out=[]
            assert offset==len(out);out.append(term.encode("utf8"))
        if current is not None:
            assert len(out)==dl[current];seen.add(current);yield current,b" ".join(out)
        for cid in set(dl)-seen:
            assert dl[cid]==0;yield cid,b""

def recover(db,g,predictor=None):
    digest,n,kind,parent,frame,cid,dl,shard=db.execute("""
       SELECT s.digest,s.n,s.kind,s.parent,f.body,r.cid,r.dl,c.shard FROM source s
       JOIN frames f ON f.fid=s.fid JOIN revisions r ON r.g=s.g JOIN contents c ON c.cid=r.cid
       WHERE s.g=?""",(g,)).fetchone()
    if kind==0:raw=D.decompress(frame,max_output_size=n+1)
    elif kind==1:
        assert parent<g
        old_n,old_kind,old_frame=db.execute("SELECT s.n,s.kind,f.body FROM source s JOIN frames f ON f.fid=s.fid WHERE s.g=?",(parent,)).fetchone()
        assert old_kind==0
        old=D.decompress(old_frame,max_output_size=old_n+1)
        raw=delta_decode(frame,old,n)
    else:
        assert kind==2 and parent==0
        if predictor is None:predictor=normalized(db,shard,cid,dl)
        raw=delta_decode(frame,predictor,n)
    assert len(raw)==n and h.sha(raw)==digest
    return raw

def prepare(db,c):
    active=collections.defaultdict(list);lens={}
    for g,cid,dl in db.execute("SELECT g,cid,dl FROM revisions WHERE g<=? AND (end_g IS NULL OR end_g>?)",(c,c)):
        active[cid].append(g);lens[g]=dl
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    assert len(lens)==n and sum(lens.values())==total
    return active,lens,n,total

def rank(db,shards,p,o,prepared):
    active,lens,n,total=prepared;freq=[]
    ar.expression(p,o)
    for phrase in p:
        matches={}
        for shard in range(shards):
            table=f"docs_{shard}"
            for cid,tf,dl in db.execute(f"SELECT rowid,cdg_count({table}),cdg_length({table}) FROM {table} WHERE {table} MATCH ?",(ar.quote(phrase),)):
                for g in active.get(cid,()):
                    assert 1<=tf<=dl and lens[g]==dl;matches[g]=tf
        freq.append(matches)
    return ar.score(freq,o,n,total,lens)

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(156);results={};sig={}
    for name,mode,block in [("marginal","marginal",0),("self_unsharded","self",0),("self_512","self",512),("self_128","self",128)]:
        path=folder/(name+".sqlite");db,size=build(path,ext,events,mode,block)
        # Reopen before verification: only persisted index and source frames used.
        db.close();db=connect(path,ext);shards=size["shards"]
        start=time.perf_counter_ns();checks=0
        if mode=="self":
            for cid,predictor in batch_predictors(db,shards):
                for g, in db.execute("SELECT g FROM revisions WHERE cid=?",(cid,)):
                    assert recover(db,g,predictor)==events[g-1][2];checks+=1
        else:
            for g,(_,_,raw) in enumerate(events,1):assert recover(db,g)==raw;checks+=1
        assert checks==len(events);audit_us=(time.perf_counter_ns()-start)/1000
        # Same fixed uniform revision samples; additional residual-only sample
        # reports the expensive index-assisted path without dilution by literals.
        sample=random.Random(156).sample(range(1,len(events)+1),min(12,len(events)))
        residuals=[g for g, in db.execute("SELECT g FROM source WHERE kind=2 ORDER BY g")]
        residual_sample=random.Random(157).sample(residuals,min(8,len(residuals)))
        def measure(ids):
            times=[]
            for g in ids:
                t=time.perf_counter_ns();assert recover(db,g)==events[g-1][2]
                times.append((time.perf_counter_ns()-t)/1000)
            return h.quant(times) if times else None
        read=measure(sample);residual_read=measure(residual_sample)
        prep={c:prepare(db,c) for c in cuts};times=[];err=0.
        plan=list(expected);rng.shuffle(plan)
        for c,p,o in plan:
            t=time.perf_counter_ns();hits,df=rank(db,shards,p,o,prep[c]);times.append((time.perf_counter_ns()-t)/1000)
            err=max(err,h.verify(hits,expected[c,p,o]))
            if (c,p,o) in sig:assert sig[c,p,o]==(hits,df)
            else:sig[c,p,o]=(hits,df)
        if corpus=="ap" and mode=="marginal":
            old=json.loads((HERE.parent/"round-149"/("results-"+str(len(events))+"-original.json")).read_text())
            assert size["frame_payload_bytes"]==old["policies"]["marginal"]["payload_bytes"]
        results[name]=dict(**size,source_checks=checks,audit_us=audit_us,uniform_read=read,residual_read=residual_read,
            query=h.quant(times),rank_checks=len(times),max_score_error=err)
        print("ARM_JSON="+json.dumps(results[name]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=156,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(queries),policies=results,limitations=[
          "physical finalized source+index subset, identical revision/source schemas; no transactional provenance ledger, not full R151 archive",
          "Zstd residual uses reconstructed normalized bytes as dictionary, source identity separate; no semantic normalization equivalence claim",
          "logical predictor length admission only; index scan cost not bounded by source-frame activation",
          "shards cap content rows, not postings bytes; every query fans out across shards",
          "one shuffled query pass, tiny random read sample, warm descriptive timing; no production guarantees",
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
