import os
import copy
import pytest
from atomic_receipts import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()

def test_atomic_append_and_replay(tmp_path):
    path=tmp_path/"archive.sqlite";db=setup(path,EXT)
    append_atomic(db,"a",b"one one two");append_atomic(db,"b",b"one three")
    r=connect(path,EXT);r.execute("BEGIN")
    assert audit_ledger(r)==2
    body,digest=issue(r,("one",),"AND",2,"all")
    append_atomic(db,"a",b"one two three four")
    assert generation(r)==2
    assert replay(r,body,digest)==body
    r.rollback();r.execute("BEGIN")
    assert audit_ledger(r)==3
    assert replay(r,body,digest)==body
    for key,value in (("scope","heads"),("total_tokens",0),("prefix_sha256","0"*64),("phrase_df",[0])):
        bad=copy.deepcopy(body);bad[key]=value
        with pytest.raises(ValueError):replay(r,bad,digest)
        if key!="scope":
            with pytest.raises(ValueError):replay(r,bad,sha(canonical(bad)).hex())
        else:
            # Rehashing a valid alternative query is not forgery resistance.
            assert replay(r,bad,sha(canonical(bad)).hex())==bad
    bad=copy.deepcopy(body);bad["hits"][0]["source_sha256"]="0"*64
    with pytest.raises(ValueError):replay(r,bad,sha(canonical(bad)).hex())
    r.close();db.close()

def test_no_transaction(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT);append_atomic(db,"a",b"one")
    with pytest.raises(ValueError,match="transaction"):issue(db,("one",),"AND",1,"all")
    db.close()

def test_ledger_corruption(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT);append_atomic(db,"a",b"one two")
    db.execute("UPDATE rank_ledger SET prefix_sha=zeroblob(32)")
    with pytest.raises(ValueError,match="chain"):audit_ledger(db)
    db.close()

def test_empty_unicode_and_nul(tmp_path):
    db=setup(tmp_path/"x.sqlite",EXT)
    for a,s in (("a",""),("b","Café e\u0301 한국어"),("a","a\x00b")):append_atomic(db,a,s.encode())
    assert audit_ledger(db)==3
    db.close()

def test_process_death(tmp_path):
    assert crash_audit(tmp_path,EXT)==list(STAGES)

def test_fixture(tmp_path):
    events=[("a",0,b"one one two"),("b",0,b"one two three"),("a",1,b"one two one"),("b",1,b"two three")]
    r=experiment(tmp_path,events,EXT)
    assert r["max_score_error"]<=1e-11 and r["all_source_readbacks"]==4
