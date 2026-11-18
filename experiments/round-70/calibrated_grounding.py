#!/usr/bin/env python3
"""R70: train-calibrated lexical grounding warning on unseen RAGTruth QA sources.

Frozen before evaluation: two unsupervised response novelty signals, per-source
train/test partition separation, 5% and 10% target training false-positive
rates. Source-group bootstrap, no raw source/response output. These are simple
lexical warning baselines, NOT claim entailment or safe-to-answer guarantees.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
RATES=(.05,.10)
SCORES=('max_sentence_novelty','fraction_novel_sentences')
BOOTSTRAP_SEED=7019
BOOTSTRAP_REPETITIONS=2000


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def confidence_scores(response,source,r69):
    dictionary=set(r69.content_words(source))
    sentence_novelty=[]
    for start,end,text in r69.fragments(response):
        terms=r69.content_words(text)
        if terms:
            novel=1-sum(tok in dictionary for tok in terms)/len(terms)
            sentence_novelty.append(novel)
    if not sentence_novelty:
        return {'max_sentence_novelty':0.0,'fraction_novel_sentences':0.0}
    return {
        'max_sentence_novelty':max(sentence_novelty),
        'fraction_novel_sentences':sum(x>.45 for x in sentence_novelty)/
                                   len(sentence_novelty),
    }


def choose_cutoff(negative_scores,target):
    """Lowest strict-risk cutoff with observed train false alarm <= target."""
    if not negative_scores or not 0<=target<=1:raise ValueError('invalid calibration')
    values=sorted(set(negative_scores))
    candidates=[min(values)-1e-9]+values
    feasible=[threshold for threshold in candidates if
              sum(x>threshold for x in negative_scores)/len(negative_scores)<=target+1e-12]
    if not feasible:raise AssertionError('no calibration threshold')
    threshold=min(feasible)
    observed=sum(x>threshold for x in negative_scores)/len(negative_scores)
    return threshold,observed


def score_counts(records,signal,threshold):
    c=Counter()
    for r in records:
        pred=r['scores'][signal]>threshold
        positive=r['gold']
        c['tp']+=int(pred and positive)
        c['fp']+=int(pred and not positive)
        c['fn']+=int(not pred and positive)
        c['tn']+=int(not pred and not positive)
    return {k:int(c[k]) for k in ('tp','fp','fn','tn')}


def metrics(c,r69):
    tp,fp,fn,tn=(c[k] for k in ('tp','fp','fn','tn'))
    result=r69.ratios(tp,fp,fn)
    result.update(c)
    result.update({
        'false_positive_rate':round(fp/(fp+tn),5) if fp+tn else None,
        'false_negative_rate':round(fn/(fn+tp),5) if fn+tp else None,
        'negative_predictive_value':round(tn/(tn+fn),5) if tn+fn else None,
        'warn_rate':round((tp+fp)/(tp+fp+fn+tn),5) if tp+fp+fn+tn else None,
    })
    return result


def grouped_bootstrap(records,signal,threshold,reps=BOOTSTRAP_REPETITIONS,
                      seed=BOOTSTRAP_SEED):
    groups=defaultdict(list)
    for row in records:groups[row['source_id']].append(row)
    names=sorted(groups)
    if len(names)<2:
        return None
    rng=random.Random(seed)
    # Group bootstrap respects the fact that all six generated responses
    # share one source and are not independent human annotation units.
    vals=[]
    for _ in range(reps):
        sample=[row for _ in names
                for row in groups[names[rng.randrange(len(names))]]]
        counts=score_counts(sample,signal,threshold)
        tp,fp,fn,tn=(counts[x] for x in ('tp','fp','fn','tn'))
        recall=tp/(tp+fn) if tp+fn else 0
        fpr=fp/(fp+tn) if fp+tn else 0
        vals.append((recall,fpr))
    result={}
    for j,key in enumerate(('recall','false_positive_rate')):
        ordered=sorted(item[j] for item in vals)
        result[key+'_group_bootstrap_95pct']=[
            round(ordered[int(.025*(reps-1))],5),
            round(ordered[int(.975*(reps-1))],5)]
    return result


def split_sources(responses,sources,r69,previous_count=None):
    source_map={str(row['source_id']):row for row in sources}
    test_sources={str(r['source_id']) for r in responses
                  if r.get('split')=='test'
                  and str(r.get('source_id')) in source_map
                  and source_map[str(r['source_id'])].get('task_type')=='QA'}
    ordered=sorted(test_sources,key=lambda sid:(
        hashlib.sha256((r69.SAMPLE_SALT+'|'+sid).encode()).hexdigest(),sid))
    boundary=r69.MAX_TEST_SOURCE_GROUPS if previous_count is None else previous_count
    if not 0<boundary<len(ordered):
        raise ValueError('no disjoint source-group confirmation set')
    old=set(ordered[:boundary])
    holdout=set(ordered[boundary:])
    assert not old.intersection(holdout)
    return source_map,old,holdout


def rows_for_split(responses,source_map,allowed,split,r69):
    results=[]
    for row in responses:
        sid=str(row.get('source_id'))
        if row.get('split')!=split or sid not in allowed:
            continue
        if row.get('quality')!='good':
            continue
        source=r69.source_text(source_map[sid])
        full,risk,faults=r69.annotated_masks(row)
        if faults:raise ValueError('human annotation offsets invalid')
        text=row['response']
        results.append({
            'source_id':sid,
            'gold':int(any(full)),
            'strict_gold':int(any(risk)),
            'scores':confidence_scores(text,source,r69),
        })
    return results


def evaluate(responses,sources,previous_count=None):
    r69=load('cdg69_for70',R69)
    source_map,old,heldout=split_sources(responses,sources,r69,previous_count)
    train_source_ids={str(row['source_id']) for row in responses
                      if row.get('split')=='train'
                      and str(row.get('source_id')) in source_map
                      and source_map[str(row['source_id'])].get('task_type')=='QA'}
    leakage=train_source_ids.intersection(heldout)
    # Group-level isolation is mandatory. If upstream split is not
    # source-exclusive, discard any overlapping source IDs from calibration.
    train_source_ids-=heldout
    training=rows_for_split(responses,source_map,train_source_ids,'train',r69)
    test=rows_for_split(responses,source_map,heldout,'test',r69)
    if len(training)<100 or len(test)<20:
        raise ValueError('insufficient independent train/test quality-good QA examples')
    if not any(r['gold'] for r in test):
        raise ValueError('no human-positive examples in untouched holdout')
    results={}
    for signal in SCORES:
        neg=[x['scores'][signal] for x in training if not x['gold']]
        if not neg:raise ValueError('no train negative examples')
        for target in RATES:
            threshold,train_fpr=choose_cutoff(neg,target)
            label=f'{signal}@train_FPR_{target}'
            c=score_counts(test,signal,threshold)
            results[label]={
                'score':signal,
                'target_train_FPR':target,
                'chosen_strict_greater_than_threshold':round(threshold,7),
                'observed_train_FPR':round(train_fpr,5),
                'holdout':metrics(c,r69),
                'holdout_group_uncertainty':grouped_bootstrap(test,signal,threshold),
                'strict_implicit_true_excluded':metrics(
                    score_counts([{**r,'gold':r['strict_gold']} for r in test],
                                 signal,threshold),r69),
            }
    # Untuned R69 .55 content overlap is same as risk > .45 at sentence level.
    anchor=score_counts(test,'max_sentence_novelty',.45)
    results['frozen_round69_overlap_0.55']={
        'score':'max_sentence_novelty',
        'chosen_strict_greater_than_threshold':.45,
        'holdout':metrics(anchor,r69),
        'holdout_group_uncertainty':grouped_bootstrap(
            test,'max_sentence_novelty',.45)}
    return {
        'train_good_qa_responses':len(training),
        'train_unique_source_groups':len({x['source_id'] for x in training}),
        'holdout_good_qa_responses':len(test),
        'holdout_unique_source_groups':len(heldout),
        'holdout_human_labeled_responses':sum(x['gold'] for x in test),
        'holdout_human_strict_labeled_responses':sum(x['strict_gold'] for x in test),
        'train_test_source_id_overlap_dropped':len(leakage),
        'old_R69_source_ids_excluded':len(old),
        'holdout_source_id_hash':hashlib.sha256(
            '\n'.join(sorted(heldout)).encode()).hexdigest(),
        'results':results,
        'limitations':[
            'thresholds calibrated on RAGTruth QA train human negatives, then applied to previously unused QA test source groups',
            'R69 test split was already inspected for 128/150 source groups; this uses remaining 22 groups only, not a new corpus family',
            'same corpus generation models and annotation guidelines, no independent deployment validation',
            'small grouped test sample leads to wide uncertainty and zero-support edge cases',
            'false-positive control is empirical training behavior, not a statistical population guarantee',
            'quality != good excluded only for calibration and confirmation; earlier R69 full QA sample included 24 non-good responses',
            'calibrated lexical warnings are not semantic entailment or generative mitigation',
            'source bytes and human labels not redistributed, just aggregate confusion and hashes',
        ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=load('r69_r70_loader',R69)
    response,res_prov=r69.download('dataset/response.jsonl')
    source,src_prov=r69.download('dataset/source_info.jsonl')
    result=evaluate(response,source)
    result['source_provenance']={
        'revision':r69.REVISION,
        'response_git_blob':res_prov['git_blob'],
        'source_git_blob':src_prov['git_blob']}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND70',json.dumps({
        'n_test':result['holdout_good_qa_responses'],
        'n_train':result['train_good_qa_responses'],
        'test_groups':result['holdout_unique_source_groups'],
        'human_pos':result['holdout_human_labeled_responses'],
        'results':result['results']},sort_keys=True))


if __name__=='__main__':
    main()
