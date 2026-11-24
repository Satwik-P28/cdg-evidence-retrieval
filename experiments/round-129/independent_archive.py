"""R129: integrated source/index archives on independent first-parent Git histories.

Frozen cohort rule: last 400 path-touch first-parent commits at pinned revision;
80 baseline paths selected by salted SHA256, exclude sampled paths deleted
during observed snapshots (reported). Actual Git blob bytes, no normalization.
Both variants share R120 schema, atomic ranking ledger and full positional FTS5.
"""
import argparse,collections,hashlib,json,os,random,re,sqlite3,statistics,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-120"))
from active_rank import setup,audit,connect,issue,replay,rank,active_oracle,native,verify
from atomic_receipts import SEED,chain,die,canonical,STAGES
from rank_replay import plan_queries
from versioned_evidence import choose,recover,generation,Receipt,read_receipt,C,sha
SPECS={
 "cpython":dict(repo="python/cpython",pin="60403a5409ff2c3f3b07dd2ca91a7a3e096839c7",pathspec=["Doc/library"],license="PSF license; upstream LICENSE"),
 "bips":dict(repo="bitcoin/bips",pin="0d99ffd39fdaf75209c43b1f8ec3fbbc23f10814",pathspec=[":(glob)bip-*.mediawiki",":(glob)bip-*.md"],license="per-BIP license declarations; source blobs not redistributed"),
}
POLICIES=("snapshot","bounded_anchor")
SALT="CDG-R129-cohort-v1|"
WINDOW=400
COHORT=80

def git(root,*args,input=None,check=True):
    p=subprocess.run(["git","-C",str(root),*args],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if check and p.returncode:raise RuntimeError("git "+repr(args)+" "+p.stderr[-1000:].decode(errors="replace"))
    return p

def eligible(name,kind):
    return (name.startswith("Doc/library/") and name.count("/")==2 and name.endswith(".rst")) if kind=="cpython" else bool(re.fullmatch(r"bip-[0-9]+\.(mediawiki|md)",name))

def tree(root,commit,kind):
    args=["ls-tree","-r","-z",commit]
    if kind=="cpython":args+=["--","Doc/library"]
    raw=git(root,*args).stdout;out={}
    for row in raw.split(b"\0"):
        if not row:continue
        info,name=row.split(b"\t",1);mode,typ,oid=info.decode().split();name=name.decode("utf8")
        if typ=="blob" and mode in ("100644","100755") and eligible(name,kind):out[name]=oid
    return out

def blob_batch(root,oids):
    # Batch prefetch from a promisor remote when present. If the server rejects
    # direct blob wants, cat-file's normal lazy fetch is the fallback.
    if git(root,"config","--get","remote.origin.promisor",check=False).stdout.strip()==b"true":
        p=git(root,"-c","fetch.negotiationAlgorithm=noop","fetch","--no-tags","--filter=blob:none","origin","--stdin",
              input=("\n".join(oids)+"\n").encode(),check=False)
        print("BLOB_PREFETCH",p.returncode,len(oids),flush=True)
    raw=git(root,"cat-file","--batch",input=("\n".join(oids)+"\n").encode()).stdout
    p=0;out={}
    for expected in oids:
        end=raw.index(b"\n",p);head=raw[p:end].decode().split();p=end+1
        if len(head)!=3 or head[0]!=expected or head[1]!="blob":raise ValueError("missing source blob")
        n=int(head[2]);body=raw[p:p+n];p+=n
        if len(body)!=n or raw[p:p+1]!=b"\n":raise ValueError("git framing")
        p+=1
        if hashlib.sha1(("blob "+str(n)+"\0").encode()+body).hexdigest()!=expected:raise ValueError("Git object digest")
        body.decode("utf8",errors="strict");out[expected]=body
    if p!=len(raw):raise ValueError("trailing git batch bytes")
    return out

def collect(root,kind,pin=None,window=WINDOW,cohort=COHORT):
    spec=SPECS[kind];pin=pin or spec["pin"]
    if git(root,"rev-parse",pin).stdout.decode().strip()!=pin:raise ValueError("pin mismatch")
    lines=git(root,"log","--first-parent","--format=%H%x09%ct","-n",str(window),pin,"--",*spec["pathspec"]).stdout.decode().splitlines()
    commits=[(line.split("\t")[0],int(line.split("\t")[1])) for line in reversed(lines)]
    if len(commits)!=window:raise ValueError("insufficient path-touch history")
    baseline=git(root,"rev-parse",commits[0][0]+"^1").stdout.decode().strip()
    bt=int(git(root,"show","-s","--format=%ct",baseline).stdout)
    base=tree(root,baseline,kind)
    selected=sorted(base,key=lambda x:sha((SALT+kind+"|"+x).encode()))[:cohort]
    if len(selected)!=cohort:raise ValueError("insufficient baseline paths")
    states=[base]+[tree(root,c,kind) for c,_ in commits]
    excluded=sorted(p for p in selected if any(p not in st for st in states))
    paths=sorted(set(selected)-set(excluded))
    if not paths:raise ValueError("empty surviving cohort")
    origins=[];ordinals=collections.Counter();prior={};cutoffs=[];commit_rows=[]
    snapshots=[(baseline,bt)]+commits
    for step,((commit,ts),st) in enumerate(zip(snapshots,states)):
        for p in paths:
            oid=st[p]
            if oid==prior.get(p):continue
            origins.append((p,ordinals[p],commit,ts,oid));ordinals[p]+=1;prior[p]=oid
        commit_rows.append(dict(commit=commit,committer_unix=ts,end_generation=len(origins)))
        if step in (0,window//3,2*window//3,window):cutoffs.append(len(origins))
    cuts=sorted(set(cutoffs))
    if len(cuts)<2:raise ValueError("no observed cohort changes")
    blobs=blob_batch(root,sorted({o[-1] for o in origins}))
    events=[(p,i,blobs[oid]) for p,i,commit,ts,oid in origins]
    manifest=dict(kind=kind,repo=spec["repo"],pin=pin,baseline=baseline,license=spec["license"],
        salt=SALT,window=window,requested_paths=cohort,selected_paths=selected,excluded_deleted=excluded,
        retained_paths=paths,changed_paths=sum(n>1 for n in ordinals.values()),cutoffs=cuts,
        first_parent_path_touch_snapshots=commit_rows,committer_timestamp_regressions=sum(b[1]<a[1] for a,b in zip(snapshots,snapshots[1:])),
        origins=[dict(g=g,path=p,ordinal=i,commit=c,committer_unix=t,blob_sha1=o,source_sha256=sha(raw).hex(),bytes=len(raw))
                 for g,((p,i,c,t,o),(_,_,raw)) in enumerate(zip(origins,events),1)])
    return events,manifest

def integrated_setup(path,ext,manifest):
    db=setup(path,ext)
    db.executescript("""CREATE TABLE origin(g INTEGER PRIMARY KEY REFERENCES revisions(generation),
      commit_sha1 TEXT NOT NULL CHECK(length(commit_sha1)=40),committer_unix INTEGER NOT NULL,
      blob_sha1 TEXT NOT NULL CHECK(length(blob_sha1)=40));
      CREATE TABLE corpus(k TEXT PRIMARY KEY,v BLOB NOT NULL) WITHOUT ROWID;""")
    # Charge complete cohort rule, selected snapshot map and provenance policy
    # inside both DBs; individual event origin rows charged separately.
    meta={k:v for k,v in manifest.items() if k!="origins"}
    db.execute("INSERT INTO corpus VALUES('manifest',?)",(canonical(meta),))
    db.commit()
    return db

def append_policy(db,article,raw,origin,policy,fault=None):
    if policy not in POLICIES or db.in_transaction:raise ValueError("invalid writer")
    text=raw.decode("utf8",errors="strict")
    commit,ts,blob=origin
    if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
    db.execute("BEGIN IMMEDIATE")
    try:
        prior=generation(db);g=prior+1
        if prior:
            prev_total,prev_hash=db.execute("SELECT total,prefix_sha FROM rank_ledger WHERE g=?",(prior,)).fetchone()
        else:prev_total,prev_hash=0,SEED
        rows=db.execute("SELECT ord,length(payload),depth FROM versions WHERE article=? ORDER BY ord",(article,)).fetchall()
        if any(i!=r[0] for i,r in enumerate(rows)):raise ValueError("ordinal")
        i=len(rows);history=[(b"",size,depth) for _,size,depth in rows]
        if policy=="bounded_anchor":
            # R115 only consults the last four literal anchors. Do not decode
            # unrelated history on either arm. Selection policy unchanged.
            for j in [j for j in range(i-1,-1,-1) if rows[j][2]==0][:4]:
                old,_,_,depth=recover(db,article,j,0);history[j]=(old,rows[j][1],depth)
        parent,depth,payload=choose(raw,i,history,policy);digest=sha(raw)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(article,i,len(raw),digest,depth,parent,payload));die("source",fault)
        db.execute("INSERT INTO revisions VALUES(?,?,?)",(g,article,i))
        db.execute("INSERT INTO origin VALUES(?,?,?,?)",(g,commit,ts,blob))
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text));die("index",fault)
        dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0];total=prev_total+dl
        db.execute("INSERT INTO rank_ledger VALUES(?,?,?,?)",(g,dl,total,chain(prev_hash,g,article,i,digest,dl,total)));die("ledger",fault)
        db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(article) DO UPDATE SET ord=excluded.ord",(article,i))
        db.execute("UPDATE meta SET generation=? WHERE singleton=1",(g,));die("meta",fault)
        db.commit();die("commit",fault)
        return g,i
    except BaseException:
        db.rollback();raise

def assert_origin(db,manifest):
    want=[(o["g"],o["commit"],o["committer_unix"],o["blob_sha1"]) for o in manifest["origins"]]
    if db.execute("SELECT * FROM origin ORDER BY g").fetchall()!=want:raise AssertionError("origin mismatch")
    expected=canonical({k:v for k,v in manifest.items() if k!="origins"})
    if db.execute("SELECT v FROM corpus WHERE k='manifest'").fetchone()[0]!=expected:raise AssertionError("manifest mismatch")

def quant(xs):
    return dict(median_us=statistics.median(xs),p95_us=sorted(xs)[int(.95*(len(xs)-1))],samples=len(xs))

def compact(db,path):
    wal=Path(str(path)+"-wal").stat().st_size
    if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:raise AssertionError("busy checkpoint")
    before=path.stat().st_size
    db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AssertionError("integrity")
    return dict(sqlite_bytes=path.stat().st_size,pre_vacuum_sqlite_bytes=before,wal_bytes_before_checkpoint=wal,
       payload_bytes=db.execute("SELECT sum(length(payload)) FROM versions").fetchone()[0],
       depth_counts=dict(db.execute("SELECT depth,count(*) FROM versions GROUP BY depth")))

def origin_tuple(o):return (o["commit"],o["committer_unix"],o["blob_sha1"])

def experiment(folder,events,manifest,ext,repeats=3):
    n=len(events);cuts=manifest["cutoffs"];ref=active_oracle(events,cuts[0]);qs=plan_queries(ref);ref.close()
    if not qs:raise ValueError("empty query plan")
    # Independently rebuild every active snapshot, before both archive builds.
    expected={};refs={}
    for c in cuts:
        ref=active_oracle(events,c);refs[c]=ref
        for ps,op in qs:expected[c,ps,op]=native(ref,ps,op)
    results={};dbs={};bodies={};rng=random.Random(129)
    policies=list(POLICIES);rng.shuffle(policies)
    for policy in policies:
        path=folder/(policy+".sqlite");db=integrated_setup(path,ext,manifest)
        append_us=[];pinned=None;receipts=[]
        for g,(a,i,raw) in enumerate(events,1):
            start=time.perf_counter_ns();got=append_policy(db,a,raw,origin_tuple(manifest["origins"][g-1]),policy)
            append_us.append((time.perf_counter_ns()-start)/1000)
            if got!=(g,i):raise AssertionError("generation")
            if g==cuts[0]:
                pinned=connect(path,ext);pinned.execute("BEGIN")
                if generation(pinned)!=g:raise AssertionError("pin")
                for ps,op in qs:
                    body,digest=issue(pinned,ps,op,g)
                    verify([(h["g"],float.fromhex(h["score_hex"])) for h in body["hits"]],expected[g,ps,op])
                    receipts.append((body,digest))
        if generation(pinned)!=cuts[0]:raise AssertionError("pinned snapshot drift")
        for body,digest in receipts:replay(pinned,body,digest)
        pinned.rollback();pinned.close()
        db.execute("BEGIN")
        if audit(db)!=n:raise AssertionError("audit")
        assert_origin(db,manifest)
        for body,digest in receipts:replay(db,body,digest)
        err=0.;rank_hits=0;receipt_bytes=0
        for c in cuts:
            for ps,op in qs:
                body,digest=issue(db,ps,op,c)
                err=max(err,verify([(h["g"],float.fromhex(h["score_hex"])) for h in body["hits"]],expected[c,ps,op]))
                rank_hits+=len(body["hits"]);receipt_bytes+=len(canonical(body))+32
                key=c,ps,op
                if key in bodies and bodies[key]!=(body,digest):raise AssertionError("policy receipt mismatch")
                bodies[key]=(body,digest)
        db.rollback()
        stats=compact(db,path);db.close()
        db=connect(path,ext);db.execute("BEGIN")
        if audit(db)!=n:raise AssertionError("reopen audit")
        assert_origin(db,manifest)
        # Receipts issued while building and on final archive must survive VACUUM/reopen.
        for body,digest in bodies.values():replay(db,body,digest)
        results[policy]=dict(**stats,append=quant(append_us),max_score_error=err,ranked_hits=rank_hits,
            receipt_checks=len(cuts)*len(qs),pinned_replays=len(receipts),fresh_replays=len(receipts),
            reopen_replays=len(bodies),external_receipt_bytes=receipt_bytes)
        dbs[policy]=db
    raw_bytes=sum(len(raw) for _,_,raw in events)
    read_times={p:[] for p in POLICIES};work={p:collections.Counter() for p in POLICIES}
    max_amp={p:[0.,0.] for p in POLICIES}
    seq=list(enumerate(events,1));rng.shuffle(seq)
    for g,(a,i,raw) in seq:
        rec=Receipt(n,g,a,i,sha(raw).hex());full=len(C.compress(raw))
        ps=list(POLICIES);rng.shuffle(ps)
        for p in ps:
            st=time.perf_counter_ns();got,encoded,decoded=read_receipt(dbs[p],rec)
            read_times[p].append((time.perf_counter_ns()-st)/1000)
            if got!=raw:raise AssertionError("exact source mismatch")
            if p=="bounded_anchor" and (2*encoded>3*full or 2*decoded>5*len(raw)):raise AssertionError("activation/decode bound")
            work[p].update(dict(reads=1,activated=encoded,decoded=decoded))
            max_amp[p][0]=max(max_amp[p][0],encoded/full)
            if raw:max_amp[p][1]=max(max_amp[p][1],decoded/len(raw))
    lens=[0]+[x[0] for x in dbs["snapshot"].execute("SELECT dl FROM rank_ledger ORDER BY g")]
    times={p:{"rank":[],"receipt":[]} for p in POLICIES}
    # Same query order and randomly interleaved variants after compact/reopen.
    for c in cuts:
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for ps,op in req:
                arms=list(POLICIES);rng.shuffle(arms)
                for p in arms:
                    db=dbs[p]
                    st=time.perf_counter_ns();got=rank(db,ps,op,c,lens,"interval")[0]
                    times[p]["rank"].append((time.perf_counter_ns()-st)/1000)
                    verify(got,expected[c,ps,op])
                    st=time.perf_counter_ns();body,digest=issue(db,ps,op,c)
                    times[p]["receipt"].append((time.perf_counter_ns()-st)/1000)
                    if (body,digest)!=bodies[c,ps,op]:raise AssertionError("timed receipt mismatch")
    for p in POLICIES:
        results[p].update(source_lookup=quant(read_times[p]),source_reads=work[p]["reads"],
            activated_payload_bytes=work[p]["activated"],decoded_source_bytes=work[p]["decoded"],
            decode_amplification=work[p]["decoded"]/max(1,raw_bytes),
            max_activation_relative_to_snapshot_frame=max_amp[p][0],max_decode_relative_to_nonempty_request=max_amp[p][1],
            warm_rank=quant(times[p]["rank"]),warm_receipt=quant(times[p]["receipt"]))
        dbs[p].rollback();dbs[p].close()
    for ref in refs.values():ref.close()
    return dict(revisions=n,documents=len(manifest["retained_paths"]),changed_documents=manifest["changed_paths"],
        raw_source_bytes=raw_bytes,cutoffs=cuts,queries_per_cutoff=len(qs),policies=results,
        build_order=policies,repetitions=repeats,query_plan=[dict(phrases=ps,op=op) for ps,op in qs])

def fixture_origin(raw,seed):
    return (hashlib.sha1(seed.encode()).hexdigest(),0,hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest())

def crash_audit(folder,ext):
    checked=[]
    for policy in POLICIES:
        for stage in STAGES:
            path=folder/(policy+"-"+stage+".sqlite");db=integrated_setup(path,ext,{"fixture":True})
            old=b"old word "*100;new=b"new word "*100
            append_policy(db,"fixture",old,fixture_origin(old,"old"),policy);db.close()
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--crash",str(path),str(ext),policy,stage],capture_output=True,timeout=30)
            if p.returncode!=77:raise AssertionError("crash stage failed "+repr(p.stderr[-500:]))
            db=connect(path,ext);db.execute("BEGIN");n=2 if stage=="commit" else 1
            if generation(db)!=n or audit(db)!=n or db.execute("SELECT count(*) FROM origin").fetchone()[0]!=n:raise AssertionError("partial state")
            body,_=issue(db,("new",),"AND",n)
            if len(body["hits"])!=int(n==2):raise AssertionError("partial index")
            got,_,_=recover(db,"fixture",n-1)[:3]
            if got!=(new if n==2 else old):raise AssertionError("partial source")
            db.rollback();db.close();checked.append(policy+":"+stage)
    return checked

def run(root,kind,ext,repeats):
    events,manifest=collect(root,kind)
    print("CORPUS",kind,len(events),len(manifest["retained_paths"]),manifest["changed_paths"],manifest["cutoffs"],flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        r=experiment(Path(tmp),events,manifest,ext,repeats)
        r["crash_stages_passed"]=crash_audit(Path(tmp),ext)
    return dict(round=129,corpus=kind,manifest_sha256=sha(canonical(manifest)).hex(),manifest=manifest,result=r,
       limits=["fixed first-parent path-touch commit snapshots; ancestry order, not globally sorted wall-clock timestamps; initial cohort seeded at common baseline",
       "sampled paths absent at any observed snapshot excluded and reported; no deletion/rename/new-file support",
       "independent repositories but two text-document genres, not representative user workload",
       "baseline-selected query plan; same queries repeated at observed commit boundaries; not a relevance benchmark",
       "both arms use identical full positional native FTS5, atomic rank ledger, validity/stats, origin and corpus schema; no compact TF advantage assumed",
       "warm rank and receipt timing after reopen, not cold disk I/O; append timings sequential one runner",
       "WAL file bytes before checkpoint, not device write amplification; process death not power loss",
       "logical compressed activation and decoded bytes, not physical page reads",
       "Git origin rows audited against pinned manifest; receipt chain binds source digest and revision, not authenticated Git metadata",
       "external receipt exports counted separately; no semantic answer or hallucination claim"])
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,path,ext,policy,stage=sys.argv;db=connect(path,ext);raw=b"new word "*100
        append_policy(db,"fixture",raw,fixture_origin(raw,"new"),policy,stage);raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=SPECS,required=True)
    p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    result=run(a.root,a.corpus,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    # Manifest can be large; print results and a compact manifest summary.
    print("RESULT_JSON="+json.dumps(result,separators=(",",":")),flush=True)
