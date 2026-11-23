#!/usr/bin/env python3
"""CDG R113, source-only multi-resource block-layout pilot.

No retrieval queries, gold evidence annotations or evaluation edit results enter
selection. Source-local *compressed* costs are obtained from original source bytes.
The multiple-choice knapsack works on conservative quantized PROXY costs; it
provides no guarantee about physical SQLite page size. Prior-art optimization,
not a novel algorithm or an online worst-case bound.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import math
from typing import Callable, Iterable

LAYOUTS = ('paper', 'group4', 'individual')
UNIT = 128
EXTRA_BLOB_ROW_BYTES = 32
COMMON_PARAGRAPH_ROW_BYTES = 56

@dataclass(frozen=True)
class Option:
    layout: str
    blob_bytes: int
    n_blocks: int
    estimated_bytes: int
    decoded_uniform_bytes_sum: int
    reencoded_uniform_bytes_sum: int
    n_paragraphs: int


def paper_options(rows: list[tuple[str, bytes]], encode: Callable[[bytes],bytes]) -> dict[str,Option]:
    """Compressed payload sizes and uniform-single-paragraph read/edit proxies.

    Group boundaries match R106: consecutive original paragraphs, group-size 4
    or one whole original paper, and individual paragraphs.
    """
    if not rows or len({x for x,_ in rows}) != len(rows):
        raise ValueError('nonempty unique original paper paragraph ids required')
    if any(not isinstance(docid,str) or not isinstance(raw,bytes) for docid,raw in rows):
        raise ValueError('invalid original input')
    common=sum(COMMON_PARAGRAPH_ROW_BYTES+len(name.encode('utf8')) for name,_ in rows)
    options={}
    for layout in LAYOUTS:
        group=(1 if layout=='individual' else 4 if layout=='group4' else len(rows))
        blocks=[rows[i:i+group] for i in range(0,len(rows),group)]
        payload=0; read=0; write=0
        for block in blocks:
            raw=b''.join(r for _,r in block)
            if len(raw)>12_000_000:raise ValueError('block over R106 source limit')
            z=encode(raw)
            payload+=len(z)
            read+=len(block)*len(raw)
            write+=len(block)*len(z)
        options[layout]=Option(layout,payload,len(blocks),
              payload+len(blocks)*EXTRA_BLOB_ROW_BYTES+common,
              read,write,len(rows))
    return options


def global_denominators(profiles:dict[str,dict[str,Option]]) -> tuple[int,int]:
    if not profiles:raise ValueError('empty profiles')
    return (sum(v['paper'].decoded_uniform_bytes_sum for v in profiles.values()),
            sum(v['paper'].reencoded_uniform_bytes_sum for v in profiles.values()))


def reward(pid: str, options:dict[str,Option], layout:str,
           mode:str, rdenom:int, wdenom:int) -> float:
    default=options['paper']; cand=options[layout]
    if mode=='balanced':
        return (0.5*(default.decoded_uniform_bytes_sum-cand.decoded_uniform_bytes_sum)/max(1,rdenom)
                +0.5*(default.reencoded_uniform_bytes_sum-cand.reencoded_uniform_bytes_sum)/max(1,wdenom))
    if mode=='read':
        return (default.decoded_uniform_bytes_sum-cand.decoded_uniform_bytes_sum)/max(1,rdenom)
    if mode=='length':
        # Conventional corpus-only length/paragraph-count heuristic, not learned.
        return (math.log1p(default.n_paragraphs)
                *(2 if layout=='individual' else 1 if layout=='group4' else 0)
                /max(1,len(options)))
    if mode=='hash':
        # Stable pseudo-random control; cannot use query text/gold.
        h=int.from_bytes(hashlib.sha256(('CDG-R113-HASH-V1|'+pid).encode()).digest()[:8],'big')
        return (h/((1<<64)-1))*(2 if layout=='individual' else 1 if layout=='group4' else 0)
    raise ValueError('unknown policy mode')


def optimize(profiles:dict[str,dict[str,Option]], *,fraction:float=0.35,
             mode:str='balanced',unit:int=UNIT):
    """Quantized multiple-choice knapsack on paper-local static proxies.

    All candidates use the same source-only estimated budget. Upward rounding
    is conservative for this proxy, not for actual SQLite B-tree page sizes.
    """
    if not (0<=fraction<=1) or unit<=0:raise ValueError('bad budget')
    pids=sorted(profiles)
    if not pids:raise ValueError('empty data')
    read0,write0=global_denominators(profiles)
    base=sum(profiles[pid]['paper'].estimated_bytes for pid in pids)
    extra=sum(max(0,profiles[pid]['individual'].estimated_bytes-profiles[pid]['paper'].estimated_bytes) for pid in pids)
    capacity=math.floor(fraction*extra/unit)
    dp=[float('-inf')]*(capacity+1);dp[0]=0.0
    choices=[];costs=[]
    # Each page of the DP tracks the best reward at its *exact* unit cost.
    for pid in pids:
        opts=profiles[pid]
        options=[opts[name] for name in LAYOUTS]
        cc=[math.ceil(max(0,o.estimated_bytes-opts['paper'].estimated_bytes)/unit) for o in options]
        rr=[reward(pid,opts,o.layout,mode,read0,write0) for o in options]
        ndp=[float('-inf')]*(capacity+1)
        choice=bytearray([255])*(capacity+1)
        for budget in range(capacity+1):
            best=float('-inf');chosen=255
            for j in range(3):
                c=cc[j]
                if c<=budget and dp[budget-c]!=float('-inf'):
                    score=dp[budget-c]+rr[j]
                    if score>best+1e-14:
                        best=score;chosen=j
            if chosen!=255:
                ndp[budget]=best;choice[budget]=chosen
        dp=ndp;choices.append(choice);costs.append(cc)
    best_budget=max(range(capacity+1),key=lambda b:(dp[b],-b))
    if dp[best_budget]==float('-inf'):raise AssertionError('DP lost all-papers solution')
    result={};remaining=best_budget
    for i in range(len(pids)-1,-1,-1):
        selected=choices[i][remaining]
        if selected==255:raise AssertionError('invalid DP predecessor')
        result[pids[i]]=LAYOUTS[selected]
        remaining-=costs[i][selected]
    if remaining!=0 or set(result)!=set(profiles):raise AssertionError('DP reconstruction failed')
    proxy_used=sum(profiles[pid][l].estimated_bytes for pid,l in result.items())
    return result,{
        'planner':'quantized multiple-choice knapsack of per-paper source-only proxies',
        'policy_mode':mode,'fraction_of_all_individual_proxy_increment':fraction,
        'unit_bytes':unit,'baseline_proxy_bytes':base,
        'estimated_total_source_proxy_bytes':proxy_used,
        'allowed_proxy_total_bytes':base+fraction*extra,
        'total_individual_over_paper_proxy_delta':extra,
        'selected_quantized_cost_bytes':best_budget*unit,
        'optimized_score':dp[best_budget],
        'not_a_physical_sqlite_budget_guarantee':True,
    }


def physical_pareto(rows:list[dict],key_storage='physical_bytes',
                    key_read='decoded_bytes',key_wal='wal_bytes') -> list[str]:
    """Non-dominated on all 3 observed metrics (no predictions or weights)."""
    for a in rows:
        for key in (key_storage,key_read,key_wal):
            if key not in a or a[key]<0:raise ValueError('incomplete observed cost')
    result=[]
    for a in rows:
        if not any((b is not a and
            all(b[k]<=a[k] for k in (key_storage,key_read,key_wal)) and
            any(b[k]<a[k] for k in (key_storage,key_read,key_wal))) for b in rows):
            result.append(a['name'])
    return sorted(result)