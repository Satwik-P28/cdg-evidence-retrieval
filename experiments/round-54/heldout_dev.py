#!/usr/bin/env python3
"""Round 54: fixed, previously untouched HotpotQA distractor dev evaluation.

R25 policies are frozen. Compare plain BM25, MMR, exact-title bridge,
precomputed-title-link bridge and a prespecified question-text-only gate.
No gold labels are passed into selection. The official dev setting supplies
gold-bearing candidate paragraphs; this is not open-corpus retrieval or QA.
Source is downloaded transiently and SHA-256 validated, never redistributed.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import statistics
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
R25=HERE.parent/'round-25'/'bridge_probe.py'
URL=('https://huggingface.co/datasets/namlh2004/hotpotqa/resolve/'
     '7e54db4656209750ff487f6fdf8e39a66dba136b/'
     'hotpot_dev_distractor_v1.json')
SHA256='e3da074df24e8369009918aa5cdbdd254dadcde4c63f7569d36afd6f2268caa8'
EXPECTED_SIZE=61065698
SAMPLE_SALT='CDG-R54-DEV-SHA256-LOCKED-v1'
FROZEN_K=(2,3,5)
FROZEN_BRIDGE_BONUS=2.0
FROZEN_SAMPLE_SIZE=512


def r25():
    spec=importlib.util.spec_from_file_location('cdg_round25_r54',R25)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_development():
    request=Request(URL,headers={'User-Agent':'CDG-research-replication/1.0'})
    with urlopen(request,timeout=180) as stream:
        blob=stream.read()
    if len(blob)!=EXPECTED_SIZE or hashlib.sha256(blob).hexdigest()!=SHA256:
        raise ValueError('Unexpected dev dataset length or SHA256; refuse evaluation')
    rows=json.loads(blob)
    if len(rows)!=7405:
        raise ValueError('Unexpected official distractor dev length')
    if any(not row.get('question') or not row.get('context') or
           not isinstance(row.get('supporting_facts'),list) for row in rows):
        raise ValueError('missing essential HotpotQA example fields')
    return rows


def support_reference_issue(row):
    """Return first structural annotation fault, never used by retrievers."""
    ctx={title:sents for title,sents in row['context']}
    for title,sid in row['supporting_facts']:
        if title not in ctx:
            return 'missing_document'
        if not isinstance(sid,int) or sid<0 or sid>=len(ctx[title]):
            return 'missing_sentence'
    return None


def integrity_audit(rows):
    counts={'valid':0,'missing_document':0,'missing_sentence':0}
    affected=[]
    for row in rows:
        issue=support_reference_issue(row)
        counts[issue or 'valid']+=1
        if issue and len(affected)<12:
            affected.append({'id':str(row.get('_id')),'fault':issue})
    return {'counts':counts,'first_12_affected':affected}


def locked_sample(data,size=FROZEN_SAMPLE_SIZE):
    if size<=0 or size>len(data):
        raise ValueError('invalid sample size')
    keys=[str(row['_id']) for row in data]
    if len(keys)!=len(set(keys)):
        raise ValueError('duplicate question ids')
    order=sorted(
        data,
        key=lambda row:(hashlib.sha256((SAMPLE_SALT+'|'+str(row['_id'])).encode()).hexdigest(),
                        str(row['_id'])))
    return order[:size]


def graph_rank(row,limit=5):
    """Same predeclared R25 title mention score; graph construction is charged."""
    helper=r25()
    context=row['context']
    if not context:return []
    texts=[title+' '+' '.join(sents) for title,sents in context]
    scores=helper.bm25_scores(row['question'],texts)
    titles=[' '+helper.canon(title)+' ' for title,_ in context]
    bodies=[' '+helper.canon(' '.join(sents))+' ' for _,sents in context]
    neighbors={i:{j for j,t in enumerate(titles)
                  if len(t)>4 and t in bodies[i]}
               for i in range(len(context))}
    selected=[]
    remaining=set(range(len(context)))
    while remaining and len(selected)<limit:
        best=None
        value=-float('inf')
        for idx in sorted(remaining):
            score=scores[idx]+(FROZEN_BRIDGE_BONUS if
                  selected and any(idx in neighbors[s] for s in selected) else 0.0)
            if (score>value+1e-10 or
                (abs(score-value)<1e-10 and
                 (best is None or context[idx][0]<context[best][0]))):
                value=score
                best=idx
        selected.append(best)
        remaining.remove(best)
    return selected


def question_gate(question):
    """Frozen text-only heuristic: avoid expansion for overt comparison questions.

    This is not allowed to inspect example.type, support labels or answer.
    """
    q=' '+question.casefold()+' '
    return any(phrase in q for phrase in (
        ' both ', 'same ', 'either ', ' which one ', ' more than ',
        ' older than ', ' younger than ', ' earlier than ', ' later than ',
        ' taller than ', ' longer than ', ' compared to ', ' or '))


def select(row,policy):
    helper=r25()
    if policy in ('bm25','bridge','mmr'):
        return helper.rank(row,policy,limit=5)
    if policy=='title_graph':
        return graph_rank(row,limit=5)
    if policy=='text_gate':
        return helper.rank(row,'bm25' if question_gate(row['question']) else 'bridge',limit=5)
    raise ValueError('unknown policy '+policy)


def measure_one(row,indices,helper):
    context=row['context']
    gold_titles={title for title,_ in row['supporting_facts']}
    chosen=[context[i] for i in indices]
    output={}
    sentence_ranks={}
    broken=support_reference_issue(row) is not None
    for i in indices:
        title,sentences=context[i]
        if sentences:
            scores=helper.bm25_scores(row['question'],sentences)
            sentence_ranks[i]=sorted(range(len(sentences)),
                                     key=lambda n:(-scores[n],n))
        else:
            sentence_ranks[i]=[]
    for k in FROZEN_K:
        current=indices[:k]
        found={context[i][0] for i in current}
        retrieved={(context[i][0],n) for i in current for n in sentence_ranks[i][:2]}
        output[str(k)]={
            'complete_docs':int(not broken and gold_titles.issubset(found)),
            'complete_sentences_top2':int(not broken and all((title,idx) in retrieved
                                              for title,idx in row['supporting_facts'])),
            'selected_utf8_bytes':sum(len(
                (context[i][0]+' '+' '.join(context[i][1])).encode('utf8'))
                for i in current)}
    return output


def aggregate(data,policies=('bm25','bridge','mmr','title_graph','text_gate')):
    helper=r25()
    buckets={m:{str(k):{'n':0,'complete_docs':0,'complete_sentences_top2':0,
                         'selected_utf8_bytes':0} for k in FROZEN_K} for m in policies}
    bytype={m:{} for m in policies}
    microtimes={m:[] for m in policies}
    paired={str(k):{'both':0,'bm25_only':0,'bridge_only':0,'neither':0}
            for k in FROZEN_K}
    gate_positive=0
    invalid_support_count=0
    for row in data:
        invalid_support_count+=int(support_reference_issue(row) is not None)
        gate_positive+=int(question_gate(row['question']))
        outputs={}
        for method in policies:
            start=time.perf_counter_ns()
            selected=select(row,method)
            microtimes[method].append((time.perf_counter_ns()-start)/1000)
            assert len(selected)==len(set(selected)) and max(selected)<len(row['context'])
            outputs[method]=measure_one(row,selected,helper)
            kind=row.get('type','unknown')
            if kind not in bytype[method]:
                bytype[method][kind]={str(k):{'n':0,'complete_docs':0,
                                            'complete_sentences_top2':0}
                                      for k in FROZEN_K}
            for k in map(str,FROZEN_K):
                for bucket in (buckets[method][k],bytype[method][kind][k]):
                    bucket['n']+=1
                    bucket['complete_docs']+=outputs[method][k]['complete_docs']
                    bucket['complete_sentences_top2']+=outputs[method][k]['complete_sentences_top2']
                    if 'selected_utf8_bytes' in bucket:
                        bucket['selected_utf8_bytes']+=outputs[method][k]['selected_utf8_bytes']
        if 'title_graph' in policies and 'bridge' in policies:
            if outputs['title_graph']!=outputs['bridge']:
                raise AssertionError('preindexed graph changed R25 bridge selection')
        if 'bm25' in policies and 'bridge' in policies:
            for k in map(str,FROZEN_K):
                a=outputs['bm25'][k]['complete_docs']
                b=outputs['bridge'][k]['complete_docs']
                paired[k]['both' if a and b else
                          'bm25_only' if a else
                          'bridge_only' if b else 'neither']+=1
    for method in policies:
        for k in map(str,FROZEN_K):
            b=buckets[method][k]
            b['mean_selected_utf8_bytes']=round(b.pop('selected_utf8_bytes')/len(data),2)
    return {
        'n':len(data),'unscorable_support_count':invalid_support_count,
        'gate_text_positive_count':gate_positive,
        'methods':buckets,'type_breakdown':bytype,'paired_bm25_bridge':paired,
        'policy_selection_p50_us':{
            k:round(statistics.median(v),3) for k,v in microtimes.items()},
        'sample_id_sha256':hashlib.sha256(
            '\n'.join(sorted(str(row['_id']) for row in data)).encode()).hexdigest(),
        'caveats':[
            'first externally held-out dev sample versus prior 100 train questions, but still validation split',
            'closed-world per-question candidate pool includes gold paragraphs by HotpotQA distractor design',
            'method code unchanged or prespecified before dev outcome; no tuning on this sample',
            'all candidate full texts read for per-question lexical BM25, not efficient open-domain search',
            'title graph build scans candidates, not a prebuilt amortized corpus index',
            'extraction measures annotated support coverage, not model answer accuracy',
            'selection CPU timings are warm sequential Python measurements, not stable hardware latency',
            'license CC BY-SA 4.0; corpus downloaded transiently, not included in git'
        ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'results.json'))
    p.add_argument('--sample-size',type=int,default=FROZEN_SAMPLE_SIZE)
    args=p.parse_args()
    rows=load_development()
    sample=locked_sample(rows,args.sample_size)
    output=aggregate(sample)
    output['integrity']={
        'full_dataset':integrity_audit(rows),
        'locked_sample':integrity_audit(sample),
        'policy':'All selected questions remain in denominators; structurally unscorable cases count as zero recoveries'}
    output['source']={
        'url':URL,'sha256':SHA256,'size_bytes':EXPECTED_SIZE,
        'download_count':len(rows),'sample_salt':SAMPLE_SALT,
        'sample_size':args.sample_size}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(output,indent=2)+'\n')
    compact={k:{j:output['methods'][k][j]['complete_docs'] for j in ('2','3','5')}
             for k in output['methods']}
    print('ROUND54',json.dumps({
        'n':output['n'],'types':{x:sum(row['type']==x for row in sample)
                                   for x in ('bridge','comparison')},
        'complete_docs':compact,
        'paired_at2':output['paired_bm25_bridge']['2'],
        'paired_at5':output['paired_bm25_bridge']['5'],
        'complete_by_type_at2':{
            method:{kind:entries['2']['complete_docs']
                    for kind,entries in output['type_breakdown'][method].items()}
            for method in ('bm25','bridge','text_gate')},
        'sample_hash':output['sample_id_sha256'],
        'invalid_support_sample':output['integrity']['locked_sample']['counts'],
        'invalid_support_full':output['integrity']['full_dataset']['counts']},sort_keys=True))


if __name__=='__main__':
    main()
