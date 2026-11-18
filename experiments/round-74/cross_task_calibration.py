#!/usr/bin/env python3
"""R74: frozen QA-train NLI calibration tested on new Data2txt RAGTruth sources.

Zero-shot SNLI/MultiNLI model as in R72, fixed architecture/revision/windows.
Calibrate on source-disjoint RAGTruth QA TRAIN groups only, then evaluate
previously unexamined DATA2TXT TEST groups. Two predeclared source
serializations: original stable JSON, and a deterministic field-wise
linearization. No task test annotations enter text conversion or thresholds.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R70=HERE.parent/'round-70'/'calibrated_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
SOURCE_SALT='CDG-R74-QA-TRAIN-TO-DATA2TXT-TEST-v1'
TRAIN_TASK='QA'
TEST_TASK='Data2txt'
TRAIN_GROUPS=24
TEST_GROUPS=24
SCORES=('max_nonentail_risk','mean_nonentail_risk','fraction_low_entail')
TARGET_TRAIN_FPRS=(.10,.20)
TEST_SERIALIZATIONS=('json','field_linearized')
FROZEN_NLI_CUTOFF=.50


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def choose_groups(responses,sources,task,split,n):
    mapping={str(s['source_id']):s for s in sources}
    valid={str(r.get('source_id')) for r in responses
           if (r.get('split')==split and r.get('quality')=='good'
               and str(r.get('source_id')) in mapping
               and mapping[str(r.get('source_id'))].get('task_type')==task)}
    ranked=sorted(valid,key=lambda sid:(
        hashlib.sha256((SOURCE_SALT+'|'+task+'|'+split+'|'+sid).encode()).hexdigest(),
        sid))
    if len(ranked)<n:raise ValueError(f'insufficient independent {task}/{split} groups')
    picked=set(ranked[:n])
    selected=[r for r in responses if (
        r.get('split')==split and r.get('quality')=='good' and
        str(r.get('source_id')) in picked)]
    return selected,hashlib.sha256('\n'.join(sorted(picked)).encode()).hexdigest()


def flatten(obj,path='',depth=0):
    if depth>12:
        raise ValueError('structured source exceeded safe nesting depth')
    if isinstance(obj,dict):
        for key in sorted(obj):
            new=(path+' '+str(key)).strip()
            yield from flatten(obj[key],new,depth+1)
    elif isinstance(obj,list):
        for i,item in enumerate(obj):
            yield from flatten(item,path+' item '+str(i+1),depth+1)
    elif obj is None:
        return
    else:
        safe_key=path.replace('_',' ').replace('-',' ')
        value=json.dumps(obj,ensure_ascii=False) if isinstance(obj,(str,bool)) else str(obj)
        yield (safe_key,value)


def source_for(row,mode,r69):
    if mode=='json' or row.get('task_type')!='Data2txt':
        return r69.source_text(row)
    info=row.get('source_info')
    if not isinstance(info,dict):
        raise ValueError('expected Data2txt structured data dictionary')
    fields=list(flatten(info))
    if not fields:raise ValueError('empty structured source')
    return ' '.join(key+' is '+value+'.' for key,value in fields)


def prepare(source_rows,source_map,r69,r72,mode,suite):
    pairs=[]
    cases=[]
    selections=Counter()
    for row in source_rows:
        sid=str(row['source_id'])
        info=source_map[sid]
        source=source_for(info,mode,r69)
        windows,total,covered=r72.source_windows(source)
        if not windows or not windows[0]:raise ValueError('empty source windows')
        selections['source_words']+=total
        selections['source_covered_words']+=covered
        fragments=r69.fragments(row['response'])
        full,strict,faults=r69.annotated_masks(row)
        if faults:raise ValueError('bad human annotation offsets')
        claim_indices=[]
        for start,end,text in fragments:
            if not text.strip():continue
            ranking=r72.candidate_windows(windows,text,r69)
            if not ranking:raise AssertionError('no evidence window')
            claim_indices.append(len(pairs))
            pairs.append((windows[ranking[0]],text))
        if not claim_indices:continue
        cases.append({
            'source_id':sid,'response_id':str(row['id']),
            'task':info['task_type'],'suite':suite,
            'gold':int(any(full)),'strict_gold':int(any(strict)),
            'lexical_warning':int(any(r69.sentence_flags(
                text,source)['content_overlap'] for _,_,text in fragments)),
            'pair_indices':claim_indices,
        })
        selections['responses']+=1
        selections['hypotheses']+=len(claim_indices)
    return pairs,cases,dict(selections)


def risks(cases,probs):
    results=[]
    for row in cases:
        entails=[probs[i] for i in row['pair_indices']]
        if not entails or any(not 0<=p<=1 for p in entails):
            raise ValueError('NLI entailment confidence invalid')
        responses={
            'max_nonentail_risk':max(1-p for p in entails),
            'mean_nonentail_risk':statistics.mean(1-p for p in entails),
            'fraction_low_entail':sum(p<FROZEN_NLI_CUTOFF for p in entails)/len(entails),
        }
        results.append({
            **{k:row[k] for k in ('source_id','response_id','task','suite',
                                  'gold','strict_gold','lexical_warning')},
            'scores':responses,
        })
    return results


def binary_confusion(rows,pred_key,gold_key='gold'):
    c=Counter()
    for row in rows:
        pred=bool(row[pred_key])
        gold=bool(row[gold_key])
        c['tp']+=int(pred and gold)
        c['fp']+=int(pred and not gold)
        c['fn']+=int(not pred and gold)
        c['tn']+=int(not pred and not gold)
    return {x:int(c[x]) for x in ('tp','fp','fn','tn')}


def summarize(train,targets,r70,r69):
    result={}
    for score in SCORES:
        negative=[r['scores'][score] for r in train if not r['gold']]
        if not negative:raise ValueError('no human-clean QA training calibration sources')
        for fpr_target in TARGET_TRAIN_FPRS:
            cutoff,observed=r70.choose_cutoff(negative,fpr_target)
            policy=f'{score}@QA_train_FPR_{fpr_target}'
            row={'train_threshold':round(cutoff,8),
                 'observed_train_false_positive_rate':round(observed,5),
                 'target_training_FPR':fpr_target,'score':score,'test_modes':{}}
            for mode,records in targets.items():
                confusion=r70.score_counts(records,score,cutoff)
                alt=r70.score_counts([{**x,'gold':x['strict_gold']}
                                       for x in records],score,cutoff)
                row['test_modes'][mode]={
                    'original_human_labels':r70.metrics(confusion,r69),
                    'strict_implicit_true_excluded':r70.metrics(alt,r69),
                    'source_group_bootstrap':r70.grouped_bootstrap(
                        records,score,cutoff,reps=1200,seed=7419)}
            result[policy]=row
    for mode,records in targets.items():
        # Fixed R72 test decision and exactly frozen R69 lexical policy.
        fixed={**r70.metrics(r70.score_counts(
            records,'max_nonentail_risk',.50),r69)}
        lexical=r70.metrics(binary_confusion(
            [{**r,'pred':r['lexical_warning']} for r in records],'pred'),r69)
        result.setdefault('fixed_controls',{})[mode]={
            'NLI_any_sentence_p_entail_below_0.50':fixed,
            'R69_content_overlap':lexical,
            'always_no_warning':r70.metrics({'tp':0,'fp':0,
                'fn':sum(r['gold'] for r in records),
                'tn':sum(not r['gold'] for r in records)},r69)}
    return result


def run(responses,sources):
    r69=load('cdg69_for74',R69)
    r70=load('cdg70_for74',R70)
    r72=load('cdg72_for74',R72)
    mapping={str(x['source_id']):x for x in sources}
    train_rows,train_hash=choose_groups(
        responses,sources,TRAIN_TASK,'train',TRAIN_GROUPS)
    test_rows,test_hash=choose_groups(
        responses,sources,TEST_TASK,'test',TEST_GROUPS)
    train_groups={str(r['source_id']) for r in train_rows}
    test_groups={str(r['source_id']) for r in test_rows}
    if train_groups.intersection(test_groups):
        raise AssertionError('source group leakage across task transfer')
    pairlists={}
    cases={}
    selection={}
    for label,rows,mode in (
        ('QA_train',train_rows,'json'),
        ('Data2txt_test_json',test_rows,'json'),
        ('Data2txt_test_linearized',test_rows,'field_linearized')
    ):
        pairlists[label],cases[label],selection[label]=prepare(
            rows,mapping,r69,r72,mode,label)
    lock=json.loads(r72.MODEL_LOCK.read_text())
    model,tokenizer,torch,entail_id,classmap,load_s=r72.load_model_and_tokenizer(lock)
    all_pairs=[]
    ranges={}
    for label,pairs in pairlists.items():
        ranges[label]=(len(all_pairs),len(all_pairs)+len(pairs))
        all_pairs.extend(pairs)
    probs,inference=r72.infer_pairs(
        all_pairs,model,tokenizer,torch,entail_id)
    scored={}
    for label,pairs in pairlists.items():
        lo,hi=ranges[label]
        scored[label]=risks(cases[label],probs[lo:hi])
    thresholds=summarize(scored['QA_train'],{
        'Data2txt_original_JSON':scored['Data2txt_test_json'],
        'Data2txt_deterministic_field_linearization':scored['Data2txt_test_linearized'],
    },r70,r69)
    return {
        'train_groups':len(train_groups),
        'test_groups':len(test_groups),
        'train_responses':len(scored['QA_train']),
        'test_responses':len(scored['Data2txt_test_json']),
        'qa_train_source_id_sha256':train_hash,
        'data2txt_test_source_id_sha256':test_hash,
        'training_good_negative_responses':sum(not x['gold'] for x in scored['QA_train']),
        'test_positive_responses':sum(x['gold'] for x in scored['Data2txt_test_json']),
        'test_strict_positive_responses':sum(x['strict_gold'] for x in scored['Data2txt_test_json']),
        'model_name':r72.MODEL_ID,'model_revision':lock['revision'],
        'model_class_labels':classmap,'model_load_seconds':round(load_s,3),
        'selection_and_source_counts':selection,
        'inference':inference,'results':thresholds,
        'limitations':[
            'QA training group calibration and Data2txt test source groups are different tasks and source IDs, but belong to the same RAGTruth paper corpus',
            'Data2txt test task was not evaluated in R69-R73; no test human labels are used to select thresholds',
            'test evaluates two prespecified text serializations of the same structured Yelp-style source fields, not two independent test sets',
            'model trained on SNLI/MultiNLI, not RAGTruth and is a general NLI control, not a trained task-specific state of art detector',
            'field linearization is deterministic but may distort intended relations, categorical booleans, missing fields or metadata context',
            'source windows are lexical overlap-selected 150 word/100 stride bounded at 96, not an optimized semantic retriever',
            'training false alarm target is empirical and not a formal test distribution guarantee',
            'same model batched inference shared across all policy results; costs cannot be assigned as independent per-policy wall time',
            'model weights, source index, physical archive IO and answer generation/mitigation are not in R74 inference accounting',
        ]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=parser.parse_args()
    r69=load('cdg69_input74',R69)
    responses,res_prov=r69.download('dataset/response.jsonl')
    sources,src_prov=r69.download('dataset/source_info.jsonl')
    output=run(responses,sources)
    output['upstream_sha']={
        'revision':r69.REVISION,'responses':res_prov['git_blob'],
        'sources':src_prov['git_blob']}
    Path(args.out).write_text(json.dumps(output,indent=2)+'\n')
    print('ROUND74',json.dumps({
        'train_responses':output['train_responses'],
        'test_responses':output['test_responses'],
        'test_positives':output['test_positive_responses'],
        'inference':output['inference'],
        'results':output['results']},sort_keys=True))


if __name__=='__main__':
    main()
