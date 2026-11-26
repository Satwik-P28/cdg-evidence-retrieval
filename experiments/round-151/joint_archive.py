"""R151: independent 2x2 integration of local marginal selection and quotient FTS.
Same R147 provenance v2, physical frame catalog, atomic writer and receipts.
"""
import argparse,hashlib,heapq,json,os,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-147"))
from integrated_pack import setup as base_setup,d,bv,pv,tp,h,nr
from transactional_pack import PTR,write_all,die,recover,reconcile_locked
import active_rank as ar

def setup(path,ext,m,quotient):
    db=base_setup(path,ext,m)
    if quotient:
        db.executescript("""
        CREATE TABLE content_catalog(digest BLOB PRIMARY KEY,cid INTEGER NOT NULL UNIQUE,dl INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE content_map(g INTEGER PRIMARY KEY REFERENCES revisions(generation),cid INTEGER NOT NULL);
        CREATE INDEX content_map_by_cid ON content_map(cid,g);
        """)
        db.commit()
    return db

def choose_marginal(db,fd,end,raw,i,hist):
    full=h.C.compress(raw)
    candidates=[(None,0,full,len(raw),len(full))]
    for j in [j for j in range(i-1,-1,-1) if hist[j][2]==0][:4]:
        old,encoded,_=hist[j]
        if 2*(len(old)+len(raw))>5*len(raw):continue
        diff=h.delta_encode(raw,old)
        if diff is None or 5*len(diff)>4*len(full) or 2*(encoded+len(diff))>3*len(full):continue
        candidates.append((j,1,diff,len(old)+len(raw),encoded+len(diff)))
    def score(c):
        j,depth,frame,dd,ab=c
        row=db.execute("SELECT off,n FROM frame_catalog WHERE digest=?",(h.sha(frame),)).fetchone()
        if row is not None:
            off,n=row
            if off<tp.HEADER or off+n>end or n!=len(frame) or os.pread(fd,n,off)!=frame:
                raise ValueError("catalog collision")
        return (0 if row else len(frame)+48,dd,ab,len(frame),-(j+1) if j is not None else 0)
    return min(candidates,key=score)[:3]

def insert_index(db,fd,g,digest,raw,text,quotient):
    if not quotient:
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text))
        return db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0]
    row=db.execute("SELECT cid,dl FROM content_catalog WHERE digest=?",(digest,)).fetchone()
    if row is None:
        cid=g;dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0]
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(cid,text))
        db.execute("INSERT INTO content_catalog VALUES(?,?,?)",(digest,cid,dl))
    else:
        cid,dl=row
        a,i=db.execute("SELECT article,ord FROM revisions WHERE generation=?",(cid,)).fetchone()
        old,*_=recover(db,fd,a,i)
        if old!=raw:raise ValueError("source digest collision")
    db.execute("INSERT INTO content_map VALUES(?,?)",(g,cid))
    return dl

def append(db,fd,a,raw,origin,policy="bounded_anchor",fault=None,quotient=False):
    if db.in_transaction or policy not in ("snapshot","bounded_anchor","marginal"):raise ValueError("bad writer")
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
        if policy in ("bounded_anchor","marginal"):
            for j in [j for j in range(i-1,-1,-1) if rows[j][1]==0][:4]:
                old,_,_,dep=recover(db,fd,a,j,0);hist[j]=(old,hist[j][1],dep)
            parent,depth,payload=(choose_marginal(db,fd,end,raw,i,hist) if policy=="marginal" else h.choose_config(raw,i,hist,policy))
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
        dl=insert_index(db,fd,g,digest,raw,text,quotient);die("index",fault)
        total=prev_total+dl
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


def audit_frames(db,fd,n):
    end=tp.state(db,fd);pos=tp.HEADER
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


def audit(db,fd,quotient):
    if not quotient:
        n=d.audit(db,fd)
    else:
        n=h.generation(db)
        assert audit_frames(db,fd,n)==n
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.qvocab USING fts5vocab(main,docs,'instance')")
        lengths=dict(db.execute("SELECT doc,count(*) FROM temp.qvocab GROUP BY doc"))
        catalog={cid:(digest,dl) for digest,cid,dl in db.execute("SELECT digest,cid,dl FROM content_catalog")}
        assert set(catalog)=={g for g, in db.execute("SELECT rowid FROM docs")}
        assert all(lengths.get(cid,0)==dl for cid,(_,dl) in catalog.items())
        rows=db.execute("""SELECT r.generation,r.article,r.ord,v.digest,l.dl,l.total,l.prefix_sha,m.cid
          FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord
          JOIN rank_ledger l ON l.g=r.generation JOIN content_map m ON m.g=r.generation
          ORDER BY r.generation""").fetchall()
        assert len(rows)==n
        prev=h.SEED;total=active_total=0;active={};ends={};stats=[];seen=set()
        for expected,(g,a,i,digest,dl,cumulative,prefix,cid) in enumerate(rows,1):
            assert g==expected and cid<=g and catalog[cid]==(digest,dl)
            if cid not in seen:assert cid==g;seen.add(cid)
            total+=dl;prev=h.chain(prev,g,a,i,digest,dl,total)
            assert cumulative==total and prefix==prev
            if a in active:
                old,ord_,old_dl=active[a];assert i==ord_+1;ends[old]=g;active_total-=old_dl
            else:assert i==0
            active[a]=(g,i,dl);ends[g]=None;active_total+=dl;stats.append((g,len(active),active_total))
        assert seen==set(catalog)
        for table in ("versions","revisions","rank_ledger","content_map","origin"):
            assert db.execute("SELECT count(*) FROM "+table).fetchone()[0]==n
        assert db.execute("SELECT start_g,end_g FROM validity ORDER BY start_g").fetchall()==sorted(ends.items())
        assert db.execute("SELECT g,n,tokens FROM active_stats ORDER BY g").fetchall()==stats
        assert dict(db.execute("SELECT article,ord FROM heads"))=={a:i for a,(_,i,_) in active.items()}
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("SELECT count(*) FROM origin_ledger").fetchone()[0]==n
    if n:pv.metadata_prefix(db,n)
    return n

def quotient_rank(db,phrases,op,c):
    ar.expression(phrases,op)
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    freq=[];groups={};lens={}
    for p in phrases:
        matches={}
        # Materialize the FTS auxiliary values before expanding active identities.
        for cid,tf,dl,g in db.execute("""WITH matches AS MATERIALIZED (
            SELECT rowid AS cid,cdg_count(docs) AS tf,cdg_length(docs) AS dl FROM docs WHERE docs MATCH ?
          ) SELECT q.cid,q.tf,q.dl,m.g FROM matches q JOIN content_map m ON m.cid=q.cid
          JOIN validity v ON v.start_g=m.g
          WHERE m.g<=? AND (v.end_g IS NULL OR v.end_g>?) ORDER BY q.cid,m.g""",(ar.quote(p),c,c)):
            if cid not in matches:matches[cid]=tf
            else:assert matches[cid]==tf
            if cid not in lens:lens[cid]=dl
            else:assert lens[cid]==dl
            groups.setdefault(cid,set()).add(g)
        freq.append(matches)
    df=[sum(len(groups[cid]) for cid in m) for m in freq]
    assert all(v<=n for v in df)
    sets=[set(m) for m in freq];cand=set.intersection(*sets) if op=="AND" else set.union(*sets)
    if not cand:return [],n,total,df
    weights=[ar.idf(n,v) for v in df];avg=total/n;out=[]
    for cid in cand:
        score=-sum(ar.positive_score(m.get(cid,0),lens[cid],avg,w) for m,w in zip(freq,weights))
        out.extend((g,score) for g in sorted(groups[cid])[:10])
    return heapq.nsmallest(10,out,key=lambda x:(x[1],x[0])),n,total,df

def issue_rank(db,fd,p,o,c,quotient):
    if not quotient:return tp.issue(db,fd,p,o,c)[0]
    if not db.in_transaction:raise ValueError("snapshot required")
    hits,n,total,df=quotient_rank(db,p,o,c)
    prefix=db.execute("SELECT prefix_sha FROM rank_ledger WHERE g=?",(c,)).fetchone()[0]
    rows=[]
    for g,s in hits:
        a,i,digest=db.execute("SELECT r.article,r.ord,v.digest FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?",(g,)).fetchone()
        raw,*_=recover(db,fd,a,i)
        if h.sha(raw)!=digest:raise ValueError("receipt source mismatch")
        rows.append(dict(g=g,article=a,ordinal=i,source_sha256=digest.hex(),score_hex=s.hex()))
    return dict(format=ar.FORMAT,scorer=ar.SCORER,cutoff=c,phrases=list(p),op=o,k=10,
        prefix_sha256=prefix.hex(),active_documents=n,active_tokens=total,phrase_df=df,hits=rows)

def issue(db,fd,p,o,c,manifest,root,quotient):
    body=issue_rank(db,fd,p,o,c,quotient);origins=[]
    for hit in body["hits"]:
        commit,stamp,blob=db.execute("SELECT commit_sha1,committer_unix,blob_sha1 FROM origin WHERE g=?",(hit["g"],)).fetchone()
        raw,*_=recover(db,fd,hit["article"],hit["ordinal"])
        if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
        origins.append(dict(g=hit["g"],commit_sha1=commit,committer_unix=stamp,blob_sha1=blob))
    result=dict(format=pv.FORMAT,manifest_sha256=manifest,origin_prefix_sha256=root,ranking=body,hit_origins=origins)
    return result,h.sha(h.canonical(result)).hex()

def batch(db,fd,req,quotient):
    for body,digest in req:
        if body.get("format")!=pv.FORMAT or h.sha(h.canonical(body)).hex()!=digest:raise ValueError("receipt commitment")
    manifest,roots,scanned=bv.prefix_set(db,[b["ranking"]["cutoff"] for b,_ in req])
    for body,digest in req:
        rank=body["ranking"];c=rank["cutoff"]
        got=issue(db,fd,tuple(rank["phrases"]),rank["op"],c,manifest,roots[c],quotient)
        if got!=(body,digest):raise ValueError("receipt replay mismatch")
    return scanned

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    old=json.loads((HERE.parent/"round-148"/("results-"+str(n)+".json")).read_text())
    marginal=json.loads((HERE.parent/"round-149"/("results-"+str(n)+"-original.json")).read_text())
    assert m["source_manifest_sha256"]==old["manifest_sha256"]==marginal["manifest_sha256"]
    first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
    refs={c:h.active_oracle(events,c) for c in cuts};queries=nr.plan(refs[first])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    results={};reference_receipts=None
    for policy,quotient in [("bounded_anchor",False),("marginal",False),("bounded_anchor",True),("marginal",True)]:
        name=policy+("_quotient" if quotient else "_revision");path=folder/(name+".sqlite")
        db=setup(path,ext,m,quotient);db.execute("PRAGMA wal_autocheckpoint=1000")
        fd=os.open(tp.side(path),os.O_RDWR);times=[];issued=[];reader=None
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            t=time.perf_counter_ns();assert append(db,fd,a,raw,origin,policy,quotient=quotient)==(g,i)
            times.append((time.perf_counter_ns()-t)/1000)
            if g in cuts:
                db.execute("BEGIN");manifest,roots,_=bv.prefix_set(db,[g])
                for p,o in queries[::4]:issued.append(issue(db,fd,p,o,g,manifest,roots[g],quotient))
                db.rollback()
            if g==first:
                reader=pv.connect(path,ext);reader.execute("BEGIN")
                assert batch(reader,fd,issued[:16],quotient)==first
        assert batch(reader,fd,issued[:16],quotient)==first
        reader.rollback();reader.close()
        db.execute("BEGIN");assert audit(db,fd,quotient)==n;end=tp.state(db,fd)
        assert end==os.fstat(fd).st_size
        db.rollback();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();db=pv.connect(path,ext);db.execute("BEGIN")
        assert audit(db,fd,quotient)==n
        start=time.perf_counter_ns();scanned=batch(db,fd,issued,quotient);batch_us=(time.perf_counter_ns()-start)/1000
        assert scanned==n
        if reference_receipts is None:reference_receipts=issued
        else:assert issued==reference_receipts
        decoded=rawbytes=activated=0;maxd=maxa=err=0.;query_times=[]
        for a,i,want in events:
            raw,ab,dd,depth=recover(db,fd,a,i);assert raw==want
            full=len(h.C.compress(raw));assert depth<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
            decoded+=dd;rawbytes+=len(raw);activated+=ab
            if raw:maxd=max(maxd,dd/len(raw))
            maxa=max(maxa,ab/full)
        for (c,p,o),want in expected.items():
            t=time.perf_counter_ns();body=issue_rank(db,fd,p,o,c,quotient);query_times.append((time.perf_counter_ns()-t)/1000)
            err=max(err,h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["hits"]],want))
        size=path.stat().st_size+end;payload=end-tp.HEADER
        distinct=db.execute("SELECT count(*) FROM frame_catalog").fetchone()[0]
        indexed=db.execute("SELECT count(*) FROM docs").fetchone()[0]
        db.rollback();db.close();os.close(fd)
        ref=marginal["policies"]["marginal" if policy=="marginal" else "baseline"]
        assert payload==ref["payload_bytes"] and distinct==ref["unique_frames"]
        assert decoded==ref["decoded_bytes"] and activated==ref["activated_bytes"]
        if name=="bounded_anchor_revision":assert size==old["policies"]["bounded_anchor"]["total_archive_bytes"]
        results[name]=dict(total_archive_bytes=size,payload_bytes=payload,unique_frames=distinct,index_rows=indexed,
          mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
          append=h.quant(times),rank_receipt=h.quant(query_times),batch_us=batch_us,rank_checks=len(expected),
          batch_receipts=len(issued),pinned_checks=16,source_reads=n,max_score_error=err)
        print("ARM_JSON="+json.dumps(results[name]),flush=True)
    for ref in refs.values():ref.close()
    return dict(round=151,revisions=n,manifest_sha256=m["source_manifest_sha256"],policies=results,
        limitations=["local marginal candidates only, no cross-article recipe extension",
          "same manifest/provenance receipt format, no untrusted-index completeness proof",
          "synthetic AP chronology, same runner sequential arms; timing descriptive",
          "cooperating writers, no power-loss or deletion/compaction guarantee"])

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,p,e,stage,mode=sys.argv;path=Path(p);db=pv.connect(path,Path(e));fd=os.open(tp.side(path),os.O_RDWR)
        raw=b"old evidence "*100 if mode=="reuse" else b"new material "*100
        append(db,fd,"b",raw,tp.fixture(raw,"child"),"snapshot",fault=stage,quotient=True)
        raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.source,a.target,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
