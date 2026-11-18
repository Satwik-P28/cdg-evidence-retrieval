#!/usr/bin/env python3
"""R66: joined retrieval, exact evidence materialization, archive and index costs.

The answer string is used ONLY after evidence selection, as an answerability
*diagnostic*, not as an input to the retriever or a generator. This is NOT
model question answering or measured hallucination; do not mislabel it.
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
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R55=HERE.parent/'round-55'/'heldout_frames.py'
R57=HERE.parent/'round-57'/'budget_router.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R25=HERE.parent/'round-25'/'bridge_probe.py'
N=128
SALT='CDG-R66-UNSEEN-DEV-IDS-LOCKED-v1'
STRATEGIES=('bm25_all','bridge_all','bm25_fts2','bridge_fts2','bridge_recycled10')
LAYOUTS=(('whole','whole','json-zlib'),('gear512','gear512','binary-zlib'))
K=(2,5)


def dynamic(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def locked_unseen(rows):
    """Exclude *all* R54 locked 512 IDs, then sample by disjoint salted hash."""
    h=dynamic('r54_for_r66_sampling',R54)
    excluded={str(row['_id']) for row in h.locked_sample(rows)}
    candidates=[row for row in rows if str(row['_id']) not in excluded]
    ranked=sorted(candidates,key=lambda row:(hashlib.sha256(
        (SALT+'|'+str(row['_id'])).encode()).hexdigest(),str(row['_id'])))
    if len(ranked)<N:raise ValueError('not enough unseen independent question IDs')
    sample=ranked[:N]
    if excluded.intersection(str(row['_id']) for row in sample):
        raise AssertionError('question ID overlap with previous data')
    return sample


def literal_answer_present(answer,raw_text):
    """Strict postselection diagnostic; exclude yes/no and empty answers.

    This is *not* generative correctness. Exact word boundaries reduce
    accidental substring hits, but cross-entity ambiguity still exists.
    """
    answer=str(answer).strip()
    if not answer or answer.casefold() in ('yes','no','unknown','none'):
        return None
    escaped=re.escape(answer)
    return bool(re.search(r'(?<!\w)'+escaped+r'(?!\w)',raw_text,flags=re.IGNORECASE))


def frame_ids(reader,source,start,end):
    if end==start:return set()
    pos=0
    touched=set()
    manifest=reader.manifests[source]
    for frame in manifest['frames']:
        nxt=pos+frame['len']
        if nxt>start and pos<end:
            touched.add(frame['sha'])
        pos=nxt
    if pos!=manifest['size']:raise AssertionError('source frame map invalid')
    return touched


def tokens(text):
    return len(re.findall(r'[^\W_]+',text,flags=re.UNICODE))


def evaluate(rows):
    m54=dynamic('r54_eval66',R54)
    m55=dynamic('r55_eval66',R55)
    m57=dynamic('r57_eval66',R57)
    m48=dynamic('r48_eval66',R48)
    with tempfile.TemporaryDirectory() as tmp:
        idx=m55.SentenceIndex(Path(tmp)/'sentences.sqlite',rows)
        readers={label:m48.VersionedReader(idx.original_blobs,frames,manifest)
                 for label,frames,manifest in LAYOUTS}
        observations={key:[] for key in STRATEGIES for _ in [0]}
        expected_source_spans=0
        try:
            for qid,row in enumerate(rows):
                if m54.support_reference_issue(row):
                    # No deletion or unseen-sample reshuffle. Score as unscorable.
                    valid=False
                else:
                    valid=True
                gold=set((title,sid) for title,sid in row['supporting_facts'])
                docs={}
                cpu_us={}
                for method in ('bm25','bridge'):
                    start=time.perf_counter_ns()
                    docs[method]=m54.select(row,method)
                    cpu_us[method]=(time.perf_counter_ns()-start)/1000
                spans_by_doc={}
                fts_cpu_us=0.0
                for did in set(docs['bm25'][:5]+docs['bridge'][:5]):
                    begin=time.perf_counter_ns()
                    ss=row['context'][did][1]
                    spans_by_doc[did]=idx.choose(qid,did,row['question'],limit=len(ss))
                    fts_cpu_us+=(time.perf_counter_ns()-begin)/1000
                for method in STRATEGIES:
                    doc_policy=method.split('_')[0]
                    for k in K:
                        selected_docs=docs[doc_policy][:k]
                        orders={did:[sid for sid,lo,hi in spans_by_doc[did]]
                                for did in selected_docs}
                        if method.endswith('all'):
                            selection=[(did,sid) for did in selected_docs
                                       for sid in range(len(row['context'][did][1]))]
                        elif method.endswith('fts2'):
                            selection=[(did,sid) for did in selected_docs
                                       for sid in orders[did][:2]]
                        elif method=='bridge_recycled10':
                            # For k2 use maximum 4 sentences total, matching the
                            # two-per-source allowance; for k5, 10.
                            selection=m57.allocation(
                                'uniform_recycle',selected_docs,orders,
                                {},qid,budget=10) if k==5 else [
                                    (did,sid) for did in selected_docs
                                    for sid in orders[did][:2]]
                        else:
                            raise ValueError('unknown strategy')
                        evidence=set((row['context'][did][0],sid)
                                     for did,sid in selection)
                        text=' '.join(row['context'][did][1][sid]
                                      for did,sid in selection)
                        count_bytes=sum(len(row['context'][did][1][sid].encode())
                                        for did,sid in selection)
                        activation={name:set() for name in readers}
                        for did,sid in selection:
                            document=idx.records[(qid,did)]
                            sentence=row['context'][did][1][sid].encode()
                            parts=m55.module('r56_for66',HERE.parent/'round-56'/'sentence_policy.py').spans(row['context'][did][1])
                            _,lo,hi=parts[sid]
                            if idx.original_blobs[document][lo:hi]!=sentence:
                                raise AssertionError('original byte offsets wrong')
                            expected_source_spans+=1
                            for name,reader in readers.items():
                                activation[name].update(frame_ids(reader,document,lo,hi))
                                receipt=reader.receipt(document,lo,hi)
                                got,_=reader.read(receipt,pin_generation=document)
                                if got!=sentence:
                                    raise AssertionError('compressed evidence changed')
                        item={
                            'qid':qid,'strategy':method,'k':k,
                            'type':row.get('type','unknown'),
                            'valid':valid,
                            'complete_documents':int(valid and
                                set(t for t,s in gold).issubset({
                                    row['context'][did][0] for did in selected_docs})),
                            'complete_gold_sentences':int(valid and gold.issubset(evidence)),
                            'answer_literal_present':literal_answer_present(row.get('answer',''),text),
                            'selected_sentences':len(selection),
                            'evidence_utf8_bytes':count_bytes,
                            'evidence_tokens_regex_proxy':tokens(text),
                            'retriever_cpu_us':cpu_us[doc_policy],
                            'fts_lookup_cpu_us_amortized':fts_cpu_us,
                        }
                        for name,reader in readers.items():
                            item[name+'_compressed_frame_bytes']=sum(
                                len(reader.archive.frames[frame])
                                for frame in activation[name])
                        observations[method].append(item)
            results={}
            for strategy,items in observations.items():
                results[strategy]={}
                for k in K:
                    part=[item for item in items if item['k']==k]
                    named=[i['answer_literal_present'] for i in part
                           if i['answer_literal_present'] is not None]
                    results[strategy][str(k)]={
                        'n':len(part),
                        'invalid_support_annotations':sum(not i['valid'] for i in part),
                        'complete_docs':sum(i['complete_documents'] for i in part),
                        'complete_gold_sentences':sum(i['complete_gold_sentences'] for i in part),
                        'answer_literal_diagnostic_applicable':len(named),
                        'answer_literal_present':sum(named),
                        'mean_evidence_tokens_regex_proxy':round(statistics.mean(
                            i['evidence_tokens_regex_proxy'] for i in part),2),
                        'mean_evidence_utf8_bytes':round(statistics.mean(
                            i['evidence_utf8_bytes'] for i in part),2),
                        'mean_whole_compressed_frame_bytes':round(statistics.mean(
                            i['whole_compressed_frame_bytes'] for i in part),2),
                        'mean_gear512_compressed_frame_bytes':round(statistics.mean(
                            i['gear512_compressed_frame_bytes'] for i in part),2),
                        'median_retriever_cpu_us':round(statistics.median(
                            i['retriever_cpu_us'] for i in part),2),
                        'median_shared_fts_lookup_cpu_us':round(statistics.median(
                            i['fts_lookup_cpu_us_amortized'] for i in part),2),
                        'mean_selected_sentences':round(statistics.mean(
                            i['selected_sentences'] for i in part),2)}
            return {
                'n':len(rows),
                'source_id_digest_sha256':hashlib.sha256(
                    '\n'.join(sorted(str(row['_id']) for row in rows)).encode()).hexdigest(),
                'source_dev_sha256':m54.SHA256,
                'independent_split':'previous R54 512 IDs excluded; new R66 fixed salted rank selection of remaining official HotpotQA distractor dev IDs',
                'index_sqlite_bytes':idx.db_bytes,
                'index_build_ms':round(idx.build_ms,3),
                'source_count':len(idx.original_blobs),
                'source_archive_bytes':{key:reader.size() for key,reader in readers.items()},
                'archive_plus_index_bytes':{key:reader.size()+idx.db_bytes
                                            for key,reader in readers.items()},
                'total_verified_exact_evidence_spans':expected_source_spans,
                'outcomes':results,
                'limitations':[
                    'gold paragraph-containing closed-world HotpotQA distractor setting, not open-corpus or reader QA',
                    'answer literal presence is only a source answerability proxy and cannot establish answer correctness or support',
                    'the exact gold answer is never shown to selection, only used postselection for diagnostic',
                    'all candidate texts used in per-question BM25 document scoring before compressed materialization',
                    'FTS index is built using all candidate source sentences, storage and build time charged',
                    'whole-source vs gear results use logical unique compressed-frame activation, not measured SSD I/O',
                    'token count is a regex proxy, not actual model tokenizer cost',
                    'CPU times are warm Python medians on a shared serial runner, not robust hardware benchmarks',
                    'no generative reader, verifier, entailment, citation authority or hallucination assessment'] }
        finally:
            idx.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    m54=dynamic('r54_load66',R54)
    all_rows=m54.load_development()
    rows=locked_unseen(all_rows)
    result=evaluate(rows)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND66',json.dumps({
        'n':result['n'],'sources':result['source_count'],
        'index':result['index_sqlite_bytes'],
        'archives':result['source_archive_bytes'],
        'outcomes':result['outcomes'],
        'verified_spans':result['total_verified_exact_evidence_spans']},sort_keys=True))


if __name__=='__main__':main()
