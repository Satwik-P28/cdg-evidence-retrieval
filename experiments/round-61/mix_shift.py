#!/usr/bin/env python3
"""Round 61: frozen R58 mixed-codec routing on independently held-back source IDs.

Stress source-family mixture. Use the *last* 128 HotpotQA dev questions'
paragraphs, not the first 128 used to develop R58. Keep the 12 pinned uv
revisions, varying how many are present and how many unrelated sources are
added. Policy and weights are unchanged from R58; this is no new corpus family.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
R58=HERE.parent/'round-58'/'mixed_archive.py'
R54=HERE.parent/'round-54'/'heldout_dev.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
POLICIES=('all_whole','all_gear512','known_cohort',
          'online_min_bytes','online_read_weighted')
HISTORY_COUNTS=(0,3,6,12)
INDEPENDENT_COUNTS=(96,384,1024)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


def input_docs():
    r54=load('cdg54_for61',R54)
    r46=load('cdg46_for61',R46)
    raw=r54.locked_sample(r54.load_development())
    last=raw[384:512]
    independent=[('independent',''.join(sentences).encode('utf8'))
                 for q in last for title,sentences in q['context']]
    if len(independent)<max(INDEPENDENT_COUNTS):
        raise AssertionError('locked remaining corpus has too few independent source paragraphs')
    history=[('history',b) for b in r46.load_source()]
    return history,independent,hashlib.sha256(
        '\n'.join(sorted(row['_id'] for row in last)).encode('utf8')).hexdigest()


def experiment(history,independent,sample_id_hash):
    r58=load('cdg58_for61',R58)
    r46=load('cdg46_archive_for61',R46)
    r47=load('cdg47_archive_for61',R47)
    out=[]
    for n_history in HISTORY_COUNTS:
        for n_independent in INDEPENDENT_COUNTS:
            cohort=history[:n_history]+independent[:n_independent]
            row={'history_count':n_history,'independent_count':n_independent,
                 'policies':{}}
            for policy in POLICIES:
                archive=r58.MixedStore(cohort,policy,r46.frame,r47)
                stats=archive.read_statistics(questions_per_source=2)
                row['policies'][policy]={
                    'archive_bytes':archive.archive_bytes(),
                    'method_choices':{
                        'whole':archive.methods.count('whole'),
                        'gear512':archive.methods.count('gear512')},
                    'mean_compressed_frame_bytes':stats['mean_compressed_frame_bytes'],
                    'span_queries':stats['queries']}
            baseline=row['policies']['all_whole']
            for policy in POLICIES:
                candidate=row['policies'][policy]
                candidate['archive_delta_pct_vs_whole']=round(
                    (candidate['archive_bytes']/baseline['archive_bytes']-1)*100,3)
                candidate['read_delta_pct_vs_whole']=round(
                    (candidate['mean_compressed_frame_bytes']/
                     baseline['mean_compressed_frame_bytes']-1)*100,3)
            out.append(row)
    wins=[]
    for row in out:
        candidate=row['policies']['online_read_weighted']
        wins.append({
            'mix':f"{row['history_count']}/{row['independent_count']}",
            'smaller_archive':candidate['archive_delta_pct_vs_whole']<0,
            'smaller_read':candidate['read_delta_pct_vs_whole']<0,
            'archive_delta_pct':candidate['archive_delta_pct_vs_whole'],
            'read_delta_pct':candidate['read_delta_pct_vs_whole']})
    return {
        'frozen_policy_source':'R58 online_read_weighted, same fixed cost coefficients',
        'holdback_sample_sha256':sample_id_hash,
        'history_sources_available':len(history),
        'independent_sources_available':len(independent),
        'scenarios':out,
        'online_read_weighted_vs_whole':wins,
        'limitations':[
            'holdback HotpotQA dev IDs were already used in R59 sentence allocation confirmation, but not R58 source routing',
            'still same HotpotQA domain and single uv README history, no independent corpus family',
            'source ratios are altered by subsampling the same sources, not genuinely independent datasets',
            'history truncation keeps earliest pinned revisions and can exaggerate dependence on sequence order',
            'only Zlib6; Zstd/Git controls in Round60 and not run over every mixture',
            'logical compressed bytes are sampled random source spans, not real evidence queries',
            'no source index, physical SSD, compute, verification, model tokens, or end-to-end answer claims']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    h,u,sample_hash=input_docs()
    result=experiment(h,u,sample_hash)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND61',json.dumps({
        'holdback_sha256':sample_hash,
        'available':{'history':len(h),'independent':len(u)},
        'outcomes':result['online_read_weighted_vs_whole']},sort_keys=True))


if __name__=='__main__':
    main()
