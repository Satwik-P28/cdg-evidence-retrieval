#!/usr/bin/env python3
"""Round 69: actual human RAGTruth QA hallucination spans versus lexical source receipts.

The RAGTruth QA *test* split supplies generated responses, original source
passages, and human span annotations. We audit literal/normalized citation
matches and sentence-level lexical support proxies without training or tuning.
A byte-exact receipt is source integrity, NEVER a semantic support judgment.
No individual third-party response or source paragraph is emitted to artifacts.
"""
from __future__ import annotations
from collections import defaultdict,Counter
import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen,Request

HERE=Path(__file__).resolve().parent
REPO='ParticleMedia/RAGTruth'
REVISION='c103204b9ce28d6bbad859304bf30de72b8ed8fe'
FILES={
    'responses':('dataset/response.jsonl','f9ae5913fb9976684f3e13be3cd3465062db54cc'),
    'sources':('dataset/source_info.jsonl','119277774009f110aa58596b93f9512f62594a89')
}
R48=HERE.parent/'round-48'/'evidence_bridge.py'
SENTENCES=re.compile(r'[^\n.!?]+(?:[.!?]+|$)',re.UNICODE)
TOKENS=re.compile(r'[^\W_]+',re.UNICODE)
SCORING_THRESHOLDS=(.50,.75)
EVAL_SPLIT='test'
EVAL_TASK='QA'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    x=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=x
    spec.loader.exec_module(x)
    return x


def git_blob_sha(raw):
    return hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()


def fetch_pinned(key,download_fn=None):
    relative,digest=FILES[key]
    url=f'https://raw.githubusercontent.com/{REPO}/{REVISION}/{relative}'
    if download_fn is None:
        def download_fn(url):
            with urlopen(Request(url,headers={'User-Agent':'CDG-RAGTruth-integrity-audit/1.0'}),
                         timeout=180) as response:
                raw=response.read(150_000_000)
            return raw
    original=download_fn(url)
    if git_blob_sha(original)!=digest:
        raise ValueError('RAGTruth upstream blob SHA does not match pinned Git commit')
    return [json.loads(line) for line in original.splitlines() if line.strip()],len(original)


def words(text):
    return [m.group().casefold() for m in TOKENS.finditer(text)]


def canonical(text):
    return ' '.join(words(text))


def span_kind(label):
    if label.get('implicit_true',False):
        return 'implicit_true'
    name=str(label.get('label_type','')).casefold()
    if 'conflict' in name:
        return 'contradictory'
    if 'baseless' in name:
        return 'baseless'
    return 'other_annotated'


def validate_labels(text,labels):
    valid=[];rejected=0
    for label in labels:
        start,end=label.get('start'),label.get('end')
        if not isinstance(start,int) or not isinstance(end,int) or not (0<=start<end<=len(text)):
            rejected+=1
            continue
        if 'text' in label and label['text']!=text[start:end]:
            rejected+=1
            continue
        valid.append((start,end,label))
    return valid,rejected


def sentence_ranges(text):
    return [(m.start(),m.end(),m.group()) for m in SENTENCES.finditer(text)
            if m.group().strip()]


def proxy_score(sentence,source):
    """Fraction of unique token trigrams in a candidate statement found in source.
    For short statements use bigram/unigram fallback. This is lexical, not NLI."""
    query=words(sentence)
    reference=words(source)
    if not query:return 0.0
    n=min(3,len(query))
    grams={tuple(query[i:i+n]) for i in range(len(query)-n+1)}
    source_grams={tuple(reference[i:i+n]) for i in range(max(0,len(reference)-n+1))}
    if not grams:return 0.0
    return len(grams&source_grams)/len(grams)


def source_text(src):
    if src.get('task_type')!='QA':
        raise ValueError('R69 focuses only on QA source passages')
    info=src.get('source_info')
    if not isinstance(info,dict) or not isinstance(info.get('passages'),str):
        raise ValueError('missing original QA passage text')
    return info['passages']


def paired_cluster_interval(rows,value_key,reps=1200):
    """Deterministic source-ID clustered bootstrap of an overall mean."""
    import random
    buckets=defaultdict(list)
    for x in rows:buckets[x['source_id']].append(x[value_key])
    groups=list(buckets.values())
    if not groups:return None
    rng=random.Random(6900)
    samples=[]
    for _ in range(reps):
        groups_sampled=[groups[rng.randrange(len(groups))] for _ in groups]
        vals=[v for group in groups_sampled for v in group]
        samples.append(sum(vals)/len(vals))
    samples.sort()
    return [round(samples[int(.025*(reps-1))],5),
            round(samples[int(.975*(reps-1))],5)]


def wilson_95(successes,n):
    """Simple independent-observation Wilson interval for transparency.

    Does not correct for repeated responses per source; source-cluster
    bootstrap is reported separately for correlated units.
    """
    if n<=0:return None
    z=1.959963984540054
    p=successes/n
    denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return [round(max(0,center-half),5),round(min(1,center+half),5)]


def metrics_from_confusion(matrix):
    tp,fp,tn,fn=(matrix.get(k,0) for k in ('tp','fp','tn','fn'))
    return {
        'tp':tp,'fp':fp,'tn':tn,'fn':fn,
        'precision':round(tp/(tp+fp),5) if tp+fp else None,
        'recall':round(tp/(tp+fn),5) if tp+fn else None,
        'specificity':round(tn/(tn+fp),5) if tn+fp else None,
        'f1':round(2*tp/(2*tp+fp+fn),5) if 2*tp+fp+fn else None,
        'support_citation_false_accepts':fn,
    }


def audit(source_rows,response_rows):
    sources={str(x['source_id']):x for x in source_rows}
    selected=[r for r in response_rows
              if r.get('split')==EVAL_SPLIT
              and r.get('quality')=='good'
              and str(r.get('source_id')) in sources
              and sources[str(r['source_id'])].get('task_type')==EVAL_TASK]
    if not selected:
        raise ValueError('no official RAGTruth test QA responses with source content')
    ids=[str(x['id']) for x in selected]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate response ID; cannot independently count annotations')
    original_sources={str(r['source_id']):source_text(sources[str(r['source_id'])])
                      for r in selected}
    ordered=sorted(original_sources)
    r48=module('cdg48_for_ragtruth69',R48)
    original=[original_sources[x].encode('utf8') for x in ordered]
    archives={
        'whole':r48.VersionedReader(original,'whole','json-zlib'),
        'gear512':r48.VersionedReader(original,'gear512','binary-zlib'),
    }
    for index,raw in enumerate(original):
        for reader in archives.values():
            got,_=reader.read(reader.receipt(index,0,len(raw)),pin_generation=index)
            if got!=raw:raise AssertionError('source archive did not restore exact passages')
    source_indices={key:i for i,key in enumerate(ordered)}
    confusion={name:Counter() for name in ('whole_literal_missing','trigram50_missing','trigram75_missing')}
    sentence_rows=[]
    span_rows=[]
    kinds=Counter()
    invalid_label_count=0
    invalid_response_count=0
    fragments_with_literal_citation=0
    for item in selected:
        response=item.get('response','')
        labels=item.get('labels',[])
        if not isinstance(response,str) or not isinstance(labels,list):
            invalid_response_count+=1
            continue
        annotated,rejected=validate_labels(response,labels)
        invalid_label_count+=rejected
        sourceid=str(item['source_id'])
        base=original_sources[sourceid]
        source_id=source_indices[sourceid]
        for start,end,label in annotated:
            text=response[start:end]
            kind=span_kind(label)
            kinds[kind]+=1
            found_at=base.find(text)
            if found_at>=0:
                prefix=len(base[:found_at].encode('utf8'))
                hi=prefix+len(text.encode('utf8'))
                for reader in archives.values():
                    got,_=reader.read(reader.receipt(source_id,prefix,hi),
                                      pin_generation=source_id)
                    if got!=text.encode('utf8'):
                        raise AssertionError('false source receipt')
                fragments_with_literal_citation+=1
            span_rows.append({
                'source_id':sourceid,
                'kind':kind,
                'exact_utf8_source_substring':int(found_at>=0),
                'normalized_phrase_in_source':int(
                    bool(canonical(text)) and canonical(text) in canonical(base)),
                'due_to_null':int(bool(label.get('due_to_null',False)))
            })
        for begin,end,text in sentence_ranges(response):
            overlaps=[(start,stop,label) for start,stop,label in annotated
                      if start<end and stop>begin]
            factual_label=int(any(span_kind(label)!='implicit_true'
                                   for start,stop,label in overlaps))
            implicit_true_only=int(
                bool(overlaps) and
                all(span_kind(label)=='implicit_true' for start,stop,label in overlaps))
            literal=int(text.strip().casefold() in base.casefold())
            tri=proxy_score(text,base)
            guessed={
                'whole_literal_missing':1-literal,
                'trigram50_missing':int(tri<SCORING_THRESHOLDS[0]),
                'trigram75_missing':int(tri<SCORING_THRESHOLDS[1]),
            }
            for name,pred in guessed.items():
                key='tp' if pred and factual_label else ('fp' if pred else 'tn') if not factual_label else 'fn'
                confusion[name][key]+=1
            sentence_rows.append({
                'source_id':sourceid,'is_human_labeled':factual_label,
                'implicit_true_only':implicit_true_only,
                'literal_support_match':literal,
                'trigram_overlap':tri,
                'response_model':str(item.get('model','')),
            })
    splits=defaultdict(set)
    for row in response_rows:
        splits[str(row.get('split'))].add(str(row.get('source_id')))
    train_test_overlap=len(splits.get('train',set())&splits.get('test',set()))
    by_kind={}
    for kind in sorted(kinds):
        items=[row for row in span_rows if row['kind']==kind]
        by_kind[kind]={
            'n':len(items),
            'literal_source_citations':sum(r['exact_utf8_source_substring'] for r in items),
            'normalized_phrase_source_matches':sum(r['normalized_phrase_in_source'] for r in items),
            'due_to_null_count':sum(r['due_to_null'] for r in items),
            'literal_match_fraction_source_clustered_bootstrap_percentiles':paired_cluster_interval(
                items,'exact_utf8_source_substring'),
            'literal_match_fraction_independent_wilson_95':wilson_95(
                sum(r['exact_utf8_source_substring'] for r in items),len(items)),
        }
    return {
        'source_id_count':len(original_sources),
        'good_test_qa_responses':len(selected),
        'response_ids_sha256':hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest(),
        'source_ids_sha256':hashlib.sha256('\n'.join(ordered).encode()).hexdigest(),
        'train_test_same_source_id_count_all_tasks':train_test_overlap,
        'human_annotation_spans':len(span_rows),
        'invalid_annotation_spans':invalid_label_count,
        'invalid_response_records':invalid_response_count,
        'span_categories':by_kind,
        'strict_source_receipts_issued_for_annotated_spans':fragments_with_literal_citation,
        'sentence_chunks':len(sentence_rows),
        'labeled_hallucinated_sentences':sum(x['is_human_labeled'] for x in sentence_rows),
        'implicit_true_only_sentence_chunks':sum(x['implicit_true_only'] for x in sentence_rows),
        'lexical_auditors':{name:metrics_from_confusion(matrix)
                            for name,matrix in confusion.items()},
        'whole_archive_bytes':archives['whole'].size(),
        'gear512_archive_bytes':archives['gear512'].size(),
        'controls':{
            'training':False,
            'thresholds':SCORING_THRESHOLDS,
            'test_only':True,
            'source_pinned_sha_git_blobs':{key:sha for key,(_,sha) in FILES.items()},
            'source_repo_commit':REVISION,
        },
        'limitations':[
            'human RAGTruth test annotations include many tasks; this pass evaluates only original QA (MS MARCO sources)',
            'human spans often identify only erroneous substring, not full factual claim; matching it in source does not establish statement entailment',
            'sentence chunks are heuristic punctuation-delimited fragments, not atomic claims',
            'unlabeled sentences are NOT verified true; absent annotations are proxy negatives only',
            'classification precision and specificity use unlabeled response sentences as proxy negatives, NOT human-confirmed nonhallucinations',
            'zero-positive source-cluster bootstrap intervals are degenerate empirical resamples, not a confidence bound; Wilson interval assumes independence and is only a reference',
            'implicit_true human flag explicitly separates unsupported-but-correct content',
            'literal and trigram match are weak lexical controls, not NLI/semantic entailment models',
            'test split is for diagnostic of frozen lexical controls; do not tune thresholds on these results',
            'source-level bootstrap accounts for shared source IDs but not independent generative model/domain effects',
            'source content-addressed receipts authenticate local byte restoration, not external origin, timestamp or semantic truth',
            'archive size excludes QA full text/embedding index, model weights and physical SSD I/O',
            'original source passages and response texts not redistributed or stored as output artifacts',
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    response_rows,response_bytes=fetch_pinned('responses')
    source_rows,source_bytes=fetch_pinned('sources')
    outcome=audit(source_rows,response_rows)
    outcome['downloaded_file_sizes']={'responses':response_bytes,'sources':source_bytes}
    Path(args.out).write_text(json.dumps(outcome,indent=2)+'\n')
    print('ROUND69',json.dumps({
        'qa_test_responses':outcome['good_test_qa_responses'],
        'source_count':outcome['source_id_count'],
        'human_spans':outcome['human_annotation_spans'],
        'span_categories':outcome['span_categories'],
        'sentence_chunks':outcome['sentence_chunks'],
        'lexical_auditors':outcome['lexical_auditors'],
        'storage':{'whole':outcome['whole_archive_bytes'],
                   'gear512':outcome['gear512_archive_bytes']},
        'invalid_labels':outcome['invalid_annotation_spans'],
        'official_source_overlap':outcome['train_test_same_source_id_count_all_tasks'],
    },sort_keys=True))


if __name__=='__main__': main()
