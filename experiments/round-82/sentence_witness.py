#!/usr/bin/env python3
"""R82: frozen pretrained NLI source-context segmentation falsification.

Compares single-sentence witness, adjacent pairs and full source at an unchanged
predeclared entailment threshold, on exact R80/R81 synthetic source receipts.
Pretrained NLI is existing published prior work. No fine-tuning, original
user-generated responses or independent human labels.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-80'))
sys.path.insert(0,str(HERE.parent/'round-81'))

from controlled_facts import (
    archived_docs, generate as r80_generate, sha_cases,
    load_pinned_model
)
from relation_ablation import sample as r81_sample

R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
R80_SHA='8a2ed2de012491086784f7098faa4b51042fa98d7cd53eb063ec78b33e1722c7'
R81_SHA='817033b230722ea1551c209c358570d394d3f2a3be45ac7f77fb7edd8c2334c3'
THRESHOLD=0.5
MODEL_CAP=384
POLICIES=('full','lexical_single','best_single','best_adjacent2',
          'single_or_adjacent2','all_windows_contradiction_veto')
RANDOM_SEED=8207


def source_sentences(doc):
    """Source-only, deterministic sentence splits; preserve original punctuation."""
    pieces=[m.group().strip() for m in re.finditer(
        r'[^.!?\n]+(?:[.!?]+|$)',doc,re.UNICODE) if m.group().strip()]
    if not pieces or ''.join(x.replace(' ','') for x in pieces)=='':
        raise ValueError('source cannot be empty')
    return pieces


def candidate_plan(doc,claim,content_words):
    """Model input windows are determined without source-state or support labels."""
    sentences=source_sentences(doc)
    single=list(sentences)
    adjacent=[' '.join(sentences[i:i+2]) for i in range(len(sentences)-1)]
    if not adjacent:
        adjacent=single[:]
    query=set(content_words(claim))
    ranked=sorted(range(len(single)),key=lambda i:(
        -len(query & set(content_words(single[i]))),i))
    best_lexical_idx=ranked[0]
    windows=list(dict.fromkeys([doc,*single,*adjacent]))
    index={text:i for i,text in enumerate(windows)}
    full=[index[doc]]
    singles=[index[x] for x in single]
    pairs=[index[x] for x in adjacent]
    return {
        'windows':windows,'sentences':len(single),
        'policies':{
            'full':full,
            'lexical_single':[index[single[best_lexical_idx]]],
            'best_single':singles,
            'best_adjacent2':pairs,
            'single_or_adjacent2':list(dict.fromkeys(singles+pairs)),
            'all_windows_contradiction_veto':list(dict.fromkeys(singles+pairs)),
        }
    }


def prepare_cases():
    rows80=r80_generate()
    rows81=r81_sample()
    if sha_cases(rows80)!=R80_SHA or sha_cases(rows81)!=R81_SHA:
        raise AssertionError('intervention fixtures changed after prior model evaluations')
    docs80,archive80=archived_docs(rows80)
    docs81,archive81=archived_docs(rows81)
    cases=[]
    for name,rows,docs in [('R80',rows80,docs80),('R81',rows81,docs81)]:
        for row,doc in zip(rows,docs):
            if row['doc']!=doc:
                raise AssertionError('archive changed source body')
            cases.append({
                'suite':name,'id':row['id'],
                'entity_group':name+'-'+row['entity_group'],
                'condition':row['family'] if name=='R80' else row['variant'],
                'state':row['state'],
                'supported':bool(row['supported']),
                'doc':doc,'claim':row['claim'],
            })
    return cases,{'R80':archive80,'R81':archive81}


def infer(cases):
    r69=__import__('controlled_facts').load('cdg_r69_r82',R69)
    r72=__import__('controlled_facts').load('cdg_r72_r82',R72)
    lock=json.loads(r72.MODEL_LOCK.read_text())
    tokenizer,model,torch,params=load_pinned_model(r72.MODEL_ID,lock['revision'])
    labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
    if set(labels.values())!={'entailment','contradiction','neutral'}:
        raise AssertionError('original NLI class contract changed')
    ent=next(k for k,v in labels.items() if v=='entailment')
    contradiction=next(k for k,v in labels.items() if v=='contradiction')
    plans=[]
    pairs=[]
    for case in cases:
        plan=candidate_plan(case['doc'],case['claim'],r69.content_words)
        indices=[]
        for premise in plan['windows']:
            indices.append(len(pairs))
            pairs.append((premise,case['claim']))
        plans.append({
            'indices':indices,
            'policies':plan['policies'],
            'source_sentence_count':plan['sentences'],
        })
    probabilities=[];tokens=[];batch_wall=[]
    total_forward_time=0
    for start in range(0,len(pairs),12):
        import torch
        batch=pairs[start:start+12]
        toks=tokenizer([x[0] for x in batch],[x[1] for x in batch],
                       max_length=MODEL_CAP,truncation='only_first',
                       padding=True,return_tensors='pt')
        lengths=[int(x) for x in toks['attention_mask'].sum(dim=1).tolist()]
        t0=time.perf_counter()
        with torch.inference_mode():
            out=torch.softmax(model(**toks).logits,dim=-1)
        total_forward_time+=time.perf_counter()-t0
        batch_wall.append(time.perf_counter()-t0)
        tokens.extend(lengths)
        probabilities.extend([(float(p[ent]),float(p[contradiction]))
                             for p in out.tolist()])
    if len(probabilities)!=len(pairs):raise AssertionError('lost model pair')
    outputs={policy:[] for policy in POLICIES}
    burdens={policy:{'pairs':0,'token_inputs':0} for policy in POLICIES}
    for case,plan in zip(cases,plans):
        for policy,local in plan['policies'].items():
            relevant=[plan['indices'][i] for i in local]
            entails=[probabilities[i][0] for i in relevant]
            contradicts=[probabilities[i][1] for i in relevant]
            if policy=='all_windows_contradiction_veto':
                accepted=(max(entails)>=THRESHOLD and
                          max(contradicts)<THRESHOLD)
            else:
                accepted=max(entails)>=THRESHOLD
            outputs[policy].append(int(accepted))
            burdens[policy]['pairs']+=len(relevant)
            burdens[policy]['token_inputs']+=sum(tokens[i] for i in relevant)
    result={
        'models':{'model_id':r72.MODEL_ID,'revision':lock['revision'],
                  'parameters':params,'model_cap_tokens':MODEL_CAP,
                  'acceptance_entailment_threshold':THRESHOLD,
                  'veto_contradiction_threshold':THRESHOLD},
        'resource_cost':{
            'total_unique_case_window_pairs':len(pairs),
            'actual_model_input_tokens_sum':sum(tokens),
            'combined_shared_forward_wall_seconds':round(total_forward_time,3),
            'policy_isolated_forward_input_counts_excluding_cross_policy_reuse':burdens,
            'claim_count':len(cases),
        },
        'sentence_count_distribution':dict(Counter(
            plan['source_sentence_count'] for plan in plans)),
    }
    del model
    return outputs,result


def confusion(cases,pred):
    if len(cases)!=len(pred):
        raise AssertionError('prediction size mismatch')
    tp=sum(bool(x['supported']) and bool(y) for x,y in zip(cases,pred))
    fn=sum(bool(x['supported']) and not bool(y) for x,y in zip(cases,pred))
    fp=sum(not bool(x['supported']) and bool(y) for x,y in zip(cases,pred))
    tn=sum(not bool(x['supported']) and not bool(y) for x,y in zip(cases,pred))
    recall=tp/(tp+fn) if tp+fn else 0
    specificity=tn/(tn+fp) if tn+fp else 0
    return {'n':len(cases),'tp':int(tp),'fp':int(fp),'fn':int(fn),'tn':int(tn),
            'balanced_accuracy':round((recall+specificity)/2,5),
            'support_recall':round(recall,5),
            'unsupported_rejection':round(specificity,5)}


def score(cases,predictions):
    result={}
    for policy,pred in predictions.items():
        suites={}
        for suite in ('R80','R81','all'):
            idx=[i for i,c in enumerate(cases) if c['suite']==suite or suite=='all']
            sub=[cases[i] for i in idx]
            guesses=[pred[i] for i in idx]
            groups={}
            for condition in sorted(set(c['condition'] for c in sub)):
                loc=[i for i,c in enumerate(sub) if c['condition']==condition]
                groups[condition]={
                    **confusion([sub[i] for i in loc],[guesses[i] for i in loc]),
                    'state_counts':{
                        state:{'n':sum(sub[i]['state']==state for i in loc),
                               'accepted':sum(bool(guesses[i]) for i in loc if sub[i]['state']==state)}
                        for state in ('supported','contradicted','unknown')},
                }
            suite_matrix=confusion(sub,guesses)
            suite_matrix['condition_slices']=groups
            suite_matrix['state_acceptance']={
                state:{'n':sum(c['state']==state for c in sub),
                       'accepted':sum(bool(g) for c,g in zip(sub,guesses)
                                      if c['state']==state)}
                for state in ('supported','contradicted','unknown')}
            suites[suite]=suite_matrix
        result[policy]=suites
    baseline=predictions['full']
    changes={}
    for policy,pred in predictions.items():
        compared={}
        for suite in ('R80','R81','all'):
            idx=[i for i,c in enumerate(cases) if c['suite']==suite or suite=='all']
            compared[suite]={
              'full_wrong_to_policy_correct':sum(
                  (bool(baseline[i])!=bool(cases[i]['supported'])) and
                  (bool(pred[i])==bool(cases[i]['supported'])) for i in idx),
              'full_correct_to_policy_wrong':sum(
                  (bool(baseline[i])==bool(cases[i]['supported'])) and
                  (bool(pred[i])!=bool(cases[i]['supported'])) for i in idx),
              'changed_decisions':sum(pred[i]!=baseline[i] for i in idx)
            }
        changes[policy]=compared
    return result,changes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=parser.parse_args()
    cases,archives=prepare_cases()
    predictions,model_cost=infer(cases)
    stats,changes=score(cases,predictions)
    output={
        'scope':'pretrained NLI evidence window selection, no model training',
        'fixtures':{'R80':R80_SHA,'R81':R81_SHA},
        'cases':len(cases),'original_archive_receipts':archives,
        'source_policy':'all evidence windows from given correct source document; NO retrieval',
        'policies':list(POLICIES),
        'model_and_inference':model_cost,
        'outcomes':stats,'paired_changes_vs_full':changes,
        'limitations':[
          'source IDs are template oracle and target context is synthetic, not independently human-annotated',
          'contexts contain explicit fictional templates; no original generated answers or external generalization',
          'all policies use fixed entailment threshold 0.50 without model retuning',
          'max single evidence can miss multi-hop chains and can falsely accept inconsistent sources',
          'contradiction veto is heuristic and may wrongly reject support due unrelated negations',
          'all policies scored using shared cached pair inference; token/pair counts per policy are cold query logical costs, NOT measured per-policy latency',
          'read traffic is warm in-memory SHA-bound compression receipt; no cold SSD, FTS5, model RAM, update latency or answer generation',
          'the aggregate claim count is 220 related examples from ten repeated entity names, not 220 independent populations',
          'no independent benchmark or universal proof of semantic improvement',
        ],
    }
    Path(args.out).write_text(json.dumps(output,indent=2)+'\n')
    print('ROUND82',json.dumps({
        'fixtures':output['fixtures'],'counts':output['cases'],
        'policy_scores':{p:{s:{k:v for k,v in data.items()
                                     if k in ('n','tp','fp','fn','tn','balanced_accuracy')}
                            for s,data in out.items()}
                         for p,out in stats.items()},
        'transitions':changes,
        'costs':model_cost,
    },sort_keys=True))


if __name__=='__main__':
    main()
