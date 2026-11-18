#!/usr/bin/env python3
"""R80 supplemental: reproduce released FactCG-DeBERTa-v3-Large single-chunk input.

Identical 120 synthetic intervention docs/claims as controlled_facts.py.
The authors' released FactCG-DBT model is pin-locked. This is a direct
single-chunk forward replication, not reproduction of the paper benchmark.
"""
from __future__ import annotations
import argparse, gc, json, statistics, time
from pathlib import Path
from controlled_facts import generate, sha_cases, archived_docs, compare

HERE=Path(__file__).resolve().parent
FACTCG_ID='yaxili96/FactCG-DeBERTa-v3-Large'
FACTCG_SHA='7582b255f0b45a1be2db6fff5076d0e8ea7aa072'
# Exact template string from derenlei/FactCG factcg/utils.py at main.
INSTRUCTION='{text_a}\n\nChoose your answer: based on the paragraph above can we conclude that "{text_b}"?\n\nOPTIONS:\n- Yes\n- No\nI think the answer is '


def prompt(doc,claim):
    return INSTRUCTION.format(text_a=doc,text_b=claim)


def infer(cases,docs):
    import torch
    from huggingface_hub import HfApi
    from transformers import AutoTokenizer,AutoConfig,AutoModelForSequenceClassification
    info=HfApi().model_info(FACTCG_ID,revision=FACTCG_SHA)
    if info.sha!=FACTCG_SHA:raise AssertionError('FactCG model not pinned')
    config=AutoConfig.from_pretrained(
        FACTCG_ID,revision=FACTCG_SHA,num_labels=2,
        finetuning_task='text-classification')
    config.problem_type='single_label_classification'
    tokenizer=AutoTokenizer.from_pretrained(
        FACTCG_ID,revision=FACTCG_SHA,use_fast=True)
    model=AutoModelForSequenceClassification.from_pretrained(
        FACTCG_ID,revision=FACTCG_SHA,config=config)
    model.eval()
    torch.set_num_threads(2)
    tokenizer.pad_token=tokenizer.eos_token
    if not tokenizer.pad_token:raise AssertionError('missing model EOS pad')
    params=sum(x.numel() for x in model.parameters())
    probabilities=[];tokens=0;truncations=0
    t0=time.perf_counter()
    for start in range(0,len(cases),8):
        batch=[prompt(d,c['claim'])
               for d,c in zip(docs[start:start+8],cases[start:start+8])]
        truncations+=sum(len(tokenizer.encode(x,add_special_tokens=True))>2048
                         for x in batch)
        enc=tokenizer(batch,max_length=2048,truncation='only_first',
                      padding='longest',return_tensors='pt')
        tokens+=int(enc['attention_mask'].sum().item())
        with torch.inference_mode():
            probs=torch.softmax(model(**enc).logits,dim=-1)[:,1].tolist()
        probabilities.extend(float(x) for x in probs)
    smoke_cases=[
        ('exact_geography','London is in the United Kingdom.','London is in the United Kingdom.',1),
        ('wrong_geography','London is in the United Kingdom, not in France.','London is in France.',0),
        ('minicheck_author_positive',
         'A group of students gather in the school library to study for their upcoming final exams.',
         'The students are preparing for an examination.',1),
        ('minicheck_author_negative',
         'A group of students gather in the school library to study for their upcoming final exams.',
         'The students are on vacation.',0),
        ('exact_fictional',
         'The operating center for Aster Initiative is in Lydon.',
         'The operating center for Aster Initiative is in Lydon.',1),
        ('explicit_fictional_negative',
         'The operating center for Aster Initiative is in Merton, not in Lydon.',
         'The operating center for Aster Initiative is in Lydon.',0),
    ]
    smoke_inputs=[prompt(doc,claim) for _,doc,claim,_ in smoke_cases]
    smoke_tokens=tokenizer(smoke_inputs,max_length=2048,
                           truncation='only_first',padding='longest',
                           return_tensors='pt')
    with torch.inference_mode():
        smoke_probs=torch.softmax(model(**smoke_tokens).logits,dim=-1)[:,1].tolist()
    smoke_diagnostics=[{
        'id':entry[0],'expected_supported_by_contract':entry[3],
        'p_class1':round(float(prob),7),'predicted_supported_at_05':int(prob>.5),
    } for entry,prob in zip(smoke_cases,smoke_probs)]
    cost={'name':FACTCG_ID,'sha':FACTCG_SHA,'parameters':params,
          'model_wall_seconds_including_six_smoke_pairs':round(time.perf_counter()-t0,3),
          'diagnostic_smoke_examples':smoke_diagnostics,
          'actual_input_tokens':tokens,'truncated_inputs':truncations,
          'rule':'P(Yes / supported) > 0.50',
          'implementation':'original author instruction template; short single-chunk softmax positive class'}
    del model
    gc.collect()
    return probabilities,cost


def run():
    cases=generate()
    docs,storage=archived_docs(cases)
    probs,meta=infer(cases,docs)
    preds=[int(x>.5) for x in probs]
    positives=[float(p) for p,x in zip(probs,cases) if x['supported']]
    negatives=[float(p) for p,x in zip(probs,cases) if not x['supported']]
    auc=sum(float(a>b)+0.5*float(a==b)
            for a in positives for b in negatives)/(len(positives)*len(negatives))
    support_by_state={
        s:{'n':sum(x['state']==s for x in cases),
           'mean_probability':round(statistics.mean(
               p for p,x in zip(probs,cases) if x['state']==s),7),
           'min_probability':round(min(p for p,x in zip(probs,cases) if x['state']==s),7),
           'max_probability':round(max(p for p,x in zip(probs,cases) if x['state']==s),7)}
        for s in ('supported','contradicted','unknown')}
    # Test-label-optimized threshold is a DIAGNOSTIC ONLY: no holdout or
    # deployment claim may use this result.
    thresholds=sorted({0.0,0.5,1.0,*map(float,probs)})
    from controlled_facts import confusion
    explored=sorted(
        ((confusion([int(p>t) for p in probs],cases)['balanced_accuracy'],t)
         for t in thresholds),reverse=True)
    diagnostic_threshold={
        'test_label_optimized_best_balanced_accuracy':explored[0][0],
        'chosen_threshold':round(explored[0][1],8),
        'INVALID_FOR_GENERALIZATION':True,
    }
    result=compare(cases,{'factcg':preds},{'factcg':meta},storage)
    result['paper']='FactCG (Lei et al., NAACL 2025), not CDG-authored training'
    result['diagnostics']={
       'support_probabilities_by_state':support_by_state,
       'positive_vs_negative_auroc_template_oracle':round(auc,6),
       'post_hoc_oracle_threshold_only_for_diagnosis':diagnostic_threshold,
    }
    result['limitations']+=[
        'template-specific synthetic support labels, not naturally annotated test claims',
        'input follows FactCG official HF single-chunk forward template but does not call authors batch chunking package',
        'short sources do not test real long-context sentence chunk aggregation',
        'FactCG fine tuning uses graph-connected synthetic training; test fixtures are independently authored but also templated',
        'results compared to MiniCheck only when same case_sha256 and frozen test cases',
        'model input includes an instruction prompt unlike MiniCheck; token and latency costs are not matched',
        'six smoke cases test checkpoint behavior and run after main cases, not a human evaluation',
        'post-hoc label-optimized threshold intentionally diagnostic and disallowed as a deployable or heldout comparison',
    ]
    print('ROUND80_FACTCG',json.dumps({
        'sample_sha256':result['case_sha256'],
        'all':result['results']['factcg']['all'],
        'families':{
            k:result['results']['factcg'][k]
            for k in ('location','date','relation','multihop')},
        'triple':result['matched_triples']['factcg'],
        'model_cost':meta,
        'diagnostics':result['diagnostics'],
    },sort_keys=True))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'factcg-results.json'))
    args=p.parse_args()
    Path(args.out).write_text(json.dumps(run(),indent=2)+'\n')


if __name__=='__main__':
    main()
