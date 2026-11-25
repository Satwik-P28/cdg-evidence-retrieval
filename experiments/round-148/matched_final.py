"""R148: fully feature-matched final comparison, same catalog and receipt v2."""
import argparse,json,os,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-147"))
from integrated_pack import setup,audit,d,bv,pv,tp,h,nr

def arm(folder,ext,events,origins,m,v2,frozen,cuts,refs,allq,queries,policy):
    n=len(events)
    path=folder/(policy+".sqlite");db=setup(path,ext,m)
    db.execute("PRAGMA wal_autocheckpoint=1000")
    fd=os.open(tp.side(path),os.O_RDWR);times=[];issued=[];reader=None;pinned=[]
    for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
        start=time.perf_counter_ns();assert d.append(db,fd,a,raw,origin,policy)==(g,i)
        times.append((time.perf_counter_ns()-start)/1000)
        if g in cuts:
            db.execute("BEGIN")
            manifest,roots,_=bv.prefix_set(db,[g])
            for p,o in queries:issued.append(bv.issue_verified(db,fd,p,o,g,manifest,roots[g]))
            db.rollback()
        if g==cuts[0]:
            reader=pv.connect(path,ext);reader.execute("BEGIN")
            pinned=issued[:len(queries)]
            assert all(pv.replay(reader,fd,body,digest)==body for body,digest in pinned)
        if g%10000==0:print("INGEST",g,flush=True)
    assert all(pv.replay(reader,fd,body,digest)==body for body,digest in pinned)
    reader.rollback();reader.close()
    db.execute("BEGIN");assert audit(db,fd)==n
    end=tp.state(db,fd);assert end==os.fstat(fd).st_size
    unique=db.execute("SELECT count(*) FROM frame_catalog").fetchone()[0]
    db.rollback();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
    db.close();os.close(fd)
    expected=frozen["policies"][policy+"_coalesced"]
    assert end-tp.HEADER==expected["payload_bytes"] and unique==expected["unique_frames"]
    start=time.perf_counter_ns();verified,scanned=bv.verify_batch(path,ext,issued);batch_us=(time.perf_counter_ns()-start)/1000
    assert verified==[b for b,_ in issued] and scanned==n
    db=pv.connect(path,ext);fd=os.open(tp.side(path),os.O_RDONLY);db.execute("BEGIN")
    assert audit(db,fd)==n
    decoded=rawbytes=encoded=0;maxd=maxa=0.;err=0.;checks=0
    for a,i,want in events:
        raw,ab,dd,depth=tp.recover(db,fd,a,i);assert raw==want
        full=len(h.C.compress(raw));assert depth<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
        decoded+=dd;encoded+=ab;rawbytes+=len(raw)
        if raw:maxd=max(maxd,dd/len(raw))
        maxa=max(maxa,ab/full)
    for c,ref in refs.items():
        for p,o in allq:
            body,_=tp.issue(db,fd,p,o,c)
            err=max(err,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,p,o)))
            checks+=1
    db.rollback();db.close();os.close(fd)
    return dict(policy=policy,revisions=n,manifest_sha256=m["source_manifest_sha256"],
        total_archive_bytes=path.stat().st_size+end,source_payload_bytes=end-tp.HEADER,
        unique_frames=unique,duplicate_revisions=n-unique,append=h.quant(times),
        batch_receipts=len(issued),batch_metadata_rows=scanned,batch_us=batch_us,
        rank_checks=checks,pinned_checks=len(pinned),source_reads=n,max_score_error=err,
        mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
        activated_bytes=encoded,reference_v2_archive_bytes=v2["policies"]["v2"]["total_archive_bytes"],
        reference_git_depth1_bytes=frozen["policies"]["git_pack_depth1"]["total_archive_bytes"],
        receipt_commitments_sha256=h.sha(h.canonical([digest for _,digest in issued])).hex(),
        limitations=["cooperating local writers; no power-loss, deletion or garbage collection",
          "v2 trusted external digest required; no publisher authentication",
          "metadata scan amortization, not sublinear single receipt verification",
          "one build per arm/cohort; timing descriptive, no Git update parity",
          "derived news text and synthetic global schedule"])

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    v2=json.loads((HERE.parent/"round-144"/("results-"+str(n)+".json")).read_text())["result"]
    frozen=json.loads((HERE.parent/"round-142"/("results-"+str(n)+".json")).read_text())
    previous=json.loads((HERE.parent/"round-147"/("results-"+str(n)+".json")).read_text())
    assert m["source_manifest_sha256"]==v2["source_manifest"]==frozen["manifest_sha256"]==previous["manifest_sha256"]
    cuts=v2["cutoffs"];refs={c:h.active_oracle(events,c) for c in cuts}
    allq=nr.plan(refs[cuts[0]]);queries=allq[::4]
    assert h.sha(h.canonical([dict(phrases=p,op=o) for p,o in allq])).hex()==frozen["query_plan_sha256"]
    assert len(queries)==v2["query_count"]
    policies={}
    for policy in ("snapshot","bounded_anchor"):
        policies[policy]=arm(folder,ext,events,origins,m,v2,frozen,cuts,refs,allq,queries,policy)
    for ref in refs.values():ref.close()
    assert policies["snapshot"]["receipt_commitments_sha256"]==policies["bounded_anchor"]["receipt_commitments_sha256"]
    for k in ("total_archive_bytes","source_payload_bytes","unique_frames","mean_decode_ratio","max_decode_ratio","max_activation_ratio"):
        assert policies["bounded_anchor"][k]==previous[k],k
    return dict(round=148,revisions=n,manifest_sha256=m["source_manifest_sha256"],policies=policies,
        complete_archive_reduction=1-policies["bounded_anchor"]["total_archive_bytes"]/policies["snapshot"]["total_archive_bytes"],
        limitations=["matched deduplication, provenance v2, index, historical query plan and source bytes",
          "same runner sequential arms, descriptive timing; no power-loss or Git transactional parity",
          "derived AP sentence text; synthetic global order; nested cohorts not independent"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.source,a.target,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
