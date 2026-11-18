#!/usr/bin/env python3
"""Round 72: pretrained NLI grounding control, no model fine-tuning.

A fixed MiniLM2 NLI encoder trained on general NLI data is applied to
RAGTruth human-annotated QA answers. It reads (source sentence, response
sentence) pairs, unlike the source-only receipt baselines. Label-blind
source-window retrieval is fully charged for token/pair counts.

IMPORTANT: a non-entailment score is NOT a calibrated hallucination score.
This is a conventional baseline to falsify naive semantic verification, not
a new classifier or an assertion that a cited source proves a response.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
import time
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R70=HERE.parent/'round-70'/'calibrated_grounding.py'
MODEL="cross-encoder/nli-MiniLM2-L6-H768"
MODEL_REVISION="b95119ce93d3e065de6214e38cd4a97b0f2f2c6d"
MAX_LENGTH=384
MAX_CLAIMS=8
MAX_PREMISES=3
BATCH_SIZE=16
POLICIES=('nli_top1_50','nli_top3_50','nli_top3_80','frozen_lexical_55')
HELDOUT_COUNT=22


def dynamic(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def source_segments(source):
    # Plain, content-only segmentation: never use human annotations, examples,
    # source IDs, answer strings or model-generated labels in source formation.
    # RAGTruth QA passages contain 'passage 1:', 'passage 2:', etc.
    by_passage=re.split(r'(?i)(?=\bpassage\s+\d+\s*:)',source)
    segments=[]
    for block in by_passage:
        text=block.strip()
        if not text:continue
        # Cut long premises on sentence-like boundaries to fit 384 tokens
        # without systematic whole-source tail loss.
        sentences=re.split(r'(?<=[.!?])\s+|\n+',text)
        for sentence in sentences:
            if not sentence.strip():continue
            # Character caps act as coarse pretokenization; tokenizer truncation
            # is separately measured at inference.
            for pos in range(0,len(sentence),700):
                span=sentence[pos:pos+700].strip()
                if span:segments.append(span)
    return segments or [source[:700]]


def select_premises(source,claim,r69,limit=MAX_PREMISES):
    pieces=source_segments(source)
    claim_terms=set(r69.content_words(claim))
    ranked=sorted(range(len(pieces)),key=lambda i:(
        -len(set(r69.content_words(pieces[i])) & claim_terms),
        i))
    return [pieces[i] for i in ranked[:limit]]


def claim_rows(records,source_map,r69):
    cases=[]
    records_out=[]
    for record in records:
        sid=str(record['source_id'])
        source=r69.source_text(source_map[sid])
        response=record['response']
        full,strict,faults=r69.annotated_masks(record)
        if faults:raise ValueError('invalid original human annotation span')
        fragments=r69.fragments(response)[:MAX_CLAIMS]
        parts=[]
        for start,end,text in fragments:
            # Ignore empty whitespace-only fragments. A selected sentence is
            # a diagnostic unit, NOT a complete semantic proposition.
            if not text.strip():continue
            premises=select_premises(source,text,r69)
            parts.append({'start':start,'end':end,'text':text,
                          'premises':premises})
            for premise in premises:
                cases.append((premise,text))
        records_out.append({
            'source_id':sid,'id':str(record['id']),
            'human_positive':bool(any(full)),
            'strict_positive':bool(any(strict)),
            'human_positive_within_examined_sentences':any(
                any(full[p['start']:p['end']]) for p in parts),
            'quality':record.get('quality'),
            'response':response,'source':source,'parts':parts,
        })
    return cases,records_out


def get_model():
    import torch
    from transformers import AutoTokenizer,AutoModelForSequenceClassification
    torch.set_num_threads(2)
    tok=AutoTokenizer.from_pretrained(
        MODEL,revision=MODEL_REVISION,use_fast=True,trust_remote_code=False)
    model=AutoModelForSequenceClassification.from_pretrained(
        MODEL,revision=MODEL_REVISION,trust_remote_code=False)
    model.eval()
    labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
    matches=[k for k,v in labels.items() if v=='entailment']
    if len(matches)!=1:
        raise ValueError(f'pretrained NLI model does not expose exactly one entailment label: {labels}')
    return tok,model,torch,matches[0],labels


def infer_pairs(pairs,tok,model,torch,entail_idx):
    values=[]
    tokens=0
    truncated_pairs=0
    total_wall=0
    with torch.no_grad():
        for i in range(0,len(pairs),BATCH_SIZE):
            batch=pairs[i:i+BATCH_SIZE]
            left=[x[0] for x in batch]
            right=[x[1] for x in batch]
            original=tok(left,right,truncation=False,add_special_tokens=True)
            truncated_pairs+=sum(len(x)>MAX_LENGTH for x in original['input_ids'])
            encoded=tok(left,right,padding=True,truncation='only_first',
                        max_length=MAX_LENGTH,return_tensors='pt')
            tokens+=int(encoded['attention_mask'].sum().item())
            start=time.perf_counter()
            logits=model(**encoded).logits
            probs=torch.softmax(logits,dim=-1)[:,entail_idx]
            total_wall+=time.perf_counter()-start
            values.extend(float(x) for x in probs.tolist())
    if len(values)!=len(pairs):raise AssertionError('model pair count mismatch')
    return values,{'pair_count':len(pairs),'model_input_tokens':tokens,
                   'truncated_pairs':truncated_pairs,
                   'model_forward_wall_seconds':round(total_wall,4)}


def score_from_entailments(values,records,r69):
    cursor=0
    by_policy={policy:[] for policy in POLICIES}
    sample_confidence=[]
    for row in records:
        strengths=[]
        for part in row['parts']:
            n=len(part['premises'])
            chunk=values[cursor:cursor+n]
            cursor+=n
            if len(chunk)!=n:raise AssertionError('missing NLI score')
            # Best matching source sentence is label-blind. It may accidentally
            # combine unrelated facts, so this is not a multi-hop proof.
            strengths.append({
                'top1_entailment':chunk[0],
                'best3_entailment':max(chunk),
            })
        answer_source=r69.predictions(row['response'],row['source'])
        lexical=any(answer_source['content_overlap'])
        flags={
            'nli_top1_50':any(s['top1_entailment']<.50 for s in strengths),
            'nli_top3_50':any(s['best3_entailment']<.50 for s in strengths),
            'nli_top3_80':any(s['best3_entailment']<.80 for s in strengths),
            'frozen_lexical_55':lexical,
        }
        for policy,pred in flags.items():
            by_policy[policy].append({
                'source_id':row['source_id'],
                'pred':bool(pred),
                'gold':row['human_positive'],
                'strict_gold':row['strict_positive'],
                'human_positive_within_examined_sentences':
                    row['human_positive_within_examined_sentences']})
        sample_confidence.append({
            'min_top1_entailment':min((s['top1_entailment'] for s in strengths),default=1),
            'min_best3_entailment':min((s['best3_entailment'] for s in strengths),default=1),
        })
    if cursor!=len(values):
        raise AssertionError('NLI scores not aligned to response sentence pairs')
    return by_policy,sample_confidence


def metric(items,strict=False):
    tp=fp=fn=tn=0
    for item in items:
        truth=item['strict_gold'] if strict else item['gold']
        pred=item['pred']
        tp+=bool(pred and truth)
        fp+=bool(pred and not truth)
        fn+=bool(not pred and truth)
        tn+=bool(not pred and not truth)
    total=tp+fp+fn+tn
    prec=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    fpr=fp/(fp+tn) if fp+tn else 0
    return {
        'n':total,'tp':tp,'fp':fp,'fn':fn,'tn':tn,
        'precision':round(prec,5),'recall':round(recall,5),
        'false_positive_rate':round(fpr,5),
        'f1':round(2*prec*recall/(prec+recall),5) if prec+recall else 0}


def group_bootstrap(items,reps=1000,seed=7206):
    import random
    group=defaultdict(list)
    for x in items:group[x['source_id']].append(x)
    names=sorted(group)
    if len(names)<2:return None
    rng=random.Random(seed)
    differences=[]
    for _ in range(reps):
        sample=[r for _ in names
                for r in group[names[rng.randrange(len(names))]]]
        differences.append(metric(sample)['f1'])
    differences.sort()
    return [
        round(differences[int(.025*(reps-1))],5),
        round(differences[int(.975*(reps-1))],5)]


def select_r70_partition(response,source,r69):
    r70=dynamic('r70_for72',R70)
    source_map,old,heldout=r70.split_sources(response,source,r69)
    selected=[row for row in response
              if row['split']=='test'
              and str(row['source_id']) in heldout
              and row.get('quality')=='good']
    if len(heldout)!=HELDOUT_COUNT:
        raise ValueError('unexpected fixed R70 group count')
    if not selected:raise ValueError('no QA test records')
    return selected,source_map,heldout


def evaluate(responses,sources,model_bundle=None):
    r69=dynamic('r69_for72',R69)
    selected,source_map,heldout=select_r70_partition(responses,sources,r69)
    pairs,records=claim_rows(selected,source_map,r69)
    if not pairs:raise ValueError('no model pairs')
    tok,model,torch,entail_idx,labels=model_bundle or get_model()
    values,runtime=infer_pairs(pairs,tok,model,torch,entail_idx)
    predictions,conf=score_from_entailments(values,records,r69)
    outcomes={}
    for policy,rows in predictions.items():
        outcomes[policy]={
            'inclusive':metric(rows),
            'implicit_true_excluded':metric(rows,strict=True),
            'source_group_bootstrap_f1_95pct':group_bootstrap(rows)
        }
    return {
        'model':MODEL,'revision':MODEL_REVISION,
        'label_mapping':labels,'model_library':'transformers AutoModelForSequenceClassification',
        'model_max_tokens':MAX_LENGTH,'max_evaluated_response_fragments':MAX_CLAIMS,
        'max_premises_per_fragment':MAX_PREMISES,
        'evaluation_source_id_digest_sha256':hashlib.sha256(
            '\n'.join(sorted(heldout)).encode()).hexdigest(),
        'partition':'previously inspected Round 70 remaining 22 RAGTruth QA test source groups; NOT independent untouched generalization',
        'source_groups':len(heldout),
        'quality_good_response_count':len(records),
        'human_unsupported_response_count':sum(x['human_positive'] for x in records),
        'human_unsupported_within_first_eight_fragments':sum(
            x['human_positive_within_examined_sentences'] for x in records),
        'results':outcomes,
        'resource':runtime,
        'source_fragment_count':sum(len(source_segments(
            r69.source_text(source_map[sid]))) for sid in heldout),
        'limitations':[
            'pretrained generic NLI model, NOT trained on RAGTruth; same QA test source groups already examined for lexical rules',
            'sentence splitting is not atomic claim extraction; one sentence may contain multiple facts',
            'premise selection based on lexical content overlap; best-of-three premise scoring is not multihop entailment',
            'no gold labels affect premise selection or model inference, fixed model checkpoint and thresholds',
            'at most eight response fragments and three source windows per fragment; omitted claims recorded',
            'pair truncation at 384 model tokens and source window char splitting limit factual completeness',
            'CPU forward wall time excludes tokenizer, source indexing, input download, model load and machine startup',
            'no causal provenance, grounded generation, storage/index physical I/O or protection against adversarial claims',
            'human labels refer to faithfulness against source; strict implicit_true target separately evaluated',
        ]}
    

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=dynamic('r69_load72',R69)
    responses,rp=r69.download('dataset/response.jsonl')
    sources,sp=r69.download('dataset/source_info.jsonl')
    data=evaluate(responses,sources)
    data['input_git_blob_digests']={
        'responses':rp['git_blob'],'sources':sp['git_blob']}
    Path(args.out).write_text(json.dumps(data,indent=2)+'\n')
    print('ROUND72',json.dumps({
        'source_groups':data['source_groups'],'responses':data['quality_good_response_count'],
        'results':data['results'],'resources':data['resource'],
        'labels':data['label_mapping']},sort_keys=True))


if __name__=='__main__':main()
