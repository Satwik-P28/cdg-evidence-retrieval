#!/usr/bin/env python3
"""Round 34: bounded local repair and imperfect witness forecasts.
Uses Round 33 synthetic known-label fixture families. Not QA/NLI performance.
"""
from __future__ import annotations
import argparse, dataclasses, json, random, sys, statistics, time
from pathlib import Path
from itertools import combinations
_here = Path(__file__).resolve().parent
_round33 = next((p for p in (_here.parent/'round-33', _here.parent/'cdg_round33') if (p/'selection_lab.py').exists()), None)
if _round33 is None: raise RuntimeError('Round 33 selection_lab.py is required')
sys.path.insert(0,str(_round33))
from selection_lab import Problem,Candidate,make_problem,greedy,exact,cost,covered


def prune(p,sel):
    s=tuple(sorted(sel))
    changed=True
    while changed:
        changed=False
        for i in s:
            candidate=tuple(x for x in s if x!=i)
            if p.required<=covered(p,candidate):
                s=candidate;changed=True;break
    return s


def repair(p,selected,max_remove=2,max_add=2):
    """Strictly cost-reducing local exchanges (up to two out and two in).
    Includes deletion. Deterministic iteration; no oracle facet labels beyond
    the planner's *declared predicted coverage model*.
    """
    current=prune(p,selected)
    n=len(p.candidates); iterations=0; evaluated=0
    while iterations<32:
        iterations+=1
        best=current; best_cost=cost(p,current)
        for nremove in range(0,min(max_remove,len(current))+1):
            for rem in combinations(current,nremove):
                base=tuple(i for i in current if i not in rem)
                avail=[i for i in range(n) if i not in base]
                for nadd in range(max_add+1):
                    for add in combinations(avail,nadd):
                        candidate=tuple(sorted(set(base)|set(add)))
                        evaluated+=1
                        if p.required <= covered(p,candidate):
                            c=cost(p,candidate)
                            if c < best_cost-1e-9 or (abs(c-best_cost)<1e-9 and candidate<best):
                                best,best_cost=candidate,c
        if cost(p,best)>=cost(p,current)-1e-9:break
        current=prune(p,best)
    return current,evaluated


def predicted_problem(p,seed,noise):
    """Flip each candidate-facet relationship with noise, while true labels stay hidden.
    Guard: no oracle injection, and inferred coverage can be wrong in both ways.
    """
    rng=random.Random(seed)
    candidates=[]
    for c in p.candidates:
        cv=frozenset(j for j in p.required if ((j in c.covers) != (rng.random()<noise)))
        candidates.append(dataclasses.replace(c,covers=cv))
    return dataclasses.replace(p,candidates=tuple(candidates))


def acquire_with_observation(true: Problem, predicted: Problem):
    """Idealized post-read verifier: reveals actual facets ONLY after an item is opened.
    Not deployable without a validated entailment/facet detector. Baseline upper
    opportunity for verification-aware acquisition, not QA or a learned method.
    """
    remaining=set(true.required)
    selected=[]; active_frames=set()
    while remaining:
        best=None;best_value=-1.0
        for i,c in enumerate(predicted.candidates):
            if i in selected:continue
            gain=len(remaining & c.covers)
            delta=sum(true.frame_cost[f] for f in c.frames-active_frames)+true.token_weight*c.token_cost
            val=gain/max(delta,1e-12)
            if val>best_value+1e-12 or (abs(val-best_value)<=1e-12 and (best is None or i<best)):
                best=i;best_value=val
        if best is None: break
        selected.append(best)
        active_frames.update(true.candidates[best].frames)
        remaining-=true.candidates[best].covers  # observed after actual read
    return tuple(selected), not remaining


def benchmark(repetitions=100,seed=33116):
    out={'seed':seed,'n_per_family':repetitions,'methods':{},'noise_stress':{},'notes':'Synthetic small known-label instances; planning time measured locally, not model inference or I/O.'}
    cases=[(fam,make_problem(seed+i*17,fam)) for fam in ('independent','shared','bridge') for i in range(repetitions)]
    data={name:[] for name in ('greedy','pruned','repair','exact')}
    per_family={fam:{k:[] for k in data} for fam in ('independent','shared','bridge')}
    for fam,p in cases:
        opt=exact(p);assert opt is not None
        g=greedy(p); assert g is not None
        pr=prune(p,g)
        rep,evals=repair(p,pr)
        oc=cost(p,opt)
        for name,sel in [('greedy',g),('pruned',pr),('repair',rep),('exact',opt)]:
            assert p.required <= covered(p,sel)
            c=cost(p,sel); assert c>=oc-1e-9
            data[name].append((c/oc,c));per_family[fam][name].append(c/oc)
        out.setdefault('repair_evaluated',[]).append(evals)
    for name,vals in data.items():
        ratios=[r for r,c in vals];out['methods'][name]={
            'n':len(vals),'mean_ratio':round(statistics.mean(ratios),5),
            'median_ratio':round(statistics.median(ratios),5),
            'max_ratio':round(max(ratios),5),
            'exact_matches':sum(abs(x-1)<1e-9 for x in ratios),
            'mean_cost':round(statistics.mean(c for r,c in vals),4),
            'family_mean_ratios':{f:round(statistics.mean(per_family[f][name]),5) for f in per_family}
        }
    out['repair_search_evaluations']={'mean':round(statistics.mean(out.pop('repair_evaluated')),1)}
    for noise in (0,0.05,0.15,0.3):
        cnt={name:{'n':0,'complete':0,'unsupported_stop':0,'coverage_missing':0,'mean_cost':0,'mean_actual_coverage':0,'mean_items':0} for name in ('greedy','repair','observed_acquisition')}
        for index,(fam,p) in enumerate(cases):
            pred=predicted_problem(p,100000+index*23,noise)
            for name in ('greedy','repair','observed_acquisition'):
                g=greedy(pred)
                if name=='observed_acquisition':
                    sel,_=acquire_with_observation(p,pred)
                elif g is not None:
                    sel=g if name=='greedy' else repair(pred,g)[0]
                else:
                    sel=None
                if sel is not None:
                    truecoverage=len(p.required & covered(p,sel))/len(p.required)
                    complete=(p.required<=covered(p,sel))
                    cnt[name]['complete']+=int(complete)
                    cnt[name]['unsupported_stop']+=int(not complete)
                    cnt[name]['mean_actual_coverage']+=truecoverage
                    cnt[name]['mean_cost']+=cost(p,sel)
                    cnt[name]['mean_items']+=len(sel)
                else: cnt[name]['coverage_missing']+=1
                cnt[name]['n']+=1
        for a in cnt.values():
            a['mean_cost']=round(a['mean_cost']/a['n'],3)
            a['mean_items']=round(a['mean_items']/a['n'],3)
            a['mean_actual_coverage']=round(a['mean_actual_coverage']/a['n'],4)
        out['noise_stress'][str(noise)]=cnt
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--repetitions',type=int,default=100);a=parser.parse_args()
    t=time.perf_counter();result=benchmark(a.repetitions);result['elapsed_wall_s']=round(time.perf_counter()-t,3)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
