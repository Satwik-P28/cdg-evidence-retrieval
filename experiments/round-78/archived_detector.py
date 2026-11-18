#!/usr/bin/env python3
"""R78: supply the *same* R76 trained verifier from SHA-verified compressed sources.

This is an archive-to-detector integration test with benchmark-provided source ID,
not a retrieval experiment or a novel detector. Original third-party text and
model weights remain upstream. Only aggregate metrics and hashes are persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
R48=ROOT/'round-48'/'evidence_bridge.py'
R69=ROOT/'round-69'/'ragtruth_grounding.py'
R73=ROOT/'round-73'/'byte_exact_windows.py'
R76=ROOT/'round-76'/'lettuce_reference.py'
SUMMARY_MAX_WORDS=96*150
LAYOUTS=('whole','gear512')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def visible_prefix_end(source_text,task):
    """Exactly the bytes needed for R76's passage assembly, no gold labels."""
    if task=='QA':
        return len(source_text.encode('utf8'))
    if task!='Summary':
        raise ValueError('unsupported task')
    matches=list(re.finditer(r'\S+',source_text))
    if len(matches)<=SUMMARY_MAX_WORDS:
        return len(source_text.encode('utf8'))
    return len(source_text[:matches[SUMMARY_MAX_WORDS-1].end()].encode('utf8'))


def substitute_source_text(source_row,text):
    row=dict(source_row)
    if row.get('task_type')=='QA':
        info=dict(row['source_info'])
        info['passages']=text
        row['source_info']=info
    elif row.get('task_type')=='Summary':
        row['source_info']=text
    else:
        raise ValueError('unsupported task')
    return row


def materialize(reader,generation,source_row,r69,r76):
    """Recover an exact original byte prefix and derive the exact R76 inputs."""
    original=r69.source_text(source_row)
    raw=original.encode('utf8')
    end=visible_prefix_end(original,source_row['task_type'])
    t0=time.perf_counter()
    receipt=reader.receipt(generation,0,end)
    decoded,cost=reader.read(receipt,pin_generation=generation)
    elapsed=time.perf_counter()-t0
    if decoded!=raw[:end]:
        raise AssertionError('archive byte receipt failed original SHA-pinned source')
    decoded_text=decoded.decode('utf8')
    passages,question,_=r76.assemble_context(
        substitute_source_text(source_row,decoded_text),r69)
    expected_passages,expected_question,_=r76.assemble_context(source_row,r69)
    if (passages,question)!=(expected_passages,expected_question):
        raise AssertionError('archive changed trained detector input')
    return (passages,question),{
        'source_bytes_requested':end,
        'compressed_frame_bytes':cost,
        'receipt_wall_seconds':elapsed,
        'source_digest_sha256':hashlib.sha256(raw).hexdigest(),
    }


def metrics(rows,r69):
    scores=defaultdict(lambda: {'response':[], 'char':[],
                                'strict_response':[], 'strict_char':[],
                                'n':0,'detector_pair_mismatches':0})
    for row in rows:
        for task in (row['task'],'all'):
            s=scores[task]
            s['response'].append(r76_confusion(row['archived'],row['gold'],True))
            s['char'].append(r76_confusion(row['archived'],row['gold'],False))
            s['strict_response'].append(r76_confusion(
                row['archived'],row['strict'],True))
            s['strict_char'].append(r76_confusion(
                row['archived'],row['strict'],False))
            s['n']+=1
            s['detector_pair_mismatches']+=int(row['archived']!=row['original'])
    r76=load('r76_metrics78',R76)
    return {k:{
        'n':v['n'],
        'response':r76.micro(v['response'],r69),
        'character':r76.micro(v['char'],r69),
        'strict_response':r76.micro(v['strict_response'],r69),
        'strict_character':r76.micro(v['strict_char'],r69),
        'paired_original_archived_mask_mismatches':v['detector_pair_mismatches'],
    } for k,v in scores.items()}


def r76_confusion(pred,gold,response_level):
    if response_level:
        pred,gold=[any(pred)],[any(gold)]
    if len(pred)!=len(gold):
        raise AssertionError('prediction/annotation shapes mismatch')
    return {
        'tp':sum(bool(a and b) for a,b in zip(pred,gold)),
        'fp':sum(bool(a and not b) for a,b in zip(pred,gold)),
        'fn':sum(bool(not a and b) for a,b in zip(pred,gold)),
        'tn':sum(bool(not a and not b) for a,b in zip(pred,gold)),
    }


def evaluate(chosen,byid,detector,r69,r48,r76):
    source_ids=sorted({str(r['source_id']) for r in chosen})
    originals=[r69.source_text(byid[sid]).encode('utf8') for sid in source_ids]
    generation_by_sid={sid:i for i,sid in enumerate(source_ids)}
    t0=time.perf_counter()
    archives={name:r48.VersionedReader(originals,name,'binary-zlib')
              for name in LAYOUTS}
    archive_build_sec=time.perf_counter()-t0
    full_checks=0
    for generation,source in enumerate(originals):
        for reader in archives.values():
            full,full_cost=reader.read(
                reader.receipt(generation,0,len(source)),
                pin_generation=generation)
            if full!=source or full_cost<=0:
                raise AssertionError('full source archival roundtrip failed')
            full_checks+=1
    with tempfile.TemporaryDirectory() as d:
        optional_idx=r48.EvidenceFTS(originals,Path(d)/'index.sqlite')
        try:
            index_size=optional_idx.index_bytes()
        finally:
            optional_idx.close()
    rows=[]
    bytes_by_layout=defaultdict(list)
    read_by_layout=defaultdict(list)
    raw_requested=[]
    original_model_sec=0.0
    archive_model_sec=0.0
    for index,row in enumerate(chosen):
        sid=str(row['source_id'])
        source=byid[sid]
        gen=generation_by_sid[sid]
        materialized={name:materialize(reader,gen,source,r69,r76)
                      for name,reader in archives.items()}
        first,_=materialized['whole']
        second,_=materialized['gear512']
        if first!=second:
            raise AssertionError('source layouts feed different model inputs')
        canonical=r76.assemble_context(source,r69)
        assert first==(canonical[0],canonical[1])
        for name,(_,cost) in materialized.items():
            bytes_by_layout[name].append(cost['compressed_frame_bytes'])
            read_by_layout[name].append(cost['receipt_wall_seconds'])
        raw_requested.append(materialized['whole'][1]['source_bytes_requested'])
        gold,strict=r76.text_mask(row,r69)
        # Alternate call order to reduce systematic warm-model bias.
        if index%2:
            archive_mask,arc_perf=r76.audited_prediction(
                detector,first[0],row['response'],first[1])
            original_mask,orig_perf=r76.audited_prediction(
                detector,canonical[0],row['response'],canonical[1])
        else:
            original_mask,orig_perf=r76.audited_prediction(
                detector,canonical[0],row['response'],canonical[1])
            archive_mask,arc_perf=r76.audited_prediction(
                detector,first[0],row['response'],first[1])
        original_model_sec+=orig_perf['elapsed_wall_sec']
        archive_model_sec+=arc_perf['elapsed_wall_sec']
        if original_mask!=archive_mask:
            raise AssertionError('model masks diverged for exact equivalent inputs')
        rows.append({'sid':sid,'task':source['task_type'],
                     'original':original_mask,'archived':archive_mask,
                     'gold':gold,'strict':strict})
    outcomes=metrics(rows,r69)
    if len(chosen)!=141 or len(source_ids)!=24:
        raise AssertionError('frozen R76 cohort drifted')
    return {
        'source_groups':len(source_ids),'response_count':len(chosen),
        'sample_source_ids_sha256':hashlib.sha256(
            '\n'.join(source_ids).encode()).hexdigest(),
        'archive_full_source_readbacks':full_checks,
        'archive_verified_response_receipts':len(chosen)*len(LAYOUTS),
        'source_original_bytes':sum(map(len,originals)),
        'archive_build_seconds':round(archive_build_sec,4),
        'optional_not_used_fts5_bytes':index_size,
        'raw_prefix_bytes_requested_per_response_mean':round(
            statistics.mean(raw_requested),3),
        'layouts':{
            name:{
                'persistent_archive_bytes':reader.size(),
                'archive_plus_optional_fts5_bytes':reader.size()+index_size,
                'mean_logical_compressed_bytes_per_response':round(
                    statistics.mean(bytes_by_layout[name]),3),
                'median_warm_memory_receipt_ms':round(
                    statistics.median(read_by_layout[name])*1000,4),
                'mean_warm_memory_receipt_ms':round(
                    statistics.mean(read_by_layout[name])*1000,4),
            } for name,reader in archives.items()},
        'cpu_inference_original_route_seconds':round(original_model_sec,3),
        'cpu_inference_archive_route_seconds':round(archive_model_sec,3),
        'human_label_outcomes':outcomes,
        'limitations':[
            'source ID is supplied by RAGTruth; no retriever was executed and no source-identification cost was included',
            'an existing RAGTruth-trained detector is used, not a CDG model or evidence of independent transfer',
            'two identical detector inputs per response confirm paired equivalence but double benchmarking workload',
            'archive reads, compression and manifest processing are warm in-memory Python; not SSD cold I/O or transaction durability',
            'compressed activation bytes are logical encoded frame traffic; no block alignment or operating-system page reads',
            'FTS5 source-line index is optional and was not queried for evidence selection',
            'model weights, tokenizer RAM, temporary source RAM, original source download and updates are not included in archive bytes',
            'human annotations evaluate existing answers, no generated answer changed or improved',
            'original upstream passages and answers are never redistributed',
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    a=p.parse_args()
    r69=load('r69_run78',R69)
    r48=load('r48_run78',R48)
    r76=load('r76_run78',R76)
    answers,answer_src=r69.download('dataset/response.jsonl')
    sources,source_src=r69.download('dataset/source_info.jsonl')
    chosen,byid,sample=r76.sample_rows(answers,sources)
    detector,model_info=r76.make_detector()
    result=evaluate(chosen,byid,detector,r69,r48,r76)
    if result['sample_source_ids_sha256']!=sample['source_ids_sha256']:
        raise AssertionError('sample source identities diverged')
    result['upstream']={
        'ragtruth_revision':r69.REVISION,
        'answer_git_blob':answer_src['git_blob'],
        'source_git_blob':source_src['git_blob'],
        'detector_git_revision':model_info['snapshot_sha'],
        'detector_parameters':model_info['model_parameters'],
        'detector_package_version':r76.VERSION,
    }
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND78',json.dumps({
        'source_groups':result['source_groups'],
        'responses':result['response_count'],
        'layouts':result['layouts'],
        'human_response':{
            task:part['response']
            for task,part in result['human_label_outcomes'].items()},
        'original_inference_seconds':result['cpu_inference_original_route_seconds'],
        'archive_inference_seconds':result['cpu_inference_archive_route_seconds'],
    },sort_keys=True))


if __name__=='__main__':
    main()
