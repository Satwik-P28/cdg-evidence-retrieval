#!/usr/bin/env python3
"""Round 33: synthetic evidence-cover optimization with shared physical frame costs.

No model-derived evidence dependencies; coverage labels are supplied by the
fixture generator. Not end-to-end retrieval or evidence semantic validation.
"""
from __future__ import annotations
import argparse
import itertools
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Candidate:
    covers: frozenset[int]
    frames: frozenset[int]
    token_cost: int

@dataclass(frozen=True)
class Problem:
    required: frozenset[int]
    candidates: tuple[Candidate, ...]
    frame_cost: tuple[int, ...]
    token_weight: float = 0.25


def cost(p: Problem, selected: tuple[int,...] | list[int]) -> float:
    fs = set()
    for i in selected: fs.update(p.candidates[i].frames)
    return sum(p.frame_cost[f] for f in fs) + p.token_weight * sum(p.candidates[i].token_cost for i in selected)


def covered(p: Problem, selected: tuple[int,...] | list[int]) -> frozenset[int]:
    out = set()
    for i in selected: out.update(p.candidates[i].covers)
    return frozenset(out)


def greedy(p: Problem) -> tuple[int,...] | None:
    remaining = set(p.required)
    selected: list[int] = []
    active_frames: set[int] = set()
    while remaining:
        best = None
        best_ratio = -1.0
        for i,c in enumerate(p.candidates):
            if i in selected: continue
            gain = len(remaining & c.covers)
            if gain == 0: continue
            delta = sum(p.frame_cost[f] for f in c.frames-active_frames) + p.token_weight*c.token_cost
            ratio = gain / max(delta, 1e-12)
            if ratio > best_ratio + 1e-12 or (abs(ratio-best_ratio) <= 1e-12 and (best is None or i < best)):
                best = i
                best_ratio = ratio
        if best is None: return None
        selected.append(best)
        active_frames.update(p.candidates[best].frames)
        remaining.difference_update(p.candidates[best].covers)
    return tuple(selected)


def exact(p: Problem) -> tuple[int,...] | None:
    """Brute-force ground truth for tiny instances; not a production policy."""
    n = len(p.candidates)
    best: tuple[int,...] | None = None
    best_cost = float('inf')
    for mask in range(1 << n):
        sel = tuple(i for i in range(n) if mask & (1<<i))
        if not p.required <= covered(p,sel): continue
        val=cost(p,sel)
        if val < best_cost - 1e-9 or (abs(val-best_cost)<=1e-9 and (best is None or sel<best)):
            best,best_cost=sel,val
    return best


def make_problem(seed:int, family:str, n:int=11, m:int=7, frames:int=6)->Problem:
    rng=random.Random(seed)
    frame_cost=tuple(rng.randint(8,30) for _ in range(frames))
    cand=[]
    for i in range(n):
        if family=='independent':
            fs=frozenset([i%frames])
            cov=frozenset(j for j in range(m) if rng.random()<0.34)
        elif family=='shared':
            fs=frozenset(rng.sample(range(max(2,frames//2)),rng.choice([1,1,2])))
            cov=frozenset(j for j in range(m) if rng.random()<0.36)
        elif family=='bridge':
            # Clustered facts and shared frames; occasionally long individual witness.
            group=(i%2);fs=frozenset([group, 2 + (i%max(1,frames-2))])
            cov=frozenset(j for j in range(m) if (j%2==group and rng.random()<0.68) or rng.random()<0.09)
        else: raise ValueError(family)
        cand.append(Candidate(cov,fs,rng.randint(1,20)))
    # Guarantee coverage but do not tell the selector which candidates supply it.
    for j in range(m):
        if not any(j in c.covers for c in cand):
            i=rng.randrange(n)
            old=cand[i]
            cand[i]=Candidate(old.covers | {j},old.frames,old.token_cost)
    return Problem(frozenset(range(m)),tuple(cand),frame_cost)


def run(repetitions:int=80,seed:int=33116)->dict:
    results={'seed':seed,'instances_per_family':repetitions,'experiment':'synthetic small-instance oracle comparison; known coverage; read/decode cost proxies only','families':{}}
    for family in ('independent','shared','bridge'):
        ratios=[];fail=0;ex=[];cost_exact=[];cost_greedy=[];equal=0
        for n in range(repetitions):
            p=make_problem(seed+n*17, family)
            opt=exact(p);g=greedy(p)
            if opt is None or g is None:fail+=1;continue
            a=cost(p,opt);b=cost(p,g)
            assert b+1e-8>=a,(family,n,opt,g,a,b)
            ratio=b/a
            ratios.append(ratio);cost_exact.append(a);cost_greedy.append(b)
            if abs(a-b)<1e-8: equal+=1
            if ratio>=1.25 and len(ex)<4:
                ex.append({'instance_seed':seed+n*17,'ratio':round(ratio,4),'greedy':list(g),'exact':list(opt),'greedy_cost':round(b,4),'exact_cost':round(a,4)})
        results['families'][family]={
          'n':len(ratios),'unsolved':fail,'mean_greedy_over_optimum':round(statistics.mean(ratios),4),
          'median_greedy_over_optimum':round(statistics.median(ratios),4),
          'worst_greedy_over_optimum':round(max(ratios),4),
          'exact_matches':equal,'mean_exact_cost':round(statistics.mean(cost_exact),3),
          'mean_greedy_cost':round(statistics.mean(cost_greedy),3),'counterexamples':ex}
    return results


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--repetitions',type=int,default=80);args=ap.parse_args()
    result=run(args.repetitions);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__': main()
