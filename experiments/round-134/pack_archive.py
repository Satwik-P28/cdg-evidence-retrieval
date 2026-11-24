"""R134: actual Git packfiles + feature-matched frozen historical search archive.

Static/finalized baseline, deliberately allowed noncausal cross-document delta
selection. No claim of equivalent incremental update or crash semantics.
"""
import argparse,collections,contextlib,hashlib,json,os,random,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-132"))
import heldout_archive as h
import versioned_evidence as ve
DEPTHS=(1,8,50)

def command(repo,*args,data=None):
    return subprocess.run(["git","-C",str(repo),*args],input=data,capture_output=True,check=True).stdout

def init(repo):
    repo.mkdir()
    command(repo,"init","--bare","--object-format=sha1","-q")

def oid(raw):
    return hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()

def prepare_objects(folder,events):
    source=folder/"loose";init(source)
    unique={}
    for a,i,raw in events:
        key=oid(raw)
        if key not in unique:
            got=command(source,"hash-object","-w","--stdin",data=raw).decode().strip()
            assert got==key
            unique[key]=(a,len(raw))
    return source,unique

def make_pack(folder,source,unique,depth):
    repo=folder/("pack-"+str(depth));init(repo)
    # Name hints improve conventional Git's opportunity to find similar blobs.
    request="".join(k+" "+a+"\n" for k,(a,n) in sorted(unique.items())).encode()
    ident=command(source,"pack-objects","--window=10","--depth="+str(depth),"--compression=9",
        "--threads=1","--delta-base-offset","--no-reuse-delta","--no-reuse-object",
        str(repo/"objects/pack/pack"),data=request).decode().strip()
    idx=repo/"objects/pack"/("pack-"+ident+".idx")
    pack=idx.with_suffix(".pack")
    rows={}
    for line in command(repo,"verify-pack","-v",str(idx)).decode().splitlines():
        f=line.split()
        if len(f) in (5,7) and f[0] in unique:
            assert f[1]=="blob"
            rows[f[0]]=(int(f[3]),int(f[5]) if len(f)==7 else 0,f[6] if len(f)==7 else None)
    assert set(rows)==set(unique)
    for k,(size,d,parent) in rows.items():
        assert 0<=d<=depth
        if parent is not None:assert rows[parent][1]==d-1
        else:assert d==0
    assert sum(v[0] for v in rows.values())+32==pack.stat().st_size
    return repo,rows,dict(pack_bytes=pack.stat().st_size,index_bytes=idx.stat().st_size,
        pack_aux_bytes=sum(p.stat().st_size for p in idx.parent.iterdir() if p not in (idx,pack)),
        unique_objects=len(rows),max_depth=max(d for _,d,_ in rows.values()))

def path_cost(key,rows,unique):
    activated=decoded=0;seen=set()
    while key is not None:
        assert key not in seen;seen.add(key)
        size,depth,parent=rows[key]
        activated+=size;decoded+=unique[key][1];key=parent
    return activated,decoded

class Reader:
    def __init__(self,repo,rows,unique):
        self.rows=rows;self.unique=unique
        self.p=subprocess.Popen(["git","-C",str(repo),"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def close(self):
        self.p.stdin.close();self.p.stdout.close()
        if self.p.wait(timeout=10):raise RuntimeError("cat-file failure")
    def recover(self,db,a,i,expected=None):
        row=db.execute("SELECT v.n,v.digest,v.payload,o.blob_sha1 FROM versions v JOIN revisions r ON r.article=v.article AND r.ord=v.ord JOIN origin o ON o.g=r.generation WHERE v.article=? AND v.ord=?",(a,i)).fetchone()
        if row is None:raise ValueError("missing packed source")
        n,digest,payload,key=row
        if payload!=bytes.fromhex(key):raise ValueError("pack pointer mismatch")
        self.p.stdin.write(key.encode()+b"\n");self.p.stdin.flush()
        header=self.p.stdout.readline().split()
        if header!=[key.encode(),b"blob",str(n).encode()]:raise ValueError("bad git batch header")
        raw=self.p.stdout.read(n)
        if self.p.stdout.read(1)!=b"\n" or len(raw)!=n or oid(raw)!=key or h.sha(raw)!=digest:raise ValueError("packed source digest")
        ab,db=path_cost(key,self.rows,self.unique)
        return raw,ab,db,self.rows[key][1]

def verify_archive(db,events,manifest,qs,refs,bodies):
    db.execute("BEGIN")
    assert h.audit(db)==len(events);h.assert_origin(db,manifest)
    timings=[];encoded=decoded=0;max_a=max_d=0.;rank_checks=0
    for a,i,want in events:
        g=db.execute("SELECT generation FROM revisions WHERE article=? AND ord=?",(a,i)).fetchone()[0]
        rec=h.Receipt(len(events),g,a,i,h.sha(want).hex());full=len(h.C.compress(want))
        start=time.perf_counter_ns();raw,ab,dd=ve.read_receipt(db,rec)
        timings.append((time.perf_counter_ns()-start)/1000)
        assert raw==want
        encoded+=ab;decoded+=dd;max_a=max(max_a,ab/full)
        if want:max_d=max(max_d,dd/len(want))
    error=0.
    for c,ref in refs.items():
        for ps,op in qs:
            body,digest=h.issue(db,ps,op,c)
            error=max(error,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],h.native(ref,ps,op)))
            key=c,ps,op
            if key in bodies:assert bodies[key]==(body,digest)
            else:bodies[key]=(body,digest)
            h.replay(db,body,digest);rank_checks+=1
    db.rollback()
    return dict(source_reads=len(events),rank_checks=rank_checks,max_score_error=error,
        decode_amplification=decoded/max(1,sum(len(v) for _,_,v in events)),
        activated_bytes=encoded,max_activation_relative_to_snapshot_frame=max_a,
        max_decode_relative_to_nonempty_request=max_d,source_read=h.quant(timings))

def experiment(folder,events,manifest,ext):
    cuts=manifest["cutoffs"];refs={c:h.active_oracle(events,c) for c in cuts}
    qs=h.plan_queries(refs[cuts[0]]);assert qs
    bodies={};results={}
    for policy in ("snapshot","bounded_anchor"):
        path=folder/(policy+".sqlite");db=h.integrated_setup(path,ext,manifest)
        for g,(a,i,raw) in enumerate(events,1):
            assert h.append_policy(db,a,raw,h.origin_tuple(manifest["origins"][g-1]),policy)==(g,i)
        size=h.compact(db,path);db.close()
        db=h.connect(path,ext)
        results[policy]=dict(**size,**verify_archive(db,events,manifest,qs,refs,bodies),total_archive_bytes=path.stat().st_size)
        db.close()
    # Clone the snapshot index/provenance; replace source payload with packed object identity.
    # Charge the pointer even though origin metadata already stores the Git blob SHA.
    import shutil
    pointer=folder/"packed-index.sqlite";shutil.copyfile(folder/"snapshot.sqlite",pointer)
    db=h.connect(pointer,ext)
    with db:
        db.executemany("UPDATE versions SET payload=? WHERE article=? AND ord=?",
            ((bytes.fromhex(oid(raw)),a,i) for a,i,raw in events))
        db.execute("INSERT INTO corpus VALUES('source_codec',?)",(b'git-pack-sha1-pointer-v1',))
    db.execute("VACUUM");assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok";db.close()
    source,unique=prepare_objects(folder,events)
    for depth in DEPTHS:
        repo,rows,stats=make_pack(folder,source,unique,depth)
        db=h.connect(pointer,ext);reader=Reader(repo,rows,unique)
        try:
            with patch.object(ve,"recover",reader.recover):
                measured=verify_archive(db,events,manifest,qs,refs,bodies)
        finally:
            db.close();reader.close()
        total=pointer.stat().st_size+sum(stats[k] for k in ("pack_bytes","index_bytes","pack_aux_bytes"))
        results["git_pack_depth"+str(depth)]=dict(**stats,**measured,sqlite_bytes=pointer.stat().st_size,total_archive_bytes=total)
    for ref in refs.values():ref.close()
    return dict(policies=results,query_plan_sha256=h.sha(h.canonical([dict(phrases=p,op=o) for p,o in qs])).hex(),
        git_version=command(source,"--version").decode().strip(),revisions=len(events),documents=len(manifest["retained_paths"]))

def run(root,corpus,ext):
    if corpus in ("gitdocs","k8sdocs"):
        events,manifest=h.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    else:
        sys.path.insert(0,str(HERE.parent/"round-131"))
        import budget_archive as old
        events,manifest=old.collect(root,corpus)
        frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    original=json.loads(frozen.read_text());assert h.sha(h.canonical(manifest)).hex()==original["manifest_sha256"]
    with tempfile.TemporaryDirectory() as tmp:
        result=experiment(Path(tmp),events,manifest,ext)
    for p in ("snapshot","bounded_anchor"):
        assert result["policies"][p]["total_archive_bytes"]==original["result"]["policies"][p]["sqlite_bytes"]
    expected=h.sha(h.canonical(original["result"]["query_plan"])).hex()
    assert result["query_plan_sha256"]==expected
    return dict(round=134,corpus=corpus,manifest_sha256=original["manifest_sha256"],result=result,
        limitations=["finalized read-only Git pack, not append/crash parity",
          "offline cross-document and future-object delta selection allowed",
          "pack and idx and sidecars counted; generic empty Git repository scaffolding excluded",
          "entry-byte activation includes pack entry headers; decoded work sums reconstructed blob lengths; excludes delta instruction buffers, caching, page I/O and CPU",
          "source timings descriptive; Git persistent subprocess IPC versus in-process SQLite",
          "same retrieval scorer and receipt bodies; not complete TimIR or WikECD comparison"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus,a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
