"""R146: amortize authenticated metadata-prefix verification in one snapshot.

No persistent verification cache. Batch either returns all verified receipts
or raises. The caller retains individual trusted receipt digests.
"""
import argparse,hashlib,json,os,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-144"))
import provenance_v2 as pv
from provenance_v2 import h,tp,nr

def prefix_set(db,cutoffs):
    wanted=set(cutoffs)
    if not db.in_transaction or not wanted or min(wanted)<1 or max(wanted)>h.generation(db):
        raise ValueError("invalid batch cutoff")
    row=db.execute("SELECT v FROM corpus WHERE k='manifest'").fetchone()
    if row is None:raise ValueError("missing manifest")
    raw=row[0];prev=pv.manifest_seed(raw);n=0;roots={}
    for g,a,i,digest,commit,stamp,blob,rank,stored in db.execute("""
        SELECT r.generation,r.article,r.ord,v.digest,o.commit_sha1,o.committer_unix,o.blob_sha1,
        l.prefix_sha,p.prefix_sha FROM revisions r
        JOIN versions v ON v.article=r.article AND v.ord=r.ord
        JOIN origin o ON o.g=r.generation JOIN rank_ledger l ON l.g=r.generation
        JOIN origin_ledger p ON p.g=r.generation WHERE r.generation<=? ORDER BY r.generation""",(max(wanted),)):
        n+=1
        if g!=n:raise ValueError("origin prefix gap")
        prev=pv.entry(prev,g,a,i,digest,commit,stamp,blob,rank)
        if prev!=stored:raise ValueError("origin prefix mismatch")
        if g in wanted:roots[g]=prev.hex()
    if n!=max(wanted) or set(roots)!=wanted:raise ValueError("origin prefix cardinality")
    return h.sha(raw).hex(),roots,n

def issue_verified(db,fd,p,o,c,manifest,root):
    body,_=tp.issue(db,fd,p,o,c)
    origins=[]
    for hit in body["hits"]:
        row=db.execute("SELECT commit_sha1,committer_unix,blob_sha1 FROM origin WHERE g=?",(hit["g"],)).fetchone()
        if row is None:raise ValueError("missing hit origin")
        commit,stamp,blob=row
        raw,*_=tp.recover(db,fd,hit["article"],hit["ordinal"])
        if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
        origins.append(dict(g=hit["g"],commit_sha1=commit,committer_unix=stamp,blob_sha1=blob))
    result=dict(format=pv.FORMAT,manifest_sha256=manifest,origin_prefix_sha256=root,ranking=body,hit_origins=origins)
    return result,h.sha(h.canonical(result)).hex()


def verify_batch(path,ext,requests):
    requests=list(requests)
    if not requests:raise ValueError("empty batch")
    # Validate all caller commitments before querying the archive.
    for body,trusted in requests:
        if body.get("format")!=pv.FORMAT or h.sha(h.canonical(body)).hex()!=trusted:
            raise ValueError("untrusted receipt")
    db=pv.connect(path,ext);fd=os.open(tp.side(path),os.O_RDONLY)
    try:
        db.execute("BEGIN")
        manifest,roots,scanned=prefix_set(db,[b["ranking"]["cutoff"] for b,_ in requests])
        out=[]
        for body,trusted in requests:
            rank=body["ranking"];c=rank["cutoff"]
            got,digest=issue_verified(db,fd,tuple(rank["phrases"]),rank["op"],c,manifest,roots[c])
            if got!=body or digest!=trusted:raise ValueError("provenance replay mismatch")
            out.append(got)
        db.rollback();return out,scanned
    finally:db.close();os.close(fd)

def verify_individual(path,ext,requests):
    db=pv.connect(path,ext);fd=os.open(tp.side(path),os.O_RDONLY)
    try:
        db.execute("BEGIN");out=[pv.replay(db,fd,b,d) for b,d in requests]
        db.rollback();return out,sum(b["ranking"]["cutoff"] for b,_ in requests)
    finally:db.close();os.close(fd)

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    old=json.loads((HERE.parent/"round-144"/("results-"+str(n)+".json")).read_text())["result"]
    assert m["source_manifest_sha256"]==old["source_manifest"]
    cuts=old["cutoffs"];ref=h.active_oracle(events,cuts[0]);queries=nr.plan(ref)[::4];ref.close()
    assert len(queries)==old["query_count"]
    path=folder/"v2.sqlite";db=pv.setup(path,ext,m);fd=os.open(tp.side(path),os.O_RDWR)
    issued=[]
    for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
        assert tp.append(db,fd,a,raw,origin)==(g,i)
        if g in cuts:
            db.execute("BEGIN")
            for p,o in queries:issued.append(pv.issue(db,fd,p,o,g))
            db.rollback()
    db.execute("BEGIN");assert pv.audit(db,fd)==n;end=tp.state(db,fd);db.rollback()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
    db.close();os.close(fd)
    assert path.stat().st_size+end==old["policies"]["v2"]["total_archive_bytes"]
    # Compare the exact same ordered requests and same snapshot scope.
    # Randomize execution order of methods per repeat, not request semantics.
    rng=random.Random(146);trials={}
    workloads={"single":[issued[-1]],"same_cutoff":issued[-len(queries):],"mixed":list(issued)}
    rng.shuffle(workloads["mixed"])
    for label,req in workloads.items():
        want=[b for b,_ in req];results={"individual":[],"batch":[]};counts={}
        for _ in range(3):
            methods=[("individual",verify_individual),("batch",verify_batch)];rng.shuffle(methods)
            for name,fn in methods:
                start=time.perf_counter_ns();got,rows=fn(path,ext,req);elapsed=(time.perf_counter_ns()-start)/1000
                assert got==want;results[name].append(elapsed);counts[name]=rows
        assert counts["batch"]==max(b["ranking"]["cutoff"] for b,_ in req)
        assert counts["individual"]==sum(b["ranking"]["cutoff"] for b,_ in req)
        trials[label]=dict(receipts=len(req),metadata_rows=counts,timing={k:h.quant(v) for k,v in results.items()},
            raw_timing_us=results)
    return dict(round=146,revisions=n,manifest_sha256=m["source_manifest_sha256"],trials=trials,
        archive_bytes=path.stat().st_size+end,source_payload_bytes=end-tp.HEADER,
        limitations=["same SQLite read snapshot per batch, no reuse across transactions",
          "requires trusted individual external receipt digests; no publisher authentication",
          "does not reduce single-receipt asymptotic cost; per-receipt ranking and hit checks unchanged",
          "three randomized method-order warm repetitions; descriptive timings",
          "derived AP text and synthetic ingestion schedule"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=run(a.source,a.target,Path(d),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
