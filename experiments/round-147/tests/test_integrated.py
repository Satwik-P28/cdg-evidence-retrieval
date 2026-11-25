import os,sys,subprocess
from pathlib import Path
import pytest
import integrated_pack as x
from integrated_pack import pv,tp,d,bv
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def init(tmp_path):
    path=tmp_path/"a.sqlite";db=x.setup(path,EXT,{"fixture":True})
    fd=os.open(tp.side(path),os.O_RDWR);raw=b"old evidence "*100
    d.append(db,fd,"a",raw,tp.fixture(raw,"first"),"snapshot")
    db.execute("BEGIN");old=pv.issue(db,fd,("old",),"AND",1);db.rollback()
    return path,db,fd,raw,old

@pytest.mark.parametrize("mode,stage",[(m,s) for m,stages in [("new",tp.STAGES),("reuse",("reuse","source","index","ledger","meta","commit"))] for s in stages])
def test_combined_crash(tmp_path,mode,stage):
    path,db,fd,raw,old=init(tmp_path)
    reader=pv.connect(path,EXT);reader.execute("BEGIN");assert pv.replay(reader,fd,*old)==old[0]
    before=tp.state(reader,fd);db.close()
    p=subprocess.run([sys.executable,str(Path(x.__file__).resolve()),"--crash",str(path),str(EXT),stage,mode],capture_output=True,timeout=60)
    assert p.returncode==77,p.stderr
    db=pv.connect(path,EXT);tp.reconcile(db,fd);db.execute("BEGIN")
    n=2 if stage=="commit" else 1
    assert x.audit(db,fd)==n;assert pv.replay(db,fd,*old)==old[0]
    if mode=="reuse" or n==1:assert tp.state(db,fd)==before
    db.rollback();d.append(db,fd,"c",raw,tp.fixture(raw,"retry"),"snapshot")
    assert pv.replay(reader,fd,*old)==old[0]
    reader.rollback();reader.close()
    db.execute("BEGIN");assert x.audit(db,fd)==n+1
    new=pv.issue(db,fd,("old",),"AND",n+1);db.rollback()
    db.close();os.close(fd)
    assert bv.verify_batch(path,EXT,[old,new])[0]==[old[0],new[0]]

def test_reused_frame_distinct_provenance(tmp_path):
    path,db,fd,raw,old=init(tmp_path);size=os.fstat(fd).st_size
    d.append(db,fd,"b",raw,tp.fixture(raw,"second"),"snapshot")
    assert os.fstat(fd).st_size==size
    db.execute("BEGIN");assert x.audit(db,fd)==2
    assert db.execute("SELECT count(*) FROM frame_catalog").fetchone()[0]==1
    new=pv.issue(db,fd,("old",),"AND",2)
    assert len(new[0]["hit_origins"])==2
    assert len({o["commit_sha1"] for o in new[0]["hit_origins"]})==2
    db.rollback();db.execute("UPDATE origin SET committer_unix=42 WHERE g=2");db.commit()
    db.close();os.close(fd)
    assert bv.verify_batch(path,EXT,[old])[0]==[old[0]]
    with pytest.raises(ValueError):bv.verify_batch(path,EXT,[old,new])
