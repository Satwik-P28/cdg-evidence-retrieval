"""R160: matched archive validation on real first-parent Git commit boundaries."""
import argparse,json,os,platform,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-159"))
from physical_io import j,h,tp,bv,fr,recover,proc_io,difference,reader,workloads,IO_FIELDS

def check_trees(root,corpus,collector,events,m):
    # Fresh Git tree reads, at the designated query cutoffs plus fixed
    # additional sampled commit boundaries. No timestamp sorting.
    snapshots=m["first_parent_path_touch_snapshots"]
    ids={0,len(snapshots)-1}
    for c in m["cutoffs"]:
        ids.add(next(i for i,s in enumerate(snapshots) if s["end_generation"]==c))
    ids.update(random.Random(160).sample(range(len(snapshots)),min(12,len(snapshots))))
    active={};position=0;checks=0;rows=[]
    for idx in sorted(ids):
        s=snapshots[idx];c=s["end_generation"]
        for p,i,raw in events[position:c]:
            import hashlib
            active[p]=(i,hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest())
        position=c
        tree=collector.tree(root,s["commit"],corpus)
        assert set(active)==set(m["retained_paths"])
        assert {p:x[1] for p,x in active.items()}=={p:tree[p] for p in m["retained_paths"]}
        checks+=len(active);rows.append(dict(commit=s["commit"],cutoff=c,committer_unix=s["committer_unix"],checked_paths=len(active)))
    return dict(snapshots=len(rows),path_checks=checks,rows=rows)

def run(root,corpus,folder,ext):
    if corpus in ("gitdocs","k8sdocs"):
        collector=h;events,m=collector.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    else:
        sys.path.insert(0,str(HERE.parent/"round-131"));import budget_archive as collector
        events,m=collector.collect(root,corpus);frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    old=json.loads(frozen.read_text());manifest=h.sha(h.canonical(m)).hex()
    assert manifest==old["manifest_sha256"]
    n=len(events);origins=[h.origin_tuple(x) for x in m["origins"]]
    cuts=m["cutoffs"];first=cuts[0];assert cuts[-1]==n
    tree_checks=check_trees(root,corpus,collector,events,m)
    refs={c:h.active_oracle(events,c) for c in cuts};qs=h.plan_queries(refs[first])
    assert qs
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
        db.execute("BEGIN");assert j.audit(db,fd,quotient)==n;h.assert_origin(db,m);end=tp.state(db,fd);db.rollback()
        before=proc_io();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();os.close(fd);finalization=difference(before,proc_io())
        sizes=[path.stat(),tp.side(path).stat()]
        total=sum(x.st_size for x in sizes);allocated=sum(x.st_blocks*512 for x in sizes)
        if policy=="snapshot":
            # Both snapshot arms must share the same unique literal frames.
            # Different raw inputs can in principle yield equal frame bytes; explicitly dedup encoded bytes.
            expected_payload=sum(map(len,{h.C.compress(raw) for _,_,raw in events}))
            assert end-tp.HEADER==expected_payload
        if reference is None:reference=issued
        else:assert issued==reference
        with reader(path,ext) as (db,fd):
            assert j.audit(db,fd,quotient)==n;h.assert_origin(db,m)
            decoded=rawbytes=activated=0;maxd=maxa=0.
            for a,i,want in events:
                raw,ab,dd,depth=recover(db,fd,a,i);assert raw==want
                full=len(h.C.compress(want));assert depth<=1 and 2*dd<=5*len(want) and 2*ab<=3*full
                decoded+=dd;rawbytes+=len(raw);activated+=ab
                if raw:maxd=max(maxd,dd/len(raw))
                maxa=max(maxa,ab/full)
            for (c,p,o),want in expected.items():
                body=fr.rank_body(db,fd,p,o,c,mode);h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["hits"]],want)
            assert fr.verify_batch(db,fd,issued,mode)==n
        reads,errors=workloads(path,ext,events,expected,issued,mode)
        results[name]=dict(total_archive_bytes=total,allocated_bytes=allocated,source_payload_bytes=end-tp.HEADER,
          append=h.quant(append_times),ingestion_process_io=ingestion,finalization_process_io=finalization,
          source_checks=n,rank_checks=len(expected),receipt_checks=len(issued),workloads=reads,advice_errors=errors,
          mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
          activated_source_bytes=activated,receipt_commitments_sha256=h.sha(h.canonical([digest for _,digest in issued])).hex())
        print("ARM_DONE="+name,flush=True)
    for ref in refs.values():ref.close()
    return dict(round=160,corpus=corpus,revisions=n,manifest_sha256=manifest,cutoffs=cuts,
      query_count=len(qs),query_plan_sha256=h.sha(h.canonical([dict(phrases=p,op=o) for p,o in qs])).hex(),
      tree_checks=tree_checks,retained_paths=len(m["retained_paths"]),changed_paths=m["changed_paths"],
      committer_timestamp_regressions=m["committer_timestamp_regressions"],pin=m["pin"],kernel=platform.release(),
      machine=platform.machine(),filesystem=os.statvfs(folder).f_bsize,policies=results,limitations=[
      "Linux /proc/self/io read_bytes/write_bytes are process storage-layer accounting, not device-sector or exclusive filesystem measurements",
      "rchar/syscr include measurement and other process reads; sidecar pread counts are exact Python requests, not physical disk IO",
      "reopen with POSIX_FADV_DONTNEED is best effort, excludes connection open and does not establish cold cache",
      "warm primes same workload in a 2 MiB SQLite page cache; OS cache may persist or evict",
      "same runner sequential builds, 64 source and 32 rank samples, three batches; descriptive timing",
      "rank-only workload excludes origin-prefix verification; batch includes it",
      "real pinned first-parent path-touch ancestry, not sorted wall-clock time; no deletion/new-file/rename or whole-commit atomicity",
      "four previously studied technical corpora, not new independent human replication",
      "no power-loss durability"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=("cpython","bips","gitdocs","k8sdocs"),required=True)
    p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.root,a.corpus,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
