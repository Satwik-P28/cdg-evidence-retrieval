#!/usr/bin/env python3
"""R74: train-only NLI warning calibration, cross-task transfer to Data2txt.

R72's frozen generic SNLI/MultiNLI model and evidence-window selector are
unchanged. Thresholds are fitted on QA *train* human-negative responses only,
then evaluated on a disjoint official Data2txt *test* source family. Neither
test labels nor model-generated outcomes enter train threshold selection.

This is a classical selective-threshold experiment. It is not a semantic
entailment guarantee, model fine-tuning, source-citation proof, or a novel
calibration algorithm.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R70=HERE.parent/'round-70'/'calibrated_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
SALT='CDG-R74-QA-TRAIN-D2T-TEST-SHA-LOCK-v1'
TRAIN_QA_SOURCE_GROUPS=32
TEST_D2T_SOURCE_GROUPS=16
TARGET_TRAIN_FPRS=(.10,.25)
RISK_SCORES=('top1_max','top3_max','top3_mean')
BOOTSTRAP_SEED=7417
BOOTSTRAP_REPS=1500


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def partition(responses,sources):
    byid={str(x['source_id']):x for x in sources}
    if len(byid)!=len(sources):
        raise ValueError('duplicate source IDs')
    candidates={
        'train':set(),'test':set(),
    }
    for row in responses:
        sid=str(row.get('source_id'))
        if sid not in byid or row.get('quality')!='good':
            continue
        task=byid[sid].get('task_type')
        if row.get('split')=='train' and task=='QA':
            candidates['train'].add(sid)
        elif row.get('split')=='test' and task=='Data2txt':
            candidates['test'].add(sid)
    selected={}
    for tag,count in (('train',TRAIN_QA_SOURCE_GROUPS),
                      ('test',TEST_D2T_SOURCE_GROUPS)):
        ranked=sorted(candidates[tag],key=lambda sid:(
            hashlib.sha256((SALT+'|'+tag+'|'+sid).encode()).hexdigest(),sid))
        if len(ranked)<count:
            raise ValueError(f'insufficient {tag} source groups')
        selected[tag]=set(ranked[:count])
    if selected['train']&selected['test']:
        raise AssertionError('source identifier leakage between QA train and Data2txt test')
    train=[x for x in responses
           if x.get('split')=='train' and x.get('quality')=='good' and
           str(x.get('source_id')) in selected['train']]
    test=[x for x in responses
          if x.get('split')=='test' and x.get('quality')=='good' and
          str(x.get('source_id')) in selected['test']]
    if len(train)<60 or len(test)<30:
        raise ValueError('too few source-distinct input responses')
    result={
        tag:{
            'source_groups':len(values),
            'sample_source_ids_sha256':hashlib.sha256(
                '\n'.join(sorted(values)).encode()).hexdigest(),
            'responses':len(train if tag=='train' else test),
            'available_source_groups':len(candidates[tag])
        }
        for tag,values in selected.items()
    }
    return train,test,byid,result


def response_risks(cases,probs):
    """Aggregate fixed R72 NLI scores at response level, WITHOUT annotations."""
    groups={}
    for case in cases:
        key=case['response_id']
        item=groups.setdefault(key,{
            'response_id':key,
            'source_id':case['source_group'],
            'task':case['task'],
            'human_positive':False,
            'strict_human_positive':False,
            'lexical_warning':False,
            'top1_values':[],'top3_values':[],
            'sentence_count':0,
        })
        if item['source_id']!=case['source_group']:
            raise AssertionError('response IDs collide across source groups')
        item['human_positive']|=bool(case['gold'])
        item['strict_human_positive']|=bool(case['strict_gold'])
        item['lexical_warning']|=bool(case['literal_warning'])
        best_one=probs[case['pair_indices']['nli_lexical_top1'][0]]
        best_three=max(probs[i] for i in case['pair_indices']['nli_lexical_top3'])
        if not (math.isfinite(best_one) and math.isfinite(best_three)):
            raise ValueError('nonfinite model score')
        item['top1_values'].append(1-best_one)
        item['top3_values'].append(1-best_three)
        item['sentence_count']+=1
    finalized=[]
    for row in groups.values():
        if not row['top1_values']:
            raise AssertionError('missing response case')
        finalized.append({
            'response_id':row['response_id'],'source_id':row['source_id'],
            'task':row['task'],
            'human_positive':row['human_positive'],
            'strict_human_positive':row['strict_human_positive'],
            'lexical_warning':row['lexical_warning'],
            'sentence_count':row['sentence_count'],
            'scores':{
                'top1_max':max(row['top1_values']),
                'top3_max':max(row['top3_values']),
                'top3_mean':statistics.mean(row['top3_values']),
            }
        })
    return finalized


def choose_cutoff(negative_risks,target):
    if not negative_risks or not 0<=target<=1:
        raise ValueError('invalid calibration distribution or risk')
    values=sorted(set(negative_risks))
    # Use strict greater-than threshold consistently at test time.
    feasible=[x for x in values if sum(v>x for v in negative_risks)/
              len(negative_risks)<=target+1e-12]
    if not feasible:
        raise AssertionError('cannot choose empirical FPR cutoff')
    threshold=min(feasible)
    empirical=sum(x>threshold for x in negative_risks)/len(negative_risks)
    return threshold,empirical


def confusion(rows,signal,threshold,strict=False):
    tp=fp=fn=tn=0
    for row in rows:
        truth=row['strict_human_positive'] if strict else row['human_positive']
        warn=row['lexical_warning'] if signal=='lexical_fixed' else (
            row['scores'][signal]>threshold)
        tp+=int(warn and truth)
        fp+=int(warn and not truth)
        fn+=int(not warn and truth)
        tn+=int(not warn and not truth)
    recall=tp/(tp+fn) if tp+fn else 0
    precision=tp/(tp+fp) if tp+fp else 0
    return {
        'n':tp+fp+fn+tn,
        'tp':tp,'fp':fp,'fn':fn,'tn':tn,
        'precision':round(precision,5),'recall':round(recall,5),
        'false_positive_rate':round(fp/(fp+tn),5) if fp+tn else 0,
        'f1':round(2*precision*recall/(precision+recall),5)
             if precision+recall else 0,
    }


def clustered_interval(rows,signal,threshold,reps=BOOTSTRAP_REPS,
                       seed=BOOTSTRAP_SEED):
    byid=defaultdict(list)
    for row in rows:byid[row['source_id']].append(row)
    ids=sorted(byid)
    if len(ids)<2:return None
    rng=random.Random(seed)
    values={'recall':[],'false_positive_rate':[],'f1':[]}
    for _ in range(reps):
        sampled=[row for _ in ids for row in byid[ids[rng.randrange(len(ids))]]]
        out=confusion(sampled,signal,threshold)
        for key in values:values[key].append(out[key])
    result={}
    for key,dist in values.items():
        dist.sort()
        result[key+'_source_group_bootstrap_95ci']=[
            dist[int(.025*(reps-1))],dist[int(.975*(reps-1))]]
    return result


def evaluate(responses,sources):
    r69=load('cdg69_for74',R69)
    r72=load('cdg72_for74',R72)
    train,test,byid,parts=partition(responses,sources)
    joint=train+test
    cases,pairs,costs=r72.compile_cases(joint,byid,r69)
    model_lock=json.loads(r72.MODEL_LOCK.read_text())
    if model_lock['name']!=r72.MODEL_ID:
        raise ValueError('pretrained model lock mismatch')
    model,tok,torch,entail,labels,load_seconds=r72.load_model_and_tokenizer(
        model_lock)
    probs,model_cost=r72.infer_pairs(pairs,model,tok,torch,entail)
    response= response_risks(cases,probs)
    train_ids={str(x['id']) for x in train}
    test_ids={str(x['id']) for x in test}
    tr=[x for x in response if x['response_id'] in train_ids]
    te=[x for x in response if x['response_id'] in test_ids]
    if len(tr)!=len(train) or len(te)!=len(test):
        raise AssertionError('response fragmentation lost sample IDs')
    if {x['source_id'] for x in tr}&{x['source_id'] for x in te}:
        raise AssertionError('source train/test leakage')
    results={}
    for signal in RISK_SCORES:
        negatives=[x['scores'][signal] for x in tr
                   if not x['human_positive']]
        if len(negatives)<20:
            raise ValueError('insufficient clean QA training responses')
        for target in TARGET_TRAIN_FPRS:
            threshold,train_fpr=choose_cutoff(negatives,target)
            key=f'{signal}_calibrated_train_FPR_{target}'
            results[key]={
                'score':signal,'train_target_FPR':target,
                'threshold_strict_greater_than':round(threshold,8),
                'train_observed_FPR':round(train_fpr,5),
                'D2T_test':confusion(te,signal,threshold),
                'D2T_implicit_true_excluded':confusion(te,signal,threshold,True),
                'group_bootstrap':clustered_interval(te,signal,threshold)
            }
    fixed={'lexical_fixed':0.0,'top1_max':.5,'top3_max':.5}
    for score,threshold in fixed.items():
        key=f'{score}_frozen_72'
        results[key]={
            'score':score,'threshold_strict_greater_than':threshold,
            'D2T_test':confusion(te,score,threshold),
            'D2T_implicit_true_excluded':confusion(te,score,threshold,True),
            'group_bootstrap':clustered_interval(te,score,threshold)
        }
    return {
        'partitions':parts,
        'model':{'name':r72.MODEL_ID,'sha':model_lock['revision'],
                 'labels':labels,'model_load_s':round(load_seconds,3)},
        'policy_contract':{
            'NLI_source_windows':'R72 identical lexical source windows 150 words/stride 100, max 96',
            'claims':'R72 deterministic sentence-like fragments, not atomic claims',
            'model_input_cap':r72.MODEL_INPUT_CAP,
            'train_thresholds_only_on_QA_human_negative_responses':TARGET_TRAIN_FPRS,
            'first_examination_of_D2T_test':'No D2T human response was evaluated in R69–73',
        },
        'train_human_positive_responses':sum(x['human_positive'] for x in tr),
        'test_human_positive_responses':sum(x['human_positive'] for x in te),
        'test_implicit_true_excluded_positive_responses':
            sum(x['strict_human_positive'] for x in te),
        'train_sentences':sum(x['sentence_count'] for x in tr),
        'test_sentences':sum(x['sentence_count'] for x in te),
        'case_counts':costs,
        'inference_resource':model_cost,
        'threshold_outcomes':results,
        'limitations':[
            'model trained on SNLI/MultiNLI, not RAGTruth; confidence thresholds empirically calibrated on RAGTruth QA training negatives',
            'first Data2txt test evaluation: different task/source representation, still same RAGTruth human annotation corpus and generator families',
            'QA training and Data2txt test grouped by immutable distinct source IDs, no test labels/outputs influence cutoffs',
            'model score non-entailment is not a probability of hallucination, contradiction or objective falsehood',
            'all thresholds prespecified 10% and 25% training FPR allowances, not a formal conformal risk guarantee',
            'R72 source window lexical selection and sentence fragmentation retained, not a trained claim decomposition or long context proof',
            'source JSON fields for Data2txt are stringified as in R69, generic NLI may not interpret structured records',
            'model token cost/CPU forward time charged; physical SSD, tokenizer, model load, dataset download and index build are separate',
            'human labels are source-faithfulness rather than universal truth; no generated answers are modified',
            'original human annotated text is not redistributed',
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=load('cdg69_load_main74',R69)
    records,rprov=r69.download('dataset/response.jsonl')
    sources,sprov=r69.download('dataset/source_info.jsonl')
    result=evaluate(records,sources)
    result['source_provenance']={
        'RAGTruth_revision':r69.REVISION,
        'source_git_blob':sprov['git_blob'],
        'response_git_blob':rprov['git_blob']
    }
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND74',json.dumps({
        'train':result['partitions']['train'],
        'test':result['partitions']['test'],
        'positives':result['test_human_positive_responses'],
        'model_resource':result['inference_resource'],
        'outcomes':{key:value['D2T_test'] for key,value in result['threshold_outcomes'].items()}
    },sort_keys=True))


if __name__=='__main__':
    main()
