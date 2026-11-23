import os
import pytest
from compact_temporal import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()

@pytest.mark.parametrize("n",[0,1,127,128,16384,2**32-1])
def test_varint(n):
    data=vint(n);assert readv(data,0)==(n,len(data))

@pytest.mark.parametrize("data",[b"",b"\x80",b"\x80\x00",b"\xff"*5])
def test_bad_varint(data):
    with pytest.raises(ValueError):readv(data,0)

def test_blocks():
    items=[("alpha",b"x"),("alphabet",b"y"),("éclair",b"z"),("école",b"abc")]
    assert unblock(unframe(frame(block(items),True)))==items
    records=[(1,0,2,3),(1,3,4,1),(129,0,5,2)]
    assert unpack_postings(pack_postings(records))==records
    with pytest.raises(ValueError):unpack_postings(pack_postings([(1,0,4,2),(1,2,5,1)]))

def test_complete(tmp_path):
    events=[("a",0,b"x x one"),("b",0,b"x two"),("a",1,b"x x three"),("a",2,b""),("b",1,b"two"),("a",3,b"x one")]
    r=run_experiment(tmp_path,events,EXT,1)
    assert all(max(c["max_score_error"].values())<=1e-11 for c in r["cutoffs"])

def test_partition(tmp_path):
    # 130 articles; term persists across 512-generation bucket boundary.
    events=[(str(i),0,b"common") for i in range(130)]
    events += [(str(i),j,b"common") for j in range(1,5) for i in range(130)]
    f=extract(events);rows,ids=metadata(events,f);coal=postings(rows,f,True);by,og=maps(rows)
    db,s=create(tmp_path/"part.sqlite",rows,ids,coal,"shared4k_time",by,og)
    assert s["segments"]==2
    assert verify_store(db,coal,"shared4k_time",by,og,len(rows)+1)==130
    for c in (1,130,512,513,650):
        a=active(rows,c)
        assert get_counts(db,"common","shared4k_time",c,a,og)[0]=={g:1 for g in a.values()}
    db.close()
