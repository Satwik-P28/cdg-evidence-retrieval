#!/usr/bin/env python3
"""R66: closed-world HotpotQA retrieval-to-answer pipeline with real extractive QA.

Freeze R25 BM25/bridge and R55 source index. Restore exact source bytes from
whole Zlib and gear512 CAS with SHA-bound receipts, select full paragraphs or
top-two FTS sentences, and run a pinned pretrained SQuAD2 answer reader.
No gold answers, support labels or question type influence retrieval/inference.
This is NOT a multi-hop-trained reader, generative RAG, or claim entailment.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import re
import statistics
import string
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R55=HERE.parent/'round-55'/'heldout_frames.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R25=HERE.parent/'round-25'/'bridge_probe.py'
LOCK=HERE/'model_lock.json'
SAMPLE_COUNT=64
SAMPLE_OFFSET=0
POLICIES=('bm25','bridge','random')
DOCUMENT_LIMITS=(2,5)
MODES=('whole_source','fts_top2')
THRESHOLDS=(0.0,.25,.50)
READER_MAX_LENGTH=384


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def normalize_answer(s):
    """Official HotpotQA/SQuAD-style normalization: articles, punctuation, space."""
    def remove_articles(text):
        return re.sub(r'\b(a|an|the)\b',' ',text)
    def remove_punc(text):
        return ''.join(ch for ch in text if ch not in set(string.punctuation))
    def white_space_fix(text):
        return ' '.join(text.split())
    return white_space_fix(remove_articles(remove_punc(s.lower())))


def exact_match(pred,reference):
    return int(normalize_answer(pred)==normalize_answer(reference))


def token_f1(pred,reference):
    p=normalize_answer(pred).split()
    g=normalize_answer(reference).split()
    if (normalize_answer(pred) in ('yes','no','noanswer') or
        normalize_answer(reference) in ('yes','no','noanswer')) and (
        normalize_answer(pred)!=normalize_answer(reference)):
        return 0.0
    common=Counter(p)&Counter(g)
    overlap=sum(common.values())
    if not p or not g:
        return float(p==g)
    if overlap==0:return 0.0
    precision=overlap/len(p);recall=overlap/len(g)
    return 2*precision*recall/(precision+recall)


def random_docs(row,count):
    ctx=row['context']
    return sorted(range(len(ctx)),
                  key=lambda i:hashlib.sha256((
                      'CDG-R66-NEGATIVE|'+str(row['_id'])+'|'+
                      str(ctx[i][0])).encode()).digest())[:count]


def choose_docs(row,policy,k,r54):
    if policy=='random':
        return random_docs(row,k)
    return r54.select(row,policy)[:k]


def compressed_keys(manifest,lo,hi):
    if lo==hi:return set()
    offset=0
    output=set()
    for frame in manifest['frames']:
        stop=offset+frame['len']
        if stop>lo and offset<hi:
            output.add(frame['sha'])
        offset=stop
    if offset!=manifest['size']:
        raise AssertionError('incorrect archive source length')
    return output


def make_context(index,readers,row,qid,did,mode):
    """Materialize one source QA context, verify both archive representations."""
    raw=index.original_blobs[index.records[(qid,did)]]
    source=index.records[(qid,did)]
    if mode=='whole_source':
        wanted=[(0,len(raw))]
    elif mode=='fts_top2':
        wanted=[(start,end) for _,start,end in index.choose(
            qid,did,row['question'],limit=2)]
    else:
        raise ValueError(mode)
    snippets=[]
    unique={kind:set() for kind in readers}
    for lo,hi in wanted:
        if lo==hi:continue
        expected=raw[lo:hi]
        for name,reader in readers.items():
            receipt=reader.receipt(source,lo,hi)
            decoded,traffic=reader.read(receipt,pin_generation=source)
            if decoded!=expected:
                raise AssertionError('unverified lossless evidence source bytes')
            unique[name].update(compressed_keys(reader.manifests[source],lo,hi))
        snippets.append({'lo':lo,'hi':hi,'text':expected.decode('utf8')})
    context=' '.join(x['text'] for x in snippets)
    if not context.strip():
        context=' '
    return {
        'source':source,
        'title':row['context'][did][0],
        'context':context,
        'snippets':snippets,
        'unique_frame_ids':{name:sorted(ids) for name,ids in unique.items()},
        'context_utf8_bytes':len(context.encode('utf8')),
    }


def citation_for_answer(answer,material,reader):
    """Only accept verbatim answer entirely inside one verified source span."""
    if not answer.strip():
        return None
    if answer not in material['context']:
        return None
    for item in material['snippets']:
        offset=item['text'].find(answer)
        if offset<0:continue
        offset_bytes=len(item['text'][:offset].encode('utf8'))
        lo=item['lo']+offset_bytes
        hi=lo+len(answer.encode('utf8'))
        receipt=reader.receipt(material['source'],lo,hi)
        got,_=reader.read(receipt,pin_generation=material['source'])
        if got!=answer.encode('utf8'):
            raise AssertionError('incorrect source citation materialization')
        return {
            'source_sha256':receipt.source_sha256,
            'generation':receipt.generation,
            'byte_start':lo,'byte_end':hi,
            'answer_sha256':hashlib.sha256(got).hexdigest(),
        }
    return None


def validate_model_lock(lock):
    revision=lock.get('revision','')
    if not isinstance(revision,str) or not re.fullmatch(r'[0-9a-f]{40}',revision):
        raise ValueError('QA model must have immutable 40-hex commit revision')
    if lock.get('name')!='deepset/tinyroberta-squad2':
        raise ValueError('unexpected answer model identity')
    return revision


def load_reader():
    """Require pinned model weights and tokenizer; no silent alternative."""
    import torch
    import transformers
    from huggingface_hub import HfApi
    lock=json.loads(LOCK.read_text())
    revision=validate_model_lock(lock)
    model_id=lock['name']
    resolved=HfApi().model_info(model_id,revision=revision)
    if resolved.sha!=revision:
        raise ValueError('upstream model revision not pinned')
    torch.manual_seed(66)
    torch.set_num_threads(2)
    tokenizer=transformers.AutoTokenizer.from_pretrained(
        model_id,revision=revision,use_fast=True)
    model=transformers.AutoModelForQuestionAnswering.from_pretrained(
        model_id,revision=revision)
    model.eval()
    answerer=transformers.pipeline('question-answering',model=model,
                                   tokenizer=tokenizer,device=-1)
    return tokenizer,answerer,{
        'id':model_id,'revision':revision,'pytorch':torch.__version__,
        'transformers':transformers.__version__,
        'max_seq_length':READER_MAX_LENGTH,'device':'cpu',
        'configured_torch_threads':2,
    }


def infer_all(reader,tasks):
    """Batch all unique (question, source, evidence mode) pairs, avoiding re-run
    for overlapping policies. Measure actual total QA batch CPU wall time."""
    inputs=[{'question':task['question'],'context':task['material']['context']}
            for task in tasks]
    start=time.perf_counter()
    predicted=reader(inputs,batch_size=12,
                     max_seq_len=READER_MAX_LENGTH,doc_stride=96,
                     handle_impossible_answer=True,top_k=1)
    elapsed=time.perf_counter()-start
    if len(predicted)!=len(tasks):
        raise AssertionError('QA model predictions changed length')
    results={}
    uncited=0
    for task,out in zip(tasks,predicted):
        answer=str(out.get('answer','')).strip()
        confidence=float(out.get('score',0.0))
        if not 0<=confidence<=1:
            raise AssertionError('reader score outside [0,1]')
        cite=citation_for_answer(
            answer,task['material'],task['archive'])
        if answer and not cite:
            uncited+=1
        results[task['key']]={
            'answer':answer if cite else '',
            'score':confidence if cite else 0.0,
            'citation':cite,
            'source_title':task['material']['title'],
            'tokens':task['tokens'],
        }
    return results,elapsed,uncited


def build_indexed_tasks(rows,index,readers,tokenizer):
    tasks=[]
    lookup={}
    for qid,row in enumerate(rows):
        for did in range(len(row['context'])):
            for mode in MODES:
                material=make_context(index,readers,row,qid,did,mode)
                length=len(tokenizer(
                    row['question'],material['context'],
                    truncation='only_second',max_length=READER_MAX_LENGTH)['input_ids'])
                key=(qid,did,mode)
                task={'key':key,'question':row['question'],
                      'material':material,'tokens':length,
                      'archive':readers['whole']}
                tasks.append(task)
                lookup[key]=task
    return tasks,lookup


def evaluate_policy(rows,policies,task_lookup,model_answers,readers,r54):
    summary=[]
    by_policy={}
    for policy in policies:
        for k in DOCUMENT_LIMITS:
            for mode in MODES:
                for threshold in THRESHOLDS:
                    metrics=[]
                    for qid,row in enumerate(rows):
                        selected=choose_docs(row,policy,k,r54)
                        gold_docs=set(t for t,_ in row['supporting_facts'])
                        picked_titles={row['context'][did][0] for did in selected}
                        complete_docs=int(
                            r54.support_reference_issue(row) is None and
                            gold_docs.issubset(picked_titles))
                        available={(
                            row['context'][did][0],sid)
                            for did in selected
                            for sid in (
                                (range(len(row['context'][did][1])) if mode=='whole_source'
                                 else [s for s,_,_ in
                                       task_lookup[(qid,did,mode)]['material']['_sid_spans']])
                            )}
                        # A source is annotated complete only when all gold facts
                        # are in materialized evidence, never from model output.
                        complete_evidence=int(
                            r54.support_reference_issue(row) is None and
                            all((t,sid) in available for t,sid in row['supporting_facts']))
                        candidates=[(did,model_answers[(qid,did,mode)])
                                    for did in selected]
                        chosen=max(candidates,key=lambda item:(
                            item[1]['score'],-selected.index(item[0])))
                        _,winner=chosen
                        answer=winner['answer'] if winner['score']>=threshold else ''
                        answered=int(bool(answer))
                        em=exact_match(answer,str(row['answer']))
                        f1=token_f1(answer,str(row['answer']))
                        activated={kind:set() for kind in readers}
                        for did in selected:
                            m=task_lookup[(qid,did,mode)]['material']
                            for kind in readers:
                                activated[kind].update(m['unique_frame_ids'][kind])
                        unique_bytes={
                            kind:sum(len(readers[kind].archive.frames[sha])
                                     for sha in activated[kind])
                            for kind in readers}
                        tokens=sum(model_answers[(qid,did,mode)]['tokens']
                                   for did in selected)
                        metrics.append({
                            'answer_em':em,'answer_f1':f1,'answered':answered,
                            'wrong_answer':answered*(1-em),
                            'gold_docs_complete':complete_docs,
                            'gold_evidence_complete':complete_evidence,
                            'correct_with_gold_evidence':em*complete_evidence,
                            'correct_without_gold_evidence':em*(1-complete_evidence),
                            'answered_without_gold_evidence':answered*(1-complete_evidence),
                            'total_qa_tokens_if_uncached':tokens,
                            'compressed_bytes_whole':unique_bytes['whole'],
                            'compressed_bytes_gear512':unique_bytes['gear512'],
                            'type':row.get('type','unknown'),
                        })
                    n=len(metrics)
                    result={
                        'policy':policy,'documents':k,'mode':mode,'threshold':threshold,
                        'n':n,
                        'answer_em':round(statistics.mean(x['answer_em'] for x in metrics),5),
                        'answer_f1':round(statistics.mean(x['answer_f1'] for x in metrics),5),
                        'answered':sum(x['answered'] for x in metrics),
                        'incorrect_nonabstained':sum(x['wrong_answer'] for x in metrics),
                        'complete_gold_docs':sum(x['gold_docs_complete'] for x in metrics),
                        'complete_gold_evidence':sum(x['gold_evidence_complete'] for x in metrics),
                        'correct_answer_and_complete_gold_evidence':sum(x['correct_with_gold_evidence'] for x in metrics),
                        'correct_answer_but_incomplete_gold_evidence':sum(x['correct_without_gold_evidence'] for x in metrics),
                        'answered_but_incomplete_gold_evidence':sum(x['answered_without_gold_evidence'] for x in metrics),
                        'mean_model_input_tokens_if_uncached':round(statistics.mean(x['total_qa_tokens_if_uncached'] for x in metrics),2),
                        'mean_unique_compressed_bytes_whole':round(statistics.mean(x['compressed_bytes_whole'] for x in metrics),2),
                        'mean_unique_compressed_bytes_gear512':round(statistics.mean(x['compressed_bytes_gear512'] for x in metrics),2),
                        'type_breakdown':{
                            kind:{'n':sum(x['type']==kind for x in metrics),
                                  'answer_em_count':sum(x['answer_em'] for x in metrics if x['type']==kind)}
                            for kind in ('bridge','comparison')}
                    }
                    summary.append(result)
                    by_policy[(policy,k,mode,threshold)]=metrics
    paired={}
    for k in DOCUMENT_LIMITS:
        for mode in MODES:
            for threshold in THRESHOLDS:
                lhs=by_policy[('bridge',k,mode,threshold)]
                rhs=by_policy[('bm25',k,mode,threshold)]
                counts={'both':0,'bridge_only':0,'bm25_only':0,'neither':0}
                for left,right in zip(lhs,rhs):
                    a=left['answer_em'];b=right['answer_em']
                    counts['both' if a and b else
                           'bridge_only' if a else
                           'bm25_only' if b else 'neither']+=1
                paired[str((k,mode,threshold))]=counts
    return summary,paired


def experiment(rows,tokenizer,reader,model_meta):
    r54=load('cdg54_r66',R54)
    r55=load('cdg55_r66',R55)
    r48=load('cdg48_r66',R48)
    start=time.perf_counter()
    with tempfile.TemporaryDirectory() as temp:
        index=r55.SentenceIndex(Path(temp)/'fts.sqlite',rows)
        readers={
            'whole':r48.VersionedReader(index.original_blobs,'whole','json-zlib'),
            'gear512':r48.VersionedReader(index.original_blobs,'gear512','binary-zlib')}
        source_archival_seconds=time.perf_counter()-start-index.build_ms/1000
        try:
            for qid,row in enumerate(rows):
                for did,(title,sentences) in enumerate(row['context']):
                    original=index.original_blobs[index.records[(qid,did)]]
                    for name,archive in readers.items():
                        source=index.records[(qid,did)]
                        rebuilt,_=archive.read(archive.receipt(source,0,len(original)),
                                               pin_generation=source)
                        if rebuilt!=original:
                            raise AssertionError('unverified source SHA readback')
            # Add explicit original sentence identity so gold supporting labels
            # only enter the final evaluator, not the source selection pipeline.
            tasks,task_lookup=build_indexed_tasks(rows,index,readers,tokenizer)
            for task in tasks:
                qid,did,mode=task['key']
                if mode=='whole_source':
                    sids=list(range(len(rows[qid]['context'][did][1])))
                else:
                    sids=[sid for sid,_,_ in index.choose(
                        qid,did,rows[qid]['question'],limit=2)]
                task['material']['_sid_spans']=[(sid,None,None) for sid in sids]
            answer_map,inference_seconds,uncited=infer_all(reader,tasks)
            observations,paired=evaluate_policy(
                rows,POLICIES,task_lookup,answer_map,readers,r54)
            return {
                'count':len(rows),'source_documents':len(index.original_blobs),
                'sample_id_sha256':hashlib.sha256(
                    '\n'.join(sorted(row['_id'] for row in rows)).encode()).hexdigest(),
                'model':model_meta,
                'actual_reader_inference_calls':len(tasks),
                'actual_reader_inference_seconds':round(inference_seconds,3),
                'uncitable_model_candidates_rejected':uncited,
                'source_index_bytes':index.db_bytes,
                'source_index_build_ms':round(index.build_ms,3),
                'source_archive_build_seconds_estimate':round(source_archival_seconds,3),
                'source_archive_bytes':{name:reader.size() for name,reader in readers.items()},
                'observations':observations,
                'paired_doc_retrieval_answer_em':paired,
                'limits':[
                    '64 locked HotpotQA distractor dev questions, already used for prior retrieval, not untouched benchmark generalization',
                    'gold candidate paragraphs always in local question pool; source paragraphs all read for per-question BM25',
                    'pretrained SQuAD2 extractive reader is NOT trained to perform multi-hop reasoning; candidate answers are scored per document independently',
                    'model confidence scores compared across documents are not calibrated',
                    'all-candidate inference is cached across retrieval variants, so actual run work exceeds each independent-policy counterfactual budget',
                    'read tokens represent tokenizer input, not API-billed tokens or actual generated text',
                    'citation exact-span check is syntactic, not entailment, truth or source authority',
                    'missing annotated support is not proof of hallucination; metric is explicitly a coverage proxy',
                    'storage/index sizes exclude model weights and in-memory embedding/CPU work; source archive build time approximate',
                    'CPU batch wall time is one shared run, not independent-policy latency',
                    'corpus license CC BY-SA 4.0, pretrained reader license and pinned commit in model lock; no third-party source bytes redistributed',
                ]}
        finally:
            index.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(HERE/'ci-results.json'))
    ap.add_argument('--count',type=int,default=SAMPLE_COUNT)
    ap.add_argument('--offset',type=int,default=SAMPLE_OFFSET)
    opts=ap.parse_args()
    if not 1<=opts.count<=128 or opts.offset<0 or opts.offset+opts.count>512:
        raise ValueError('sample size must be within fixed 512 dev question IDs')
    r54=load('cdg54_source_r66',R54)
    frozen=r54.locked_sample(r54.load_development())
    selection=frozen[opts.offset:opts.offset+opts.count]
    tokenizer,reader,meta=load_reader()
    out=experiment(selection,tokenizer,reader,meta)
    out['dataset_source_sha256']=r54.SHA256
    out['selected_offset']=opts.offset
    path=Path(opts.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print('ROUND66',json.dumps({
        'count':out['count'],'model':out['model'],
        'actual_model_calls':out['actual_reader_inference_calls'],
        'inference_seconds':out['actual_reader_inference_seconds'],
        'index_bytes':out['source_index_bytes'],
        'archives':out['source_archive_bytes'],
        'outcomes':[
            row for row in out['observations']
            if row['mode']=='whole_source' and row['threshold']==0.0
            and row['documents'] in (2,5)
        ],
        'paired':out['paired_doc_retrieval_answer_em']
    },sort_keys=True))


if __name__=='__main__':
    main()
