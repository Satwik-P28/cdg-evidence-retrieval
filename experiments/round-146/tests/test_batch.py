import os
from pathlib import Path
import pytest
import batch_verify as b
from batch_verify import pv,tp,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def fixture(tmp_path):
    path=tmp_path/"a.sqlite";db=pv.setup(path,EXT,{"fixture":True})
    fd=os.open(tp.side(path),os.O_RDWR);req=[]
    for j,raw in enumerate((b"alpha evidence "*100,b"beta evidence "*100,b"gamma evidence "*100)):
        tp.append(db,fd,"a",raw,tp.fixture(raw,str(j)))
        db.execute("BEGIN");req.append(pv.issue(db,fd,("evidence",),"AND",j+1));db.rollback()
    db.close();os.close(fd);return path,req
def test_mixed_and_duplicate(tmp_path):
    path,req=fixture(tmp_path);mixed=[req[2],req[0],req[2],req[1]]
    got,rows=b.verify_batch(path,EXT,mixed)
    assert got==[x[0] for x in mixed] and rows==3
    assert b.verify_individual(path,EXT,mixed)[0]==got
@pytest.mark.parametrize("mode",["origin","manifest","root","forged_digest","missing_ledger"])
def test_reject(tmp_path,mode):
    path,req=fixture(tmp_path)
    db=pv.connect(path,EXT)
    if mode=="origin":db.execute("UPDATE origin SET committer_unix=42 WHERE g=2")
    elif mode=="manifest":db.execute("UPDATE corpus SET v=? WHERE k='manifest'",(b'{}',))
    elif mode=="root":db.execute("UPDATE origin_ledger SET prefix_sha=? WHERE g=2",(b"x"*32,))
    elif mode=="missing_ledger":db.execute("DELETE FROM origin_ledger WHERE g=2")
    else:req[2]=(req[2][0],"f"*64)
    db.commit();db.close()
    with pytest.raises(ValueError):b.verify_batch(path,EXT,req)
def test_no_cross_transaction_cache(tmp_path):
    path,req=fixture(tmp_path);assert b.verify_batch(path,EXT,req)[1]==3
    db=pv.connect(path,EXT);db.execute("UPDATE origin SET committer_unix=42 WHERE g=3");db.commit();db.close()
    assert b.verify_batch(path,EXT,req[:2])[1]==2
    with pytest.raises(ValueError):b.verify_batch(path,EXT,req)
