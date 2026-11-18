#!/usr/bin/env python3
"""R76: strong in-domain LettuceDetect span-verifier baseline on R72 cohort.

LettuceDetect is an EXISTING published detector fine-tuned on RAGTruth.
It is therefore an in-domain supervised reference, not independent transfer
or CDG originality. Its architecture and tokenizer/weights are pinned.
All source and generated texts remain transient; only aggregate confusion,
cost, source identity and alignment audit are published.

The input budget and model size differ from R72's generic NLI; CPU runtimes
are descriptive and not a controlled per-token superiority comparison.
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
from pathlib import Path
from collections import Counter,defaultdict

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
R73=HERE.parent/'round-73'/'byte_exact_windows.py'
MODEL_ID='KRLabsOrg/lettucedect-base-modernbert-en-v1'
MODEL_REVISION='0ff0f0dd23052cf751dae374f57a539aa092e772'
MODEL_LICENSE='MIT'
PACKAGE='lettucedetect'
VERSION='0.2.3'
MAX_TOKENS=2048
BATCH_SIZE=4
SOURCE_WORD_WINDOW=150
SUMMARY_MAX_WINDOWS=96
TASKS=('QA','Summary')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


def assemble_context(source_row,r69):
    task=source_row.get('task_type')
    if task not in TASKS:
        raise ValueError('unsupported source task')
    original=r69.source_text(source_row)
    if not original.strip():raise ValueError('empty source')
    if task=='QA':
        # Source has already been provided as numbered passages. Split them
        # but do not rewrite substantive passage text or consult any gold labels.
        pieces=[p.strip() for p in re.split(
            r'(?i)(?=\bpassage\s+\d+\s*:)',original) if p.strip()]
        info=source_row['source_info']
        question=info.get('question') if isinstance(info,dict) else None
        return pieces,question,{
            'source_total_words':len(original.split()),
            'source_used_words':len(original.split()),
            'source_limited':False,
            'passage_chunks':len(pieces),
        }
    # Summary articles are often long. Use non-overlapping source word windows
    # as passage chunks so package's context chunking can preserve source text.
    words=original.split()
    visible=words[:SUMMARY_MAX_WINDOWS*SOURCE_WORD_WINDOW]
    chunks=[' '.join(visible[p:p+SOURCE_WORD_WINDOW])
            for p in range(0,len(visible),SOURCE_WORD_WINDOW)]
    return chunks,None,{
        'source_total_words':len(words),
        'source_used_words':len(visible),
        'source_limited':len(visible)<len(words),
        'passage_chunks':len(chunks),
    }


def text_mask(row,r69):
    full,strict,issues=r69.annotated_masks(row)
    if issues:raise ValueError('invalid human span offsets')
    return full,strict


def make_detector():
    import torch
    from huggingface_hub import HfApi,snapshot_download
    from lettucedetect.models.inference import HallucinationDetector
    torch.set_num_threads(2)
    snapshot_info=HfApi().model_info(MODEL_ID,revision=MODEL_REVISION)
    if snapshot_info.sha!=MODEL_REVISION:
        raise ValueError('LettuceDetect snapshot identity changed')
    t0=time.perf_counter()
    path=snapshot_download(MODEL_ID,revision=MODEL_REVISION)
    detector=HallucinationDetector(
        method='transformer',model_path=path,
        device='cpu',max_length=MAX_TOKENS)
    model=detector.detector.model
    model.eval()
    return detector,{
        'repository':MODEL_ID,
        'snapshot_sha':snapshot_info.sha,
        'model_parameters':sum(x.numel() for x in model.parameters()),
        'loaded_seconds':round(time.perf_counter()-t0,3),
    }


def audited_prediction(detector,passages,answer,question):
    start=time.perf_counter()
    raw=detector.predict(context=passages,answer=answer,question=question,
                         output_format='spans',min_confidence=0.0)
    elapsed=time.perf_counter()-start
    if not isinstance(raw,list):
        raise ValueError('detector did not return a span list')
    spans=[]
    for item in raw:
        lo,hi=item.get('start'),item.get('end')
        if not (isinstance(lo,int) and isinstance(hi,int)
                and 0<=lo<hi<=len(answer)):
            raise ValueError('predicted span offset outside original answer')
        if item.get('text') is not None and item['text']!=answer[lo:hi]:
            raise ValueError('predicted substring does not match answer')
        if not math.isfinite(float(item.get('confidence',0))):
            raise ValueError('nonfinite predicted confidence')
        spans.append((lo,hi))
    mask=[False]*len(answer)
    for lo,hi in spans:
        for i in range(lo,hi):
            mask[i]=True
    return mask,{
        'elapsed_wall_sec':elapsed,
        'spans':len(spans),
        'predicted_chars':sum(mask),
    }


def confusion(a,b):
    if len(a)!=len(b):raise ValueError('mask shape mismatch')
    tp=sum(bool(x and y) for x,y in zip(a,b))
    fp=sum(bool(x and not y) for x,y in zip(a,b))
    fn=sum(bool(not x and y) for x,y in zip(a,b))
    tn=sum(bool(not x and not y) for x,y in zip(a,b))
    return {'tp':tp,'fp':fp,'fn':fn,'tn':tn}


def micro(scores,r69):
    overall=Counter()
    for item in scores:
        overall.update(item)
    tp,fp,fn,tn=[int(overall[key]) for key in ('tp','fp','fn','tn')]
    return {
        'tp':tp,'fp':fp,'fn':fn,'tn':tn,
        **r69.ratios(tp,fp,fn),
        'false_positive_rate':round(fp/(fp+tn),5) if fp+tn else 0,
    }


def sample_rows(all_rows,source_rows):
    r72=load('r72_sample76',R72)
    r73=load('r73_sample76',R73)
    chosen,byid,meta=r72.group_sample(all_rows,source_rows)
    if meta['source_ids_sha256']!=r73.LOCKED_IDS_SHA256:
        raise ValueError('sample differs from R72/R73 source identity lock')
    if len(chosen)!=141 or meta['source_groups']!={'QA':8,'Summary':16}:
        raise ValueError('expected frozen R72 QA+Summary model reference sample')
    return chosen,byid,meta


def evaluate(rows,byid,detector,r69):
    outcomes={task:{'response':[],'char':[],
                    'strict_response':[],'strict_char':[],
                    'wall_seconds':[],'predicted_spans':[],
                    'tokens_prechunk_proxy':[],
                    'source_chunk_limit_count':0,
                    'source_words_visible':0,
                    'source_words_total':0,
                    'model_predicted_answer_chars':0,
                    'human_positive_responses':0}
              for task in (*TASKS,'all')}
    total=len(rows)
    model=detector.detector
    tokenizer=model.tokenizer
    for row in rows:
        task=byid[str(row['source_id'])]['task_type']
        passages,question,source_meta=assemble_context(
            byid[str(row['source_id'])],r69)
        # This is a PRECHUNK tokenizer workload proxy, not a count of actual
        # internal model forward chunks when long contexts are regrouped.
        input_text=' '.join(passages)+(question or '')+row['response']
        approx_tokens=len(tokenizer.encode(input_text,add_special_tokens=True))
        mask,raw=audited_prediction(detector,passages,row['response'],question)
        gold,strict=text_mask(row,r69)
        for target in (task,'all'):
            block=outcomes[target]
            block['char'].append(confusion(mask,gold))
            block['strict_char'].append(confusion(mask,strict))
            block['response'].append(confusion([any(mask)],[any(gold)]))
            block['strict_response'].append(confusion([any(mask)],[any(strict)]))
            block['wall_seconds'].append(raw['elapsed_wall_sec'])
            block['predicted_spans'].append(raw['spans'])
            block['tokens_prechunk_proxy'].append(approx_tokens)
            block['source_chunk_limit_count']+=int(source_meta['source_limited'])
            block['source_words_visible']+=source_meta['source_used_words']
            block['source_words_total']+=source_meta['source_total_words']
            block['model_predicted_answer_chars']+=raw['predicted_chars']
            block['human_positive_responses']+=int(any(gold))
    aggregated={}
    for task,block in outcomes.items():
        aggregated[task]={
            'n':len(block['response']),
            'human_positive_responses':block['human_positive_responses'],
            'response_level':micro(block['response'],r69),
            'character_level':micro(block['char'],r69),
            'implicit_true_excluded_response':micro(block['strict_response'],r69),
            'implicit_true_excluded_character':micro(block['strict_char'],r69),
            'inference_wall_seconds_sum':round(sum(block['wall_seconds']),3),
            'median_per_response_wall_seconds':round(
                statistics.median(block['wall_seconds']),3),
            'total_prediction_spans':sum(block['predicted_spans']),
            'estimated_input_tokens_prechunk':sum(block['tokens_prechunk_proxy']),
            'source_limited_responses':block['source_chunk_limit_count'],
            'source_words_visible':block['source_words_visible'],
            'source_words_total':block['source_words_total'],
            'predicted_positive_answer_chars':block['model_predicted_answer_chars'],
        }
    return aggregated


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=ap.parse_args()
    r69=load('r69_load76',R69)
    responses,rp=r69.download('dataset/response.jsonl')
    sources,sp=r69.download('dataset/source_info.jsonl')
    chosen,byid,sample=sample_rows(responses,sources)
    model,model_info=make_detector()
    outcomes=evaluate(chosen,byid,model,r69)
    result={
        'model':model_info,'package':PACKAGE,'version':VERSION,
        'model_max_context_tokens':MAX_TOKENS,
        'R72_frozen_source_sample':sample,
        'dataset_git_revision':r69.REVISION,
        'dataset_response_blob':rp['git_blob'],
        'dataset_source_blob':sp['git_blob'],
        'task_outcomes':outcomes,
        'scope':'published task-specific RAGTruth-trained model as a strong in-domain baseline, NOT new independent generalization',
        'limitations':[
            'LettuceDetect was trained on RAGTruth original training split; test is in-domain and prior work already reports its effectiveness',
            'comparison with R72 generic NLI is NOT matched for model architecture, training corpus, token budget or compute',
            'R72 used 384-token NLI input and here a 2048-token context; no per-token dominance claimed',
            'pre-chunk tokenizer counts include raw source and response, not exact internal chunked input tokens',
            'RAGTruth source-specific reader output is already generated; there is no CDG answer generation or hallucination reduction',
            'all annotations human-created source-faithfulness spans; implicit_true scored both ways',
            'source passage count and detector model footprint may dominate compressed evidence storage costs',
            'source texts and original model responses are downloaded transiently; only compact metrics and digests are saved',
            'QA passage splitting and summarization source windows alter presentation of original source; this is a local replication, not authors official benchmark reproduction',
        ],
    }
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND76',json.dumps({
        'model':model_info,
        'sample':sample,
        'task_response':{k:v['response_level'] for k,v in outcomes.items()},
        'task_character':{k:v['character_level'] for k,v in outcomes.items()},
        'wall_seconds':outcomes['all']['inference_wall_seconds_sum']},sort_keys=True))


if __name__=='__main__':
    main()
