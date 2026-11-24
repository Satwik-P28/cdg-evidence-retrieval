import os
from pathlib import Path
import pytest
import transactional_pack as p

def test_crash(tmp_path):
    assert len(p.crash_suite(tmp_path,Path(os.environ["CDG_FTS_EXTENSION"])))==len(p.STAGES)

def test_orphan_and_corruption(tmp_path):
    ext=Path(os.environ["CDG_FTS_EXTENSION"]);path=tmp_path/"a.sqlite";db=p.setup(path,ext,{})
    fd=os.open(p.side(path),os.O_RDWR);raw=b"test "*200
    p.append(db,fd,"a",raw,p.fixture(raw,"a"))
    db.execute("BEGIN");end=p.state(db,fd);db.rollback()
    os.pwrite(fd,b"orphan",end);assert p.reconcile(db,fd)==end
    db.execute("BEGIN");assert p.audit(db,fd)==1;db.rollback()
    os.ftruncate(fd,end-1)
    db.execute("BEGIN")
    with pytest.raises(ValueError,match="truncated"):p.audit(db,fd)
    db.rollback();db.close();os.close(fd)

def test_identity(tmp_path):
    ext=Path(os.environ["CDG_FTS_EXTENSION"]);path=tmp_path/"b.sqlite";db=p.setup(path,ext,{})
    fd=os.open(p.side(path),os.O_RDWR);os.pwrite(fd,b"x"*p.HEADER,0)
    db.execute("BEGIN")
    with pytest.raises(ValueError,match="identity"):p.audit(db,fd)
    db.rollback();db.close();os.close(fd)
