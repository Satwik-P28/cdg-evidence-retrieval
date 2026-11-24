import os
import pytest
from fragment_index import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
POS=Path(os.environ["CDG_POS_EXTENSION"]).resolve()

def test_partition_coverage():
    seq=tuple(range(1,201))
    for m in ("fixed","minima"):
        parts=partitions(seq,m,16)
        assert tuple(t for _,p in parts for t in p)==seq
        assert all(len(p)<=64 for _,p in parts)
    assert partitions((),"minima",16)==[]
    repeated=(1,)*200
    assert tuple(t for _,p in partitions(repeated,"minima",16) for t in p)==repeated

def test_boundary_phrase_and_reused_fragment(tmp_path):
    events=[("a",0,("one "*31+"two three").encode()),("b",0,("one "*31+"two three").encode()),
        ("a",1,("one "*31+"two four").encode())]
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);words=["","four","one","three","two"]
    wordids={t:i for i,t in enumerate(words)}
    seq=[tuple(wordids[t] for t in s) for s in tokens(pos)]
    db,r=create(tmp_path/"frag.sqlite",rows,ids,seq,words,"fixed32_coalesced",EXT,POS)
    act=active(rows,2)
    assert phrase_freq("two three",lambda t:term_positions(db,t,2,act))=={1:1,2:1}
    assert r["unique_fragments"]==3
    db.close()

def test_full_fixture(tmp_path):
    events=[("a",0,b"x x one"),("b",0,"café one two".encode()),("a",1,b"x x three"),
        ("a",2,b""),("b",1,b"two one"),("a",3,b"x one")]
    r=experiment(tmp_path,events,EXT,POS,1)
    assert all(max(x["max_error"].values())<=1e-11 for x in r["cutoffs"])
    assert all(x["verified_original_tokens"]==r["original_tokens"] for m,x in r["layouts"].items() if m in LAYOUTS)
