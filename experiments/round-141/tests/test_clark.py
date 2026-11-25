from clark_retrieval import ts,gold,contains,terms
def test_intervals():
    rows=[{"Answer":"A","Known start timestamp":"2020-01-01T00:00:00Z","Known end timestamp":"2021-01-01T00:00:00Z"},{"Answer":"B","Known start timestamp":"2021-01-01T00:00:00Z","Known end timestamp":""}]
    assert gold(rows,ts("2020-12-31T00:00:00Z"))=="A"
    assert gold(rows,ts("2021-01-01T00:00:00Z"))=="B"
def test_token_match():
    assert contains("The New York team.", "new york")
    assert not contains("renew york", "new york")
    assert terms("What team is Jane a member of?")==("team","jane")
