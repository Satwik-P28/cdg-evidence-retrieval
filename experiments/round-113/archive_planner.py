#!/usr/bin/env python3
"""R113: original QASPER independent-paper source-only storage planner.

Original QASPER TRAIN trains only the shared compression dictionary. All
candidate DEV article layouts use source-local original bytes, with no DEV
question text, access history, gold evidence or synthetic mutation outcomes.
Ranking/WAL tests are evaluated only AFTER archive decisions are frozen.

This is a static allocation prototype, NOT an online layout scheduler or a
worst-case guaranteed optimizer. Actual SQLite sizes and WAL bytes are read
from materialized R106 archives. Models and workloads are explicitly distinct.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-106'))
from trace_adaptive_archive import (
    fetch_qasper, TRAIN_SHA, DEV_SHA, load_dev, original_papers,
    independently_trained_samples, train_dictionaries, document_bytes,
    base_fts_db, paper_rank, all_query_rankings, build_archive,
    source_integrity, read_cost, synthetic_edit_plan, live_expected,
    dynamic_cost, stablehash,
)
from cost_planner import paper_options,optimize,physical_pareto,LAYOUTS

POLICIES=(
    'all_paper','all_group4','all_individual',
    'length_budget_35','hash_budget_35',
    'planner_balanced_35','planner_balanced_65',
)
EDIT_COUNT=24
BUDGETS=(8*1024*1024, 9*1024*1024)
EXPERIMENT_SALT='CDG-R113-SOURCE-ONLY-INDEPENDENT-ARTICLES-v1'


def frozen_choices(profiles):
    pids=sorted(profiles)
    out={}
    for layout in LAYOUTS:
        out['all_'+layout]=({pid:layout for pid in pids},{'type':'fixed static layout'})
    for mode in ('length','hash','balanced'):
        for fraction in ((.35,.65) if mode=='balanced' else (.35,)):
            choices,details=optimize(profiles,mode=mode,fraction=fraction)
            policy=('planner_'+mode if mode=='balanced' else mode+'_budget')+'_'+str(int(fraction*100))
            out[policy]=(choices,details)
    if set(out)!=set(POLICIES):raise AssertionError('expected policies not built')
    return out


def source_profiles(docs,dict_data):
    """Use the corpus available at build time, without any DEV question access."""
    import zstandard as zstd
    encoder=zstd.ZstdCompressor(level=9,dict_data=zstd.ZstdCompressionDict(dict_data['raw']))
    papers=original_papers(docs)
    profiles={}
    for paper,rowids in papers.items():
        raws=[(str(docs[rid-1]['doc_id']),document_bytes(docs[rid-1])) for rid in rowids]
        if len(raws)!=len({x for x,_ in raws}):raise AssertionError('duplicate paragraph source IDs')
        profiles[paper]=paper_options(raws,encoder.compress)
    return profiles


def static_proxy_cost(profiles,choices):
    total={k:0 for k in ('estimated_bytes','blob_bytes','decoded_uniform_bytes_sum','reencoded_uniform_bytes_sum','n_blocks')}
    for pid,ly in choices.items():
        v=profiles[pid][ly]
        for name in total:total[name]+=getattr(v,name)
    return total


def evaluate(train,dev,policies=POLICIES,edit_count=EDIT_COUNT):
    if set(train)&set(dev):raise AssertionError('QASPER original TRAIN/DEV article overlap')
    docs,cases,source_stats=load_dev(dev)
    # Only original TRAIN source data trains zstd dictionary, no labels.
    samples,train_meta=independently_trained_samples(train)
    dictionary=train_dictionaries(samples,(65536,))[65536]
    profiles=source_profiles(docs,dictionary)
    frozen=frozen_choices(profiles)
    if set(policies)-set(frozen):raise ValueError('invalid requested policy')
    # Here we freeze every policy BEFORE reading any DEV question text.
    plan={name:frozen[name] for name in policies}
    edits=synthetic_edit_plan(docs,edit_count)
    expected=live_expected(docs,edits)
    with tempfile.TemporaryDirectory(prefix='cdg-r113-') as tmp:
        folder=Path(tmp)
        template=folder/'fts-template.sqlite'
        original=base_fts_db(template,docs)
        try:
            original_stats=original.execute('SELECT hex(block) FROM sources_data WHERE id=1').fetchone()[0]
            rankings=all_query_rankings(original,cases)
        finally:original.close()
        outcomes=[]
        for name in policies:
            assignments,metadata=plan[name]
            if set(assignments)!=set(profiles):raise AssertionError('incomplete planner source layout')
            file=folder/(name+'.sqlite')
            db,build=build_archive(file,template,docs,assignments,dictionary)
            try:
                physical=file.stat().st_size
                original_integrity=source_integrity(db,docs,original_stats)
                for case in cases:
                    a=paper_rank(db,case['claim'],case['row_start'],case['row_end'],10)
                    if a!=rankings[case['id']]:
                        raise AssertionError('layout changed original FTS ranking')
                top1=read_cost(db,docs,cases,rankings,1)
                top10=read_cost(db,docs,cases,rankings,10)
                update=dynamic_cost(db,file,docs,edits,cases,expected)
                outcomes.append({
                  'policy':name,
                  'assignment_sha256':hashlib.sha256(json.dumps(assignments,sort_keys=True).encode()).hexdigest(),
                  'source_only_planner':metadata,
                  'layout_counts':dict(Counter(assignments.values())),
                  'source_local_proxy':static_proxy_cost(profiles,assignments),
                  'physical_source_index_sqlite_bytes':physical,
                  'fits_real_sqlite_budgets_bytes':{str(b):physical<=b for b in BUDGETS},
                  'original_source_receipts_verified':original_integrity,
                  'original_query_ranking_parity':len(cases),
                  'original_top1_source_reads':top1,
                  'original_top10_source_reads':top10,
                  'synthetic_edit_stress':update,
                  'build':build,
                })
            finally:db.close()
        points=[{
            'name':row['policy'],
            'physical_bytes':row['physical_source_index_sqlite_bytes'],
            'decoded_bytes':row['original_top10_source_reads']['decoded_original_source_bytes'],
            'wal_bytes':row['synthetic_edit_stress']['wal_appended_bytes'],
        } for row in outcomes]
        return {
          'round':113,'contract':'R106 physically materialized source+FTS store plus offline source-only static layout selection',
          'source_sha256':{'train':TRAIN_SHA,'dev':DEV_SHA},
          'dictionary_sha256':dictionary['sha256'].hex(),
          'dictionary_source':'independent original TRAIN articles, no answer labels',
          'original_dev_paragraphs':len(docs),'original_dev_articles':len(profiles),
          'original_dev_questions':len(cases),
          'selection':'DEV source bytes+paper boundaries only; no questions, gold evidence, ranking, or synthetic edits',
          'planning_policy_frozen_before_dev_questions_access':True,
          'source_workload_independence':'Original TRAIN/DEV paper IDs disjoint; evaluation questions belong only to DEV papers, but the DEV source bytes must be inspected to build the archive',
          'synthetic_edits_count':len(edits),'budgets_bytes':list(BUDGETS),
          'policies':list(policies),'results':outcomes,
          'observed_three_resource_pareto_policy_names':physical_pareto(points),
          'points':points,
          'limitations':[
            'Predeclared planning weights and static source-only features. Multiple-choice knapsack and layout decisions have extensive prior art; no novelty claim.',
            'Optimization uses compressed DEV article source bytes (without heldout queries) as a normal archive-build input; it is not zero-shot to source data.',
            'Estimated source size uses approximate 32 B/block and 56 B/row metadata. Quantized DP cannot guarantee a physical SQLite byte budget.',
            'QASPER has no real time-ordered query access log or revision trace. Original QASPER questions test reads; source revisions are artificial stress only.',
            'No dynamic live layout migration. The selected layout remains fixed after source updates.',
            'No cached blocks across distinct questions. No remote SSD, hardware-controlled latency, energy or total model/vector memory measured.',
            'Original FTS5 retrieval ranking is held fixed; no independent evidence recall or generated answer quality gain is possible from layout selection alone.',
            'The repo has prior experiments with QASPER DEV (R101-R106): this is not an independent unseen benchmark corpus relative to the broader project.',
            'Results should be interpreted as exploratory model comparison; need third-party dataset, real timestamped traces and existing optimizing-system baselines for a publication claim.',
          ],
        }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--edits',type=int,default=EDIT_COUNT)
    parser.add_argument('--policies',nargs='*',choices=POLICIES,default=POLICIES)
    args=parser.parse_args()
    if not 0<=args.edits<=128:raise ValueError('invalid edit count')
    upstream=fetch_qasper()
    if upstream['train']['sha256']!=TRAIN_SHA or upstream['dev']['sha256']!=DEV_SHA:
        raise AssertionError('original QASPER source SHA changed')
    outcome=evaluate(upstream['train']['data'],upstream['dev']['data'],args.policies,args.edits)
    Path(args.out).write_text(json.dumps(outcome,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'n_articles':outcome['original_dev_articles'],
       'questions':outcome['original_dev_questions'],
       'policies':[{k:r[k] for k in ('policy','physical_source_index_sqlite_bytes','layout_counts')}
                   for r in outcome['results']],
       'pareto':outcome['observed_three_resource_pareto_policy_names']},sort_keys=True))

if __name__=='__main__':main()