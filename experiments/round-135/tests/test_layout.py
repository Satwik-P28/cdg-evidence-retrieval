import io
from layout_archive import PTR,pointer,fetch_frame,create_wiki,loads,retrieve_range,Revision

def test_pointer():
    data=io.BytesIO(b"hello world")
    assert fetch_frame(data,PTR.pack(6,5))==b"world"

def test_published_wikecd_roundtrip():
    # Include missing final newline and Unicode; require byte-preserving native API.
    texts=["one\ntwo\n","one\nthree\n","one\nthree\nα"]
    revs=[Revision(i,"2024-01-01T00:00:00Z",t) for i,t in enumerate(texts)]
    for budget in (None,10000):
        a,b=loads(create_wiki("test",revs,budget))
        for i,t in enumerate(texts):assert retrieve_range(a,b,i,0)==[t]
