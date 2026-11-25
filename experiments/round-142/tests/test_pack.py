import os
from pathlib import Path
import news_native_pack as n
from transactional_pack import setup,append,fixture,side,recover
import heldout_archive as h

def test_batch_objects(tmp_path):
    ev=[("a",0,b"one"),("a",1,b"two"),("b",0,b"one")]
    repo,unique=n.prepare_batched(tmp_path,ev)
    assert len(unique)==2
    pack,rows,stats=n.gp.make_pack(tmp_path,repo,unique,1)
    assert stats["unique_objects"]==2

def test_coalescing(tmp_path):
    ext=Path(os.environ["CDG_FTS_EXTENSION"]);path=tmp_path/"a.sqlite";db=setup(path,ext,{})
    fd=os.open(side(path),os.O_RDWR);raw=b"same content "*100
    append(db,fd,"a",raw,fixture(raw,"a"),"snapshot")
    append(db,fd,"b",raw,fixture(raw,"b"),"snapshot")
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.close();os.close(fd)
    dest=tmp_path/"b.sqlite";x=n.coalesce(path,dest,ext)
    assert x["duplicate_frames"]==1 and x["unique_frames"]==1
    db=h.connect(dest,ext);fd=os.open(side(dest),os.O_RDONLY);db.execute("BEGIN")
    assert recover(db,fd,"a",0)[0]==recover(db,fd,"b",0)[0]==raw
    db.rollback();db.close();os.close(fd)
