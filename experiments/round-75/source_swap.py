#!/usr/bin/env python3
"""R75: source-swap counterfactual test of a pinned zero-shot NLI verifier.

Responses remain IDENTICAL while their evidence source is exchanged with the
most lexically similar distinct source in the same RAGTruth Data2txt test task.
No human annotations influence source swaps or NLI inference.

Question: does the supposed grounding scorer measurably prefer the actual
evidence source to a comparable, intentionally different source?

This measures source sensitivity, NOT factual correctness under swapped
contexts. Both passages might support a given general claim; no human
counterfactual annotation exists.
"""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,math,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path
import random

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
R74=HERE.parent/'round-74'/'cross_task_calibration.py'
SEED=7517
BOOTSTRAPS=1500
SOURCE_SWAP_RULE='most-Jaccard-similar distinct Data2txt source_id, using source leaf-value tokens only'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


def leaves(info):
    if isinstance(info,dict):
        for value in info.values():
            yield from leaves(value)
    elif isinstance(info,list):
        for value in info:
            yield from leaves(value)
    elif info is not None:
        yield str(info)


def counterfactual_map(source_map,ids,r69):
    ranked=sorted(ids)
    if len(ranked)<2:
        raise ValueError('need two or more distinct source IDs for counterfactual')
    bags={
        sid:set(r69.words(' '.join(leaves(source_map[sid]['source_info']))))
        for sid in ranked}
    alternatives={}
    scores={}
    for sid in ranked:
        def jaccard(other):
            inter=len(bags[sid]&bags[other])
            union=len(bags[sid]|bags[other]) or 1
            return inter/union
        best=min((x for x in ranked if x!=sid),
                 key=lambda x:(-jaccard(x),x))
        if best==sid:raise AssertionError('self source swap')
        alternatives[sid]=best
        scores[sid]=jaccard(best)
    return alternatives,scores


def collect_per_response(cases,probs):
    record={}
    for row in cases:
        sid=row['source_group']
        rid=row['response_id']
        item=record.setdefault(rid,{
            'source_id':sid,'gold':False,'strict_gold':False,
            'entailment':[],'claims':0})
        if item['source_id']!=sid:
            raise ValueError('response source ID collision')
        item['gold']|=bool(row['gold'])
        item['strict_gold']|=bool(row['strict_gold'])
        candidates=[probs[i] for i in row['pair_indices']['nli_lexical_top3']]
        if not candidates:raise ValueError('no candidate source window')
        value=max(candidates)
        if not math.isfinite(value):
            raise ValueError('nonfinite NLI score')
        item['entailment'].append(value)
        item['claims']+=1
    return {
        key:{
            'source_id':item['source_id'],
            'gold':item['gold'],
            'strict_gold':item['strict_gold'],
            'min_entailment':min(item['entailment']),
            'mean_entailment':statistics.mean(item['entailment']),
            'claims':item['claims'],
        }
        for key,item in record.items()
    }


def group_ci(rows,metric='delta_min_entailment',reps=BOOTSTRAPS,seed=SEED):
    groups=defaultdict(list)
    for r in rows:groups[r['source_id']].append(r)
    ids=sorted(groups)
    if len(ids)<2:return None
    rng=random.Random(seed)
    values=[]
    for _ in range(reps):
        sub=[row for _ in ids for row in groups[ids[rng.randrange(len(ids))]]]
        values.append(statistics.mean(x[metric] for x in sub))
    values.sort()
    return [
        round(values[int(.025*(reps-1))],5),
        round(values[int(.975*(reps-1))],5)]


def evaluate(responses,sources):
    r69=load('r69_for75',R69)
    r72=load('r72_for75',R72)
    r74=load('r74_for75',R74)
    _training,test,source_map,parts=r74.partition(responses,sources)
    ids=sorted(set(str(x['source_id']) for x in test))
    options,similarity=counterfactual_map(source_map,ids,r69)
    swapped_map=copy.deepcopy(source_map)
    for sid in ids:
        alternate=options[sid]
        # Task/source id stay anchored. Only the source value is changed.
        swapped_map[sid]['source_info']=copy.deepcopy(source_map[alternate]['source_info'])
    original_cases,original_pairs,original_counts=r72.compile_cases(
        test,source_map,r69)
    swapped_cases,swapped_pairs,swapped_counts=r72.compile_cases(
        test,swapped_map,r69)
    if (len(original_cases)!=len(swapped_cases) or
        len(original_cases)==0 or len(original_pairs)==0):
        raise AssertionError('counterfactual lost response/claim alignment')
    for a,b in zip(original_cases,swapped_cases):
        for key in ('response_id','source_group','gold','strict_gold'):
            if a[key]!=b[key]:
                raise AssertionError('counterfactual changed labels or response identity')
    lock=json.loads(r72.MODEL_LOCK.read_text())
    model,tok,torch,entail,labels,load_seconds=r72.load_model_and_tokenizer(lock)
    combined=original_pairs+swapped_pairs
    probs,resources=r72.infer_pairs(combined,model,tok,torch,entail)
    n=len(original_pairs)
    actual=collect_per_response(original_cases,probs[:n])
    swapped=collect_per_response(swapped_cases,probs[n:])
    if set(actual)!=set(swapped) or len(actual)!=len(test):
        raise AssertionError('counterfactual response count mismatch')
    rows=[]
    for rid in actual:
        a,b=actual[rid],swapped[rid]
        if a['source_id']!=b['source_id'] or a['claims']!=b['claims']:
            raise AssertionError('source mapping or claim segmentation changed')
        rows.append({
            'source_id':a['source_id'],
            'gold':a['gold'],'strict_gold':a['strict_gold'],
            'claims':a['claims'],
            'actual_min_entailment':a['min_entailment'],
            'swapped_min_entailment':b['min_entailment'],
            'delta_min_entailment':a['min_entailment']-b['min_entailment'],
            'delta_mean_entailment':a['mean_entailment']-b['mean_entailment'],
        })
    def summarise(subset):
        if not subset:return {}
        deltas=[x['delta_min_entailment'] for x in subset]
        return {
            'n':len(subset),
            'prefer_actual_count':sum(x>1e-6 for x in deltas),
            'prefer_swapped_count':sum(x< -1e-6 for x in deltas),
            'near_tie_count':sum(abs(x)<=1e-6 for x in deltas),
            'median_delta_min_entailment':round(statistics.median(deltas),5),
            'mean_delta_min_entailment':round(statistics.mean(deltas),5),
            'mean_delta_mean_entailment':round(statistics.mean(
                x['delta_mean_entailment'] for x in subset),5),
            'mean_original_entailment':round(statistics.mean(
                x['actual_min_entailment'] for x in subset),5),
            'mean_swapped_entailment':round(statistics.mean(
                x['swapped_min_entailment'] for x in subset),5),
            'source_group_bootstrap_delta_min_95ci':group_ci(subset),
        }
    return {
        'scope':'R75 matched-source-versus-swap response-conditioned NLI, no counterfactual truth oracle',
        'model':{
            'name':r72.MODEL_ID,'sha':lock['revision'],
            'label_mapping':labels,'load_seconds':round(load_seconds,3),
        },
        'original_R74_D2T_test_partition':parts['test'],
        'swap_policy':SOURCE_SWAP_RULE,
        'source_swap_group_count':len(options),
        'source_similarity_mean':round(statistics.mean(similarity.values()),5),
        'source_similarity_range':[round(min(similarity.values()),5),
                                   round(max(similarity.values()),5)],
        'response_count':len(rows),
        'sentence_count':len(original_cases),
        'original_model_pairs':len(original_pairs),
        'swapped_model_pairs':len(swapped_pairs),
        'total_model_inference':resources,
        'summaries':{
            'all':summarise(rows),
            'human_clean':summarise([r for r in rows if not r['gold']]),
            'human_unsupported':summarise([r for r in rows if r['gold']]),
        },
        'source_identity_hashes':{
            'real_source_ids_sha256':parts['test']['sample_source_ids_sha256'],
            'swap_mapping_sha256':hashlib.sha256(
                '\n'.join(f'{k}:{options[k]}' for k in sorted(options)).encode()).hexdigest(),
        },
        'limitations':[
            'swapped source is intentionally not annotated by humans, so no source-swap prediction is labeled correct or incorrect',
            'source selection uses original QA-train-to-Data2txt frozen group IDs from R74; task already inspected in R74',
            'Jaccard nearest source is lexical and may retain genuine support for generic claims in both contexts',
            'source matching uses JSON leaf-value words, not learned semantic retrieval',
            'R72 fixed generic NLI model reused, no training or threshold fitting and no gold labels in source swaps',
            'multiple sentence-like claims aggregated, not atomic fact entailment',
            'source-window/context truncation can hide relevant source and undermine causal interpretation',
            'paired score shifts are diagnostic of source sensitivity, not factual grounding guarantees',
            'model forward CPU seconds/token counts charged; physical storage and index costs covered separately in R73',
            'RAGTruth original source text and generated answers are transient, not redistributed',
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=load('r69_loader_75',R69)
    replies,rmeta=r69.download('dataset/response.jsonl')
    sources,smeta=r69.download('dataset/source_info.jsonl')
    data=evaluate(replies,sources)
    data['dataset_revision']=r69.REVISION
    data['source_git_blob']=smeta['git_blob']
    data['response_git_blob']=rmeta['git_blob']
    Path(args.out).write_text(json.dumps(data,indent=2)+'\n')
    print('ROUND75',json.dumps({
        'responses':data['response_count'],
        'source_groups':data['source_swap_group_count'],
        'similarity_mean':data['source_similarity_mean'],
        'results':data['summaries'],
        'model_cost':data['total_model_inference']},sort_keys=True))


if __name__=='__main__':
    main()
