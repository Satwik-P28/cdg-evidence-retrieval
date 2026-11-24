import os
from compact_boundary import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
POS=Path(os.environ["CDG_POS_EXTENSION"]).resolve()
CROSS=Path(os.environ["CDG_CROSS_EXTENSION"]).resolve()
DEC=Path(os.environ["CDG_NATIVE_DECODER"]).resolve()

def test_integrated_fixture(tmp_path):
    events=[("a",0,b"one two three "*100),("b",0,b"one two three "*100),
            ("a",1,b"zero "+b"one two three "*100),("a",2,b""),("b",1,b"one two three "*80)]
    r=experiment(tmp_path,events,EXT,POS,CROSS,DEC,1)
    assert all(max(x["max_error"].values())<=1e-11 for x in r["cutoffs"])
    assert r["expanded_crossing_entries"]>0
    assert r["layouts"]["all4"]["term_entries"]>0
    assert r["layouts"]["boundary4"]["term_entries"]==0

def test_hot_dispatch_and_temporal_intervals(tmp_path):
    # A term with 130 distinct article intervals qualifies as hot.
    events=[(str(i),0,b"x x y") for i in range(130)]+[("0",1,b"y")]
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);by,og=maps(rows);db=sqlite3.connect(tmp_path/"hot.sqlite")
    tf=postings(rows,freqs,True)
    r=install(db,tmp_path/"hot.sqlite",rows,by,og,{},tf,"hot4")
    assert r["term_entries"]==2
    d=Decoder(DEC)
    for c in (1,130,131):
        a=active(rows,c);state=d.prepare(a,og,len(ids)+1)
        got,z=counts(db,"x",c,a,"hot4",d,state)
        assert z["tf_dispatch"]==1
        assert got=={g:2 for g in a.values() if "x" in freqs[g]}
    db.close()
