import os
import pytest
from active_rank import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()

def test_active_differential(tmp_path):
    events=[("a",0,b"one one two"),("b",0,b"one two three"),("a",1,b"one two one"),("b",1,b"two three"),("a",2,b"three three three")]
    path=tmp_path/"x.sqlite";db=setup(path,EXT)
    for a,i,raw in events:append_atomic(db,a,raw)
    assert audit(db)==5
    lens,_=load_ledger(db,5)
    for c in range(1,6):
        ref=active_oracle(events,c)
        for p,op in [(("one",),"AND"),(("one two",),"AND"),(("one","three"),"OR"),(("one","two"),"AND")]:
            for m in ("scan","prepared","interval"):
                got=rank(db,p,op,c,lens,m,prepare(db,c,lens))[0]
                verify(got,native(ref,p,op))
        ref.close()
    db.close()

def test_active_empty_documents(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT)
    append_atomic(db,"a",b"");append_atomic(db,"b",b"one");append_atomic(db,"b",b"")
    assert audit(db)==3
    lens,_=load_ledger(db,3)
    assert rank(db,("one",),"AND",3,lens,"interval")==([],2,0,[0])
    db.close()

def test_interval_corruption(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT)
    append_atomic(db,"a",b"one");append_atomic(db,"a",b"two")
    db.execute("UPDATE validity SET end_g=NULL WHERE start_g=1")
    with pytest.raises(ValueError,match="validity"):audit(db)
    db.close()

def test_stats_corruption(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT);append_atomic(db,"a",b"one")
    db.execute("UPDATE active_stats SET tokens=99")
    with pytest.raises(ValueError,match="statistic"):audit(db)
    db.close()

def test_receipt_snapshot(tmp_path):
    path=tmp_path/"x.sqlite";db=setup(path,EXT);append_atomic(db,"a",b"one two")
    r=connect(path,EXT);r.execute("BEGIN")
    body,h=issue(r,("one",),"AND",1)
    append_atomic(db,"a",b"two three")
    replay(r,body,h);r.rollback();r.execute("BEGIN");replay(r,body,h)
    assert not issue(r,("one",),"AND",2)[0]["hits"]
    r.close();db.close()

def test_process_death(tmp_path):
    assert crash_audit(tmp_path,EXT)==list(STAGES)
