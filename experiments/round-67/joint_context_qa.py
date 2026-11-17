#!/usr/bin/env python3
"""R67: joint-evidence extractive QA and explicit annotated-evidence oracle.

The same pinned SQuAD2 extractive model from R66 sees one contiguous context.
Compare BM25 vs frozen bridge vs deterministic random docs, and separately
a gold-supporting-sentence oracle diagnostic. All normal retrieval is label-blind.
Hard cap on the model's full question+context tokenizer sequence length.
Gold labels appear only after inference, except in the clearly isolated oracle.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import time

import extractive_qa as q66

HERE=Path(__file__).resolve().parent
SAMPLE_COUNT=64
MODES=('whole_source','fts_top2')
POLICIES=('bm25','bridge','random')
K_VALUES=(2,5)
MAX_SEQ_LEN=384
THRESHOLDS=(0.0,.25)


def budget_prefix(question,context,tokenizer,max_tokens=MAX_SEQ_LEN):
    """Return a strict contiguous source-text prefix, not tokenizer-decoded text.

    The latter can alter whitespace/Unicode and break exact source receipts.
    Deterministic binary search uses source characters as the trimming unit.
    """
    def count(value):
        return len(tokenizer(question,value,add_special_tokens=True,
                             truncation=False)['input_ids'])
    original=count(context)
    if original<=max_tokens:
        return context,original,False
    if count('')>max_tokens:
        raise ValueError('question exceeds model token cap')
    lo=0;hi=len(context)
    while lo<hi:
        mid=(lo+hi+1)//2
        if count(context[:mid])<=max_tokens:
            lo=mid
        else:
            hi=mid-1
    bounded=context[:lo]
    if count(bounded)>max_tokens:
        raise AssertionError('strict sequence token cap violated')
    return bounded,count(bounded),True


def join_materials(materials):
    """Map every original sentence span to its actual concatenation position."""
    parts=[]
    coverage=[]
    cursor=0
    for _,material,sentence_ids in materials:
        if parts:
            cursor+=2
        parts.append(material['context'])
        local_cursor=0
        if sentence_ids is not None and len(material['snippets'])!=len(sentence_ids):
            raise AssertionError('source/sentence span mismatch')
        if sentence_ids is not None:
            for snippet,sid in zip(material['snippets'],sentence_ids):
                start=cursor+local_cursor
                end=start+len(snippet['text'])
                coverage.append((material['title'],sid,start,end))
                local_cursor+=len(snippet['text'])+1
        cursor+=len(material['context'])
    text='\n\n'.join(parts)
    if len(text)!=cursor:
        raise AssertionError('concatenation accounting error')
    return text,coverage


def make_oracle_task(qid,row,index,readers):
    """Annotation-informed diagnostic only; not an executable retrieval policy."""
    by_title={title:i for i,(title,_) in enumerate(row['context'])}
    text=[]
    evidence=[]
    for title,sid in row['supporting_facts']:
        did=by_title.get(title)
        if did is None:continue
        _,sentences=row['context'][did]
        if not 0<=sid<len(sentences):continue
        original=sentences[sid].encode('utf8')
        byte_start=len(''.join(sentences[:sid]).encode('utf8'))
        src=index.records[(qid,did)]
        for reader in readers.values():
            actual,_=reader.read(
                reader.receipt(src,byte_start,byte_start+len(original)),
                pin_generation=src)
            if actual!=original:
                raise AssertionError('oracle reference is not an exact source sentence')
        evidence.append((src,byte_start,byte_start+len(original)))
        text.append(sentences[sid])
    return {
        'qid':qid,'mode':'oracle_supporting_facts',
        'policy':'gold_oracle_diagnostic','documents':None,
        'raw_context':'\n\n'.join(text),
        'material_indices':evidence,
        'source_docs':sorted({source for source,lo,hi in evidence}),
        'source_titles':set(title for title,sid in row['supporting_facts']),
        'original_annotated_sentences':set((title,sid) for title,sid in row['supporting_facts']),
        'oracle':True
    }


def prepare_tasks(rows,index,readers,tokenizer):
    r54=q66.load('cdg54_joint67',q66.R54)
    tasks=[]
    corpus_cache={}
    for qid,row in enumerate(rows):
        for did in range(len(row['context'])):
            for mode in MODES:
                corpus_cache[(qid,did,mode)]=q66.make_context(
                    index,readers,row,qid,did,mode)
        for mode in MODES:
            for policy in POLICIES:
                for k in K_VALUES:
                    chosen=q66.choose_docs(row,policy,k,r54)
                    material=[]
                    for did in chosen:
                        src=corpus_cache[(qid,did,mode)]
                        if mode=='fts_top2':
                            sids=[sid for sid,_,_ in index.choose(
                                qid,did,row['question'],limit=2)]
                        else:sids=None
                        material.append((did,src,sids))
                    text,selected_spans=join_materials(material)
                    full_evidence=set()
                    if mode=='whole_source':
                        # Positions are mapped from the selected raw paragraphs
                        # without any gold labels. A sentence is complete only if
                        # its end is inside the capped model context.
                        cursor=0
                        for position,(did,m,_) in enumerate(material):
                            if position:cursor+=2
                            local=0
                            title=row['context'][did][0]
                            for sid,sentence in enumerate(row['context'][did][1]):
                                end=cursor+local+len(sentence)
                                selected_spans.append((title,sid,cursor+local,end))
                                local+=len(sentence)
                            cursor+=len(m['context'])
                    bounded,tokens,truncated=budget_prefix(
                        row['question'],text,tokenizer,MAX_SEQ_LEN)
                    full_evidence={(title,sid) for title,sid,start,end in selected_spans
                                   if end<=len(bounded)}
                    task={
                        'qid':qid,'mode':mode,'policy':policy,'documents':k,
                        'raw_context':text,'context':bounded,'tokens':tokens,
                        'truncated':truncated,
                        'selected_document_ids':chosen,
                        'selected_titles':set(row['context'][did][0] for did in chosen),
                        'annotated_sentences_in_model_context':full_evidence,
                        'materials':material,'oracle':False
                    }
                    tasks.append(task)
        oracle=make_oracle_task(qid,row,index,readers)
        bounded,tokens,truncated=budget_prefix(
            row['question'],oracle['raw_context'],tokenizer,MAX_SEQ_LEN)
        oracle['context']=bounded;oracle['tokens']=tokens;oracle['truncated']=truncated
        tasks.append(oracle)
    return tasks


def locate_source_answer(answer,task,readers):
    if not answer or answer not in task['context']:
        return False
    if task['oracle']:
        # The oracle consists only of already receipt-verified original sentences.
        return any(answer.encode('utf8') in
                   readers['whole'].read(
                       readers['whole'].receipt(source,lo,hi),pin_generation=source)[0]
                   for source,lo,hi in task['material_indices'])
    for did,material,sids in task['materials']:
        if q66.citation_for_answer(answer,material,readers['whole']):
            return True
    return False


def run_reader(tasks,rows,readers,tokenizer,answerer):
    prompts=[{'question':rows[task['qid']]['question'],
              'context':task['context'] or ' '}
             for task in tasks]
    started=time.perf_counter()
    predictions=answerer(prompts,batch_size=12,
                         max_seq_len=MAX_SEQ_LEN,doc_stride=64,
                         handle_impossible_answer=True,top_k=1)
    duration=time.perf_counter()-started
    if len(predictions)!=len(tasks):
        raise AssertionError('different answer reader output count')
    observations=[]
    rejected=0
    for task,pred in zip(tasks,predictions):
        score=float(pred.get('score',0.0))
        answer=str(pred.get('answer','')).strip()
        allowed=locate_source_answer(answer,task,readers)
        if answer and not allowed:
            rejected+=1
        if not allowed:
            answer='';score=0.
        gold=str(rows[task['qid']]['answer'])
        reference=set(tuple(x) for x in rows[task['qid']]['supporting_facts'])
        evidence=(reference <= (
            reference if task['oracle'] and not task['truncated']
            else task.get('annotated_sentences_in_model_context',set())))
        for threshold in THRESHOLDS:
            current=answer if score>=threshold else ''
            observations.append({
                'qid':task['qid'],'oracle':task['oracle'],
                'policy':task['policy'],'k':task['documents'],
                'mode':task['mode'],'threshold':threshold,
                'answer_em':q66.exact_match(current,gold),
                'answer_f1':q66.token_f1(current,gold),
                'answer_is_source_verbatim':bool(current),
                'answered':bool(current),
                'incorrect_answer':bool(current) and not q66.exact_match(current,gold),
                'annotated_evidence_complete':int(evidence),
                'question_type':rows[task['qid']]['type'],
                'tokens':task['tokens'],'truncated':int(task['truncated']),
                'context_chars':len(task['context']),
                'retrieval_gold_docs_complete':int(
                    task['oracle'] or set(t for t,s in reference) <= task['selected_titles']),
            })
    return observations,duration,rejected


def aggregate(observations):
    grouped=defaultdict(list)
    for r in observations:
        grouped[(r['policy'],r['k'],r['mode'],r['threshold'])].append(r)
    outcomes=[]
    for (policy,k,mode,threshold),cases in sorted(grouped.items(),
                 key=lambda x:(x[0][0],x[0][1] or 0,x[0][2],x[0][3])):
        n=len(cases)
        outcomes.append({
            'policy':policy,'k':k,'mode':mode,'threshold':threshold,'n':n,
            'answer_em':round(statistics.mean(x['answer_em'] for x in cases),5),
            'answer_f1':round(statistics.mean(x['answer_f1'] for x in cases),5),
            'answer_em_count':sum(x['answer_em'] for x in cases),
            'answered':sum(x['answered'] for x in cases),
            'incorrect_nonabstained':sum(x['incorrect_answer'] for x in cases),
            'gold_docs_complete':sum(x['retrieval_gold_docs_complete'] for x in cases),
            'gold_evidence_in_model_context':sum(x['annotated_evidence_complete'] for x in cases),
            'correct_answer_and_complete_gold_evidence':sum(
                x['answer_em']*x['annotated_evidence_complete'] for x in cases),
            'mean_tokenizer_input_tokens':round(statistics.mean(x['tokens'] for x in cases),2),
            'truncated_contexts':sum(x['truncated'] for x in cases),
        })
    paired={}
    for k in K_VALUES:
        for mode in MODES:
            for threshold in THRESHOLDS:
                a=sorted(grouped[('bridge',k,mode,threshold)],key=lambda x:x['qid'])
                b=sorted(grouped[('bm25',k,mode,threshold)],key=lambda x:x['qid'])
                counts={'both':0,'bridge_only':0,'bm25_only':0,'neither':0}
                for x,y in zip(a,b):
                    if x['qid']!=y['qid']:
                        raise AssertionError('paired evidence not aligned')
                    ok1=x['answer_em'];ok2=y['answer_em']
                    counts['both' if ok1 and ok2 else
                           'bridge_only' if ok1 else
                           'bm25_only' if ok2 else 'neither']+=1
                paired[str((k,mode,threshold))]=counts
    return outcomes,paired


def experiment(rows,tokenizer,reader,model_meta):
    r55=q66.load('cdg55_joint67',q66.R55)
    r48=q66.load('cdg48_joint67',q66.R48)
    with tempfile.TemporaryDirectory() as tmp:
        index=r55.SentenceIndex(Path(tmp)/'evidence.sqlite',rows)
        readers={
            'whole':r48.VersionedReader(index.original_blobs,'whole','json-zlib'),
            'gear512':r48.VersionedReader(index.original_blobs,'gear512','binary-zlib')}
        try:
            tasks=prepare_tasks(rows,index,readers,tokenizer)
            scores,inference_sec,uncited=run_reader(
                tasks,rows,readers,tokenizer,reader)
            outcomes,paired=aggregate(scores)
            return {
                'questions':len(rows),'model':model_meta,
                'sample_ids_sha256':hashlib.sha256(
                    '\n'.join(sorted(row['_id'] for row in rows)).encode()).hexdigest(),
                'actual_model_calls':len(tasks),
                'actual_model_seconds':round(inference_sec,3),
                'discarded_uncitable_model_candidates':uncited,
                'source_index_bytes':index.db_bytes,
                'archive_bytes':{x:y.size() for x,y in readers.items()},
                'conditions':outcomes,'paired_bridge_vs_bm25':paired,
                'limitations':[
                    'same 64 HotpotQA distractor dev rows as R66, not an independent source family',
                    'SQuAD2 extractive reader lacks trained multihop reasoning and is not generative RAG',
                    'whole-source and FTS evidence contexts capped at 384 total model tokens by deterministic prefix truncation',
                    'text cropped after selected source documents have already been decoded and FTS-indexed',
                    'gold supporting sentences supplied only to explicitly labeled oracle condition, never actual document retrievers',
                    'comparison with R66 per-document QA is not same token budget: per-doc reader gets separate input window per paragraph',
                    'literal citation containment and matching reference answer are not semantic entailment or source credibility',
                    'oracle context gold labels used only to diagnose model ceiling, not a deployable retrieval algorithm',
                    'model token counts approximate per-condition inputs and do not include source pre-scoring, archive ingest or storage indexing',
                    'actual CPU wall time is shared batched inference over all policies',
                    'no claim of hallucination reduction or novel multihop reasoning method',
                ]}
        finally:
            index.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--count',type=int,default=SAMPLE_COUNT)
    p.add_argument('--offset',type=int,default=0)
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    if args.count<1 or args.count>128 or args.offset<0 or args.offset+args.count>512:
        raise ValueError('unbounded sampling rejected')
    r54=q66.load('cdg54_data67',q66.R54)
    rows=r54.locked_sample(r54.load_development())[args.offset:args.offset+args.count]
    tokenizer,reader,model_meta=q66.load_reader()
    result=experiment(rows,tokenizer,reader,model_meta)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    focus=[x for x in result['conditions']
           if x['threshold']==0 and x['mode'] in ('whole_source','oracle_supporting_facts')]
    print('ROUND67',json.dumps({
        'count':result['questions'],
        'reader_calls':result['actual_model_calls'],
        'reader_seconds':result['actual_model_seconds'],
        'conditions':focus,
        'paired':result['paired_bridge_vs_bm25']
    },sort_keys=True))


if __name__=='__main__':
    main()
