#!/usr/bin/env python3
"""R72: zero-shot source-conditioned NLI against human RAGTruth spans.

The fixed pretrained cross-encoder was trained on SNLI/MultiNLI, not RAGTruth.
No RAGTruth train/test labels enter sentence selection, claim segmentation or
NLI confidence thresholds. Model identity is locked by a full Hub Git SHA
before data evaluation. No original source or generated answer is emitted.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, re, statistics, sys, time
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
MODEL_ID='cross-encoder/nli-deberta-v3-xsmall'
MODEL_LOCK=HERE/'model_lock.json'
TASK_GROUPS={'QA':8,'Summary':16}
SALT='CDG-R72-FROZEN-NLI-SUMMARY-TEST-v1'
SOURCE_WINDOW_WORDS=150
SOURCE_WINDOW_STRIDE=100
MAX_SOURCE_WINDOWS=96
CLAIM_TOKEN_CAP=128
MODEL_INPUT_CAP=384
BATCH_SIZE=16
ENTAIL_THRESHOLD=.50
METHODS=('lexical_55','nli_first','nli_lexical_top1','nli_lexical_top3')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def group_sample(responses,sources):
    byid={str(row['source_id']):row for row in sources}
    if len(byid)!=len(sources):raise ValueError('duplicate source ID')
    ids_by_task=defaultdict(set)
    for row in responses:
        sid=str(row.get('source_id'))
        if (row.get('split')=='test' and row.get('quality')=='good'
                and sid in byid):
            task=byid[sid].get('task_type')
            if task in TASK_GROUPS:ids_by_task[task].add(sid)
    picked={}
    for task,n in TASK_GROUPS.items():
        ids=sorted(ids_by_task[task],key=lambda sid:(
            hashlib.sha256((SALT+'|'+task+'|'+sid).encode()).hexdigest(),sid))
        if len(ids)<n:raise ValueError(f'not enough {task} test groups')
        picked[task]=ids[:n]
    union=set(sid for ids in picked.values() for sid in ids)
    selected=[row for row in responses if (
        row.get('split')=='test' and row.get('quality')=='good'
        and str(row.get('source_id')) in union)]
    digest=hashlib.sha256('\n'.join(sorted(union)).encode()).hexdigest()
    return selected,byid,{
        'source_groups':{task:len(ids) for task,ids in picked.items()},
        'response_count':len(selected),'source_ids_sha256':digest,
        'source_task_group_counts':{task:len(ids_by_task[task]) for task in TASK_GROUPS},
    }


def source_windows(text):
    words=re.findall(r'\S+',text)
    if not words:return [''],0,0
    positions=list(range(0,len(words),SOURCE_WINDOW_STRIDE))
    if positions and positions[-1]>=len(words):
        positions.pop()
    wins=[]
    visited=0
    for start in positions[:MAX_SOURCE_WINDOWS]:
        segment=words[start:start+SOURCE_WINDOW_WORDS]
        if not segment:break
        wins.append(' '.join(segment))
        visited=max(visited,start+len(segment))
    return wins,len(words),visited


def candidate_windows(windows,claim,r69):
    query=set(r69.content_words(claim))
    # Deterministic scoring of full source windows. No annotations.
    scored=[(len(query.intersection(r69.content_words(w))),i)
            for i,w in enumerate(windows)]
    scored.sort(key=lambda x:(-x[0],x[1]))
    return [i for _,i in scored[:3]]


def segment_labels(row,r69):
    answer=row['response']
    gold,strict,faults=r69.annotated_masks(row)
    if faults:raise ValueError(f'bad human annotation offsets {faults}')
    spans=r69.fragments(answer)
    return [(start,end,text,int(any(gold[start:end])),int(any(strict[start:end])))
            for start,end,text in spans]


def compile_cases(responses,byid,r69):
    cases=[]
    all_pairs=[]
    totals=Counter()
    lengths=[]
    groups=Counter()
    for row in responses:
        sid=str(row['source_id'])
        task=byid[sid]['task_type']
        src=r69.source_text(byid[sid])
        windows,source_words,covered=source_windows(src)
        groups[(task,sid)]+=1
        if groups[(task,sid)]==1:
            totals['source_words_total']+=source_words
            totals['source_words_covered']+=covered
            totals['source_truncated_groups']+=int(covered<source_words)
        if not windows or not windows[0]:raise ValueError('empty source text')
        for beg,end,claim,gold,strict in segment_labels(row,r69):
            if not claim.strip():continue
            ranked=candidate_windows(windows,claim,r69)
            # Order 0 + distinct lexical top3. Each evidence option has its own
            # scored pair; sharing identical pairs is allowed via key dedup.
            used={0}
            used.update(ranked)
            pair_by_window={}
            for j in sorted(used):
                pair_by_window[j]=len(all_pairs)
                all_pairs.append((windows[j],claim))
            cases.append({
                'task':task,'source_group':sid,'response_id':str(row['id']),
                'gold':gold,'strict_gold':strict,'literal_warning':
                   r69.sentence_flags(claim,src)['content_overlap'],
                'pair_indices':{
                    'nli_first':[pair_by_window[0]],
                    'nli_lexical_top1':[pair_by_window[ranked[0]]],
                    'nli_lexical_top3':[pair_by_window[i] for i in ranked]},
            })
            totals['claim_sentences']+=1
            lengths.append(len(r69.words(claim)))
    totals['response_count']=len(responses)
    totals['distinct_source_groups']=len(groups)
    totals['pair_count']=len(all_pairs)
    totals['max_response_sentence_words']=max(lengths) if lengths else 0
    return cases,all_pairs,dict(totals)


def load_model_and_tokenizer(lock):
    import torch
    from transformers import AutoModelForSequenceClassification,AutoTokenizer
    torch.manual_seed(7212)
    torch.set_num_threads(2)
    revision=lock['revision']
    if not re.fullmatch(r'[a-f0-9]{40}',revision):
        raise ValueError('NLI model revision must be an immutable SHA')
    t0=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(MODEL_ID,revision=revision)
    model=AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID,revision=revision,use_safetensors=True)
    model.eval()
    labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
    required={'contradiction','entailment','neutral'}
    if set(labels.values())!=required or len(labels)!=3:
        raise ValueError(f'unexpected NLI model class order: {labels}')
    entail_id=next(k for k,v in labels.items() if v=='entailment')
    return model,tokenizer,torch,entail_id,labels,time.perf_counter()-t0


def infer_pairs(pairs,model,tokenizer,torch,entail_id):
    probabilities=[]
    pair_tokens=0
    truncated_claims=0
    t0=time.perf_counter()
    for p in range(0,len(pairs),BATCH_SIZE):
        batch=pairs[p:p+BATCH_SIZE]
        premises=[]
        hypotheses=[]
        for premise,claim in batch:
            claim_ids=tokenizer.encode(claim,add_special_tokens=False)
            if len(claim_ids)>CLAIM_TOKEN_CAP:
                claim=tokenizer.decode(claim_ids[:CLAIM_TOKEN_CAP],
                                       skip_special_tokens=True)
                truncated_claims+=1
            premises.append(premise)
            hypotheses.append(claim)
        toks=tokenizer(
            premises,hypotheses,padding=True,
            truncation='only_first',max_length=MODEL_INPUT_CAP,
            return_tensors='pt')
        if toks['input_ids'].shape[1]>MODEL_INPUT_CAP:
            raise AssertionError('NLI model max input violated')
        pair_tokens+=int(toks['attention_mask'].sum().item())
        with torch.inference_mode():
            probs=torch.softmax(model(**toks).logits,dim=-1)
        for value in probs[:,entail_id].tolist():
            if not 0<=value<=1 or not math.isfinite(value):
                raise ValueError('nonfinite NLI confidence')
            probabilities.append(value)
    if len(probabilities)!=len(pairs):raise AssertionError('missing NLI result')
    return probabilities,{
        'model_pair_count':len(pairs),
        'pair_input_tokens_sum':pair_tokens,
        'model_forward_wall_seconds':round(time.perf_counter()-t0,3),
        'hypotheses_truncated_to_128_tokens':truncated_claims,
    }


def score_cases(cases,probs,r69):
    by_case=[]
    for row in cases:
        scores={method:(
            bool(row['literal_warning']) if method=='lexical_55' else
            max(probs[i] for i in row['pair_indices'][method])<ENTAIL_THRESHOLD
        ) for method in METHODS}
        by_case.append({**{key:row[key] for key in
                         ('task','source_group','response_id','gold','strict_gold')},
                       'warnings':scores})
    return by_case


def measures(rows,method,r69,label='gold'):
    matrix=Counter()
    response=defaultdict(list)
    for row in rows:
        y=bool(row[label]);p=bool(row['warnings'][method])
        matrix['tp']+=int(p and y);matrix['fp']+=int(p and not y)
        matrix['fn']+=int(not p and y);matrix['tn']+=int(not p and not y)
        response[row['response_id']].append((p,y))
    rmatrix=Counter()
    for values in response.values():
        p=any(x for x,_ in values);y=any(x for _,x in values)
        rmatrix['tp']+=int(p and y);rmatrix['fp']+=int(p and not y)
        rmatrix['fn']+=int(not p and y);rmatrix['tn']+=int(not p and not y)
    return {'sentence':confusion(matrix,r69),'response':confusion(rmatrix,r69)}


def confusion(m,r69):
    tp,fp,fn,tn=[int(m[key]) for key in ('tp','fp','fn','tn')]
    result=dict(tp=tp,fp=fp,fn=fn,tn=tn)
    result.update(r69.ratios(tp,fp,fn))
    result['false_positive_rate']=round(fp/(fp+tn),5) if fp+tn else None
    result['false_negative_rate']=round(fn/(fn+tp),5) if fn+tp else None
    return result


def calculate(cases,probs,r69):
    labelled=score_cases(cases,probs,r69)
    output={}
    for task in (*TASK_GROUPS,'all'):
        selected=[r for r in labelled if task=='all' or r['task']==task]
        output[task]={
            'sentences':len(selected),
            'responses':len({r['response_id'] for r in selected}),
            'human_positive_sentences':sum(r['gold'] for r in selected),
            'methods':{m:{
                'original_human_labels':measures(selected,m,r69),
                'implicit_true_excluded':measures(selected,m,r69,'strict_gold')
            } for m in METHODS},
        }
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    lock=json.loads(MODEL_LOCK.read_text())
    if lock.get('name')!=MODEL_ID:
        raise ValueError('NLI model lock identity mismatch')
    r69=load('cdg_r69_for72',R69)
    responses,provenance=r69.download('dataset/response.jsonl')
    sources,source_provenance=r69.download('dataset/source_info.jsonl')
    picked,byid,sample=group_sample(responses,sources)
    cases,pairs,counts=compile_cases(picked,byid,r69)
    model,tokenizer,torch,entail_id,labels,load_seconds=load_model_and_tokenizer(lock)
    probs,cost=infer_pairs(pairs,model,tokenizer,torch,entail_id)
    result={
        'scope':'zero-shot NLI source-conditioned response warning; not trained on RAGTruth',
        'source_upstream':{'ragtruth_revision':r69.REVISION,
                           'response_git_blob':provenance['git_blob'],
                           'sources_git_blob':source_provenance['git_blob']},
        'model':{'name':MODEL_ID,'revision':lock['revision'],
                 'label_mapping':labels,'license':'Apache-2.0',
                 'training_data':'SNLI and MultiNLI',
                 'load_seconds':round(load_seconds,3)},
        'sample':sample,'task_counts':counts,
        'costs':cost,'methods':calculate(cases,probs,r69),
        'limitations':[
            'RAGTruth original human annotations are source-faithfulness judgments, not objective truth',
            'QA test domain already inspected in R69–71; Summary task was not inspected in those rounds',
            'zero-shot NLI model trained on SNLI/MultiNLI, not optimized or trained on RAGTruth',
            'source window selection is lexical, with at most 96 150-word windows and possible omission of later source',
            'NLI is sentence-based, not atomic claim decomposition or long-context joint entailment',
            'entailment score threshold 0.50 was fixed before test evaluation, not calibrated',
            'max entailment over up to three windows can miss contradictions between source passages',
            'not a generator, no interventions or reduction in hallucination frequency measured',
            'model tokens and inference time charged, but no GPU/SSD, persistent weights or full storage index',
            'no redistribution of original human-labeled responses or passages',
        ],
    }
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND72',json.dumps({
        'sample':sample,'cases':len(cases),'costs':cost,
        'model':result['model'],
        'task_outcomes':{
            task:{m:output['methods'][m]['original_human_labels']['response']
                  for m in METHODS}
            for task,output in result['methods'].items()}},sort_keys=True))


if __name__=='__main__':main()
