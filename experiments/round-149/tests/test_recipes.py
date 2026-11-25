import random
from marginal_recipes import encode,features

def test_duplicate_literal():
    raw=bytes(random.Random(149).choices(b"abcdefghijklmnopqrstuvwxyz ",k=5000))
    events=[("a",0,raw),("b",0,raw),("b",1,raw)]
    x=encode(events,"marginal")
    assert x["unique_frames"]==1 and x["literals"]==3 and x["max_decode_ratio"]==1
def test_exact_recipe_across_documents():
    raw=bytes(random.Random(149).choices(b"abcdefghijklmnopqrstuvwxyz ",k=5000))
    revised=raw[:2500]+b"inserted text"+raw[2500:]
    events=[("a",0,raw),("a",1,revised),("b",0,revised)]
    old=encode(events,"baseline");new=encode(events,"recipe")
    assert new["cross_article_deltas"]==1
    assert new["payload_bytes"]<old["payload_bytes"]
    assert new["max_decode_ratio"]<=2.5 and new["max_activation_ratio"]<=1.5
def test_sketch_determinism():
    raw=b"alpha beta gamma delta epsilon "*100
    assert features(raw)==features(raw) and len(features(raw))<=4
    ev=[("a",0,raw),("b",0,raw+b"last"),("a",1,raw+b"edit")]
    for p in ("baseline","marginal","recipe","recipe_sketch"):
        a=encode(ev,p);b=encode(ev,p)
        assert a["recipe_sha256"]==b["recipe_sha256"]
