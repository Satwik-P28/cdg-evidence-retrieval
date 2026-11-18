#!/usr/bin/env python3
"""R77: hold model/labels fixed, vary only LettuceDetect prompt construction.

Test published RAGTruth-trained LettuceDetect on the same 141 R72/R76
QA+Summary responses under two real input routes:
  1. R76's source passage list + task question,
  2. original RAGTruth generator prompt supplied to predict_prompt.

All predictions are verified to refer to the original response character
spans; no human labels influence inference. This tests a package input
boundary, not a novel semantic model or new independent benchmark.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,random,statistics,sys,time
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R76=HERE.parent/'round-76'/'lettuce_reference.py'
SALT='CDG-R77-PROMPT-CONSTRUCTION-SAME-R72-COHORT'
BOOTSTRAPS=1500


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def predicted_mask(answer,spans):
    if not isinstance(spans,list):
        raise ValueError('detector output is not a span list')
    mask=[False]*len(answer)
    for item in spans:
        lo,hi=item.get('start'),item.get('end')
        if not (isinstance(lo,int) and isinstance(hi,int)
                and 0<=lo<hi<=len(answer)):
            raise ValueError('span offsets outside original answer')
        if item.get('text') is not None and answer[lo:hi]!=item['text']:
            raise ValueError('predicted span text not exact source response substring')
        for j in range(lo,hi):mask[j]=True
    return mask


def predict_prompt(detector,prompt,answer):
    t0=time.perf_counter()
    spans=detector.predict_prompt(prompt=prompt,answer=answer,
                                  output_format='spans',min_confidence=0.0)
    return predicted_mask(answer,spans),time.perf_counter()-t0


def group_bootstrap(rows,reps=BOOTSTRAPS,seed=7712):
    """Paired response-F1 difference, groups are original source IDs."""
    buckets=defaultdict(list)
    for row in rows:buckets[row['sid']].append(row)
    keys=sorted(buckets)
    if len(keys)<2:return None
    rng=random.Random(seed)
    values=[]
    for _ in range(reps):
        sample=[r for _ in keys for r in buckets[keys[rng.randrange(len(keys))]]]
        left=metrics_for_rows(sample,'context')['f1']
        right=metrics_for_rows(sample,'original_prompt')['f1']
        values.append(right-left)
    values.sort()
    return [round(values[int(.025*(reps-1))],5),
            round(values[int(.975*(reps-1))],5)]


def metrics_for_rows(rows,policy):
    tp=fp=fn=tn=0
    for row in rows:
        result=row[policy]['flag']
        gold=row['human_positive']
        tp+=int(result and gold)
        fp+=int(result and not gold)
        fn+=int(not result and gold)
        tn+=int(not result and not gold)
    precision=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    return {'n':len(rows),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'precision':round(precision,5),
            'recall':round(recall,5),
            'f1':round(2*precision*recall/(precision+recall),5)
                 if precision+recall else 0,
            'false_positive_rate':round(fp/(fp+tn),5) if fp+tn else 0}


def compute(rows,byid,detector,r69,r76):
    tokenizer=detector.detector.tokenizer
    results=[]
    timing=Counter()
    encoded=Counter()
    for row in rows:
        sid=str(row['source_id'])
        task=byid[sid]['task_type']
        passages,question,meta=r76.assemble_context(byid[sid],r69)
        prompt=byid[sid].get('prompt')
        if not isinstance(prompt,str) or not prompt.strip():
            raise ValueError('original RAGTruth source prompt unavailable')
        answer=row['response']
        source_mask,_=r76.audited_prediction(detector,passages,answer,question)
        start=time.perf_counter()
        original_mask,prompt_wall=predict_prompt(detector,prompt,answer)
        context_wall=time.perf_counter()-start-prompt_wall
        # context_wall is just the overhead between calls and is not used as
        # runtime measure; use direct measured route durations instead.
        _=context_wall
        # Charge the source prompt tokenizer cost before any model truncation;
        # models may see fewer tokens than the original prompt provides.
        source_tokens=len(tokenizer.encode(' '.join(passages)+(question or ''),
                                           add_special_tokens=True))
        prompt_tokens=len(tokenizer.encode(prompt,add_special_tokens=True))
        encoded['context_prechunk_source_tokens']+=source_tokens
        encoded['original_prompt_source_tokens']+=prompt_tokens
        encoded['original_prompt_over_2048']+=int(
            prompt_tokens>r76.MAX_TOKENS)
        timing['original_prompt_model_wall_sec']+=prompt_wall
        gold,strict=r76.text_mask(row,r69)
        results.append({
            'sid':sid,'task':task,'human_positive':bool(any(gold)),
            'strict_positive':bool(any(strict)),
            'context':{'flag':any(source_mask),'chars':sum(source_mask)},
            'original_prompt':{'flag':any(original_mask),
                               'chars':sum(original_mask)},
            'human_positive_chars':sum(gold),
            'context_correct_at_response':any(source_mask)==any(gold),
            'original_correct_at_response':any(original_mask)==any(gold),
        })
    task_results={}
    for task in ('QA','Summary','all'):
        subset=[x for x in results if task=='all' or x['task']==task]
        comparison=Counter()
        for row in subset:
            a=row['context_correct_at_response']
            b=row['original_correct_at_response']
            comparison['both_correct' if a and b else
                       'context_only_correct' if a else
                       'original_prompt_only_correct' if b else
                       'both_wrong']+=1
        task_results[task]={
            'source_count':len({x['sid'] for x in subset}),
            'human_positive_responses':sum(x['human_positive'] for x in subset),
            'context':metrics_for_rows(subset,'context'),
            'original_prompt':metrics_for_rows(subset,'original_prompt'),
            'paired_outcome_counts':dict(comparison),
            'source_group_bootstrap_f1_original_minus_context_95ci':
                group_bootstrap(subset),
        }
    return {
        'task_outcomes':task_results,
        'input_tokens':{k:int(v) for k,v in encoded.items()},
        'original_prompt_inference_wall_seconds':round(
            timing['original_prompt_model_wall_sec'],3),
        'response_count':len(results),
        'disagreement_count':sum(
            x['context']['flag']!=x['original_prompt']['flag']
            for x in results),
        'source_group_digest_sha256':hashlib.sha256(
            '\n'.join(sorted({x['sid'] for x in results})).encode()).hexdigest(),
        'limitations':[
            'same 141 R72/76 QA+Summary source groups, already observed; not a new test corpus',
            'LettuceDetect is trained on RAGTruth; this is in-domain preprocessing sensitivity, not independent generalization',
            'predict_prompt with full original generator prompt may truncate source to 2048 tokens rather than automatically chunking passages',
            'context mode uses R76 constructed passage list and automatic chunking, so compute differs',
            'original task prompts may include instructions/formatting, not solely facts, and should not be treated as verified citation spans',
            'response-level any-span flag can exaggerate false alarms on long answer responses',
            'human annotations are source-faithfulness not objective truth; implicit_true separate metrics needed',
            'only model wall measured for original prompt; response evaluation and other preprocessing timings not directly comparable',
            'no new model fine-tuning, hallucination intervention or improved answer correctness demonstrated',
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=load('r69_load77',R69)
    r76=load('r76_load77',R76)
    responses,rmeta=r69.download('dataset/response.jsonl')
    sources,smeta=r69.download('dataset/source_info.jsonl')
    rows,byid,sample=r76.sample_rows(responses,sources)
    detector,model_info=r76.make_detector()
    result=compute(rows,byid,detector,r69,r76)
    result['model']=model_info
    result['r76_sample_identity']=sample
    result['corpus_revision']=r69.REVISION
    result['source_blob_sha']=smeta['git_blob']
    result['response_blob_sha']=rmeta['git_blob']
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND77',json.dumps({
        'n':result['response_count'],
        'disagreement':result['disagreement_count'],
        'tasks':result['task_outcomes'],
        'input_tokens':result['input_tokens'],
        'wall':result['original_prompt_inference_wall_seconds']},sort_keys=True))


if __name__=='__main__':
    main()
