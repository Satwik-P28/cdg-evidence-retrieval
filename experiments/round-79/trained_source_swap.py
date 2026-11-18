#!/usr/bin/env python3
"""R79: source sensitivity of the existing trained LettuceDetect baseline.

Keeps generated response/question fixed. Contrast the original source with
nearest and farthest alternate *same-task* source from the frozen R76 cohort.
No human annotation, gold source ID, or response text influences alternative
selection; original source IDs only define the candidate pools. Swapped
evidence has no independent human support labels, so results describe detector
sensitivity, NOT factual accuracy or mitigation.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,random,statistics,sys,time
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R76=HERE.parent/'round-76'/'lettuce_reference.py'
ITER=1500
SEED=7904


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:raise ImportError(str(path))
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def jaccard(a,b):
    if not a and not b:return 1.0
    return len(a & b)/len(a | b) if (a or b) else 0.0


def select_alternates(rows,byid,r69):
    """Source-only, label-blind selection, deterministic identity tie-break."""
    keys=sorted({str(r['source_id']) for r in rows})
    group={sid:byid[sid]['task_type'] for sid in keys}
    words={sid:set(r69.content_words(r69.source_text(byid[sid])))
           for sid in keys}
    mapping={}
    for sid in keys:
        candidates=[other for other in keys if other!=sid and group[other]==group[sid]]
        if len(candidates)<2:
            raise ValueError('need at least two alternate sources per task')
        ranked=sorted(((jaccard(words[sid],words[c]),c)
                       for c in candidates),key=lambda x:(x[0],x[1]))
        lo,hi=ranked[0],ranked[-1]
        mapping[sid]={
            'nearest':hi[1],'farthest':lo[1],
            'nearest_jaccard':round(hi[0],6),
            'farthest_jaccard':round(lo[0],6),
        }
        if mapping[sid]['nearest']==sid or mapping[sid]['farthest']==sid:
            raise AssertionError('source selection oracle leak')
    return mapping


def context_for_pair(original_sid,alternate_sid,byid,r69,r76):
    original=byid[original_sid]
    src=byid[alternate_sid]
    if original['task_type']!=src['task_type']:
        raise ValueError('cross-task evidence perturbation prohibited')
    paragraphs,_,_=r76.assemble_context(src,r69)
    _,fixed_question,_=r76.assemble_context(original,r69)
    return paragraphs,fixed_question


def changed(a,b):
    if len(a)!=len(b):raise ValueError('response mask shape mismatch')
    return {'response_flag_changed':int(any(a)!=any(b)),
            'character_change_rate':sum(x!=y for x,y in zip(a,b))/max(1,len(a)),
            'flagged_char_delta':sum(b)-sum(a)}


def bootstrap_difference(rows,reps=ITER,seed=SEED):
    """Paired far-minus-near change-rate, resample source ID groups."""
    groups=defaultdict(list)
    for row in rows:groups[row['source_id']].append(row)
    keys=sorted(groups)
    if len(keys)<2:return None
    rng=random.Random(seed)
    out=[]
    for _ in range(reps):
        sample=[x for _ in keys for x in groups[keys[rng.randrange(len(keys))]]]
        out.append(statistics.mean(
            x['farthest']['response_flag_changed']-
            x['nearest']['response_flag_changed'] for x in sample))
    out.sort()
    return [round(out[int(.025*(reps-1))],5),
            round(out[int(.975*(reps-1))],5)]


def aggregate(rows):
    result={}
    for task in ('QA','Summary','all'):
        subset=[r for r in rows if task=='all' or r['task']==task]
        if not subset:
            result[task]={'responses':0,'source_groups':0,
                          'original_predicted_positive':0,
                          'near_far_difference_unavailable':'no examples for task'}
            continue
        block={'responses':len(subset),
               'source_groups':len({r['source_id'] for r in subset}),
               'original_predicted_positive':sum(r['original_positive'] for r in subset)}
        for name in ('nearest','farthest'):
            values=[r[name] for r in subset]
            block[name]={
                'response_prediction_switched':sum(v['response_flag_changed'] for v in values),
                'response_switch_rate':round(statistics.mean(
                    v['response_flag_changed'] for v in values),5),
                'mean_character_mask_change':round(statistics.mean(
                    v['character_change_rate'] for v in values),5),
                'mean_predicted_char_delta':round(statistics.mean(
                    v['flagged_char_delta'] for v in values),3),
            }
        block['source_group_bootstrap_far_minus_near_response_switch_95ci']=\
            bootstrap_difference(subset)
        result[task]=block
    return result


def evaluate(rows,byid,detector,r69,r76):
    alternatives=select_alternates(rows,byid,r69)
    outcome=[]
    totals=Counter()
    t_start=time.perf_counter()
    for row in rows:
        sid=str(row['source_id'])
        source=byid[sid]
        original_passages,question,_=r76.assemble_context(source,r69)
        canonical,perf=r76.audited_prediction(
            detector,original_passages,row['response'],question)
        totals['original_inference_seconds']+=perf['elapsed_wall_sec']
        gold,_=r76.text_mask(row,r69)
        found={
            'source_id':sid,'task':source['task_type'],
            'original_positive':int(any(canonical)),
            'original_human_positive':int(any(gold)),
        }
        for key in ('nearest','farthest'):
            swap=alternatives[sid][key]
            paragraphs,fixed_question=context_for_pair(
                sid,swap,byid,r69,r76)
            if fixed_question!=question:
                raise AssertionError('question changed during source perturbation')
            predicted,details=r76.audited_prediction(
                detector,paragraphs,row['response'],fixed_question)
            totals[key+'_inference_seconds']+=details['elapsed_wall_sec']
            found[key]=changed(canonical,predicted)
            found[key]['evidence_jaccard']=alternatives[sid][key+'_jaccard']
        outcome.append(found)
    results=aggregate(outcome)
    original_gold=Counter()
    for r in outcome:
        pred=bool(r['original_positive'])
        y=bool(r['original_human_positive'])
        original_gold.update(tp=int(pred and y),fp=int(pred and not y),
                             fn=int(not pred and y),tn=int(not pred and not y))
    return {
        'responses':len(rows),
        'unique_source_groups':len(alternatives),
        'task_source_groups':dict(Counter(byid[s]['task_type'] for s in alternatives)),
        'alternative_source_jaccard':{
            name:{
                'mean':round(statistics.mean(x[name+'_jaccard']
                                             for x in alternatives.values()),6),
                'min':min(x[name+'_jaccard'] for x in alternatives.values()),
                'max':max(x[name+'_jaccard'] for x in alternatives.values()),
            } for name in ('nearest','farthest')},
        'original_confusion':dict(original_gold),
        'switch_metrics':results,
        'model_inference_seconds':{k:round(v,3) for k,v in totals.items()},
        'overall_wall_seconds':round(time.perf_counter()-t_start,3),
        'limitations':[
            'same-task source swap is not a truth-labeled counterfactual; alternative sources may also support the answer',
            'the source candidate pool is 24 frozen RAGTruth source groups rather than realistic corpus-scale retrieval',
            'source selection uses source-only lexical overlap and no human labels, but the benchmark supplies original source identity',
            'questions kept fixed for QA; Summary has no question; answer text unchanged',
            'the trained model saw RAGTruth training domain, so this is an in-domain sensitivity audit',
            'span and response changes do not necessarily imply improved detection or source attribution',
            'no CDG answer generated or corrected and no independently human-verified alternative evidence',
            'CPU and token budgets not matched with generic NLI; no compression performed in this semantic perturbation round',
            'source-group bootstrap is descriptive; no independent population generalization promised',
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=load('r69_run79',R69)
    r76=load('r76_run79',R76)
    answers,response_meta=r69.download('dataset/response.jsonl')
    sources,source_meta=r69.download('dataset/source_info.jsonl')
    chosen,byid,selection=r76.sample_rows(answers,sources)
    detector,model_meta=r76.make_detector()
    summary=evaluate(chosen,byid,detector,r69,r76)
    if summary['responses']!=141 or summary['unique_source_groups']!=24:
        raise AssertionError('frozen cohort drifted')
    summary['provenance']={
        'ragtruth_git_revision':r69.REVISION,
        'response_git_blob':response_meta['git_blob'],
        'source_git_blob':source_meta['git_blob'],
        'sample_source_digest':selection['source_ids_sha256'],
        'trained_detector_sha':model_meta['snapshot_sha'],
        'model_parameters':model_meta['model_parameters'],
    }
    Path(args.out).write_text(json.dumps(summary,indent=2)+'\n')
    print('ROUND79',json.dumps({
        'responses':summary['responses'],
        'jaccard':summary['alternative_source_jaccard'],
        'original_confusion':summary['original_confusion'],
        'switch_metrics':summary['switch_metrics'],
        'inference_seconds':summary['model_inference_seconds'],
    },sort_keys=True))


if __name__=='__main__':
    main()
