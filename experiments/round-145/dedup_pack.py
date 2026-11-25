"""R145: transactional exact encoded-frame reuse. Separate from R144 v2."""
import argparse,hashlib,json,os,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
import news_retrieval as nr
import transactional_pack as tp
import heldout_archive as h
from transactional_pack import PTR,write_all,die,recover,reconcile_locked

def setup(path,ext,manifest):
    db=tp.setup(path,ext,manifest)
    db.execute("CREATE TABLE frame_catalog(digest BLOB PRIMARY KEY CHECK(length(digest)=32),off INTEGER NOT NULL CHECK(off>=32),n INTEGER NOT NULL CHECK(n>0)) WITHOUT ROWID")
    db.commit();return db

def append(db,fd,a,raw,origin,policy="bounded_anchor",fault=None):
    if db.in_transaction or policy not in ("snapshot","bounded_anchor"):raise ValueError("bad writer")
    text=raw.decode("utf8");commit,ts,blob=origin
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
    db.execute("BEGIN IMMEDIATE")
    try:
        end=reconcile_locked(db,fd)
        prior=h.generation(db);g=prior+1
        prev_total,prev_hash=db.execute("SELECT total,prefix_sha FROM rank_ledger WHERE g=?",(prior,)).fetchone() if prior else (0,h.SEED)
        rows=db.execute("SELECT ord,depth,payload FROM versions WHERE article=? ORDER BY ord",(a,)).fetchall()
        if any(j!=v[0] for j,v in enumerate(rows)):raise ValueError("ordinal")
        i=len(rows);hist=[(b"",PTR.unpack(ptr)[1],dep) for _,dep,ptr in rows]
        if policy=="bounded_anchor":
            for j in [j for j in range(i-1,-1,-1) if rows[j][1]==0][:4]:
                old,_,_,dep=recover(db,fd,a,j,0);hist[j]=(old,hist[j][1],dep)
            parent,depth,payload=h.choose_config(raw,i,hist,policy)
        else:parent,depth,payload=None,0,h.C.compress(raw)
        key=h.sha(payload);found=db.execute("SELECT off,n FROM frame_catalog WHERE digest=?",(key,)).fetchone()
        if found is not None:
            off,size=found
            if off<tp.HEADER or size!=len(payload) or off+size>end or os.pread(fd,size,off)!=payload:
                raise ValueError("catalog frame mismatch")
            die("reuse",fault)
            new_end=end
        else:
            off=end;size=len(payload)
            die("before_write",fault)
            split=max(1,size//2)
            write_all(fd,payload[:split],end);die("partial_write",fault)
            write_all(fd,payload[split:],end+split);die("written",fault)
            os.fsync(fd);die("synced",fault)
            db.execute("INSERT INTO frame_catalog VALUES(?,?,?)",(key,off,size))
            new_end=end+size
        digest=h.sha(raw)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(a,i,len(raw),digest,depth,parent,PTR.pack(off,size)));die("source",fault)
        db.execute("INSERT INTO revisions VALUES(?,?,?)",(g,a,i))
        db.execute("INSERT INTO origin VALUES(?,?,?,?)",(g,commit,ts,blob))
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text));die("index",fault)
        dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0];total=prev_total+dl
        db.execute("INSERT INTO rank_ledger VALUES(?,?,?,?)",(g,dl,total,h.chain(prev_hash,g,a,i,digest,dl,total)));die("ledger",fault)
        db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(article) DO UPDATE SET ord=excluded.ord",(a,i))
        db.execute("UPDATE meta SET generation=? WHERE singleton=1",(g,))
        db.execute("UPDATE pack_state SET end_offset=? WHERE singleton=1",(new_end,));die("meta",fault)
        db.commit();die("commit",fault)
        return g,i
    except BaseException:
        # Never truncate here: commit errors may be ambiguous. Reconcile only
        # under a fresh write transaction after SQLite resolves visibility.
        db.rollback();raise


def audit(db,fd):
    n=h.audit(db);end=tp.state(db,fd);pos=tp.HEADER
    catalog={}
    for key,off,size in db.execute("SELECT digest,off,n FROM frame_catalog ORDER BY off"):
        if off!=pos or size<=0 or off+size>end:raise ValueError("catalog gap/overlap")
        payload=os.pread(fd,size,off)
        if len(payload)!=size or h.sha(payload)!=key:raise ValueError("catalog digest mismatch")
        catalog[(off,size)]=key;pos+=size
    if pos!=end:raise ValueError("catalog end mismatch")
    seen=set()
    for a,i,ptr in db.execute("SELECT r.article,r.ord,v.payload FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord ORDER BY r.generation"):
        pair=PTR.unpack(ptr)
        if pair not in catalog:raise ValueError("missing frame catalog entry")
        seen.add(pair);recover(db,fd,a,i)
    if seen!=set(catalog):raise ValueError("unreferenced catalog entry")
    return n

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    prev=json.loads((HERE.parent/"round-142"/("results-"+str(n)+".json")).read_text())
    assert prev["manifest_sha256"]==m["source_manifest_sha256"]
    old=json.loads((HERE.parent/"round-138"/("results-"+str(n)+".json")).read_text())["result"]
    cuts=old["cuts"];refs={c:h.active_oracle(events,c) for c in cuts}
    queries=nr.plan(refs[cuts[0]])
    assert h.sha(h.canonical([dict(phrases=p,op=o) for p,o in queries])).hex()==old["query_plan_sha256"]
    bodies={};results={}
    for arm,policy,dedup in [("snapshot","snapshot",False),("bounded_anchor","bounded_anchor",False),("snapshot_reuse","snapshot",True),("bounded_anchor_reuse","bounded_anchor",True)]:
        path=folder/(arm+".sqlite")
        db=setup(path,ext,m) if dedup else tp.setup(path,ext,m)
        db.execute("PRAGMA wal_autocheckpoint=1000")
        fd=os.open(tp.side(path),os.O_RDWR);times=[];reader=None;pinned={}
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            t=time.perf_counter_ns()
            assert (append if dedup else tp.append)(db,fd,a,raw,origin,policy)==(g,i)
            times.append((time.perf_counter_ns()-t)/1000)
            if g==cuts[0]:
                reader=h.connect(path,ext);reader.execute("BEGIN")
                for p,o in queries[::4]:pinned[p,o]=tp.issue(reader,fd,p,o,g)
            if g%10000==0:print("INGEST",arm,g,flush=True)
        for (p,o),want in pinned.items():
            assert tp.issue(reader,fd,p,o,cuts[0])==want
        reader.rollback();reader.close()
        db.execute("BEGIN");assert (audit if dedup else tp.audit)(db,fd)==n
        end=tp.state(db,fd);assert end==os.fstat(fd).st_size
        unique=db.execute("SELECT count(*) FROM frame_catalog").fetchone()[0] if dedup else n
        db.rollback();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM");db.close()
        db=h.connect(path,ext);db.execute("BEGIN")
        source_checks=decoded=rawbytes=encoded=0;maxd=maxa=0.;reads=[];err=0.;checks=0
        for a,i,want in events:
            t=time.perf_counter_ns();raw,ab,dd,d=recover(db,fd,a,i);reads.append((time.perf_counter_ns()-t)/1000)
            assert raw==want
            full=len(h.C.compress(raw))
            if policy=="bounded_anchor":assert d<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
            source_checks+=1;decoded+=dd;encoded+=ab;rawbytes+=len(raw)
            if raw:maxd=max(maxd,dd/len(raw))
            maxa=max(maxa,ab/full)
        for c,ref in refs.items():
            for p,o in queries:
                value=tp.issue(db,fd,p,o,c);body,d=value
                err=max(err,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,p,o)))
                if (c,p,o) in bodies:assert value==bodies[c,p,o]
                else:bodies[c,p,o]=value
                checks+=1
        db.rollback();db.close();os.close(fd)
        result=dict(total_archive_bytes=path.stat().st_size+end,sqlite_bytes=path.stat().st_size,sidecar_bytes=end,
            payload_bytes=end-tp.HEADER,unique_frames=unique,duplicate_revisions=n-unique,
            append=h.quant(times),read=h.quant(reads),source_reads=source_checks,rank_checks=checks,
            pinned_checks=len(pinned),max_score_error=err,mean_decode_ratio=decoded/max(1,rawbytes),
            max_decode_ratio=maxd,max_activation_ratio=maxa,activated_bytes=encoded)
        expected=prev["policies"][policy+("_coalesced" if dedup else "")]
        assert result["payload_bytes"]==expected["payload_bytes"]
        if not dedup:assert result["total_archive_bytes"]==expected["total_archive_bytes"]
        if dedup:
            for k in ("mean_decode_ratio","max_decode_ratio","max_activation_ratio","activated_bytes"):assert result[k]==results[policy][k]
            assert unique==expected["unique_frames"]
        results[arm]=result
    for ref in refs.values():ref.close()
    return dict(round=145,revisions=n,documents=len(m["retained_paths"]),manifest_sha256=m["source_manifest_sha256"],
        query_plan_sha256=old["query_plan_sha256"],policies=results,
        limitations=["exact encoded-frame reuse, not source-object equivalence across different anchor contexts",
          "catalog lookup charged; physical layout and metadata overhead measured",
          "append-only, no deletion/compaction, cooperating writers, no hardware power-loss validation",
          "v1 receipts only; provenance v2 separately evaluated", "derived text and synthetic global ingestion chronology"])

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,p,e,stage,mode=sys.argv;path=Path(p);db=h.connect(path,Path(e));fd=os.open(tp.side(path),os.O_RDWR)
        raw=b"old evidence "*100 if mode=="reuse" else b"new material "*100
        append(db,fd,"b",raw,tp.fixture(raw,"child"),"snapshot",fault=stage);raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=run(a.source,a.target,Path(d),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
