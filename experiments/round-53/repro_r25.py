#!/usr/bin/env python3
"""Round 53: cross-reproduce the original 100-question HotpotQA-derived R25 study.

Fetch EXACT pinned Git blob with upstream SHA check, compare independently
written old JavaScript aggregate metrics with Python reproduction. No source
text is published by this script and no LLM answer-quality claims are made.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SCRIPT=ROOT.parent/'round-25'/'bridge_probe.py'
HISTORIC=ROOT.parent/'round-25'/'results.json'


def loader():
    spec=importlib.util.spec_from_file_location('cdg_original_r25_python',SCRIPT)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(m)
    return m


def compact(result):
    return {
        'questions':result['questions'],
        'paired':result['paired'],
        'complete_documents':{
            method:{str(k):result['methods'][method][str(k)]['all']['complete_docs']
                    for k in (2,3,5)}
            for method in ('bm25','bridge','mmr')
        },
        'complete_top2_sentences':{
            method:{str(k):result['methods'][method][str(k)]['all']['complete_sentences_top2']
                    for k in (2,3,5)}
            for method in ('bm25','bridge','mmr')
        },
    }


def evaluate(data,old):
    original=loader()
    # Explicitly validate all gold sentence references against the provided
    # question-local contexts before any retrieval.
    original.validate(data)
    fresh=compact(original.evaluate(data))
    expected={
        'questions':old['corpus']['questions'],
        'paired':old['paired_complete_docs'],
        'complete_documents':{
            key:{str(k):old['methods'][key][str(k)]['all']['complete_docs'] for k in (2,3,5)}
            for key in ('bm25','bridge','mmr')},
        'complete_top2_sentences':{
            key:{str(k):old['methods'][key][str(k)]['all']['complete_gold_sentences_with_top2_per_document']
                 for k in (2,3,5)}
            for key in ('bm25','bridge','mmr')},
    }
    mismatches=[]
    for key in ('questions','paired','complete_documents','complete_top2_sentences'):
        if fresh[key]!=expected[key]:
            mismatches.append({'field':key,'python':fresh[key],'historical_js':expected[key]})
    return {'source_git_blob_sha':original.BLOB_SHA,
            'upstream_revision':original.REVISION,
            'observed':fresh,
            'previous_js':expected,
            'cross_implementation_equal':not mismatches,
            'mismatches':mismatches,
            'limits':['curated upstream train sample of 100, gold documents within each question-local pool',
                      'not held out and not verified against official HotpotQA dev archive',
                      'source text downloaded only transiently and not redistributed',
                      'no answer generator, semantic verifier, FTS5 or compressed read measurement']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    p.add_argument('--strict',action='store_true',help='fail on cross-implementation discrepancy')
    options=p.parse_args()
    historical=json.loads(HISTORIC.read_text())
    original=loader()
    with tempfile.TemporaryDirectory() as home:
        data=original.get_data(Path(home)/'qa_train.json',download=True)
        result=evaluate(data,historical)
    Path(options.out).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print('ROUND53',json.dumps({
        'questions':result['observed']['questions'],
        'python_complete_documents':result['observed']['complete_documents'],
        'same_as_independent_js':result['cross_implementation_equal'],
        'mismatches':result['mismatches']
    },ensure_ascii=False))
    if options.strict and not result['cross_implementation_equal']:
        raise AssertionError('Python reproducer and historical JS results disagree; investigate before publication')


if __name__=='__main__':
    main()
