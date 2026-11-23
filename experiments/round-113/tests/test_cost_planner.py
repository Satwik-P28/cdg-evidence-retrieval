import itertools
import random
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cost_planner import (LAYOUTS,Option,optimize,paper_options,physical_pareto,reward,UNIT)


def dummy_codec(payload):
    return b'xxx'+payload[:3]


def fixture_profiles(n=10):
    out={}
    for i in range(n):
        rows=[(f'paper{i}|{j}',b'abc'*(j+1)*(i%5+1)) for j in range(i+1)]
        out[f'paper{i}']=paper_options(rows,dummy_codec)
    return out


def test_group_boundaries_and_cost_are_exact():
    rows=[(str(i),b'a'*(i+1)) for i in range(9)]
    opts=paper_options(rows,lambda x:b'x'*((len(x)+7)//8))
    assert opts['individual'].n_blocks==9
    assert opts['group4'].n_blocks==3
    assert opts['paper'].n_blocks==1
    assert opts['paper'].decoded_uniform_bytes_sum==9*45
    assert opts['individual'].decoded_uniform_bytes_sum==45
    assert opts['group4'].decoded_uniform_bytes_sum==4*10+4*26+1*9
    assert opts['paper'].n_paragraphs==9

@pytest.mark.parametrize('policy',['balanced','read','length','hash'])
@pytest.mark.parametrize('fraction',[0,0.2,0.35,0.65,1])
def test_deterministic_valid_budget_and_no_gold(policy,fraction):
    p=fixture_profiles()
    result,meta=optimize(p,mode=policy,fraction=fraction,unit=8)
    again,meta2=optimize(p,mode=policy,fraction=fraction,unit=8)
    assert result==again and meta==meta2
    assert len(result)==len(p) and set(result.values())<=set(LAYOUTS)
    assert meta['selected_quantized_cost_bytes']<=meta['allowed_proxy_total_bytes']-meta['baseline_proxy_bytes']+1e-7
    assert meta['not_a_physical_sqlite_budget_guarantee'] is True


def test_budget_zero_must_keep_free_choices_only():
    p=fixture_profiles()
    choices,_=optimize(p,fraction=0,unit=1)
    for pid,layout in choices.items():
        assert p[pid][layout].estimated_bytes<=p[pid]['paper'].estimated_bytes


def test_invalid_inputs():
    with pytest.raises(ValueError):paper_options([],dummy_codec)
    with pytest.raises(ValueError):paper_options([('x',b'a'),('x',b'b')],dummy_codec)
    with pytest.raises(ValueError):optimize({},fraction=.5)
    with pytest.raises(ValueError):optimize(fixture_profiles(),fraction=1.1)
    with pytest.raises(ValueError):optimize(fixture_profiles(),unit=0)
    with pytest.raises(ValueError):optimize(fixture_profiles(),mode='not-policy')


def test_proxied_dp_matches_exhaustive_small_instance():
    # Force exact 1-byte costs and search all 3^4 choices, same reward definition.
    p=fixture_profiles(4)
    result,meta=optimize(p,fraction=.65,unit=1,mode='balanced')
    rden=sum(p[pid]['paper'].decoded_uniform_bytes_sum for pid in p)
    wden=sum(p[pid]['paper'].reencoded_uniform_bytes_sum for pid in p)
    budget=meta['allowed_proxy_total_bytes']-meta['baseline_proxy_bytes']
    best=float('-inf')
    for combo in itertools.product(LAYOUTS,repeat=len(p)):
        cost=sum(max(0,p[pid][ly].estimated_bytes-p[pid]['paper'].estimated_bytes) for pid,ly in zip(sorted(p),combo))
        if cost<=budget:
            val=sum(reward(pid,p[pid],ly,'balanced',rden,wden) for pid,ly in zip(sorted(p),combo))
            best=max(best,val)
    actual=sum(reward(pid,p[pid],ly,'balanced',rden,wden) for pid,ly in result.items())
    assert actual==pytest.approx(best,abs=1e-12)


def test_pareto_basic():
    records=[{'name':'a','physical_bytes':10,'decoded_bytes':10,'wal_bytes':10},
             {'name':'b','physical_bytes':9,'decoded_bytes':9,'wal_bytes':9},
             {'name':'c','physical_bytes':12,'decoded_bytes':5,'wal_bytes':5}]
    assert physical_pareto(records)==['b','c']