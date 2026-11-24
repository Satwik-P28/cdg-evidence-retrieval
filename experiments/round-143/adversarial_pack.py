"""R143: competing local processes, injected I/O errors, ambiguous commit,
and receipt-contract negative controls. No power-loss or malicious-writer proof.
"""
import argparse,collections,errno,json,multiprocessing as mp,os,random,sqlite3,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-137"))
import transactional_pack as tp
import heldout_archive as h
import zstandard

def raw_for(seed,w,j):
    # Shared article histories, distinct operations, deterministic bytes.
    return ("common evidence "+("word "*120)+f"worker {w} operation {j} seed {seed}").encode()

def writer(path,ext,seed,w,count,gate,queue):
    db=h.connect(path,ext);fd=os.open(tp.side(path),os.O_RDWR)
    gate.wait(30)
    try:
        for j in range(count):
            raw=raw_for(seed,w,j);article="shared-"+str(j%3)
            g,i=tp.append(db,fd,article,raw,tp.fixture(raw,f"{seed}:{w}:{j}"))
            queue.put((w,j,g,i))
    finally:db.close();os.close(fd)

def dying_writer(path,ext,seed,stage,gate):
    db=h.connect(path,ext);fd=os.open(tp.side(path),os.O_RDWR)
    gate.wait(30)
    raw=raw_for(seed,999,0)
    tp.append(db,fd,"shared-0",raw,tp.fixture(raw,"dying-"+str(seed)),fault=stage)
    raise AssertionError("fault not reached")

def concurrency(folder,ext,seed,workers,count,stage):
    path=folder/"archive.sqlite";db=tp.setup(path,ext,{"stress_seed":seed})
    fd=os.open(tp.side(path),os.O_RDWR)
    first=b"common evidence original "*100
    tp.append(db,fd,"shared-0",first,tp.fixture(first,"first"))
    reader=h.connect(path,ext);reader.execute("BEGIN")
    pinned=tp.issue(reader,fd,("common",),"AND",1)
    ctx=mp.get_context("spawn");gate=ctx.Event();q=ctx.Queue()
    jobs=[ctx.Process(target=writer,args=(path,ext,seed,w,count,gate,q)) for w in range(workers)]
    dying=ctx.Process(target=dying_writer,args=(path,ext,seed,stage,gate))
    for p in jobs+[dying]:p.start()
    gate.set();acks=[];pinned_checks=0
    try:
        for _ in range(workers*count):
            acks.append(q.get(timeout=90))
            if len(acks)%8==0:
                assert h.generation(reader)==1
                assert tp.issue(reader,fd,("common",),"AND",1)==pinned
                pinned_checks+=1
        for p in jobs+[dying]:p.join(30)
        assert all(p.exitcode==0 for p in jobs),[p.exitcode for p in jobs]
        assert dying.exitcode==77
    finally:
        for p in jobs+[dying]:
            if p.is_alive():p.terminate();p.join()
        q.close();q.join_thread()
    assert len(set((w,j) for w,j,_,_ in acks))==workers*count
    tp.reconcile(db,fd);db.execute("BEGIN")
    n=1+workers*count+int(stage=="commit")
    assert tp.audit(db,fd)==n
    assert tp.state(db,fd)==os.fstat(fd).st_size
    rows=db.execute("SELECT generation,article,ord FROM revisions ORDER BY generation").fetchall()
    actual={}
    for g,a,i in rows:
        raw,ab,dd,d=tp.recover(db,fd,a,i);actual[g]=(a,i,raw)
        full=len(h.C.compress(raw));assert d<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
    assert actual[1]==("shared-0",0,first)
    for w,j,g,i in acks:assert actual[g]==("shared-"+str(j%3),i,raw_for(seed,w,j))
    assert len({g for _,_,g,_ in acks})==workers*count
    if stage=="commit":
        leftovers=set(actual)-{1}-{g for _,_,g,_ in acks};assert len(leftovers)==1
        assert actual[leftovers.pop()][2]==raw_for(seed,999,0)
    events=[actual[g] for g in range(1,n+1)]
    checks=0
    for c in sorted({1,max(1,n//3),max(1,2*n//3),n}):
        ref=h.active_oracle(events,c)
        for p,o in [(("common",),"AND"),(("operation",),"AND"),(("worker","seed"),"OR")]:
            body,_=tp.issue(db,fd,p,o,c)
            h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,p,o));checks+=1
        ref.close()
    db.rollback();assert tp.issue(reader,fd,("common",),"AND",1)==pinned
    reader.rollback();reader.close();db.close();os.close(fd)
    return dict(seed=seed,workers=workers,acks=len(acks),death_stage=stage,visible=n,
        pinned_checks=pinned_checks+1,rank_checks=checks,source_checks=n)

class CommitProxy:
    def __init__(self,db,after):self.db=db;self.after=after
    def __getattr__(self,key):return getattr(self.db,key)
    def commit(self):
        if self.after:self.db.commit()
        raise OSError(errno.EIO,"injected ambiguous commit boundary")

def failures(folder,ext):
    results=[]
    for mode in ("short_writes","write_enospc","write_eio","fsync_eio","commit_before","commit_after"):
        path=folder/(mode+".sqlite");db=tp.setup(path,ext,{});fd=os.open(tp.side(path),os.O_RDWR)
        first=b"old evidence "*100;tp.append(db,fd,"a",first,tp.fixture(first,"old"))
        raw=b"new evidence "*100;orig=tp.fixture(raw,mode)
        pwrite=os.pwrite;fsync=os.fsync;calls=0
        def inject(f,data,off):
            nonlocal calls
            calls+=1
            if mode=="short_writes":return pwrite(f,data[:max(1,len(data)//2)],off)
            if calls==2:raise OSError(errno.ENOSPC if mode=="write_enospc" else errno.EIO,"injected")
            return pwrite(f,data,off)
        def sync(f):raise OSError(errno.EIO,"injected file fsync")
        caught=False
        try:
            if mode.startswith("commit"):
                tp.append(CommitProxy(db,mode=="commit_after"),fd,"a",raw,orig)
            elif mode=="fsync_eio":
                with patch.object(tp.os,"fsync",sync):tp.append(db,fd,"a",raw,orig)
            else:
                with patch.object(tp.os,"pwrite",inject):tp.append(db,fd,"a",raw,orig)
        except OSError:caught=True
        assert caught==(mode!="short_writes")
        n=2 if mode in ("short_writes","commit_after") else 1
        db.execute("BEGIN");assert tp.audit(db,fd)==n
        if n==2:assert tp.recover(db,fd,"a",1)[0]==raw
        orphan=os.fstat(fd).st_size-tp.state(db,fd);db.rollback()
        end=tp.reconcile(db,fd);assert end==os.fstat(fd).st_size
        retry=b"retry evidence "*100;tp.append(db,fd,"a",retry,tp.fixture(retry,"retry"))
        db.execute("BEGIN");assert tp.audit(db,fd)==n+1;db.rollback()
        db.close();os.close(fd);results.append(dict(mode=mode,visible=n,orphan_bytes=orphan,retry=True))
    return results

def corruption(folder,ext):
    results=[]
    for mode in ("frame_flip","pointer_out_of_range","pointer_wrong_frame","source_digest","origin_metadata"):
        path=folder/(mode+".sqlite");db=tp.setup(path,ext,{});fd=os.open(tp.side(path),os.O_RDWR)
        for j,raw in enumerate((b"alpha evidence "*100,b"beta evidence "*100)):
            tp.append(db,fd,"a",raw,tp.fixture(raw,str(j)),"snapshot")
        db.execute("BEGIN");old=tp.issue(db,fd,("beta",),"AND",2);db.rollback()
        ptr=db.execute("SELECT payload FROM versions WHERE article='a' AND ord=1").fetchone()[0]
        off,n=tp.PTR.unpack(ptr)
        if mode=="frame_flip":
            x=os.pread(fd,1,off);os.pwrite(fd,bytes([x[0]^255]),off)
        elif mode=="pointer_out_of_range":
            db.execute("UPDATE versions SET payload=? WHERE article='a' AND ord=1",(tp.PTR.pack(off+n,n),))
        elif mode=="pointer_wrong_frame":
            db.execute("UPDATE versions SET payload=(SELECT payload FROM versions WHERE article='a' AND ord=0) WHERE article='a' AND ord=1")
        elif mode=="source_digest":
            db.execute("UPDATE versions SET digest=? WHERE article='a' AND ord=1",(b"x"*32,))
        else:
            db.execute("UPDATE origin SET commit_sha1=?,committer_unix=? WHERE g=2",("f"*40,999))
        db.commit();db.execute("BEGIN")
        rejected=False;unchanged=False
        try:
            got=tp.issue(db,fd,("beta",),"AND",2)
            unchanged=got==old
            rejected=got!=old
        except (ValueError,zstandard.ZstdError,sqlite3.DatabaseError):rejected=True
        # Known negative control: v1 receipt excludes origin. Do not claim
        # tamper-evident origin provenance for v1.
        assert rejected==(mode!="origin_metadata")
        if mode=="origin_metadata":assert unchanged
        db.rollback();db.close();os.close(fd)
        results.append(dict(mode=mode,rejected=rejected,unchanged_receipt=unchanged))
    return results

def run(ext,seed,workers,count):
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);con=[]
        for j,stage in enumerate(("partial_write","synced","meta","commit")):
            folder=root/("con-"+stage);folder.mkdir()
            con.append(concurrency(folder,ext,seed+j,workers,count,stage))
        f=root/"failures";f.mkdir();c=root/"corruption";c.mkdir()
        return dict(round=143,seed=seed,workers=workers,operations_per_writer=count,concurrency=con,
            failures=failures(f,ext),corruption=corruption(c,ext),
            limitations=["cooperating processes on Linux local storage, no hardware power-loss test",
                "Python-layer I/O error injection and simulated commit exceptions, not SQLite VFS faults",
                "synthetic stress workload, scheduler-dependent ordering",
                "v1 receipt does not bind origin metadata; known negative control"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--extension",type=Path,required=True);p.add_argument("--seed",type=int,required=True);p.add_argument("--workers",type=int,default=4);p.add_argument("--count",type=int,default=32);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.extension.resolve(),a.seed,a.workers,a.count);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
