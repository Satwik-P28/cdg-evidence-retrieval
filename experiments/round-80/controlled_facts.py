#!/usr/bin/env python3
"""R80: controlled, template-oracle support perturbations versus published checkers.

This is a synthetic mechanism stress test, NOT human-annotated real RAG or
independent generalization. Models pretrained by others, SHA-pinned; no training.
Each fixed claim has 3 source alternatives: supported, explicitly contradicted,
and unknown. Evaluate 4 relation families with exact compressed source receipts.
"""
from __future__ import annotations
import argparse, gc, hashlib, importlib.util, json, math, statistics, sys, time
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R72=HERE.parent/'round-72'/'zero_shot_nli.py'
R76=HERE.parent/'round-76'/'lettuce_reference.py'
MINICHECK_ID='lytang/MiniCheck-DeBERTa-v3-Large'
# Historical immutable revision linked from official HF model card; verified at runtime.
MINICHECK_SHA='05782341a53df45bf7bee868863563907e083ee0'
FAMILIES=('location','date','relation','multihop')
STATES=('supported','contradicted','unknown')
MODELS=('lexical','nli','minicheck','lettuce','mc_and_nli','mc_and_lettuce','mc_or_nli')
DATA_SALT='CDG-R80-MULTI-CONTROL-CLAIM-v1'
NAME_PAIRS=(
 ('Aster','Borel','Lydon','Merton','Oriel','2018','2024'),
 ('Belen','Corin','Navor','Tresson','Pellor','2017','2025'),
 ('Cedar','Dalen','Orwen','Pelsa','Fendol','2016','2023'),
 ('Dover','Elen','Rivon','Warton','Solmer','2015','2022'),
 ('Eldin','Faris','Tirlen','Vennor','Winsta','2014','2021'),
 ('Falcon','Garen','Uvel','Korem','Grenis','2013','2020'),
 ('Grove','Haven','Valen','Dexter','Cenbar','2012','2019'),
 ('Helix','Iorin','Weslin','Harlon','Merrow','2011','2018'),
 ('Ivory','Jaren','Xelmar','Norven','Zentar','2010','2017'),
 ('Juno','Keres','Yarven','Olston','Berdan','2009','2016'),
)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def new_case(i,family,state):
    a,b,city,alt_city,warehouse,year,alt_year=NAME_PAIRS[i]
    asset=a+' Initiative'
    other=b+' Initiative'
    if family=='location':
        claim=f'The operating center for {asset} is in {city}.'
        variants={
            'supported':f'The registry lists the operating center for {asset} in {city}, not in {alt_city}.',
            'contradicted':f'The registry lists the operating center for {asset} in {alt_city}, not in {city}.',
            'unknown':f'The registry lists the backup center for {other} in {alt_city}. The location of the operating center for {asset} is not listed.',
        }
    elif family=='date':
        claim=f'{asset} began service in {year}.'
        variants={
            'supported':f'The official first-service year of {asset} was {year}, not {alt_year}.',
            'contradicted':f'The official first-service year of {asset} was {alt_year}, not {year}.',
            'unknown':f'The official inspection year of {asset} was {year}. Its first-service year is not listed in this record.',
        }
    elif family=='relation':
        claim=f'{asset} supervises {other}.'
        variants={
            'supported':f'The organization chart lists {asset} as the supervisor of {other}. {other} does not supervise {asset}.',
            'contradicted':f'The organization chart lists {other} as the supervisor of {asset}. {asset} does not supervise {other}.',
            'unknown':f'The organization chart lists {asset} and {other} as separately reviewed initiatives. Their supervisory arrangement is not specified.',
        }
    elif family=='multihop':
        claim=f'The designated warehouse for {asset} is in {city}.'
        variants={
            'supported':f'The designated warehouse for {asset} is {warehouse} Depot. {warehouse} Depot is in {city}.',
            'contradicted':f'The designated warehouse for {asset} is {warehouse} Depot. {warehouse} Depot is in {alt_city}, not in {city}.',
            'unknown':f'{warehouse} Depot is in {city}. The record does not specify the designated warehouse for {asset}.',
        }
    else:
        raise ValueError('invalid family')
    prefix='Fictional registry extract. Every statement below concerns one frozen reporting period. '
    doc=prefix+variants[state]
    case_id=f'{i:02d}-{family}-{state}'
    return {'id':case_id,'entity_group':f'entity-{i:02d}','family':family,
            'state':state,'supported':state=='supported','claim':claim,
            'doc':doc}


def generate():
    cases=[new_case(i,family,state)
           for i in range(len(NAME_PAIRS)) for family in FAMILIES for state in STATES]
    if len(cases)!=120 or len({x['id'] for x in cases})!=120:
        raise AssertionError('cohort drift')
    for i in range(len(NAME_PAIRS)):
        for family in FAMILIES:
            trio=[x for x in cases if x['entity_group']==f'entity-{i:02d}'
                  and x['family']==family]
            if len(trio)!=3 or len({x['claim'] for x in trio})!=1:
                raise AssertionError('unpaired intervention')
            if set(x['state'] for x in trio)!=set(STATES):
                raise AssertionError('unbalanced contrast')
    return cases


def sha_cases(cases):
    src='\n'.join(json.dumps(row,sort_keys=True,ensure_ascii=False)
                  for row in cases).encode('utf8')
    return hashlib.sha256(src).hexdigest()


def archived_docs(cases):
    """Same source identity oracle on both storage methods; no retrieval."""
    r48=load('cdg_r48_r80',R48)
    blobs=[x['doc'].encode('utf8') for x in cases]
    archives={mode:r48.VersionedReader(blobs,mode,'binary-zlib')
              for mode in ('whole','gear512')}
    activated=defaultdict(list)
    reads=0
    for idx,case in enumerate(cases):
        original=blobs[idx]
        for mode,reader in archives.items():
            receipt=reader.receipt(idx,0,len(original))
            back,traffic=reader.read(receipt,pin_generation=idx)
            if back!=original or hashlib.sha256(back).digest()!=hashlib.sha256(original).digest():
                raise AssertionError('source receipt failed')
            activated[mode].append(traffic)
            reads+=1
    return [x.decode('utf8') for x in blobs],{
        'verified_receipts':reads,
        'archive_persistent_bytes':{mode:reader.size() for mode,reader in archives.items()},
        'mean_logical_activation_bytes':{
            mode:round(statistics.mean(activated[mode]),3) for mode in archives},
        'source_utf8_bytes':sum(map(len,blobs)),
        'note':'Source identity supplied by template oracle; in-memory archive readers, no FTS5 or SSD IO.',
    }


def lexical_scores(cases,docs):
    r69=load('cdg_r69_r80',R69)
    return [int(not r69.sentence_flags(c['claim'],doc)['content_overlap'])
            for c,doc in zip(cases,docs)]


def load_pinned_model(name,sha):
    from huggingface_hub import HfApi
    from transformers import AutoModelForSequenceClassification,AutoTokenizer
    import torch
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise AssertionError('model revision must be full git commit')
    info=HfApi().model_info(name,revision=sha)
    if info.sha!=sha:
        raise AssertionError('model identity was not pinned')
    tok=AutoTokenizer.from_pretrained(name,revision=sha,use_fast=True)
    model=AutoModelForSequenceClassification.from_pretrained(name,revision=sha)
    model.eval()
    torch.set_num_threads(2)
    return tok,model,torch,int(sum(x.numel() for x in model.parameters()))


def nli_scores(cases,docs):
    r72=load('cdg_r72_r80',R72)
    lock=json.loads(r72.MODEL_LOCK.read_text())
    tok,model,torch,params=load_pinned_model(r72.MODEL_ID,lock['revision'])
    labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
    if set(labels.values())!={'contradiction','entailment','neutral'}:
        raise ValueError('NLI label map changed')
    idx=next(k for k,v in labels.items() if v=='entailment')
    probs=[];num_tokens=0
    t0=time.perf_counter()
    for st in range(0,len(cases),12):
        docs_batch=docs[st:st+12]
        claims=[x['claim'] for x in cases[st:st+12]]
        toks=tok(docs_batch,claims,return_tensors='pt',padding=True,
                 truncation='only_first',max_length=384)
        num_tokens+=int(toks['attention_mask'].sum().item())
        with torch.inference_mode():
            out=torch.softmax(model(**toks).logits,dim=-1)[:,idx].tolist()
        probs.extend(float(x) for x in out)
    wall=time.perf_counter()-t0
    del model
    gc.collect()
    return probs,{'name':r72.MODEL_ID,'revision':lock['revision'],
                  'params':params,'cpu_inference_seconds':round(wall,3),
                  'actual_input_tokens':num_tokens,'rule':'entailment probability >= 0.50'}


def minicheck_scores(cases,docs):
    """Official MiniCheck-DeBERTa single-chunk input formulation:
    tokenize(doc + tokenizer.eos_token + claim), 2048 cap, P(class 1).
    No NLTK sentence chunks needed for these one-sentence, short documents.
    This is a direct one-chunk forward replication, not a call to their CLI.
    """
    tok,model,torch,params=load_pinned_model(MINICHECK_ID,MINICHECK_SHA)
    if not tok.eos_token:
        raise AssertionError('MiniCheck tokenizer lacks EOS separator')
    probs=[];total_tokens=0;truncated=0
    t0=time.perf_counter()
    for st in range(0,len(cases),8):
        batch=[doc+tok.eos_token+case['claim']
               for doc,case in zip(docs[st:st+8],cases[st:st+8])]
        all_len=[len(tok.encode(t,add_special_tokens=True)) for t in batch]
        truncated+=sum(n>2048 for n in all_len)
        toks=tok(batch,max_length=2048,truncation=True,padding=True,
                 return_tensors='pt')
        total_tokens+=int(toks['attention_mask'].sum().item())
        with torch.inference_mode():
            out=torch.softmax(model(**toks).logits,dim=-1)[:,1].tolist()
        probs.extend(float(x) for x in out)
    wall=time.perf_counter()-t0
    del model
    gc.collect()
    return probs,{'name':MINICHECK_ID,'revision':MINICHECK_SHA,'params':params,
                  'cpu_inference_seconds':round(wall,3),
                  'actual_input_tokens':total_tokens,'truncated_inputs':truncated,
                  'rule':'published MiniCheck single-chunk P(supported) > 0.50',
                  'replication':'author-faithful short-doc input, independently implemented forward pass'}


def lettuce_scores(cases,docs):
    r76=load('cdg_r76_r80',R76)
    detector,info=r76.make_detector()
    warnings=[];time_s=0;raw_chars=0;ans_chars=0
    t0=time.perf_counter()
    for case,doc in zip(cases,docs):
        mask,detail=r76.audited_prediction(detector,[doc],case['claim'],None)
        warnings.append(int(any(mask)))
        time_s+=detail['elapsed_wall_sec']
        raw_chars+=sum(mask)
        ans_chars+=len(mask)
    wall=time.perf_counter()-t0
    del detector
    gc.collect()
    return [1-v for v in warnings],{
        'name':r76.MODEL_ID,'revision':info['snapshot_sha'],
        'params':info['model_parameters'],'cpu_forward_wall_seconds':round(time_s,3),
        'total_scoring_wall_seconds':round(wall,3),'predicted_unsupported_chars':raw_chars,
        'total_answer_chars':ans_chars,'rule':'supported iff no unsupported span',
        'prior_training':'original RAGTruth train partition, not trained on these synthetic templates'}


def confusion(pred,cases):
    if len(pred)!=len(cases):
        raise ValueError('length mismatch')
    tp=sum(int(bool(p) and c['supported']) for p,c in zip(pred,cases))
    fp=sum(int(bool(p) and not c['supported']) for p,c in zip(pred,cases))
    fn=sum(int(not bool(p) and c['supported']) for p,c in zip(pred,cases))
    tn=sum(int(not bool(p) and not c['supported']) for p,c in zip(pred,cases))
    precision=tp/(tp+fp) if tp+fp else 0
    recall=tp/(tp+fn) if tp+fn else 0
    specificity=tn/(tn+fp) if tn+fp else 0
    return {'n':len(cases),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'accuracy':round((tp+tn)/max(1,len(cases)),5),
            'balanced_accuracy':round((recall+specificity)/2,5),
            'supported_recall':round(recall,5),
            'unsupported_rejection_rate':round(specificity,5),
            'precision':round(precision,5),
            'f1':round(2*precision*recall/(precision+recall),5) if precision+recall else 0}


def paired_stats(cases,pred):
    results={}
    for family in (*FAMILIES,'all'):
        inds=[i for i,c in enumerate(cases) if family=='all' or c['family']==family]
        rows=[cases[i] for i in inds]
        guesses=[pred[i] for i in inds]
        obj=confusion(guesses,rows)
        obj['states']={state:{
            'n':sum(x['state']==state for x in rows),
            'accepted':sum(int(bool(p)) for p,x in zip(guesses,rows) if x['state']==state),
        } for state in STATES}
        results[family]=obj
    return results


def compare(cases,preds,meta,archive):
    if any(len(vals)!=len(cases) for vals in preds.values()):
        raise AssertionError('prediction lengths do not match frozen cases')
    stats={name:paired_stats(cases,vals) for name,vals in preds.items()}
    groups=defaultdict(list)
    for i,c in enumerate(cases):
        groups[c['entity_group']].append(i)
    # Per paired triple: correct iff all 3 intervention statuses classified.
    contrast={}
    for name,vals in preds.items():
        exactly=0;fragile_support=0;false_accept_unknown=0
        per_group=[]
        for ix in groups.values():
            full=sum(int(bool(vals[i])==bool(cases[i]['supported'])) for i in ix)
            per_group.append(full/len(ix))
        for i in range(len(NAME_PAIRS)):
            for family in FAMILIES:
                ix=[j for j,c in enumerate(cases)
                    if c['family']==family and c['entity_group']==f'entity-{i:02d}']
                if all(bool(vals[j])==bool(cases[j]['supported']) for j in ix):
                    exactly+=1
                if vals[ix[0]]!=1: # cases generated supported,contradicted,unknown order
                    fragile_support+=1
                false_accept_unknown+=int(bool(vals[ix[2]]))
        contrast[name]={
            'fully_correct_support_contradiction_unknown_triples':exactly,
            'total_triples':len(NAME_PAIRS)*len(FAMILIES),
            'misclassified_supported_triples':fragile_support,
            'unknown_source_false_accepts':false_accept_unknown,
            'mean_entity_group_accuracy':round(statistics.mean(per_group),5),
        }
    return {
        'case_sha256':sha_cases(cases),'count':len(cases),
        'generated_entity_groups':len(NAME_PAIRS),
        'interventions_per_claim':3,
        'family_counts':dict(Counter(c['family'] for c in cases)),
        'state_counts':dict(Counter(c['state'] for c in cases)),
        'source_words_mean':round(statistics.mean(len(c['doc'].split()) for c in cases),3),
        'source_words_range':[min(len(c['doc'].split()) for c in cases),
                              max(len(c['doc'].split()) for c in cases)],
        'claim_words_mean':round(statistics.mean(len(c['claim'].split()) for c in cases),3),
        'archives':archive,'models':meta,'results':stats,'matched_triples':contrast,
        'limitations':[
          'controlled labels are template-derived logical oracle, NOT independent human annotations or naturally generated hallucinations',
          'fictional short documents and repeated templates can be solved by rules, not evidence for real cross-domain reliability',
          'classification supported-versus-unsupported combines explicit contradiction and absence; report their strata separately',
          'all model thresholds were fixed at 0.50 before test; no fitting to template labels, but templates and analyses are publicly visible',
          'published pretrained models have different training data and budgets, no matched model cost or proof of comparative architecture superiority',
          'MiniCheck forward-input replication is author-equivalent for single document chunks, not full official library/long-document benchmark',
          'LettuceDetect uses no question on an already separated one-sentence claim, unlike its official RAGTruth QA prompting',
          'known oracle source identity, no real retrieval, no user question answering or generated answer correction',
          'warm-memory archive source path; no physical cold SSD, update overhead, model RAM or full index storage',
          'no scientific novelty or universal performance theorem follows from these toy tests',
        ],
    }


def run():
    cases=generate()
    docs,archives=archived_docs(cases)
    lex=lexical_scores(cases,docs)
    nli,nli_meta=nli_scores(cases,docs)
    mc,mc_meta=minicheck_scores(cases,docs)
    ld,ld_meta=lettuce_scores(cases,docs)
    scores={
        'lexical':lex,
        'nli':[int(x>=.5) for x in nli],
        'minicheck':[int(x>.5) for x in mc],
        'lettuce':ld,
    }
    scores['mc_and_nli']=[int(x and y) for x,y in zip(scores['minicheck'],scores['nli'])]
    scores['mc_and_lettuce']=[int(x and y) for x,y in zip(scores['minicheck'],scores['lettuce'])]
    scores['mc_or_nli']=[int(x or y) for x,y in zip(scores['minicheck'],scores['nli'])]
    meta={
        'lexical':{'rule':'R69 content overlap support if >=0.55, no model'},
        'nli':nli_meta,'minicheck':mc_meta,'lettuce':ld_meta,
        'mc_and_nli':{'rule':'predeclared no training; acceptance only if both MC and NLI accept',
                      'inference_cost':'sum of both underlying models, no speed-up'},
        'mc_and_lettuce':{'rule':'predeclared no training; acceptance only if both MC and Lettuce accept',
                          'inference_cost':'sum of both underlying models, no speed-up'},
        'mc_or_nli':{'rule':'predeclared no training; acceptance if either MC or NLI accepts',
                     'inference_cost':'sum of both underlying models, no speed-up'},
    }
    result=compare(cases,scores,meta,archives)
    print('ROUND80',json.dumps({
        'case_sha256':result['case_sha256'],'n':result['count'],
        'methods':{k:v['all'] for k,v in result['results'].items()},
        'by_family':{k:{fam:{'balanced_accuracy':v[fam]['balanced_accuracy'],
                              'states':v[fam]['states']} for fam in FAMILIES}
                     for k,v in result['results'].items()},
        'model_costs':meta,
        'archive':archives,
    },sort_keys=True))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    result=run()
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
