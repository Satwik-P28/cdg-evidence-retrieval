#!/usr/bin/env python3
"""Round 21: fully synthetic non-oracle graph edge predictor under distribution shift.
This is NOT a real QA/RAG evaluation. Inference uses noisy observed edge features only,
never the hidden true pairing. The noise model is explicit and reproducible.
"""
import json
import numpy as np

MATCHINGS=np.array([[[0,1],[2,3]],[[0,2],[1,3]],[[0,3],[1,2]]],dtype=np.int16)
EDGES=np.array([[0,1],[2,3],[0,2],[1,3],[0,3],[1,2]],dtype=np.int16)

def trial(n, mu, seed, model_mu=None, overhead=0.08):
    rng=np.random.default_rng(seed)
    true=rng.integers(0,3,size=n)
    rel=rng.random((n,4))
    # Features represent a learned but imperfect observable edge-coherence signal.
    signal=rng.normal(0,1,(n,6))
    signal[np.arange(n),2*true]+=mu
    signal[np.arange(n),2*true+1]+=mu
    model_mu=mu if model_mu is None else model_mu
    # Log posterior from known likelihood model. No gold pairing at inference.
    logit=model_mu*(signal[:,::2]+signal[:,1::2]) - model_mu**2
    logit-=logit.max(axis=1,keepdims=True)
    probs=np.exp(logit); probs/=probs.sum(axis=1,keepdims=True)
    predicted=probs.argmax(axis=1)
    confidence=probs[np.arange(n),predicted]
    top2=np.argsort(-rel,axis=1)[:,:2]
    true_pair=np.sort(MATCHINGS[true],axis=2)
    baseline=np.any(np.all(np.sort(top2,axis=1)[:,None,:]==true_pair,axis=2),axis=1)
    pred_pairs=MATCHINGS[predicted]
    pair_scores=np.take_along_axis(rel,pred_pairs[:,:,0],axis=1)+np.take_along_axis(rel,pred_pairs[:,:,1],axis=1)
    pick=pair_scores.argmax(axis=1)
    chosen=pred_pairs[np.arange(n),pick]
    graph=np.any(np.all(np.sort(chosen,axis=1)[:,None,:]==true_pair,axis=2),axis=1)
    # Additional graph inference/validation incurs fixed overhead, utility units
    # equal to one correct evidence set. Graph is used only if its predicted
    # correctness advantage clears that charge relative to 1/3 baseline.
    use=(confidence-1/3)>overhead
    gated=np.where(use,graph,baseline)
    return dict(n=n,mu=mu,model_mu=model_mu,overhead=overhead,
        independent_success=round(float(baseline.mean()),5),
        graph_success=round(float(graph.mean()),5),
        graph_net_utility=round(float(graph.mean()-overhead),5),
        gated_success=round(float(gated.mean()),5),
        gated_net_utility=round(float(gated.mean()-overhead*use.mean()),5),
        gating_fraction=round(float(use.mean()),5),
        estimated_graph_probability=round(float(confidence.mean()),5),
        pairing_accuracy=round(float((predicted==true).mean()),5))

def main():
    results={
     'protocol':'round21-synthetic-noisy-matching-v1',
     'description':'Four candidates; hidden one of three perfect pairings; two alternative 2-part witnesses; six noisy edge observations. Non-oracle at inference. Fixed budget two fragments.',
     'n_per_condition':60000,'seed':20261112,
     'conditions':[trial(60000,mu,20261112+i) for i,mu in enumerate([0,.25,.5,.75,1,1.5,2])],
     'shift':[trial(60000,mu,20261112+50+i,model_mu=1.0) for i,mu in enumerate([0,.25,.5,1,1.5,2])],
     'limitations':['Synthetic edge observations generated from hidden truth. No learned natural language entailment, no real corpus, no actual byte I/O.','The inference model knows the noise family and assumed signal strength.','Overhead is a hypothetical utility charge, not measured latency or monetary cost.']
    }
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
