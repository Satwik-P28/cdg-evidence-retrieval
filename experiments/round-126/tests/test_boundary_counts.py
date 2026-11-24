import os
import pytest
from boundary_counts import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
POS=Path(os.environ["CDG_POS_EXTENSION"]).resolve()
CROSS=Path(os.environ["CDG_CROSS_EXTENSION"]).resolve()

def test_first_boundary_tiny_repeated():
    for seq in ((1,1,1,1,1),(1,2,3,1,2,3),(1,),()):
        for size in (1,2,3):
            parts=partitions(seq,"fixed",size)
            _,got=boundary_data(seq,parts)
            assert got==independent_cross(seq,parts)
            if size==1:
                assert got==collections.Counter(seq[p:p+k] for k in (2,3) for p in range(len(seq)-k+1))

def test_native_cross():
    db=sqlite3.connect(":memory:");extension(db,CROSS)
    db.execute("CREATE VIRTUAL TABLE edge USING fts5(body)")
    db.execute("INSERT INTO edge VALUES('x x x x')")
    assert db.execute("SELECT cdg_cross(edge,2) FROM edge WHERE edge MATCH ?",('"x x"',)).fetchone()==(1,)
    assert db.execute("SELECT cdg_cross(edge,2) FROM edge WHERE edge MATCH ?",('"x x x"',)).fetchone()==(2,)
    assert db.execute("SELECT cdg_cross(edge,1) FROM edge WHERE edge MATCH ?",('"x x x"',)).fetchone()==(1,)
    with pytest.raises(sqlite3.OperationalError):
        db.execute("SELECT cdg_cross(edge,2) FROM edge WHERE edge MATCH 'x'").fetchone()

def test_actual_crossing(tmp_path):
    events=[("a",0,b"one two three "*100),("b",0,b"one two three "*100),("a",1,b"zero "+b"one two three "*100),
            ("a",2,b""),("b",1,b"one two three "*80)]
    r=experiment(tmp_path,events,EXT,POS,CROSS,1)
    assert r["crossing_ngram_occurrences"]>0
    assert all(max(c["max_error"].values())<=1e-11 for c in r["cutoffs"])
    assert any(c["crossing_occurrences"]>0 for c in r["cutoffs"])

def test_long_phrase_refused():
    with pytest.raises(ValueError):validate_phrase("one two three four")
