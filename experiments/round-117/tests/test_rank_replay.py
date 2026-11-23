import random
import pytest
from rank_replay import *

def test_inverse_roundtrip():
    rng=random.Random(117)
    for _ in range(2000):
        dl=rng.randint(1,50000);tf=rng.randint(1,dl)
        avg=rng.uniform(1,10000)
        w=idf(500,rng.randint(1,500))
        assert invert(-positive_score(tf,dl,avg,w),dl,avg,w)==tf

@pytest.mark.parametrize("score",[-10.0,0.0,float("nan")])
def test_refusal(score):
    with pytest.raises(ValueError): invert(score,10,5,1)

def test_repeated_phrase_and_boolean(tmp_path):
    events=[("a",0,b"one one one two"),("b",0,b"one two three"),
            ("a",1,b"one two one two"),("b",1,b"two two three"),("c",0,b"")]
    r=experiment(tmp_path,events)
    assert r["integer_frequency_differentials"]>0
    assert all(x["max_inverse_score_error"]<=1e-11 for x in r["cutoffs"])

def test_direct_integer_phrase_counts(tmp_path):
    db=setup(tmp_path/"f.sqlite")
    append(db,"a",b"one one one","snapshot");append(db,"a",b"one two one two","snapshot")
    materialize_ledger(db,2)
    lengths,totals=load_ledger(db,2)
    for phrase,want in (("one one",{1:2}),("one two",{2:2}),("one",{1:3,2:2})):
        assert inverse_counts(db,phrase,lengths,totals)==positional_counts(db,phrase)==want
    db.close()
