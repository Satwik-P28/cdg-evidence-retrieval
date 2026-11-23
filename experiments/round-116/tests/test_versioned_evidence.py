from dataclasses import replace
import pytest
from versioned_evidence import *

@pytest.mark.parametrize("policy",POLICIES)
def test_snapshot_and_receipts(tmp_path,policy):
    path=tmp_path/"archive.sqlite"
    db=setup(path);append(db,"a",b"alpha beta "*100,policy)
    reader=connect(path);reader.execute("BEGIN")
    r=search(reader,'"alpha"')[0][0]
    append(db,"a",b"gamma beta "*100,policy)
    assert generation(reader)==1
    assert read_receipt(reader,r)[0]==b"alpha beta "*100
    assert not search(reader,'"gamma"')
    reader.rollback();reader.execute("BEGIN")
    assert generation(reader)==2 and search(reader,'"gamma"')
    assert not search(reader,'"alpha"',"heads")
    assert read_receipt(reader,r)[0]==b"alpha beta "*100
    for invalid in (replace(r,digest="0"*64),replace(r,ordinal=1),replace(r,observed_generation=0),replace(r,article="b")):
        with pytest.raises(ValueError):read_receipt(reader,invalid)
    reader.close();db.close()

@pytest.mark.parametrize("policy",POLICIES)
def test_crash(tmp_path,policy):
    assert len(crash_audit(tmp_path,policy))==4

@pytest.mark.parametrize("policy",POLICIES)
def test_oracle(tmp_path,policy):
    events=[("a",0,b"alpha beta "*30),("b",0,b"beta gamma "*30),("a",1,b"gamma beta "*30),("b",1,b"delta beta "*30)]
    r=physical_audit(tmp_path/"index.sqlite",events,policy,['"alpha"','"beta"','"alpha beta"'],2)
    assert r["all_revision_readbacks"]==4 and r["prefix"]["queries"]==6
