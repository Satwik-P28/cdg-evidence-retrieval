import os
from pathlib import Path
import pytest
import cost_selection as cs
from cost_selection import (split_plan,greedy,knapsack,local_search,score_terms,materialize,
    extract,make_freq_lookup,workload_value,evaluate,f,h,tt,connect)

EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_split_is_deterministic_and_disjoint():
    qs=[(("a b",),"AND"),(("c",),"AND"),(("d e",),"OR"),(("f g h",),"AND"),(("i",),"AND"),
        (("j k",),"AND"),(("l m",),"AND"),(("n",),"AND"),(("o p",),"OR"),(("q",),"AND")]
    a=split_plan(qs);b=split_plan(qs)
    assert a==b
    assert set(a)<={'train','validation','heldout'} and a['train']
    flat=[q for part in a.values() for q in part]
    assert sorted(map(repr,flat))==sorted(map(repr,qs))
    assert sum(len(a.get(k,())) for k in ('train','validation','heldout'))==len(qs)

def test_optimizers_respect_budget():
    rows=[(10.0,100.0,10.0,1),(5.0,50.0,10.0,2),(2.0,40.0,20.0,3),(1.0,30.0,30.0,4),(0.5,50.0,100.0,5)]
    for budget in (0,10,25,60,150):
        chosen,spent=greedy(rows,budget)
        assert spent<=budget
        expected=[]
        running=0.0
        for ratio,value,cost,tid in rows:
            if cost<=budget-running:expected.append(tid);running+=cost
        assert chosen==expected
        chosen,spent=knapsack(rows,budget)
        assert spent<=budget
        kept,spent=local_search(rows,budget,chosen)
        assert spent<=budget
        value=sum(next(r[1] for r in rows if r[3]==t) for t in kept)
        base=sum(next(r[1] for r in rows if r[3]==t) for t in chosen)
        assert value>=base

def test_knapsack_beats_naive_ratio_on_classic_instance():
    rows=[(1.0,60.0,10.0,1),(1.0,100.0,20.0,2),(1.0,120.0,30.0,3)]
    chosen,_=knapsack(rows,50.0)
    assert sorted(chosen)==[2,3]

def test_score_terms_policies():
    terms={b"a":(dict(df=10,cf=20,posbytes=100,blocks=1,srccost=1000,redundancy=5,avgdl=7.0),{}),
           b"b":(dict(df=5,cf=50,posbytes=10,blocks=1,srccost=10,redundancy=1,avgdl=7.0),{})}
    ids={b"a":1,b"b":2}
    for policy in ("df","cf","srccost","redundancy","ratio_df"):
        rows=score_terms(terms,ids,policy,{})
        assert {r[3] for r in rows}=={1,2}
        assert rows==sorted(rows,key=lambda r:(-r[0],-r[1],r[3]))
    rows=score_terms(terms,ids,"train_candidates",{1:100.0})
    assert rows[0][3]==1 and len(rows)==1
    with pytest.raises(ValueError):score_terms(terms,ids,"nope",{})

def _corpus(tmp_path,target_terms):
    ev=[]
    for i in range(60):
        if i%3==0:raw=b"alpha beta gamma delta alpha beta"
        elif i%3==1:raw=b"beta gamma filler alpha gamma"
        else:raw=b"gamma delta filler beta filler"
        ev.append(("a%d"%i,0,raw+b" mark%d"%i))
    folder=tmp_path/"work";folder.mkdir(exist_ok=True)
    base=folder/"base.sqlite"
    db,_=f.build(base,EXT,ev,"marginal",False)
    terms=extract(db)
    tt.build_tape(db,base,ev,"frequency")
    ids,_=tt.vocabulary(db)
    lookup=make_freq_lookup(db)
    value_map=workload_value(db,[(c,p,o) for c in (20,40,60)
        for p,o in [(('alpha beta',),'AND'),(('beta gamma',),'AND')]],ids,lookup)
    lookup_counts=(len(lookup(ids[b"alpha"])),len(lookup(-1)))
    db.close()
    cs.EXTENSION=EXT
    cuts=[20,40,60]
    refs={c:h.active_oracle(ev,c) for c in cuts}
    qs=[(("alpha beta",),"AND"),(("beta gamma",),"AND"),(("gamma delta filler",),"AND"),(("alpha",),"AND")]
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    for ref in refs.values():ref.close()
    splits={"all":qs}
    chosen=[ids[t] for t in target_terms if t in ids]
    path=folder/"arm.sqlite"
    size=materialize(base,path,terms,ids,chosen)
    db=connect(path,EXT)
    stats=evaluate(db,ids,cuts,expected,splits,size["sqlite_bytes"])
    db.close()
    return size,stats,len(terms),lookup_counts,terms,ids,value_map

@pytest.mark.parametrize("selected",[[],[b"alpha",b"beta"],[b"alpha",b"beta",b"gamma",b"delta",b"filler"]])
def test_selection_keeps_exact_ranking(tmp_path,selected):
    size,stats,nt,_,terms,ids,_=_corpus(tmp_path,selected)
    assert stats["all"]["score_error"]==0.0
    assert stats["all"]["rank_checks"]==len([20,40,60])*4*2
    assert size["selected_terms"]==len(selected)
    if not selected:assert stats["all"]["work"].get("source_reads",0)>0
    if len(selected)==5:assert stats["all"]["work"].get("source_reads",0)==0

def test_workload_value_uses_frequency_index(tmp_path):
    size,stats,nt,lookup_counts,terms,ids,value_map=_corpus(tmp_path,[])
    assert lookup_counts[0]>0 and lookup_counts[1]==0
    assert value_map[ids[b"alpha"]]>0 and value_map[ids[b"beta"]]>0
    top=cs.score_terms(terms,ids,"train_candidates",value_map)[0][3]
    assert top in {ids[b"alpha"],ids[b"beta"],ids[b"gamma"],ids[b"delta"],ids[b"filler"]}
    ranked=cs.topk(terms,ids,2)
    assert len(ranked)==2 and ranked[0][1]>=ranked[1][1]
