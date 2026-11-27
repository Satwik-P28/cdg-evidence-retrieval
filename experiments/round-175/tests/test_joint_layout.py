import os
from pathlib import Path
import pytest
import joint_layout as jl
from joint_layout import (build_hot,materialize,rank_joint,hot_contents,f,h,tt,prepare,connect)
from blocked_positions import BlockIndex
import cost_selection as cs

EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def _corpus(tmp_path):
    ev=[]
    for i in range(40):
        if i==5:raw=b"alpha beta gamma rare"
        elif i%3==0:raw=b"alpha beta alpha gamma"
        elif i%3==1:raw=b"beta gamma delta alpha"
        else:raw=b"gamma alpha beta delta beta"
        ev.append(("a%d"%i,0,raw+b" mark%d"%i))
    folder=tmp_path/"work";folder.mkdir()
    base=folder/"base.sqlite"
    db,_=f.build(base,EXT,ev,"marginal",False)
    terms=cs.extract(db)
    tt.build_tape(db,base,ev,"frequency")
    ids,_=tt.vocabulary(db)
    db.close()
    jl.EXTENSION=EXT
    return ev,base,terms,ids

@pytest.mark.parametrize("hot_k,selected",[(0,[]),(0,[b"alpha",b"beta",b"gamma"]),
                                          (5,[]),(5,[b"alpha",b"beta",b"gamma"]),
                                          (1000,[b"alpha",b"beta",b"gamma",b"delta"])])
@pytest.mark.parametrize("unify",[False,True])
def test_joint_layout_keeps_exact_ranking(tmp_path,hot_k,selected,unify):
    ev,base,terms,ids=_corpus(tmp_path)
    chosen=[ids[t] for t in selected]
    path=tmp_path/"arm.sqlite"
    db=materialize(base,path,terms,ids,chosen,unify)
    hot=build_hot(db,hot_k) if hot_k else None
    db.commit();db.close()
    db=connect(path,EXT);index=BlockIndex(db,ids,True)
    queries=[(("alpha beta",),"AND"),(("alpha beta gamma",),"AND"),(("beta gamma rare",),"AND"),
             (("alpha alpha",),"AND"),(("alpha",),"AND")]
    for cutoff in (10,20,40):
        ref=h.active_oracle(ev,cutoff)
        prep=prepare(db,cutoff)
        for p,o in queries:
            hits,df,w=rank_joint(db,p,o,prep,index,hot)
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    if hot:assert len(hot)==min(hot_k,40)
    db.close()

def test_hot_region_reduces_source_reads(tmp_path):
    ev,base,terms,ids=_corpus(tmp_path)
    reads={}
    for hot_k in (0,40):
        path=tmp_path/("h%d.sqlite"%hot_k)
        db=materialize(base,path,terms,ids,[],False)
        hot=build_hot(db,hot_k) if hot_k else None
        db.commit();db.close()
        db=connect(path,EXT);index=BlockIndex(db,ids,True)
        _,_,w=rank_joint(db,("alpha beta gamma",),"AND",prepare(db,40),index,hot)
        reads[hot_k]=w.get("source_reads",0)
        db.close()
    assert reads[40]<=reads[0]

def test_hot_contents_ordering(tmp_path):
    ev,base,terms,ids=_corpus(tmp_path)
    db=connect(base,EXT)
    cids=hot_contents(db,3)
    assert len(cids)==3 and len(set(cids))==3
    service={}
    for cid in cids:
        g=db.execute("SELECT min(g) FROM revisions WHERE cid=?",(cid,)).fetchone()[0]
        _,_,ab=jl.recover(db,g)
        service[cid]=db.execute("SELECT count(*) FROM revisions WHERE cid=?",(cid,)).fetchone()[0]*ab
    assert max(service.values())>=min(service.values())
    db.close()

def test_term_level_unified_drops_postings(tmp_path):
    ev,base,terms,ids=_corpus(tmp_path)
    chosen=[ids[b"alpha"],ids[b"beta"]]
    path=tmp_path/"u.sqlite"
    db=materialize(base,path,terms,ids,chosen,True)
    db.commit()
    left={tid for tid, in db.execute("SELECT tid FROM token_postings")}
    assert not (left & set(chosen))
    assert db.execute("SELECT count(*) FROM term_blocks").fetchone()[0]==2
    db.close()
    db=connect(path,EXT);index=BlockIndex(db,ids,True)
    counts=index.all_counts(ids[b"alpha"])
    assert counts and all(v>=1 for v in counts.values())
    db.close()
