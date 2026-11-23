import sqlite3
from pathlib import Path
import pytest
from revision_bench import *

@pytest.mark.parametrize("policy",POLICIES)
def test_complete_archive(tmp_path,policy):
    docs=[("one",[b"alpha "*300,b"alpha "*200+b"BETA "*30,b"",b"hello"*50]),("two",[b"hello"*50,b"hello"*50+b"x"])]
    r=benchmark(tmp_path/"x.sqlite",docs,policy)
    assert r["versions"]==6 and r["all_revision_receipts_verified"]
    assert r["sqlite_bytes"]>0 and r["wal_bytes_append_all"]>0

@pytest.mark.parametrize("policy",["fixed512","fixed2048","cdc1024"])
def test_chunks(policy):
    raw=bytes(range(256))*100
    pieces=partition(raw,policy)
    assert b"".join(pieces)==raw
    assert not partition(b"",policy)
    assert max(map(len,pieces))<=4096

def test_delta():
    prev=b"some data "*1000
    raw=prev+b"NEW"
    assert delta_decode(delta_encode(raw,prev),prev,len(raw))==raw

def test_corrupt_receipt(tmp_path):
    db=setup(tmp_path/"bad.sqlite")
    append(db,"a",0,b"abc",b"",0,0,"snapshot")
    db.execute("UPDATE versions SET digest=zeroblob(32)")
    with pytest.raises(ValueError,match="receipt"):
        recover(db,"a",0)
    db.close()

def test_order_and_selection(tmp_path):
    folder=tmp_path/"article"; folder.mkdir()
    (folder/"10.txt").write_bytes(b"later")
    (folder/"2.txt").write_bytes(b"earlier")
    a,hash1=load(tmp_path)
    assert a==[("article",[b"earlier",b"later"])]
    assert load(tmp_path)[1]==hash1
    assert select(a,1,"seed")==a
