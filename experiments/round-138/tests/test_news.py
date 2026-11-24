from news_retrieval import quote_span,drift

def test_quote():
    assert quote_span(b"other\nThe alpha result.\nend",("alpha",))==(b"The alpha result.",True)
    assert quote_span(b"alphabet\nother",("alpha",))==(b"alphabet",False)

def test_drift():
    events=[("a",0,b"alpha old"),("b",0,b"beta"),("a",1,b"alpha new")]
    q=(("alpha",),"AND")
    x=drift(events,2,[q],{q:[(1,-1.)]},{q:[(3,-1.)]})["counts"]
    assert x["rank_order_changed"]==0 and x["revision_order_changed"]==1
    assert x["latest_source_changed"]==1 and x["span_missing_from_latest"]==1
