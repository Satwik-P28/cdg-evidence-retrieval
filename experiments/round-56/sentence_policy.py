#!/usr/bin/env python3
"""Round 56: fixed-budget, label-blind sentence selection from real HotpotQA.

Ablate FTS5 BM25, paragraph-local BM25, exact-title-link priority, token MMR
and a deterministic random control at matched 1/2/3/4/full sentence budgets.
Report exact gold supporting-fact coverage and per-question unique compressed
frame activation with complete archive+index footprint. Exploratory after R54-55.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R55=HERE.parent/'round-55'/'heldout_frames.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R25=HERE.parent/'round-25'/'bridge_probe.py'
METHODS=('fts','local_bm25','mention_first','sentence_mmr','random_hash')
BUDGETS=(1,2,3,4,999)
POLICIES=('bm25','bridge')
K_VALUES=(2,5)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def spans(sentences):
    offset=0
    out=[]
    for sid,text in enumerate(sentences):
        end=offset+len(text.encode('utf8'))
        out.append((sid,offset,end))
        offset=end
    return out


def rank_sentences(question,sentences,selected_titles,own_title,
                   qid,did,method,fts_order,helper):
    n=len(sentences)
    if not n:return []
    if method=='fts':
        ids=[x[0] for x in fts_order]
        ids+= [x for x in range(n) if x not in ids]
        return ids
    scores=helper.bm25_scores(question,sentences)
    local=sorted(range(n),key=lambda sid:(-scores[sid],sid))
    if method=='local_bm25':
        return local
    if method=='random_hash':
        return sorted(range(n),key=lambda sid:hashlib.sha256(
            f'R56_NEGATIVE_CONTROL|{qid}|{did}|{sid}'.encode()).digest())
    if method=='mention_first':
        mentions=[]
        for sid,text in enumerate(sentences):
            sentence=' '+helper.canon(text)+' '
            match=any(
                len(title)>4 and title in sentence
                for title in (' '+helper.canon(title)+' '
                              for title in selected_titles if title!=own_title))
            if match:mentions.append(sid)
        priority=set(mentions)
        return [sid for sid in local if sid in priority]+[
                sid for sid in local if sid not in priority]
    if method=='sentence_mmr':
        tokens=[set(helper.words(text)) for text in sentences]
        maximum=max(max(scores),1e-8)
        remaining=set(range(n))
        chosen=[]
        while remaining:
            best=None;score=-float('inf')
            for sid in sorted(remaining):
                similarity=max((helper.jaccard(tokens[sid],tokens[prior])
                                for prior in chosen),default=0.0)
                candidate=.75*scores[sid]/maximum-.25*similarity
                if (candidate>score+1e-10 or
                    (abs(candidate-score)<1e-10 and (best is None or sid<best))):
                    score=candidate;best=sid
            remaining.remove(best)
            chosen.append(best)
        return chosen
    raise ValueError(method)


def frame_ids(manifest,start,end):
    if start==end:return set()
    out=set();offset=0
    for item in manifest['frames']:
        stop=offset+item['len']
        if stop>start and offset<end:
            out.add(item['sha'])
        offset=stop
    if offset!=manifest['size']:
        raise AssertionError('unmatched source manifest length')
    return out


def evaluate(rows):
    m54=load('cdg54_for56',R54)
    m55=load('cdg55_for56',R55)
    m48=load('cdg48_for56',R48)
    m25=load('cdg25_for56',R25)
    with tempfile.TemporaryDirectory() as folder:
        index=m55.SentenceIndex(Path(folder)/'sentences.sqlite',rows)
        readers={
            'whole':m48.VersionedReader(index.original_blobs,'whole','json-zlib'),
            'gear512':m48.VersionedReader(index.original_blobs,'gear512','binary-zlib'),
        }
        try:
            for variant,reader in readers.items():
                for doc,original in enumerate(index.original_blobs):
                    if reader.read(reader.receipt(doc,0,len(original)),
                                   pin_generation=doc)[0]!=original:
                        raise AssertionError('original source failed verified full read')
            details=[]
            runtimes={name:[] for name in METHODS}
            verified=set()
            for qid,row in enumerate(rows):
                gold=set((t,s) for t,s in row['supporting_facts'])
                valid=m54.support_reference_issue(row) is None
                for policy in POLICIES:
                    ranked_docs=m54.select(row,policy)
                    for k in K_VALUES:
                        chosen_docs=ranked_docs[:k]
                        chosen_titles=[row['context'][i][0] for i in chosen_docs]
                        gold_docs={title for title,_ in gold}
                        complete_documents=valid and gold_docs.issubset(set(chosen_titles))
                        ranked_by_method={}
                        for did in chosen_docs:
                            source=index.records[(qid,did)]
                            title,sentences=row['context'][did]
                            fts_rank=index.choose(qid,did,row['question'],
                                                  limit=len(sentences))
                            for method in METHODS:
                                start=time.perf_counter_ns()
                                ordering=rank_sentences(
                                    row['question'],sentences,chosen_titles,title,
                                    qid,did,method,fts_rank,m25)
                                runtimes[method].append((time.perf_counter_ns()-start)/1000)
                                if set(ordering)!=set(range(len(sentences))):
                                    raise AssertionError('sentence ranking not a permutation')
                                ranked_by_method[(did,method)]=ordering
                        for method in METHODS:
                            for budget in BUDGETS:
                                recovered=set()
                                touched={kind:set() for kind in readers}
                                logical_bytes=0
                                selected_sentences=0
                                for did in chosen_docs:
                                    title,sentences=row['context'][did]
                                    archive_id=index.records[(qid,did)]
                                    offsets=spans(sentences)
                                    lookup=dict((sid,(lo,hi)) for sid,lo,hi in offsets)
                                    ordering=ranked_by_method[(did,method)]
                                    selected=ordering if budget==999 else ordering[:budget]
                                    for sid in selected:
                                        recovered.add((title,sid))
                                        lo,hi=lookup[sid]
                                        logical_bytes+=hi-lo
                                        selected_sentences+=1
                                        for variant,reader in readers.items():
                                            touched[variant].update(frame_ids(
                                                reader.manifests[archive_id],lo,hi))
                                            key=(variant,archive_id,sid)
                                            if key not in verified:
                                                receipt=reader.receipt(archive_id,lo,hi)
                                                got,_=reader.read(receipt,pin_generation=archive_id)
                                                if got!=sentences[sid].encode('utf8'):
                                                    raise AssertionError('citation span not lossless')
                                                verified.add(key)
                                entry={'qid':qid,'type':row['type'],'policy':policy,
                                       'k':k,'selector':method,'sentence_budget':budget,
                                       'complete_documents':int(complete_documents),
                                       'complete_sentences':int(valid and gold.issubset(recovered)),
                                       'selected_sentences':selected_sentences,
                                       'uncompressed_selected_bytes':logical_bytes}
                                for variant,reader in readers.items():
                                    entry[variant+'_unique_compressed_bytes']=sum(
                                        len(reader.archive.frames[key])
                                        for key in touched[variant])
                                details.append(entry)
            grouped={}
            for entry in details:
                key=(entry['policy'],entry['k'],entry['selector'],entry['sentence_budget'])
                grouped.setdefault(key,[]).append(entry)
            metrics=[]
            for (policy,k,method,budget),cases in sorted(grouped.items()):
                metrics.append({
                    'policy':policy,'k':k,'selector':method,'sentence_budget':budget,
                    'questions':len(cases),
                    'complete_gold_docs':sum(x['complete_documents'] for x in cases),
                    'complete_gold_sentences':sum(x['complete_sentences'] for x in cases),
                    'mean_selected_sentences':round(statistics.mean(x['selected_sentences'] for x in cases),2),
                    'mean_uncompressed_selected_bytes':round(statistics.mean(x['uncompressed_selected_bytes'] for x in cases),2),
                    'mean_gear512_compressed_frame_bytes':round(statistics.mean(x['gear512_unique_compressed_bytes'] for x in cases),2),
                    'mean_whole_compressed_frame_bytes':round(statistics.mean(x['whole_unique_compressed_bytes'] for x in cases),2),
                })
            return {
                'sample_size':len(rows),'reference_sha_salt':m54.SAMPLE_SALT,
                'index_bytes':index.db_bytes,
                'archive_bytes':{kind:reader.size() for kind,reader in readers.items()},
                'verified_unique_source_spans':len(verified),
                'scoring_p50_us':{key:round(statistics.median(value),3)
                                  for key,value in runtimes.items()},
                'metrics':metrics,
                'limitations':[
                    'dev sample already examined in R54-55; this is exploratory policy ablation, not untouched holdout',
                    'all question-local source texts pre-read for document BM25',
                    'locally computed sentence BM25/mention scores also access all sentence text',
                    'selected frame bytes count perfect per-query deduplication, not real SSD reads',
                    'full FTS sentence index and manifest bytes included in footprint',
                    'random control deterministic but not proof of semantic entailment',
                    'matches annotated sentence identity only; cannot validate claim support or answers',
                ],
            }
        finally:
            index.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sample-size',type=int,default=128)
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    helper=load('cdg54_load_for56',R54)
    if not 1<=args.sample_size<=128:
        raise ValueError('R56 sample bounded to the same first 128 locked dev IDs')
    sample=helper.locked_sample(helper.load_development())[:args.sample_size]
    result=evaluate(sample)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    focus=[x for x in result['metrics'] if
           x['policy']=='bridge' and x['k']==5 and x['sentence_budget'] in (2,3,4,999)]
    print('ROUND56',json.dumps({
        'n':result['sample_size'],
        'index_bytes':result['index_bytes'],'archive_bytes':result['archive_bytes'],
        'verified_spans':result['verified_unique_source_spans'],
        'bridge_k5':focus},sort_keys=True))


if __name__=='__main__':
    main()
