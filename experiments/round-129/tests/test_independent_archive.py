import os
import pytest
from independent_archive import *
EXT=Path(os.environ["CDG_FTS_EXTENSION"]).resolve()
def test_matched_archive(tmp_path):
    events=[("a",0,b"one two three "*100),("b",0,b"one four "*80),
            ("a",1,b"zero "+b"one two three "*100),("b",1,b"one four "*79+b"new"),
            ("a",2,b"zero "+b"one two three "*99+b"five")]
    origins=[]
    for g,(a,i,raw) in enumerate(events,1):
        c,t,o=fixture_origin(raw,str(g));origins.append(dict(g=g,path=a,ordinal=i,commit=c,committer_unix=t,blob_sha1=o,source_sha256=sha(raw).hex(),bytes=len(raw)))
    manifest=dict(retained_paths=["a","b"],changed_paths=2,cutoffs=[2,4,5],origins=origins)
    r=experiment(tmp_path,events,manifest,EXT,1)
    assert all(x["source_reads"]==5 and x["max_score_error"]<=1e-11 for x in r["policies"].values())
    assert r["policies"]["snapshot"]["depth_counts"]=={0:5}
def test_origin_failure(tmp_path):
    db=integrated_setup(tmp_path/"bad.sqlite",EXT,{"fixture":True})
    with pytest.raises(ValueError):append_policy(db,"a",b"x",fixture_origin(b"y","bad"),"snapshot")
    assert generation(db)==0;db.close()
def test_git_history(tmp_path):
    root=tmp_path/"git";root.mkdir()
    def run(*args):return git(root,*args).stdout.decode().strip()
    run("init");run("config","user.name","Fixture");run("config","user.email","fixture@example.invalid")
    a=root/"bip-0001.mediawiki";b=root/"bip-0002.md";a.write_text("first one");b.write_text("second one")
    run("add",".");run("commit","-m","base")
    a.write_text("first two");run("add",".");run("commit","-m","edit")
    b.unlink();run("add","-A");run("commit","-m","delete")
    a.write_text("first three");run("add",".");run("commit","-m","edit again")
    pin=run("rev-parse","HEAD");events,m=collect(root,"bips",pin,3,2)
    assert [raw for _,_,raw in events]==[b"first one",b"first two",b"first three"]
    assert m["excluded_deleted"]==["bip-0002.md"]
    assert m["cutoffs"]==[1,2,3]
