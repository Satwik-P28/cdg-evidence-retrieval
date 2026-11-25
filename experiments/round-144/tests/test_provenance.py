import os,subprocess,sys,sqlite3
from pathlib import Path
import pytest
import provenance_v2 as p
from provenance_v2 import tp,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def create(tmp_path):
    path=tmp_path/"a.sqlite";db=p.setup(path,EXT,{"cohort":"frozen"})
    fd=os.open(tp.side(path),os.O_RDWR)
    for j,raw in enumerate((b"alpha evidence "*100,b"beta evidence "*100)):
        tp.append(db,fd,"a",raw,tp.fixture(raw,str(j)))
    db.execute("BEGIN");body,digest=p.issue(db,fd,("beta",),"AND",2);db.rollback()
    return path,db,fd,body,digest

@pytest.mark.parametrize("mode",["origin_commit","origin_time","origin_blob","manifest","stored_root","nonhit_origin","forged_chain","missing_ledger","body_mutation"])
def test_trusted_commitment(tmp_path,mode):
    path,db,fd,body,digest=create(tmp_path)
    if mode=="origin_commit":db.execute("UPDATE origin SET commit_sha1=? WHERE g=2",("f"*40,))
    elif mode=="origin_time":db.execute("UPDATE origin SET committer_unix=42 WHERE g=2")
    elif mode=="origin_blob":db.execute("UPDATE origin SET blob_sha1=? WHERE g=2",("f"*40,))
    elif mode=="manifest":db.execute("UPDATE corpus SET v=? WHERE k='manifest'",(b'{}',))
    elif mode=="stored_root":db.execute("UPDATE origin_ledger SET prefix_sha=? WHERE g=2",(b"x"*32,))
    elif mode=="nonhit_origin":db.execute("UPDATE origin SET committer_unix=42 WHERE g=1")
    elif mode=="missing_ledger":db.execute("DELETE FROM origin_ledger WHERE g=1")
    elif mode=="forged_chain":
        db.execute("UPDATE origin SET committer_unix=42 WHERE g=1")
        raw=db.execute("SELECT v FROM corpus WHERE k='manifest'").fetchone()[0]
        prev=p.manifest_seed(raw)
        for row in db.execute("SELECT r.generation,r.article,r.ord,v.digest,o.commit_sha1,o.committer_unix,o.blob_sha1,l.prefix_sha FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord JOIN origin o ON o.g=r.generation JOIN rank_ledger l ON l.g=r.generation ORDER BY r.generation").fetchall():
            prev=p.entry(prev,*row);db.execute("UPDATE origin_ledger SET prefix_sha=? WHERE g=?",(prev,row[0]))
    else:body["hit_origins"][0]["committer_unix"]=42
    db.commit();db.execute("BEGIN")
    with pytest.raises(ValueError):p.replay(db,fd,body,digest)
    db.rollback();db.close();os.close(fd)

@pytest.mark.parametrize("stage",tp.STAGES)
def test_crash(tmp_path,stage):
    path,db,fd,body,digest=create(tmp_path)
    reader=p.connect(path,EXT);reader.execute("BEGIN")
    assert p.replay(reader,fd,body,digest)==body
    db.close()
    proc=subprocess.run([sys.executable,str(Path(p.__file__).resolve()),"--crash",str(path),str(EXT),stage],capture_output=True,timeout=60)
    assert proc.returncode==77,proc.stderr
    db=p.connect(path,EXT);tp.reconcile(db,fd);db.execute("BEGIN")
    n=3 if stage=="commit" else 2
    assert p.audit(db,fd)==n
    assert p.replay(db,fd,body,digest)==body
    db.rollback()
    raw=b"retry evidence "*100;tp.append(db,fd,"a",raw,tp.fixture(raw,"retry"))
    assert p.replay(reader,fd,body,digest)==body
    reader.rollback();reader.close()
    db.execute("BEGIN");assert p.audit(db,fd)==n+1;assert p.replay(db,fd,body,digest)==body
    db.rollback();db.close();os.close(fd)


def test_udf_contract(tmp_path):
    import inspect
    db=sqlite3.connect(":memory:");p.register(db)
    values=(b"x"*32,1,"article",0,b"y"*32,"a"*40,0,"b"*40,b"z"*32)
    assert len(values)==len(inspect.signature(p.entry).parameters)
    assert db.execute("SELECT cdg_origin_entry(?,?,?,?,?,?,?,?,?)",values).fetchone()[0]==p.entry(*values)
    db.close()
