import os
import pytest
from native_compare import *

def test_native_counts(tmp_path):
    db=setup(tmp_path/"x.sqlite");extension(db,os.environ["CDG_FTS_EXTENSION"])
    for a,raw in (("a",b"one one one"),("a",b"one two one two"),("b",b"")):append(db,a,raw,"snapshot")
    materialize_ledger(db,3);lens,totals=load_ledger(db,3)
    assert counts(db,"one one",lens)=={1:2}
    assert counts(db,"one two",lens)=={2:2}
    assert counts(db,"one",lens,1)=={1:3}
    with pytest.raises(sqlite3.OperationalError):
        db.execute("SELECT cdg_count(docs) FROM docs WHERE docs MATCH 'one OR two'").fetchall()
    db.close()

@pytest.mark.parametrize("value",["","café CAFÉ","e\u0301 test","한국어 中文","one-two","a\x00b","😊 a", "A_1"])
def test_tokenizer(tmp_path,value):
    db=setup(tmp_path/"x.sqlite");extension(db,os.environ["CDG_FTS_EXTENSION"])
    append(db,"a",value.encode(),"snapshot")
    materialize_ledger(db,1)
    dl=db.execute("SELECT dl FROM rank_ledger").fetchone()[0]
    assert db.execute("SELECT cdg_token_count(?)",(value,)).fetchone()[0]==dl
    db.close()

def test_full_fixture(tmp_path):
    events=[("a",0,b"one one one two"),("b",0,b"one two three"),("a",1,b"one two one two"),("b",1,b"two two three")]
    r=experiment(tmp_path,events,os.environ["CDG_FTS_EXTENSION"],1)
    assert r["native_tokenizer_length_checks"]==4
    assert all(max(x["max_error"].values())<=1e-11 for x in r["cutoffs"])
