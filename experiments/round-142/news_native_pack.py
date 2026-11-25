"""R142: large-scale native Git pack vs transactional and coalesced CDG.

Same finalized historical index, provenance and receipt contract. Offline Git
pack and coalesced frames do not claim transactional ingestion equivalence.
"""
import argparse,collections,hashlib,json,os,random,shutil,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
sys.path.insert(0,str(HERE.parent/"round-134"))
import news_retrieval as nr
import transactional_pack as tp
import heldout_archive as h
import pack_archive as gp

def prepare_batched(folder,events):
    repo=folder/"loose";gp.init(repo)
    unique={};pending=[];scratch=folder/"hash-input";scratch.mkdir()
    def flush():
        if not pending:return
        request="".join(str(path.resolve())+"\n" for _,path in pending).encode()
        got=gp.command(repo,"hash-object","-w","--no-filters","--stdin-paths",data=request).decode().splitlines()
        assert got==[key for key,_ in pending]
        for _,path in pending:path.unlink()
        pending.clear()
    for a,i,raw in events:
        key=gp.oid(raw)
        if key not in unique:
            unique[key]=(a,len(raw))
            path=scratch/key;path.write_bytes(raw);pending.append((key,path))
            if len(pending)>=1000:flush()
    flush();scratch.rmdir()
    return repo,unique

def compact(db,path):
    db.commit();db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    return path.stat().st_size

def verify(db,fd,events,queries,refs,bodies,reader=None):
    db.execute("BEGIN");assert h.audit(db)==len(events)
    rawbytes=decoded=activated=0;maxa=maxd=0.;times=[]
    order=list(range(len(events)));random.Random(142).shuffle(order)
    for j in order:
        a,i,want=events[j];full=len(h.C.compress(want))
        st=time.perf_counter_ns()
        got,ab,dd,d=(reader.recover(db,a,i) if reader else tp.recover(db,fd,a,i))
        times.append((time.perf_counter_ns()-st)/1000)
        assert got==want
        rawbytes+=len(want);decoded+=dd;activated+=ab;maxa=max(maxa,ab/full)
        if want:maxd=max(maxd,dd/len(want))
    err=0.;checks=0;receipt_times=[]
    def git_recover(db,fd,a,i,expected=None):
        return reader.recover(db,a,i,expected)
    # Patch only the local serial verification call, never a live concurrent service.
    import contextlib
    with patch.object(tp,"recover",git_recover) if reader else contextlib.nullcontext():
        for c,ref in refs.items():
            for p,o in queries:
                st=time.perf_counter_ns();body,d=tp.issue(db,fd,p,o,c)
                receipt_times.append((time.perf_counter_ns()-st)/1000)
                err=max(err,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,p,o)))
                key=c,p,o
                if key in bodies:assert bodies[key]==(body,d)
                else:bodies[key]=(body,d)
                checks+=1
    db.rollback()
    return dict(source_reads=len(events),rank_checks=checks,max_score_error=err,
        mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
        activated_bytes=activated,source_read=h.quant(times),receipt=h.quant(receipt_times))

def build(folder,events,origins,manifest,ext,policy):
    path=folder/(policy+".sqlite");db=tp.setup(path,ext,manifest)
    db.execute("PRAGMA wal_autocheckpoint=1000")
    fd=os.open(tp.side(path),os.O_RDWR)
    for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
        assert tp.append(db,fd,a,raw,origin,policy)==(g,i)
    db.execute("BEGIN");assert tp.audit(db,fd)==len(events)
    end=tp.state(db,fd);db.rollback();assert end==os.fstat(fd).st_size
    size=compact(db,path);db.close();os.close(fd)
    return path,dict(sqlite_bytes=size,sidecar_bytes=end,payload_bytes=end-tp.HEADER,total_archive_bytes=size+end)

def coalesce(path,dest,ext):
    shutil.copyfile(path,dest);db=h.connect(dest,ext)
    old=os.open(tp.side(path),os.O_RDONLY)
    new=os.open(tp.side(dest),os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
    try:
        header=os.pread(old,tp.HEADER,0);assert len(header)==tp.HEADER
        tp.write_all(new,header,0);pos=tp.HEADER
        seen={};duplicates=0
        with db:
            rows=db.execute("SELECT article,ord,payload FROM versions ORDER BY article,ord").fetchall()
            for a,i,ptr in rows:
                off,n=tp.PTR.unpack(ptr);frame=os.pread(old,n,off);assert len(frame)==n
                key=h.sha(frame)
                if key in seen:
                    new_off,new_n=seen[key]
                    assert new_n==n and os.pread(new,n,new_off)==frame
                    duplicates+=1
                else:
                    new_off=pos;tp.write_all(new,frame,pos);pos+=n
                    seen[key]=(new_off,n)
                db.execute("UPDATE versions SET payload=? WHERE article=? AND ord=?",(tp.PTR.pack(new_off,n),a,i))
            os.fsync(new);db.execute("UPDATE pack_state SET end_offset=? WHERE singleton=1",(pos,))
            db.execute("INSERT INTO corpus VALUES('source_codec',?)",(b'coalesced-read-only-frames-v1',))
        size=compact(db,dest)
        assert os.fstat(new).st_size==pos
    finally:db.close();os.close(old);os.close(new)
    return dict(sqlite_bytes=size,sidecar_bytes=pos,payload_bytes=pos-tp.HEADER,
        total_archive_bytes=size+pos,unique_frames=len(seen),duplicate_frames=duplicates)

def run(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events);initial=len(m["retained_paths"])
    frozen=json.loads((HERE.parent/"round-138"/("results-"+str(n)+".json")).read_text())["result"]
    assert m["source_manifest_sha256"]==frozen["manifest"]
    cuts=frozen["cuts"];refs={c:h.active_oracle(events,c) for c in cuts};queries=nr.plan(refs[cuts[0]])
    assert h.sha(h.canonical([dict(phrases=p,op=o) for p,o in queries])).hex()==frozen["query_plan_sha256"]
    bodies={};results={};paths={}
    for policy in ("snapshot","bounded_anchor"):
        path,size=build(folder,events,origins,m,ext,policy);paths[policy]=path
        assert size["payload_bytes"]==frozen["policies"][policy]["payload_bytes"]
        assert size["total_archive_bytes"]==frozen["policies"][policy]["total_archive_bytes"]
        db=h.connect(path,ext);fd=os.open(tp.side(path),os.O_RDONLY)
        results[policy]=dict(**size,**verify(db,fd,events,queries,refs,bodies))
        db.close();os.close(fd)
    for policy in ("snapshot","bounded_anchor"):
        dest=folder/(policy+"-coalesced.sqlite");size=coalesce(paths[policy],dest,ext)
        db=h.connect(dest,ext);fd=os.open(tp.side(dest),os.O_RDONLY)
        measured=verify(db,fd,events,queries,refs,bodies)
        assert all(measured[k]==results[policy][k] for k in ("mean_decode_ratio","max_decode_ratio","max_activation_ratio","activated_bytes"))
        results[policy+"_coalesced"]=dict(**size,**measured)
        db.close();os.close(fd)
    # Identical rank/provenance metadata, charge per-revision SHA1 pointer plus
    # pack + idx. Remove CDG-specific pack-state header metadata.
    dest=folder/"git-index.sqlite";shutil.copyfile(paths["snapshot"],dest)
    db=h.connect(dest,ext)
    with db:
        db.executemany("UPDATE versions SET payload=? WHERE article=? AND ord=?",
            ((bytes.fromhex(gp.oid(raw)),a,i) for a,i,raw in events))
        db.execute("DROP TABLE pack_state")
        db.execute("INSERT INTO corpus VALUES('source_codec',?)",(b'git-pack-sha1-pointer-v1',))
    sqlite_bytes=compact(db,dest);db.close()
    repo,unique=prepare_batched(folder,events)
    for depth in gp.DEPTHS:
        pack,rows,stats=gp.make_pack(folder,repo,unique,depth)
        reader=gp.Reader(pack,rows,unique);db=h.connect(dest,ext)
        try:measured=verify(db,None,events,queries,refs,bodies,reader)
        finally:reader.close();db.close()
        results["git_pack_depth"+str(depth)]=dict(**stats,**measured,sqlite_bytes=sqlite_bytes,
            total_archive_bytes=sqlite_bytes+sum(stats[k] for k in ("pack_bytes","index_bytes","pack_aux_bytes")))
    for ref in refs.values():ref.close()
    return dict(round=142,revisions=n,documents=initial,manifest_sha256=m["source_manifest_sha256"],
        source_sha256=nr.SOURCE_SHA,query_plan_sha256=frozen["query_plan_sha256"],
        git_version=gp.command(repo,"--version").decode().strip(),unique_source_objects=len(unique),
        exact_duplicate_revisions=n-len(unique),policies=results,
        limitations=["finalized comparison: Git and coalesced layouts are read-only, not transactional append parity",
            "Git offline cross-document/future-object deltas and exact source dedup allowed",
            "coalesced CDG exact encoded-frame dedup only; per-revision parent metadata retained",
            "derived news text and synthetic ordinal schedule as R138",
            "logical decoded source sizes, not actual CPU/cache/I/O; Git entry activation includes headers",
            "same query and source manifest; no semantic retrieval or answer quality claim"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=run(a.source,a.target,Path(d),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
