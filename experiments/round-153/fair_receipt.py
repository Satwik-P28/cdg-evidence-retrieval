"""R153: equal-semantics efficient revision control against the R151 quotient archive."""
import argparse,hashlib,json,os,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-151"))
import joint_archive as j
from joint_archive import h,pv,tp,bv,nr,ar,recover

def fast_revision_rank(db,phrases,op,c):
    ar.expression(phrases,op)
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    freq=[];lens={}
    for p in phrases:
        matches={}
        for g,tf,dl,stored in db.execute("""WITH matches AS MATERIALIZED (
          SELECT rowid AS g,cdg_count(docs) AS tf,cdg_length(docs) AS dl
          FROM docs WHERE docs MATCH ?
        ) SELECT q.g,q.tf,q.dl,l.dl FROM matches q JOIN validity v ON v.start_g=q.g
          JOIN rank_ledger l ON l.g=q.g
          WHERE q.g<=? AND (v.end_g IS NULL OR v.end_g>?)""",(ar.quote(p),c,c)):
            assert dl==stored and 1<=tf<=dl
            matches[g]=tf;lens[g]=dl
        freq.append(matches)
    hits,df=ar.score(freq,op,n,total,lens)
    return hits,n,total,df

def rank_body(db,fd,p,o,c,mode):
    if mode=="legacy":return tp.issue(db,fd,p,o,c)[0]
    if not db.in_transaction:raise ValueError("snapshot required")
    hits,n,total,df=(j.quotient_rank(db,p,o,c) if mode=='quotient' else fast_revision_rank(db,p,o,c))
    prefix=db.execute("SELECT prefix_sha FROM rank_ledger WHERE g=?",(c,)).fetchone()[0]
    rows=[]
    for g,s in hits:
        a,i,digest=db.execute("SELECT r.article,r.ord,v.digest FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?",(g,)).fetchone()
        raw,*_=recover(db,fd,a,i)
        if h.sha(raw)!=digest:raise ValueError("receipt source mismatch")
        rows.append(dict(g=g,article=a,ordinal=i,source_sha256=digest.hex(),score_hex=s.hex()))
    return dict(format=ar.FORMAT,scorer=ar.SCORER,cutoff=c,phrases=list(p),op=o,k=10,
        prefix_sha256=prefix.hex(),active_documents=n,active_tokens=total,phrase_df=df,hits=rows)

def issue(db,fd,p,o,c,manifest,root,mode):
    body=rank_body(db,fd,p,o,c,mode);origins=[]
    for hit in body["hits"]:
        commit,stamp,blob=db.execute("SELECT commit_sha1,committer_unix,blob_sha1 FROM origin WHERE g=?",(hit["g"],)).fetchone()
        raw,*_=recover(db,fd,hit["article"],hit["ordinal"])
        if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
        origins.append(dict(g=hit["g"],commit_sha1=commit,committer_unix=stamp,blob_sha1=blob))
    result=dict(format=pv.FORMAT,manifest_sha256=manifest,origin_prefix_sha256=root,ranking=body,hit_origins=origins)
    return result,h.sha(h.canonical(result)).hex()

def verify_batch(db,fd,requests,mode):
    manifest,roots,scanned=bv.prefix_set(db,[x["ranking"]["cutoff"] for x,_ in requests])
    for old,digest in requests:
        assert h.sha(h.canonical(old)).hex()==digest
        r=old["ranking"];c=r["cutoff"]
        assert issue(db,fd,tuple(r["phrases"]),r["op"],c,manifest,roots[c],mode)==(old,digest)
    return scanned

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    old=json.loads((HERE.parent/"round-151"/("results-"+str(n)+".json")).read_text())
    assert old["manifest_sha256"]==m["source_manifest_sha256"]
    first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
    refs={c:h.active_oracle(events,c) for c in cuts};queries=nr.plan(refs[first])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    paths={};requests={};results={}
    for mode in ("revision","quotient"):
        path=folder/(mode+".sqlite");db=j.setup(path,ext,m,mode=="quotient");fd=os.open(tp.side(path),os.O_RDWR)
        db.execute("PRAGMA wal_autocheckpoint=1000")
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            assert j.append(db,fd,a,raw,origin,"marginal",quotient=mode=="quotient")== (g,i)
            if g in cuts:
                db.execute("BEGIN");manifest,roots,_=bv.prefix_set(db,[g])
                requests[mode]=requests.get(mode,[])+[j.issue(db,fd,p,o,g,manifest,roots[g],mode=="quotient") for p,o in queries[::4]]
                db.rollback()
        db.execute("BEGIN");assert j.audit(db,fd,mode=="quotient")==n;end=tp.state(db,fd);db.rollback()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();os.close(fd)
        assert path.stat().st_size+end==old["policies"]["marginal_"+mode]["total_archive_bytes"]
        paths[mode]=path
    assert requests["revision"]==requests["quotient"]
    req=requests["revision"]
    dbs={k:pv.connect(path,ext) for k,path in paths.items()}
    fds={k:os.open(tp.side(path),os.O_RDONLY) for k,path in paths.items()}
    for db in dbs.values():db.execute("BEGIN")
    rng=random.Random(153);methods=("legacy","fast_revision","quotient")
    times={k:[] for k in methods};batches={k:[] for k in methods};maxerr={k:0. for k in methods}
    try:
        for repeat in range(3):
            order=list(expected);rng.shuffle(order)
            for c,p,o in order:
                variants=list(methods);rng.shuffle(variants);sig=None
                for method in variants:
                    key="quotient" if method=="quotient" else "revision"
                    t=time.perf_counter_ns();body=rank_body(dbs[key],fds[key],p,o,c,method);times[method].append((time.perf_counter_ns()-t)/1000)
                    maxerr[method]=max(maxerr[method],h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],expected[c,p,o]))
                    if sig is None:sig=body
                    else:assert body==sig
            variants=list(methods);rng.shuffle(variants)
            for method in variants:
                key="quotient" if method=="quotient" else "revision"
                t=time.perf_counter_ns();assert verify_batch(dbs[key],fds[key],req,method)==n
                batches[method].append((time.perf_counter_ns()-t)/1000)
        for method in methods:
            results[method]=dict(rank_receipt=h.quant(times[method]),batch=h.quant(batches[method]),
                batch_raw_us=batches[method],rank_checks=len(times[method]),max_score_error=maxerr[method])
    finally:
        for db in dbs.values():db.rollback();db.close()
        for fd in fds.values():os.close(fd)
        for ref in refs.values():ref.close()
    return dict(round=153,revisions=n,manifest_sha256=m["source_manifest_sha256"],policies=results,
        limitations=["same revision physical archive for legacy and fast revision, same R151 quotient archive",
          "same native tokenizer, phrase/boolean grammar and source verification, 3 warm interleaved repetitions",
          "full prefix provenance scan once per batch; single receipt rank timing excludes origin-prefix verification",
          "synthetic AP schedule, descriptive single-runner timings, no production SLA"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.source,a.target,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
