#!/usr/bin/env python3
"""R85: original expert-labeled SciFact source documents, three evidence routes.

Fixed prior-art checkpoints from CDG R80: MiniCheck, FactCG, general NLI,
LettuceDetect. Train-only threshold calibration and source-disjoint SciFact
dev evaluation. The rationale-only route uses *gold evidence sentence IDs*
and is an oracle upper-bound input, not an available retrieval policy.
Full-corpus TF-IDF retrieval cost and evidence recall are measured separately.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import gc
import hashlib
import json
import math
import pickle
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-80'))
from controlled_facts import load_pinned_model,load as load_module
from factcg_control import FACTCG_ID,FACTCG_SHA,prompt as factcg_prompt
from scifact_data import load_release,select_pairs

R72=HERE.parent/'round-72'/'zero_shot_nli.py'
R76=HERE.parent/'round-76'/'lettuce_reference.py'
R80=HERE.parent/'round-80'/'controlled_facts.py'
MINICHECK_ID='lytang/MiniCheck-DeBERTa-v3-Large'
MINICHECK_SHA='05782341a53df45bf7bee868863563907e083ee0'
RAGTRUTH_DETECTOR_ID='KRLabsOrg/lettucedect-base-modernbert-en-v1'
COHORT_SHA='735fd797de6258eb0b667d5d789e76f341eb1abefdca284647d638974a5184df'
ROUTES=('full','lexical2','oracle_rationale')
MODELS=('nli','minicheck','factcg','lettuce')
TRAIN_FPR_TARGETS=(0.10,0.25)
BOOTSTRAP_REPS=600
SEED=8359


def content_terms(text):
    return re.findall(r"[a-z0-9]+",text.lower())


def best_lexical_two(case):
    """Source-only claim-overlap ranking; no rationale IDs or gold labels."""
    source=case['sentences']
    query=set(content_terms(case['claim']))
    ranked=sorted(range(len(source)),key=lambda i:(
        -len(query.intersection(content_terms(source[i]))),
        -sum(t in query for t in content_terms(source[i])),i))
    indices=sorted(ranked[:2])
    return indices


def input_text(case,route):
    header='Title: '+case['title']+'\nAbstract: '
    if route=='full':
        return case['doc']
    if route=='lexical2':
        return header+' '.join(case['sentences'][i] for i in best_lexical_two(case))
    if route=='oracle_rationale':
        return header+case['rationale']
    raise ValueError("unknown evidence route")


def build_inputs(train,dev):
    examples=[]
    for split,cases in (('train',train),('dev',dev)):
        for case in cases:
            for route in ROUTES:
                text=input_text(case,route)
                if not text or not case['claim']:
                    raise AssertionError('empty model input')
                examples.append({
                    'key':case['key'],'split':split,'route':route,
                    'gold':int(case['gold']),'claim_id':case['claim_id'],
                    'doc_id':case['doc_id'],'doc':text,
                    'claim':case['claim'],
                    'model_input_bytes':len(text.encode('utf8')),
                    'passage_count':1 if route!='lexical2' else min(2,len(case['sentences'])),
                })
    if len(examples)!=(len(train)+len(dev))*len(ROUTES):
        raise AssertionError('route expansion mismatch')
    return examples


def inference_classifier(name,examples):
    import torch
    if name=='nli':
        r72=load_module('r72_scifact83',R72)
        lock=json.loads(r72.MODEL_LOCK.read_text())
        model_id=r72.MODEL_ID
        revision=lock['revision']
    elif name=='minicheck':
        model_id=MINICHECK_ID
        revision=MINICHECK_SHA
    elif name=='factcg':
        model_id=FACTCG_ID
        revision=FACTCG_SHA
    else:
        raise ValueError('invalid checker')
    tokenizer,model,torch,params=load_pinned_model(model_id,revision)
    if name=='nli':
        labels={str(v).lower():int(k) for k,v in model.config.id2label.items()}
        positive_idx=labels['entailment']
        max_length=384
    else:
        positive_idx=1
        max_length=2048
    pairs=[];lens=[];cutoff=0
    t0=time.perf_counter()
    for batch_start in range(0,len(examples),8):
        subset=examples[batch_start:batch_start+8]
        docs=[x['doc'] for x in subset]
        claims=[x['claim'] for x in subset]
        if name=='nli':
            raw=tokenizer(docs,claims,max_length=max_length,
                          truncation='only_first',padding=True,
                          return_tensors='pt')
            unclipped_lengths=[len(tokenizer.encode(
                d,c,add_special_tokens=True,truncation=False))
                for d,c in zip(docs,claims)]
        elif name=='minicheck':
            if not tokenizer.eos_token:
                raise AssertionError('MiniCheck EOS missing')
            texts=[d+tokenizer.eos_token+c for d,c in zip(docs,claims)]
            unclipped_lengths=[len(tokenizer.encode(t,add_special_tokens=True))
                                for t in texts]
            raw=tokenizer(texts,max_length=max_length,
                          truncation=True,padding=True,return_tensors='pt')
        else:
            tokenizer.pad_token=tokenizer.eos_token
            if not tokenizer.pad_token:
                raise AssertionError('FactCG EOS pad missing')
            texts=[factcg_prompt(d,c) for d,c in zip(docs,claims)]
            unclipped_lengths=[len(tokenizer.encode(t,add_special_tokens=True))
                                for t in texts]
            raw=tokenizer(texts,max_length=max_length,
                          truncation='only_first',padding='longest',
                          return_tensors='pt')
        cutoff+=sum(n>max_length for n in unclipped_lengths)
        lens.extend(int(x) for x in raw['attention_mask'].sum(dim=1).tolist())
        with torch.inference_mode():
            probabilities=torch.softmax(model(**raw).logits,dim=-1)[:,positive_idx].tolist()
        pairs.extend(float(x) for x in probabilities)
    wall=time.perf_counter()-t0
    meta={
        'model_id':model_id,'model_revision':revision,
        'parameters':params,'route_model_pairs':len(examples),
        'unpadded_actual_input_tokens':sum(lens),
        'unclipped_input_count_exceeding_model_limit':cutoff,
        'maximum_model_input_tokens':max_length,
        'scoring_plus_tokenization_seconds':round(wall,3),
        'classification':'P(supported) from released pretrained weights',
        'reproduction':'authors single short-doc chunk input with model-native tokenizer',
    }
    del model,tokenizer
    gc.collect()
    return pairs,meta


def inference_lettuce(examples):
    r76=load_module('r76_scifact83',R76)
    detector,info=r76.make_detector()
    out=[];elapsed=0
    t0=time.perf_counter()
    for row in examples:
        mask,detail=r76.audited_prediction(
            detector,[row['doc']],row['claim'],None)
        elapsed+=detail['elapsed_wall_sec']
        out.append(float(int(not any(mask))))
    meta={
        'model_id':RAGTRUTH_DETECTOR_ID,
        'model_revision':info['snapshot_sha'],
        'parameters':info['model_parameters'],
        'route_model_pairs':len(examples),
        'forward_wall_seconds':round(elapsed,3),
        'scoring_plus_tokenization_seconds':round(time.perf_counter()-t0,3),
        'classification':'1 if no predicted unsupported claim character else 0',
        'limitation':'LettuceDetect trained on RAGTruth and designed to detect answer spans, not SciFact entailment',
    }
    del detector
    gc.collect()
    return out,meta


def confusion(y_true,y_score,threshold):
    if len(y_true)!=len(y_score) or not y_true:
        raise ValueError('invalid label/score alignment')
    preds=[int(v>threshold) for v in y_score]
    tp=sum(int(g==1 and p==1) for g,p in zip(y_true,preds))
    fp=sum(int(g==0 and p==1) for g,p in zip(y_true,preds))
    fn=sum(int(g==1 and p==0) for g,p in zip(y_true,preds))
    tn=sum(int(g==0 and p==0) for g,p in zip(y_true,preds))
    rec=tp/(tp+fn) if (tp+fn) else 0.0
    spec=tn/(tn+fp) if (tn+fp) else 0.0
    precision=tp/(tp+fp) if (tp+fp) else 0.0
    f1=(2*precision*rec/(precision+rec)) if precision+rec else 0
    return {
        'n':len(y_true),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
        'balanced_accuracy':round((rec+spec)/2,5),
        'support_recall':round(rec,5),
        'contradiction_rejection':round(spec,5),
        'f1':round(f1,5),
        'accuracy':round((tp+tn)/len(y_true),5),
    }


def train_threshold(y_true,score,target_fpr):
    """Select threshold on calibration split only, no dev score/label inspection.

    Minimize threshold subject to empirical train FPR <= target, which
    maximizes train positive recall (up to score ties). No deployment
    guarantee for the nominal FPR target under task/source drift.
    """
    if len(y_true)!=len(score) or not y_true:
        raise ValueError('invalid calibration')
    negs=[p for y,p in zip(y_true,score) if y==0]
    if len(negs)<10:
        raise ValueError('insufficient human-negative calibration examples')
    candidates=sorted(set([-1e-9,*score,1.0]))
    compatible=[t for t in candidates
                if sum(p>t for p in negs)/len(negs)<=target_fpr+1e-12]
    return min(compatible) if compatible else 1.0


def auroc(y_true,scores):
    positives=[v for y,v in zip(y_true,scores) if y==1]
    negatives=[v for y,v in zip(y_true,scores) if y==0]
    if not positives or not negatives:
        return None
    return round(sum(int(a>b)+0.5*int(a==b)
                     for a in positives for b in negatives)/
                 (len(positives)*len(negatives)),6)


def evaluate(examples,scores):
    if len(examples)!=len(scores):
        raise AssertionError('score alignment')
    keyed={(x['split'],x['route']):[] for x in examples}
    for row,score in zip(examples,scores):
        keyed[row['split'],row['route']].append((row,float(score)))
    result={}
    for route in ROUTES:
        train=keyed['train',route]
        test=keyed['dev',route]
        tr_gold=[r['gold'] for r,_ in train]
        te_gold=[r['gold'] for r,_ in test]
        tr_prob=[p for _,p in train]
        te_prob=[p for _,p in test]
        if not train or not test:
            raise AssertionError('empty SciFact split')
        policies={'fixed_0_5':0.5}
        for target in TRAIN_FPR_TARGETS:
            policies[f'train_fpr_{target:.2f}']=train_threshold(tr_gold,tr_prob,target)
        result[route]={
            'train_size':len(train),'dev_size':len(test),
            'train_auroc':auroc(tr_gold,tr_prob),
            'dev_auroc':auroc(te_gold,te_prob),
            'threshold_policies':{
                name:{
                    'threshold_selected_on_train_only':round(float(t),8),
                    'train':confusion(tr_gold,tr_prob,t),
                    'dev':confusion(te_gold,te_prob,t),
                } for name,t in policies.items()},
            'dev_scores_by_key':{r['key']:p for r,p in test},
        }
    return result


def bootstrap_delta(examples,evaluation,policy='fixed_0_5',
                    alternative='lexical2',baseline='full'):
    """Paired claim group bootstrap over dev, not 64 independent draws."""
    byroute={}
    for route in (baseline,alternative):
        chosen=[x for x in examples if x['split']=='dev' and x['route']==route]
        scores=evaluation[route]['dev_scores_by_key']
        threshold=evaluation[route]['threshold_policies'][policy][
            'threshold_selected_on_train_only']
        byroute[route]={x['key']:(x['claim_id'],x['gold'],int(scores[x['key']]>threshold))
                        for x in chosen}
    keys=sorted(byroute[baseline])
    if set(keys)!=set(byroute[alternative]):
        raise AssertionError('missing paired case in context comparison')
    groups=defaultdict(list)
    for key in keys:
        cid,label,_=byroute[baseline][key]
        if (cid,label)!=(byroute[alternative][key][:2]):
            raise AssertionError('labels changed between routes')
        groups[cid].append(key)
    unique_groups=sorted(groups)
    def ba(selected_keys,route):
        g=[byroute[route][k][1] for k in selected_keys]
        p=[byroute[route][k][2] for k in selected_keys]
        if not any(g) or all(g):
            return None
        rec=sum(y and x for y,x in zip(g,p))/sum(g)
        spec=sum((not y) and (not x) for y,x in zip(g,p))/(len(g)-sum(g))
        return (rec+spec)/2
    rng=random.Random(SEED)
    differences=[]
    for _ in range(BOOTSTRAP_REPS):
        sample=[k for _ in unique_groups
                for k in groups[unique_groups[rng.randrange(len(unique_groups))]]]
        first=ba(sample,baseline)
        second=ba(sample,alternative)
        if first is not None and second is not None:
            differences.append(second-first)
    if len(differences)<BOOTSTRAP_REPS*.95:
        raise AssertionError('too many degenerate grouped bootstrap resamples')
    differences.sort()
    lo=differences[round(.025*(len(differences)-1))]
    hi=differences[round(.975*(len(differences)-1))]
    observed=ba(keys,alternative)-ba(keys,baseline)
    return {
        'delta_balanced_accuracy_alternative_minus_full':round(observed,5),
        'claim_group_bootstrap_95ci':[round(lo,5),round(hi,5)],
        'bootstrap_iterations_valid':len(differences),
        'distinct_dev_claim_groups':len(unique_groups),
    }


def retrieval_profile(dev,corpus):
    """Independent corpus-wide TF-IDF/word-matching retrieval.

    GOLD evidence doc IDs never enter vectorizer, query or index construction.
    Gold IDs are read AFTER ranking solely to compute evidence recall.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np
    ids=sorted(corpus)
    docs=['Title: '+str(corpus[i].get('title') or '')+' Abstract: '+
          ' '.join(corpus[i].get('abstract') or []) for i in ids]
    t0=time.perf_counter()
    vectorizer=TfidfVectorizer(lowercase=True,strip_accents='unicode',
                               stop_words='english',norm='l2',max_features=60000)
    matrix=vectorizer.fit_transform(docs)
    index_seconds=time.perf_counter()-t0
    q=vectorizer.transform([x['claim'] for x in dev])
    t1=time.perf_counter()
    scores=(q@matrix.T).toarray()
    query_seconds=time.perf_counter()-t1
    order=[]
    for j,case in enumerate(dev):
        # Negative score, then ascending corpus index for deterministic ties.
        ranked=np.lexsort((np.arange(len(ids)), -scores[j]))
        if ids[int(ranked[0])] not in corpus:
            raise AssertionError('retrieval ID missing')
        order.append([ids[int(k)] for k in ranked[:10]])
    target=[x['doc_id'] for x in dev]
    return {
        'retriever':'Scikit-learn TF-IDF l2 cosine unigrams, English stop words, 60k vocabulary cap',
        'corpus_size':len(ids),
        'evaluation_queries':len(dev),
        'gold_id_recall_at_k':{
            str(k):round(sum(t in rank[:k] for t,rank in zip(target,order))/len(dev),5)
            for k in (1,3,5,10)},
        'calibration_or_dev_gold_used_in_index_or_query':False,
        'index_construction_seconds':round(index_seconds,3),
        'query_matrix_multiplication_seconds':round(query_seconds,3),
        'estimated_serialized_pickle_index_bytes':len(pickle.dumps(
            (vectorizer,matrix,ids),protocol=pickle.HIGHEST_PROTOCOL)),
        'original_sources_retrieved_at1':[int(t==rank[0]) for t,rank in zip(target,order)],
        'caution':'Gold-evidence recall, not answer correctness; an unannotated retrieved doc is NOT automatically a negative label',
    }


def run(models=MODELS):
    files,src=load_release()
    train,dev,corpus,cohort=select_pairs(files)
    if cohort['selected_key_sha256']!=COHORT_SHA:
        raise AssertionError('frozen human SciFact case membership drifted')
    examples=build_inputs(train,dev)
    baseline_retrieval=retrieval_profile(dev,corpus)
    results={}
    for name in models:
        if name=='lettuce':
            scores,meta=inference_lettuce(examples)
        else:
            scores,meta=inference_classifier(name,examples)
        evaluation=evaluate(examples,scores)
        # Every model route evaluated at fixed0.5 AND calibration-only FPR.
        uncertainty={}
        for pol in ('fixed_0_5','train_fpr_0.10','train_fpr_0.25'):
            uncertainty[pol]={
              x:bootstrap_delta(examples,evaluation,policy=pol,alternative=x)
              for x in ('lexical2','oracle_rationale')}
        # Strip even derived per-case probabilities from published artifacts;
        # avoid disclosing data reconstructable to copyrighted source text.
        for route in ROUTES:
            del evaluation[route]['dev_scores_by_key']
        results[name]={
            'resource_cost':meta,'evaluation':evaluation,
            'paired_source_selection_uncertainty':uncertainty,
        }
        print('R85_METHOD',json.dumps({
            'name':name,
            'dev_fixed':{route:evaluation[route]['threshold_policies']['fixed_0_5']['dev']
                         for route in ROUTES},
            'dev_train_fpr10':{route:evaluation[route]['threshold_policies']['train_fpr_0.10']['dev']
                               for route in ROUTES},
            'resource_cost':meta,
        },sort_keys=True),flush=True)
    return {
        'source':src,
        'selected_cohort':cohort,
        'models':results,
        'full_corpus_retrieval':baseline_retrieval,
        'model_pairs_per_method':len(examples),
        'source_routes':list(ROUTES),
        'limitations':[
            'The R83 dev evaluation is a frozen source-disjoint portion of the official SciFact development split, not a never-published model benchmark or hidden-test result',
            'Labels annotate support or contradiction for a gold abstract; there is NO unknown-source accuracy label here',
            'Gold rationale sentence IDs select oracle_rationale; this is an upper-bound input control, not deployment evidence selection',
            'Gold doc ID is oracle supplied for model comparisons, while TF-IDF independent retrieval has separately measured gold ID recall',
            'Dev stratification is balanced by existing annotations; prevalence-dependent accuracy differs from natural deployment',
            'Training-only thresholds can still overfit 64 calibration examples; empirical train FPR is not a formal guarantee of dev FPR',
            'Use of SciFact in published checker training cannot be excluded, so no claims of external independence of pretrained weight training',
            'MiniCheck and FactCG single-chunk approximations preserve official short-doc input formatting but omit full multi-chunk aggregation',
            'NLI token cap 384 may truncate long abstracts; tokenizer truncation counts reported',
            'LettuceDetect is trained for unsupported answer span detection and its claim-as-answer mode is an adaptation',
            'Source retrieval TF-IDF is a basic lexical baseline, not BM25 or dense retrieval, nor an end-to-end answer quality measure',
            'No claim generation, source citation support effect, physical SSD cold reads, index mutation, source update or production model serving',
            'S2ORC abstracts remain with original copyright holder; CI logs/artifacts persist only aggregate metrics',
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(HERE/'ci-results.json'))
    ap.add_argument('--model',choices=(*MODELS,'all'),default='all')
    args=ap.parse_args()
    out=run(MODELS if args.model=='all' else (args.model,))
    Path(args.out).write_text(json.dumps(out,indent=2)+'\n')
    print('ROUND85',json.dumps({
        'source_sha256':out['source']['archive_sha256'],
        'cohort_sha256':out['selected_cohort']['selected_key_sha256'],
        'retrieval':{k:v for k,v in out['full_corpus_retrieval'].items()
                     if k in ('gold_id_recall_at_k','corpus_size','estimated_serialized_pickle_index_bytes')},
        'main_fixed_dev':{
            n:{r:values['evaluation'][r]['threshold_policies']['fixed_0_5']['dev']['balanced_accuracy']
               for r in ROUTES} for n,values in out['models'].items()},
    },sort_keys=True))


if __name__=='__main__':
    main()
