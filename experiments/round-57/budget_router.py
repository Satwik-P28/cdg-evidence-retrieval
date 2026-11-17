#!/usr/bin/env python3
"""Round 57: global sentence-budget allocation with a prespecified second partition.

Select exactly at most 10 sentence identities across five retrieved HotpotQA
documents. Compare fixed-per-document, recycling, front/back loading, graph
priority, global lexical and a negative random allocator. No oracle policy.
Report first 128 cases separately from next 128 SHA-locked dev cases.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R55=HERE.parent/'round-55'/'heldout_frames.py'
R56=HERE.parent/'round-56'/'sentence_policy.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R25=HERE.parent/'round-25'/'bridge_probe.py'
ALLOCATORS=('uniform2','uniform_recycle','front_4_3_1_1_1',
            'balanced_3_3_2_1_1','reverse_1_1_2_3_3',
            'link_weighted','global_rank','random')
SELECTORS=('fts','local_bm25','mention_first')
DOCUMENT_POLICIES=('bm25','bridge')
GLOBAL_BUDGET=10


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def allocation(method,ranked_docs,orders,weights,qid,budget=GLOBAL_BUDGET):
    if budget<0:raise ValueError('negative budget')
    seq=[d for d in ranked_docs]
    if not 1<=len(seq)<=5:
        raise ValueError('requires one to five available candidate documents')
    if method=='random':
        entries=[(d,sid) for d in seq for sid in orders[d]]
        ranked=sorted(entries,key=lambda pair:hashlib.sha256(
            f'R57_NEGATIVE|{qid}|{pair[0]}|{pair[1]}'.encode()).digest())
        return ranked[:budget]
    if method=='global_rank':
        entries=[]
        for order_d,d in enumerate(seq):
            for sid_rank,sid in enumerate(orders[d]):
                # Deterministic blend of normalized within-document sentence rank and
                # selected-document rank; no gold/sentence annotations.
                score=1/(sid_rank+1)+.25/(order_d+1)
                entries.append((-score,order_d,sid_rank,d,sid))
        entries.sort()
        return [(d,sid) for _,_,_,d,sid in entries[:budget]]
    if method=='link_weighted':
        caps=[int(bool(orders[d])) for d in seq]
    else:
        caps={
            'uniform2':[2,2,2,2,2],
            'uniform_recycle':[2,2,2,2,2],
            'front_4_3_1_1_1':[4,3,1,1,1],
            'balanced_3_3_2_1_1':[3,3,2,1,1],
            'reverse_1_1_2_3_3':[1,1,2,3,3],
        }.get(method)
        if caps is None:raise ValueError(method)
        caps=[min(x,len(orders[d])) for x,d in zip(caps[:len(seq)],seq)]
    chosen=[(d,sid) for d,cap in zip(seq,caps) for sid in orders[d][:cap]]
    if method=='uniform2' or len(chosen)>=budget:
        return chosen[:budget]
    remaining=set((d,sid) for d in seq for sid in orders[d])-set(chosen)
    used={d:sum(1 for chosen_doc,_ in chosen if chosen_doc==d) for d in seq}
    while remaining and len(chosen)<budget:
        if method=='link_weighted':
            candidates=[]
            for order_d,d in enumerate(seq):
                if used[d]<len(orders[d]):
                    utility=(1+weights.get(d,0))/(1+used[d])
                    candidates.append((-utility,order_d,d))
            if not candidates:break
            _,_,d=min(candidates)
        else:
            # Explicit deterministic source-order recycling when a cap is unfilled.
            d=next((d for d in seq if used[d]<len(orders[d])),None)
            if d is None:break
        sid=orders[d][used[d]]
        if (d,sid) not in remaining:
            raise AssertionError('recycling duplicate sentence')
        chosen.append((d,sid));remaining.remove((d,sid));used[d]+=1
    return chosen


def link_weights(row,selected,m25):
    titles=[row['context'][d][0] for d in selected]
    out={}
    for d in selected:
        own=row['context'][d][0]
        content=' '+m25.canon(' '.join(row['context'][d][1]))+' '
        count=sum(int(len(title)>4 and title in content)
                  for title in (' '+m25.canon(x)+' ' for x in titles if x!=own))
        out[d]=count
    return out


def span_to_frame_keys(reader,document,start,end):
    manifest=reader.manifests[document]
    pos=0;out=set()
    for desc in manifest['frames']:
        stop=pos+desc['len']
        if stop>start and pos<end:
            out.add(desc['sha'])
        pos=stop
    if pos!=manifest['size']:raise AssertionError('incomplete source span')
    return out


def experiment(rows,split_size=128):
    if len(rows)!=split_size*2:
        raise ValueError('two equal fixed segments required')
    m54=load('cdg54_r57',R54)
    m55=load('cdg55_r57',R55)
    m56=load('cdg56_r57',R56)
    m48=load('cdg48_r57',R48)
    m25=load('cdg25_r57',R25)
    with tempfile.TemporaryDirectory() as folder:
        index=m55.SentenceIndex(Path(folder)/'index.sqlite',rows)
        readers={
            'whole':m48.VersionedReader(index.original_blobs,'whole','json-zlib'),
            'gear512':m48.VersionedReader(index.original_blobs,'gear512','binary-zlib'),
        }
        try:
            for variant,reader in readers.items():
                for i,original in enumerate(index.original_blobs):
                    data,_=reader.read(reader.receipt(i,0,len(original)),pin_generation=i)
                    if data!=original:raise AssertionError('source hash readback mismatch')
            entries=[];verified=set()
            for qid,row in enumerate(rows):
                partition='discovery' if qid<split_size else 'second_partition'
                if m54.support_reference_issue(row):
                    raise ValueError('annotation issue in fixed R57 sample')
                gold=set((t,s) for t,s in row['supporting_facts'])
                for doc_policy in DOCUMENT_POLICIES:
                    selected=m54.select(row,doc_policy)[:5]
                    named=[row['context'][d][0] for d in selected]
                    doc_upper=int(set(t for t,s in gold).issubset(set(named)))
                    weights=link_weights(row,selected,m25)
                    orders={}
                    for d in selected:
                        title,sentences=row['context'][d]
                        fts_rank=index.choose(qid,d,row['question'],limit=len(sentences))
                        for selector in SELECTORS:
                            order=m56.rank_sentences(row['question'],sentences,named,title,
                                                     qid,d,selector,fts_rank,m25)
                            orders[(selector,d)]=order
                    for selector in SELECTORS:
                        per_doc={d:orders[(selector,d)] for d in selected}
                        for allocator in ALLOCATORS:
                            chosen=allocation(allocator,selected,per_doc,weights,qid)
                            if len(chosen)>GLOBAL_BUDGET or len(chosen)!=len(set(chosen)):
                                raise AssertionError('budget overflow or duplicate')
                            recovered={(row['context'][d][0],sid) for d,sid in chosen}
                            touched={variant:set() for variant in readers}
                            rawbytes=0
                            for d,sid in chosen:
                                original=row['context'][d][1][sid].encode('utf8')
                                source=index.records[(qid,d)]
                                lo,hi=m56.spans(row['context'][d][1])[sid][1:]
                                rawbytes+=hi-lo
                                if index.original_blobs[source][lo:hi]!=original:
                                    raise AssertionError('incorrect citation offsets')
                                for variant,reader in readers.items():
                                    touched[variant].update(span_to_frame_keys(
                                        reader,source,lo,hi))
                                    key=(variant,source,sid)
                                    if key not in verified:
                                        got,_=reader.read(
                                            reader.receipt(source,lo,hi),pin_generation=source)
                                        if got!=original:raise AssertionError('receipt mismatch')
                                        verified.add(key)
                            entries.append({
                                'partition':partition,'policy':doc_policy,
                                'selector':selector,'allocator':allocator,
                                'qid':qid,'complete_docs':doc_upper,
                                'complete_support':int(gold.issubset(recovered)),
                                'selected_sentences':len(chosen),
                                'selected_plain_bytes':rawbytes,
                                'gear512_read_bytes':sum(len(readers['gear512'].archive.frames[x])
                                                         for x in touched['gear512']),
                                'whole_read_bytes':sum(len(readers['whole'].archive.frames[x])
                                                       for x in touched['whole'])})
            grouped={}
            for entry in entries:
                key=(entry['partition'],entry['policy'],entry['selector'],entry['allocator'])
                grouped.setdefault(key,[]).append(entry)
            output=[]
            for (partition,policy,selector,allocator),cases in sorted(grouped.items()):
                output.append({
                    'partition':partition,'policy':policy,'selector':selector,
                    'allocator':allocator,'budget':GLOBAL_BUDGET,
                    'n':len(cases),
                    'document_upper_bound':sum(x['complete_docs'] for x in cases),
                    'all_gold_sentences_recovered':sum(x['complete_support'] for x in cases),
                    'mean_sentences_selected':round(statistics.mean(x['selected_sentences'] for x in cases),3),
                    'mean_plain_bytes_selected':round(statistics.mean(x['selected_plain_bytes'] for x in cases),3),
                    'mean_gear512_frame_bytes':round(statistics.mean(x['gear512_read_bytes'] for x in cases),3),
                    'mean_whole_frame_bytes':round(statistics.mean(x['whole_read_bytes'] for x in cases),3)})
            return {
                'questions':len(rows),'partition_size':split_size,'fixed_budget':GLOBAL_BUDGET,
                'source_index_bytes':index.db_bytes,
                'candidate_pool_short_of_5':sum(len(row['context'])<5 for row in rows),
                'archive_bytes':{k:v.size() for k,v in readers.items()},
                'verified_unique_source_spans':len(verified),
                'results':output,
                'limitations':[
                    'second partition from same previously aggregate-evaluated dev split; not a new corpus family',
                    'allocations were proposed after examining R54-56 aggregate outcomes; exploratory only',
                    'global budget 10, source snippets counted with ideal in-query frame reuse',
                    'all question-local document texts were used for initial BM25 scoring',
                    'sentence selection itself reads full local sentence text for scoring',
                    'no generated answers, semantic entailment, physical I/O or model-token accounting'
                ]}
        finally:
            index.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    m54=load('cdg54_source_r57',R54)
    rows=m54.locked_sample(m54.load_development())[:256]
    results=experiment(rows)
    Path(args.out).write_text(json.dumps(results,indent=2)+'\n')
    focus=[x for x in results['results'] if x['policy']=='bridge'
           and x['selector']=='fts']
    print('ROUND57',json.dumps({
        'questions':results['questions'],
        'index_bytes':results['source_index_bytes'],
        'archive_bytes':results['archive_bytes'],
        'bridge_fts_allocation':focus},sort_keys=True))


if __name__=='__main__':
    main()
