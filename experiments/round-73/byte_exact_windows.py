#!/usr/bin/env python3
"""R73: byte-exact source receipts for the *identical* R72 NLI evidence windows.

This is a storage-path and accounting audit, NOT a new claim verifier.
Original UTF-8 byte spans are retrieved from whole-Zlib and content-defined
CAS source frames, then normalized in precisely the same way as R72. A
separate FTS5 index is measured as an OPTIONAL conventional index overhead,
not claimed necessary for the in-memory overlap selector used here.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,re,statistics,sys,tempfile,time
from collections import Counter,defaultdict
from dataclasses import dataclass
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
TASK_GROUPS={'QA':8,'Summary':16}
SALT='CDG-R72-FROZEN-NLI-SUMMARY-TEST-v1'
LOCKED_IDS_SHA256='fd43a5ef07f80a51b05f590f55867eaefa70c9d02374fef7fd54d788d9cb9d84'
WORD_WIDTH=150
WORD_STRIDE=100
MAX_WINDOWS=96
METHODS=('first','lexical_top1','lexical_top3')


@dataclass(frozen=True)
class ByteWindow:
    byte_start:int
    byte_end:int
    normalized:str


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def sample(responses,sources):
    mapping={str(s['source_id']):s for s in sources}
    ids_by_task=defaultdict(set)
    for r in responses:
        sid=str(r.get('source_id'))
        if (r.get('split')=='test' and r.get('quality')=='good'
                and sid in mapping and mapping[sid].get('task_type') in TASK_GROUPS):
            ids_by_task[mapping[sid]['task_type']].add(sid)
    picked={}
    for task,count in TASK_GROUPS.items():
        ranked=sorted(ids_by_task[task],key=lambda sid:(
            hashlib.sha256((SALT+'|'+task+'|'+sid).encode()).hexdigest(),sid))
        if len(ranked)<count:raise ValueError('insufficient task source groups')
        picked[task]=ranked[:count]
    selected=set(x for ids in picked.values() for x in ids)
    digest=hashlib.sha256('\n'.join(sorted(selected)).encode()).hexdigest()
    if digest!=LOCKED_IDS_SHA256:
        raise ValueError('source sample does not match the independently run R72 NLI experiment')
    records=[r for r in responses if r.get('split')=='test' and
             r.get('quality')=='good' and str(r.get('source_id')) in selected]
    if len(records)!=141:
        raise ValueError('R72 paired source cohort response count changed')
    return records,mapping,sorted(selected),digest


def source_byte_windows(text):
    matches=list(re.finditer(r'\S+',text))
    if not matches:return []
    windows=[]
    for position in list(range(0,len(matches),WORD_STRIDE))[:MAX_WINDOWS]:
        until=min(len(matches),position+WORD_WIDTH)
        begin=matches[position].start()
        end=matches[until-1].end()
        raw=text[begin:end]
        expected=' '.join(m.group() for m in matches[position:until])
        normalized=' '.join(raw.split())
        if normalized!=expected:
            raise AssertionError('source window normalization changed words')
        windows.append(ByteWindow(
            byte_start=len(text[:begin].encode('utf8')),
            byte_end=len(text[:end].encode('utf8')),
            normalized=expected))
    return windows


def lexical_window_rank(windows,claim,r69):
    query=set(r69.content_words(claim))
    scored=sorted(
        ((len(query.intersection(r69.content_words(win.normalized))),i)
         for i,win in enumerate(windows)),
        key=lambda x:(-x[0],x[1]))
    return [j for _,j in scored[:3]]


def frame_ids(reader,generation,start,end):
    spans=reader.manifests[generation]
    current=0
    hits=set()
    for entry in spans['frames']:
        stop=current+entry['len']
        if stop>start and current<end:
            hits.add(entry['sha'])
        current=stop
    if current!=spans['size']:raise AssertionError('frame lengths changed original source length')
    return hits


def layout_bytes(reader,frames):
    return sum(len(reader.archive.frames[key]) for key in frames)


def evaluate(responses,sources):
    r69=load('cdg69_for_r73',R69)
    r48=load('cdg48_for_r73',R48)
    sample_rows,source_mapping,group_ids,digest=sample(responses,sources)
    originals=[r69.source_text(source_mapping[sid]).encode('utf8') for sid in group_ids]
    if not all(originals):raise ValueError('empty original QA/Summary source')
    starts=time.perf_counter_ns()
    windows={sid:source_byte_windows(r69.source_text(source_mapping[sid]))
             for sid in group_ids}
    window_precompute_ms=(time.perf_counter_ns()-starts)/1e6
    source_at={sid:i for i,sid in enumerate(group_ids)}
    if not all(windows.values()):raise AssertionError('source window generation failed')
    with tempfile.TemporaryDirectory() as tmp:
        idx=r48.EvidenceFTS(originals,Path(tmp)/'source_index.sqlite')
        archive={
            'whole':r48.VersionedReader(originals,'whole','binary-zlib'),
            'gear512':r48.VersionedReader(originals,'gear512','binary-zlib')}
        try:
            for source_index,blob in enumerate(originals):
                for reader in archive.values():
                    receipt=reader.receipt(source_index,0,len(blob))
                    recovered,_=reader.read(receipt,pin_generation=source_index)
                    if recovered!=blob:raise AssertionError('original source readback diverged')
            collected={task:{method:[] for method in METHODS}
                       for task in (*TASK_GROUPS,'all')}
            selection_ms=[]
            spans_verified=0
            source_chunks=Counter()
            for row in sample_rows:
                sid=str(row['source_id'])
                task=source_mapping[sid]['task_type']
                srcindex=source_at[sid]
                srcblob=originals[srcindex]
                spans=windows[sid]
                policy_frames={
                    method:{name:set() for name in archive}
                    for method in METHODS}
                policy_raw={method:0 for method in METHODS}
                claim_count=0
                for _,_,claim in r69.fragments(row['response']):
                    if not claim.strip():continue
                    t0=time.perf_counter_ns()
                    order=lexical_window_rank(spans,claim,r69)
                    selection_ms.append((time.perf_counter_ns()-t0)/1e6)
                    if not order:raise AssertionError('no source window for claim')
                    claim_count+=1
                    selected={
                        'first':[0],
                        'lexical_top1':[order[0]],
                        'lexical_top3':order,
                    }
                    checked=set()
                    for method,indices in selected.items():
                        for i in indices:
                            w=spans[i]
                            if not 0<=w.byte_start<w.byte_end<=len(srcblob):
                                raise AssertionError('UTF-8 source window range invalid')
                            if w.normalized!=' '.join(
                                srcblob[w.byte_start:w.byte_end].decode('utf8').split()):
                                raise AssertionError('NLI premise does not match normalized archived source')
                            policy_raw[method]+=w.byte_end-w.byte_start
                            for name,reader in archive.items():
                                policy_frames[method][name].update(
                                    frame_ids(reader,srcindex,w.byte_start,w.byte_end))
                            if i not in checked:
                                for name,reader in archive.items():
                                    receipt=reader.receipt(srcindex,w.byte_start,w.byte_end)
                                    restored,_=reader.read(receipt,pin_generation=srcindex)
                                    if restored!=srcblob[w.byte_start:w.byte_end]:
                                        raise AssertionError('compressed source window changed')
                                    spans_verified+=1
                                checked.add(i)
                for method,framed in policy_frames.items():
                    row_result={
                        'source_group':sid,'claim_count':claim_count,
                        'raw_window_bytes_requested':policy_raw[method],
                        'whole_compressed_frame_bytes':layout_bytes(
                            archive['whole'],framed['whole']),
                        'gear512_compressed_frame_bytes':layout_bytes(
                            archive['gear512'],framed['gear512']),
                    }
                    for target in (task,'all'):
                        collected[target][method].append(row_result)
                source_chunks[task]+=claim_count
            if source_chunks['QA']+source_chunks['Summary']!=760:
                raise AssertionError('R73 analyzed a different number of response fragments than R72')
            result={}
            for task,metrics in collected.items():
                result[task]={}
                for method,rows in metrics.items():
                    result[task][method]={
                        'responses':len(rows),
                        'mean_claims_per_response':round(statistics.mean(
                            r['claim_count'] for r in rows),3),
                        'mean_raw_window_bytes_requested_per_response':round(
                            statistics.mean(r['raw_window_bytes_requested'] for r in rows),3),
                        'mean_whole_unique_compressed_bytes_per_response':round(
                            statistics.mean(r['whole_compressed_frame_bytes'] for r in rows),3),
                        'mean_gear_unique_compressed_bytes_per_response':round(
                            statistics.mean(r['gear512_compressed_frame_bytes'] for r in rows),3),
                    }
            return {
                'source_sample_sha256':digest,
                'responses':len(sample_rows),
                'sources':len(group_ids),
                'claims':sum(source_chunks.values()),
                'source_task_claims':dict(source_chunks),
                'original_source_utf8_bytes':sum(map(len,originals)),
                'archive_bytes':{name:reader.size() for name,reader in archive.items()},
                'separate_optional_fts5_index_bytes':idx.index_bytes(),
                'archive_plus_optional_fts5_index_bytes':{
                    name:reader.size()+idx.index_bytes() for name,reader in archive.items()},
                'source_window_count':sum(len(x) for x in windows.values()),
                'source_window_precompute_ms':round(window_precompute_ms,3),
                'mean_in_memory_lexical_window_selection_ms':round(
                    statistics.mean(selection_ms),4),
                'verified_full_source_receipts':len(originals)*len(archive),
                'verified_original_window_receipts':spans_verified,
                'methods':result,
                'limitations':[
                    'this is a model-free archive/read-cost audit of the exact R72 source groups and window selection, no new semantic prediction',
                    'window normalized whitespace equals R72 NLI premise but the underlying original source receipt protects only the unnormalized byte span',
                    'source windows are selected by an in-memory content-word scan, not by FTS5; FTS5 disk bytes are optional conventional-control overhead, not secretly required',
                    'compressed frame bytes are unique within each response policy, assuming a warm response-local frame cache, not measured physical SSD reads',
                    'no source-document revision history, concurrent updates, fsync transactions, GPU/CPU model time or model weights included in archive footprint',
                    'actual R72 pretrained inference time/input token costs must be considered separately, not added as comparable bytes',
                    'all original RAGTruth sources/responses are transient, only compact aggregate values are committed',
                ]}
        finally:
            idx.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=ap.parse_args()
    r69=load('cdg69_load_r73',R69)
    responses,rx=r69.download('dataset/response.jsonl')
    sources,sx=r69.download('dataset/source_info.jsonl')
    result=evaluate(responses,sources)
    result['provenance']={
        'revision':r69.REVISION,
        'response_blob_sha':rx['git_blob'],'source_blob_sha':sx['git_blob']}
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND73',json.dumps({
        'sources':result['sources'],
        'responses':result['responses'],'claims':result['claims'],
        'archives':result['archive_bytes'],
        'optional_fts':result['separate_optional_fts5_index_bytes'],
        'verified':result['verified_original_window_receipts'],
        'methods':result['methods']},sort_keys=True))


if __name__=='__main__':
    main()
