import os,sys,subprocess
from pathlib import Path
import pytest
import dedup_pack as d
from dedup_pack import h,tp
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def init(tmp_path):
    path=tmp_path/"a.sqlite";db=d.setup(path,EXT,{})
    fd=os.open(tp.side(path),os.O_RDWR);raw=b"old evidence "*100
    d.append(db,fd,"a",raw,tp.fixture(raw,"first"),"snapshot")
    return path,db,fd,raw
@pytest.mark.parametrize("mode,stage",[(m,s) for m,stages in [("new",tp.STAGES),("reuse",("reuse","source","index","ledger","meta","commit"))] for s in stages])
def test_crash(tmp_path,mode,stage):
    path,db,fd,raw=init(tmp_path)
    reader=h.connect(path,EXT);reader.execute("BEGIN");old=tp.issue(reader,fd,("old",),"AND",1)
    before=tp.state(reader,fd);db.close()
    p=subprocess.run([sys.executable,str(Path(d.__file__).resolve()),"--crash",str(path),str(EXT),stage,mode],capture_output=True,timeout=60)
    assert p.returncode==77,p.stderr
    db=h.connect(path,EXT);tp.reconcile(db,fd);db.execute("BEGIN")
    n=2 if stage=="commit" else 1
    assert d.audit(db,fd)==n
    assert tp.issue(db,fd,("old",),"AND",1)==old
    if mode=="reuse" or n==1:assert tp.state(db,fd)==before
    db.rollback()
    d.append(db,fd,"c",raw,tp.fixture(raw,"retry"),"snapshot")
    assert tp.issue(reader,fd,("old",),"AND",1)==old
    reader.rollback();reader.close()
    db.execute("BEGIN");assert d.audit(db,fd)==n+1;assert tp.recover(db,fd,"c",0)[0]==raw
    db.rollback();db.close();os.close(fd)
def test_catalog_corruption(tmp_path):
    path,db,fd,raw=init(tmp_path)
    db.execute("UPDATE frame_catalog SET digest=?", (b"x"*32,));db.commit();db.execute("BEGIN")
    with pytest.raises(ValueError,match="catalog digest"):d.audit(db,fd)
    db.rollback();db.close();os.close(fd)
def test_duplicate(tmp_path):
    path,db,fd,raw=init(tmp_path);size=os.fstat(fd).st_size
    d.append(db,fd,"b",raw,tp.fixture(raw,"second"),"snapshot")
    assert os.fstat(fd).st_size==size
    db.execute("BEGIN");assert d.audit(db,fd)==2
    assert db.execute("SELECT count(*) FROM frame_catalog").fetchone()[0]==1
    db.rollback();db.close();os.close(fd)
