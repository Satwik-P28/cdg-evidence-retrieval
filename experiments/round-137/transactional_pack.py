"""R137 append-only frame file, SQLite-serialized writers, commit-last protocol.

Scope: Linux local filesystem, cooperating writers, immutable committed prefix.
No power-loss claim; process-death and injected failures tested separately.
"""
import argparse,hashlib,json,os,random,sqlite3,struct,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-132"))
import heldout_archive as h
import active_rank as ar
from anchor_bench import D,delta_decode
PTR=struct.Struct(">QQ")
HEADER=32
STAGES=("before_write","partial_write","written","synced","source","index","ledger","meta","commit")

def side(path):return Path(str(path)+".frames")
def die(stage,fault):
    if stage==fault:os._exit(77)

def write_all(fd,data,offset):
    while data:
        n=os.pwrite(fd,data,offset)
        if n<=0:raise OSError("short frame write")
        offset+=n;data=data[n:]

def setup(path,ext,manifest):
    if Path(path).exists() or side(path).exists():raise FileExistsError(path)
    db=h.integrated_setup(path,ext,manifest)
    ident=os.urandom(HEADER)
    fd=os.open(side(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:write_all(fd,ident,0);os.fsync(fd)
    finally:os.close(fd)
    dirfd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(dirfd)
    finally:os.close(dirfd)
    db.execute("CREATE TABLE pack_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),ident BLOB NOT NULL CHECK(length(ident)=32),end_offset INTEGER NOT NULL CHECK(end_offset>=32))")
    db.execute("INSERT INTO pack_state VALUES(1,?,?)",(ident,HEADER))
    db.commit();return db

def state(db,fd):
    ident,end=db.execute("SELECT ident,end_offset FROM pack_state WHERE singleton=1").fetchone()
    if os.pread(fd,HEADER,0)!=ident:raise ValueError("pack identity mismatch")
    if os.fstat(fd).st_size<end:raise ValueError("committed pack truncated")
    return end

def reconcile_locked(db,fd):
    # Only call while holding BEGIN IMMEDIATE. Old readers only reference the
    # immutable committed prefix, and no other cooperating writer can append.
    end=state(db,fd)
    if os.fstat(fd).st_size>end:
        os.ftruncate(fd,end);os.fsync(fd)
    return end

def recover(db,fd,a,i,expected=None):
    if not db.in_transaction:raise ValueError("snapshot required")
    end=state(db,fd)
    row=db.execute("SELECT n,digest,depth,parent_ord,payload FROM versions WHERE article=? AND ord=?",(a,i)).fetchone()
    if row is None:raise ValueError("missing revision")
    n,digest,depth,parent,ptr=row
    if len(ptr)!=PTR.size or depth not in (0,1) or (expected is not None and expected!=depth):raise ValueError("invalid frame metadata")
    off,size=PTR.unpack(ptr)
    if off<HEADER or size<=0 or off+size>end:raise ValueError("frame outside committed prefix")
    data=os.pread(fd,size,off)
    if len(data)!=size:raise ValueError("truncated frame")
    if depth==0:
        if parent is not None:raise ValueError("literal parent")
        raw=D.decompress(data,max_output_size=n+1);ab=size;dd=len(raw)
    else:
        if parent is None or not 0<=parent<i:raise ValueError("invalid anchor")
        old,ab,dd,_=recover(db,fd,a,parent,0)
        raw=delta_decode(data,old,n);ab+=size;dd+=len(raw)
    if len(raw)!=n or h.sha(raw)!=digest:raise ValueError("source digest")
    return raw,ab,dd,depth

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
        die("before_write",fault)
        split=max(1,len(payload)//2)
        write_all(fd,payload[:split],end);die("partial_write",fault)
        write_all(fd,payload[split:],end+split);die("written",fault)
        os.fsync(fd);die("synced",fault)
        digest=h.sha(raw)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(a,i,len(raw),digest,depth,parent,PTR.pack(end,len(payload))));die("source",fault)
        db.execute("INSERT INTO revisions VALUES(?,?,?)",(g,a,i))
        db.execute("INSERT INTO origin VALUES(?,?,?,?)",(g,commit,ts,blob))
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text));die("index",fault)
        dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0];total=prev_total+dl
        db.execute("INSERT INTO rank_ledger VALUES(?,?,?,?)",(g,dl,total,h.chain(prev_hash,g,a,i,digest,dl,total)));die("ledger",fault)
        db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(article) DO UPDATE SET ord=excluded.ord",(a,i))
        db.execute("UPDATE meta SET generation=? WHERE singleton=1",(g,))
        db.execute("UPDATE pack_state SET end_offset=? WHERE singleton=1",(end+len(payload),));die("meta",fault)
        db.commit();die("commit",fault)
        return g,i
    except BaseException:
        # Never truncate here: commit errors may be ambiguous. Reconcile only
        # under a fresh write transaction after SQLite resolves visibility.
        db.rollback();raise

def reconcile(db,fd):
    db.execute("BEGIN IMMEDIATE")
    try:end=reconcile_locked(db,fd);db.commit();return end
    except BaseException:db.rollback();raise

def issue(db,fd,phrases,op,c):
    if not db.in_transaction:raise ValueError("explicit snapshot required")
    lens,_=ar.load_ledger(db,h.generation(db))
    hits,n,total,df=ar.rank(db,phrases,op,c,lens,"interval")
    prefix=db.execute("SELECT prefix_sha FROM rank_ledger WHERE g=?",(c,)).fetchone()[0]
    rows=[]
    for g,s in hits:
        a,i,d=db.execute("""SELECT r.article,r.ord,v.digest FROM revisions r JOIN versions v
            ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?""",(g,)).fetchone()
        raw,_,_,_=recover(db,fd,a,i)
        if h.sha(raw)!=d:raise ValueError("receipt source mismatch")
        rows.append(dict(g=g,article=a,ordinal=i,source_sha256=d.hex(),score_hex=s.hex()))
    body=dict(format=ar.FORMAT,scorer=ar.SCORER,cutoff=c,phrases=list(phrases),op=op,k=10,
        prefix_sha256=prefix.hex(),active_documents=n,active_tokens=total,phrase_df=df,hits=rows)
    return body,h.sha(h.canonical(body)).hex()

def audit(db,fd):
    n=h.audit(db);end=state(db,fd);pos=HEADER
    for a,i,ptr in db.execute("SELECT r.article,r.ord,v.payload FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord ORDER BY r.generation"):
        off,size=PTR.unpack(ptr)
        if off!=pos or size<=0:raise ValueError("pack gap/overlap")
        pos+=size;recover(db,fd,a,i)
    if pos!=end:raise ValueError("pack ledger mismatch")
    return n

def fixture(raw,tag):return h.fixture_origin(raw,tag)

def crash_suite(folder,ext):
    outcomes=[]
    for stage in STAGES:
        path=folder/(stage+".sqlite");db=setup(path,ext,{"fixture":True});fd=os.open(side(path),os.O_RDWR)
        append(db,fd,"a",b"old word "*100,fixture(b"old word "*100,"old"))
        reader=h.connect(path,ext);reader.execute("BEGIN");old=issue(reader,fd,("old",),"AND",1)
        before=state(reader,fd);db.close()
        p=subprocess.run([sys.executable,__file__,"--crash",str(path),str(ext),stage],capture_output=True,timeout=60)
        if p.returncode!=77:raise AssertionError((stage,p.returncode,p.stderr[-1000:]))
        assert h.generation(reader)==1 and issue(reader,fd,("old",),"AND",1)==old
        db=h.connect(path,ext);db.execute("BEGIN")
        n=2 if stage=="commit" else 1
        assert audit(db,fd)==n and issue(db,fd,("old",),"AND",1)==old
        orphan=os.fstat(fd).st_size-state(db,fd);db.rollback()
        after=reconcile(db,fd);assert os.fstat(fd).st_size==after
        assert after>before if n==2 else after==before
        raw=b"retry word "*100;append(db,fd,"a",raw,fixture(raw,"retry"))
        db.execute("BEGIN");assert audit(db,fd)==n+1;db.rollback()
        assert issue(reader,fd,("old",),"AND",1)==old
        reader.rollback();reader.close();db.close();os.close(fd)
        outcomes.append(dict(stage=stage,visible_generations=n,orphan_bytes=orphan,retry_pass=True))
    return outcomes

def experiment(folder,events,manifest,ext):
    cuts=manifest["cutoffs"];refs={c:h.active_oracle(events,c) for c in cuts};qs=h.plan_queries(refs[cuts[0]])
    results={};bodies={}
    for policy in ("snapshot","bounded_anchor"):
        path=folder/(policy+".sqlite");db=setup(path,ext,manifest);fd=os.open(side(path),os.O_RDWR)
        times=[];reader=None;pinned={}
        for g,(a,i,raw) in enumerate(events,1):
            t=time.perf_counter_ns();assert append(db,fd,a,raw,h.origin_tuple(manifest["origins"][g-1]),policy)==(g,i)
            times.append((time.perf_counter_ns()-t)/1000)
            if g==cuts[0]:
                reader=h.connect(path,ext);reader.execute("BEGIN")
                pinned={(p,o):issue(reader,fd,p,o,g) for p,o in qs}
        assert h.generation(reader)==cuts[0]
        for (p,o),want in pinned.items():assert issue(reader,fd,p,o,cuts[0])==want
        reader.rollback();reader.close()
        db.execute("BEGIN");assert audit(db,fd)==len(events);h.assert_origin(db,manifest)
        db.rollback();db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();db=h.connect(path,ext);db.execute("BEGIN")
        assert audit(db,fd)==len(events)
        err=0.;checks=0
        for c,ref in refs.items():
            for p,o in qs:
                body,digest=issue(db,fd,p,o,c)
                err=max(err,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,p,o)))
                if (c,p,o) in bodies:assert bodies[c,p,o]==(body,digest)
                else:bodies[c,p,o]=(body,digest)
                checks+=1
        encoded=decoded=raw_bytes=0;maxa=maxd=0.;reads=[]
        for a,i,want in events:
            t=time.perf_counter_ns();raw,ab,dd,d=recover(db,fd,a,i);reads.append((time.perf_counter_ns()-t)/1000)
            assert raw==want
            full=len(h.C.compress(raw))
            if policy=="bounded_anchor":assert d<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
            encoded+=ab;decoded+=dd;raw_bytes+=len(raw);maxa=max(maxa,ab/full)
            if raw:maxd=max(maxd,dd/len(raw))
        end=state(db,fd);assert end==os.fstat(fd).st_size
        db.rollback();db.close();os.close(fd)
        results[policy]=dict(sqlite_bytes=path.stat().st_size,sidecar_bytes=end,payload_bytes=end-HEADER,
          total_archive_bytes=path.stat().st_size+end,append=h.quant(times),read=h.quant(reads),
          activated_bytes=encoded,decode_amplification=decoded/max(1,raw_bytes),max_activation=maxa,max_decode=maxd,
          source_reads=len(events),rank_checks=checks,max_score_error=err,pinned_checks=len(pinned))
    for ref in refs.values():ref.close()
    return dict(policies=results,query_plan_sha256=h.sha(h.canonical([dict(phrases=p,op=o) for p,o in qs])).hex())

def run(root,corpus,ext):
    if corpus in ("gitdocs","k8sdocs"):
        events,m=h.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    else:
        sys.path.insert(0,str(HERE.parent/"round-131"));import budget_archive as old
        events,m=old.collect(root,corpus);frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    f=json.loads(frozen.read_text());assert h.sha(h.canonical(m)).hex()==f["manifest_sha256"]
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d);result=experiment(folder,events,m,ext);result["crash_suite"]=crash_suite(folder,ext)
    for p,x in result["policies"].items():assert x["payload_bytes"]==f["result"]["policies"][p]["payload_bytes"]
    assert result["query_plan_sha256"]==h.sha(h.canonical(f["result"]["query_plan"])).hex()
    return dict(round=137,corpus=corpus,manifest_sha256=f["manifest_sha256"],result=result,
      limits=["process death only; no measured power-loss durability","cooperating SQLite-serialized local writers, immutable committed prefix, no compaction",
        "explicit fsync ordering; file creation crash and filesystem faults not modeled","revision-level atomicity, not whole Git commit"])

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,p,e,fault=sys.argv;path=Path(p);db=h.connect(path,Path(e));fd=os.open(side(path),os.O_RDWR)
        raw=b"new word "*100;append(db,fd,"a",raw,fixture(raw,"new"),fault=fault);raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus,a.extension.resolve());a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
