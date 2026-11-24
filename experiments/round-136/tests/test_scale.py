import sqlite3
from newsedits_scale import sample,read_article,run

def test_fixture(tmp_path):
    source=tmp_path/"input.db";db=sqlite3.connect(source)
    db.execute("CREATE TABLE split_sentences(entry_id,version,sent_idx,sentence)")
    db.executemany("INSERT INTO split_sentences VALUES(?,?,?,?)",[(1,0,1,"β"),(1,0,0,"a"),(1,2,0,"b"),(2,0,0,"solo")])
    db.commit()
    assert sample(db,10)==([(1,2)],2,1)
    assert read_article(db,1,2)==[(0,"a\nβ".encode()),(2,b"b")]
    db.close()
    folder=tmp_path/"out";folder.mkdir()
    x=run(source,10,folder)
    assert x["retained_revisions"]==2 and not x["target_reached"]
    assert all(y["reads"]==2 for y in x["policies"].values())
