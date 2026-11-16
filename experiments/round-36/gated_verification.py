#!/usr/bin/env python3
"""Round 36, independently simulated candidate screening and costly verification.

Synthetic controlled diagnostic only. No language model, actual retrieval, or formal conformal guarantee.
"""
import argparse, json, math, random, statistics

N_CAL = 3000
N_TEST = 3000
SEED = 20261116


def instances(n, rng, shift=False):
    rows=[]
    for _ in range(n):
        # Query difficulty is correlated with error and cost; shifted OOD questions
        hard=rng.random() < (.70 if shift else .25)
        base=.44 if hard else .83
        correct=rng.random()<base
        # Two correlated noisy signals; when shifted they share a spuriously positive feature.
        latent=rng.gauss(0, .23 if not shift else .30)
        cheap=max(0.,min(1.,(.70 if correct else .30)+latent+rng.gauss(0,.16)+( .17 if shift and hard else 0)))
        deep=max(0.,min(1.,(.83 if correct else .17)+.55*latent+rng.gauss(0,.12)+(.21 if shift and hard else 0)))
        rows.append(dict(correct=correct,cheap=cheap,deep=deep,hard=hard))
    return rows


def choose_threshold(cal, target_fdr=.05):
    """Observed finite calibration selection, NOT distribution-free FDR bound."""
    candidates=[round(.50+i*.01,2) for i in range(50)]
    acceptable=[]
    for threshold in candidates:
        subset=[r for r in cal if r['deep']>=threshold]
        if len(subset)<40:continue
        bad=sum(not r['correct'] for r in subset)
        # Conservative Wilson upper confidence bound (z=1.96) at estimated level
        n=len(subset);p=bad/n;z=1.96
        upper=(p+z*z/(2*n)+z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/(1+z*z/n)
        if upper <= target_fdr:acceptable.append(threshold)
    return min(acceptable) if acceptable else 1.01


def evaluate(rows,threshold,gate=.50,cost=10,screen_cost=.3):
    out={}
    # All policies share the same sampled signals and decision labels.
    for policy in ('accept_all','deep_all','screen_then_deep','screen_only'):
        accepted=[];verifications=0;spend=0
        for r in rows:
            spend+=screen_cost if policy in ('screen_then_deep','screen_only') else 0
            if policy=='accept_all':allow=True
            elif policy=='screen_only':allow=r['cheap']>=gate
            elif policy=='deep_all':
                verifications+=1;spend+=cost
                allow=r['deep']>=threshold
            else:
                if r['cheap']<gate:allow=False
                else:
                    verifications+=1;spend+=cost
                    allow=r['deep']>=threshold
            if allow:accepted.append(r)
        false=sum(not r['correct'] for r in accepted)
        true=sum(r['correct'] for r in accepted)
        out[policy]={'accepted':len(accepted),'true_accepted':true,'false_accepted':false,
          'false_accept_fraction':round(false/max(1,len(accepted)),5),
          'correct_answer_coverage':round(true/len(rows),5),
          'abstention_fraction':round(1-len(accepted)/len(rows),5),
          'cost_per_query':round(spend/len(rows),5),'deep_verifications':verifications}
    return out


def simulate(seed=SEED):
    rng=random.Random(seed)
    train=instances(N_CAL,rng)
    test=instances(N_TEST,rng)
    shifted=instances(N_TEST,rng,shift=True)
    threshold=choose_threshold(train,.05)
    # Explicit resource and utility decision: gate is frozen, no tuning on shifted/test.
    configs={}
    for gate in (.35,.50,.65):
        configs[str(gate)]={'iid':evaluate(test,threshold,gate),'shifted':evaluate(shifted,threshold,gate)}
    return {'seed':seed,'calibration_n':len(train),'test_n':len(test),'shifted_n':len(shifted),
      'deep_threshold_selected_on_calibration':threshold,'gate_values':[.35,.50,.65],
      'target_observed_calibration_upper_risk':.05,
      'verifier_cost':10,'screen_cost':.3,'results':configs,
      'scope':'Entirely synthetic shared-noise verifier scores, not conformal coverage and not an evaluation of real RAG'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);o=p.parse_args()
    result=simulate();open(o.output,'w').write(json.dumps(result,indent=2)+'\n')
    print('threshold',result['deep_threshold_selected_on_calibration'])
    for g,v in result['results'].items():
        print('gate',g)
        for k,t in v.items():
            print(k,{p:{q:s for q,s in a.items() if q in ('false_accept_fraction','correct_answer_coverage','cost_per_query')} for p,a in t.items()})
if __name__=='__main__':main()
