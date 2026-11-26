"""R159: matched archive comparison with Linux process IO and sidecar syscall accounting."""
import argparse,contextlib,json,os,platform,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-153"))
import fair_receipt as fr
from fair_receipt import j,h,pv,tp,bv,nr,recover

IO_FIELDS=("rchar","wchar","syscr","syscw","read_bytes","write_bytes","cancelled_write_bytes")

def proc_io():
    rows=dict(line.split(":",1) for line in Path("/proc/self/io").read_text().splitlines())
    return {k:int(rows[k]) for k in IO_FIELDS}

def difference(a,b):
    return {k:b[k]-a[k] for k in IO_FIELDS}

def measured(fn,fd):
    original=os.pread;calls=0;requested=returned=0
    def tracked(f,n,off):
        nonlocal calls,requested,returned
        out=original(f,n,off)
        if f==fd:calls+=1;requested+=n;returned+=len(out)
        return out
    before=proc_io();start=time.perf_counter_ns()
    os.pread=tracked
    try:out=fn()
    finally:os.pread=original
    elapsed=(time.perf_counter_ns()-start)/1000;io=difference(before,proc_io())
    return out,dict(elapsed_us=elapsed,sidecar_pread_calls=calls,sidecar_requested_bytes=requested,sidecar_returned_bytes=returned,**io)

def summary(rows):
    return {k:dict(total=sum(x[k] for x in rows),**h.quant([x[k] for x in rows])) for k in rows[0]}

def advise(path):
    # Advisory only; successful return is NOT proof of a cold cache.
    errors=[]
    for p in (path,tp.side(path)):
        fd=os.open(p,os.O_RDONLY)
        try:os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
        except OSError as e:errors.append(str(e))
        finally:os.close(fd)
    return errors

@contextlib.contextmanager
def reader(path,ext):
    db=pv.connect(path,ext);fd=os.open(tp.side(path),os.O_RDONLY)
    try:
        db.execute("PRAGMA mmap_size=0");db.execute("PRAGMA cache_size=-2048")
        db.execute("BEGIN");yield db,fd
    finally:db.rollback();db.close();os.close(fd)

def workloads(path,ext,events,expected,req,mode):
    rng=random.Random(159)
    sources=rng.sample(range(len(events)),min(64,len(events)))
    queries=rng.sample(list(expected),min(32,len(expected)))
    def task(db,fd,kind,k):
        if kind=="source":
            a,i,want=events[k];raw,*_=recover(db,fd,a,i);assert raw==want
        elif kind=="rank":
            c,p,o=k;body=fr.rank_body(db,fd,p,o,c,mode)
            h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],expected[k])
        else:assert fr.verify_batch(db,fd,req,mode)==len(events)
    plans={"source":sources,"rank":queries,"batch":[0,1,2]}
    result={};errors=[]
    for cache in ("warm","reopen_advised"):
        for kind,keys in plans.items():
            rows=[]
            if cache=="warm":
                with reader(path,ext) as (db,fd):
                    for k in keys:task(db,fd,kind,k)
                    for k in keys:
                        _,metrics=measured(lambda:task(db,fd,kind,k),fd);rows.append(metrics)
            else:
                for k in keys:
                    errors.extend(advise(path))
                    with reader(path,ext) as (db,fd):
                        _,metrics=measured(lambda:task(db,fd,kind,k),fd);rows.append(metrics)
            result[cache+"_"+kind]=summary(rows)
    return result,errors

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    old=json.loads((HERE.parent/"round-151"/("results-"+str(n)+".json")).read_text())
    r148=json.loads((HERE.parent/"round-148"/("results-"+str(n)+".json")).read_text())
    assert old["manifest_sha256"]==r148["manifest_sha256"]==m["source_manifest_sha256"]
    first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
    refs={c:h.active_oracle(events,c) for c in cuts};qs=nr.plan(refs[first])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    results={};reference=None
    for policy,quotient in [("snapshot",False),("snapshot",True),("marginal",False),("marginal",True)]:
        name=policy+("_quotient" if quotient else "_revision");mode="quotient" if quotient else "fast_revision"
        path=folder/(name+".sqlite");db=j.setup(path,ext,m,quotient);fd=os.open(tp.side(path),os.O_RDWR)
        db.execute("PRAGMA wal_autocheckpoint=1000")
        issued=[];append_times=[];io_before=proc_io()
        # Exclude receipt issuance from ingestion counters by measuring separate spans.
        ingestion={k:0 for k in IO_FIELDS}
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            start=time.perf_counter_ns()
            assert j.append(db,fd,a,raw,origin,policy,quotient=quotient)==(g,i)
            append_times.append((time.perf_counter_ns()-start)/1000)
            if g in cuts:
                span=difference(io_before,proc_io())
                for k,v in span.items():ingestion[k]+=v
                db.execute("BEGIN");manifest,roots,_=bv.prefix_set(db,[g])
                issued.extend(fr.issue(db,fd,p,o,g,manifest,roots[g],mode) for p,o in qs[::4])
                db.rollback();io_before=proc_io()
        db.execute("BEGIN");assert j.audit(db,fd,quotient)==n;end=tp.state(db,fd);db.rollback()
        before=proc_io();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();os.close(fd);finalization=difference(before,proc_io())
        sizes=[path.stat(),tp.side(path).stat()]
        total=sum(x.st_size for x in sizes);allocated=sum(x.st_blocks*512 for x in sizes)
        if policy=="marginal":assert total==old["policies"][name]["total_archive_bytes"]
        if name=="snapshot_revision":assert total==r148["policies"]["snapshot"]["total_archive_bytes"]
        if reference is None:reference=issued
        else:assert issued==reference
        with reader(path,ext) as (db,fd):
            assert j.audit(db,fd,quotient)==n
            for a,i,want in events:assert recover(db,fd,a,i)[0]==want
            for (c,p,o),want in expected.items():
                body=fr.rank_body(db,fd,p,o,c,mode);h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["hits"]],want)
            assert fr.verify_batch(db,fd,issued,mode)==n
        reads,errors=workloads(path,ext,events,expected,issued,mode)
        results[name]=dict(total_archive_bytes=total,allocated_bytes=allocated,source_payload_bytes=end-tp.HEADER,
          append=h.quant(append_times),ingestion_process_io=ingestion,finalization_process_io=finalization,
          source_checks=n,rank_checks=len(expected),receipt_checks=len(issued),workloads=reads,advice_errors=errors)
        print("ARM_DONE="+name,flush=True)
    for ref in refs.values():ref.close()
    return dict(round=159,revisions=n,manifest_sha256=m["source_manifest_sha256"],kernel=platform.release(),
      machine=platform.machine(),filesystem=os.statvfs(folder).f_bsize,policies=results,limitations=[
      "Linux /proc/self/io read_bytes/write_bytes are process storage-layer accounting, not device-sector or exclusive filesystem measurements",
      "rchar/syscr include measurement and other process reads; sidecar pread counts are exact Python requests, not physical disk IO",
      "reopen with POSIX_FADV_DONTNEED is best effort, excludes connection open and does not establish cold cache",
      "warm primes same workload in a 2 MiB SQLite page cache; OS cache may persist or evict",
      "same runner sequential builds, 64 source and 32 rank samples, three batches; descriptive timing",
      "rank-only workload excludes origin-prefix verification; batch includes it",
      "synthetic AP schedule; no power-loss durability or independent human reproduction"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.source,a.target,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
