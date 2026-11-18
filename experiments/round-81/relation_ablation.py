#!/usr/bin/env python3
"""R81: fixed-claim directionality, reverse-negation and sentence-order ablation.

Reuses frozen R80 published checkpoints. Same supervised relation claim has
several *logically supporting* surface forms, plus explicit contradictory
or unknown sources. Purpose: identify source wording effects without
post-hoc threshold tuning. Synthetic labels, NOT human evaluation.
"""
from __future__ import annotations
import argparse,hashlib,json,statistics,time,sys
from collections import Counter,defaultdict
from pathlib import Path
# The R80 benchmark is a sibling experiment directory in the monorepo.
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'round-80'))
from controlled_facts import (
    NAME_PAIRS,archived_docs,sha_cases,nli_scores,minicheck_scores,
    lettuce_scores,lexical_scores,confusion
)
from factcg_control import infer as factcg_scores

HERE=Path(__file__).resolve().parent
# The R80 label-oracle diagnostic threshold, frozen BEFORE any R81 results.
# It is not deployment-calibrated or an independent model selection.
FACTCG_R80_DIAGNOSTIC_CUTOFF=0.10503259
VARIANTS=(
 'exact','active','passive','neutral_after',
 'reverse_negation_after','reverse_negation_before',
 'reverse_supervision','direct_negation','reverse_negation_only','unrelated'
)
SUPPORT=frozenset(VARIANTS[:6])
CONTRA=frozenset(VARIANTS[6:8])
UNKNOWN=frozenset(VARIANTS[8:])
assert SUPPORT|CONTRA|UNKNOWN==set(VARIANTS)


def make_case(i,variant):
    a,b,city,alt_city,warehouse,year,other_year=NAME_PAIRS[i]
    first=a+' Initiative';second=b+' Initiative'
    claim=f'{first} supervises {second}.'
    active=f'The organization chart identifies {first} as the supervisor of {second}.'
    reverse=f'{second} does not supervise {first}.'
    text={
        'exact':claim,
        'active':active,
        'passive':f'According to the organization chart, {second} is supervised by {first}.',
        'neutral_after':active+' The chart was reviewed during routine inspection.',
        'reverse_negation_after':active+' '+reverse,
        'reverse_negation_before':reverse+' '+active,
        'reverse_supervision':f'The organization chart identifies {second} as supervisor of {first}. It explicitly says {first} does not supervise {second}.',
        'direct_negation':f'The organization chart explicitly says {first} does not supervise {second}.',
        'reverse_negation_only':reverse,
        'unrelated':f'The organization chart lists {first} and {second} as separately registered initiatives. No supervisory relationship is specified.',
    }[variant]
    if variant in SUPPORT:
        state='supported'
    elif variant in CONTRA:
        state='contradicted'
    else:
        state='unknown'
    return {
        'id':f'{i:02d}-{variant}','entity_group':f'entity-{i:02d}',
        'variant':variant,'state':state,'supported':state=='supported',
        'claim':claim,
        'doc':'Fictional registry; one stable period. '+text,
    }


def sample():
    rows=[make_case(i,var) for i in range(len(NAME_PAIRS)) for var in VARIANTS]
    if len(rows)!=100 or len(set(x['id'] for x in rows))!=100:
        raise AssertionError('variant sample drifted')
    for i in range(len(NAME_PAIRS)):
        group=[x for x in rows if x['entity_group']==f'entity-{i:02d}']
        if [x['variant'] for x in group]!=list(VARIANTS):
            raise AssertionError('missing paired variant')
        if len(set(x['claim'] for x in group))!=1:
            raise AssertionError('claim changed during wording intervention')
    return rows


def by_variant(rows,models,model_info,archive):
    outputs={}
    pair_effects={}
    for model,pred in models.items():
        if len(pred)!=len(rows):raise AssertionError('length mismatch')
        blocks={}
        for variant in VARIANTS:
            indices=[i for i,x in enumerate(rows) if x['variant']==variant]
            subset=[rows[i] for i in indices]
            vals=[pred[i] for i in indices]
            stats=confusion(vals,subset)
            stats['source_state']=subset[0]['state']
            stats['predicted_supported']=sum(int(bool(v)) for v in vals)
            blocks[variant]=stats
        outputs[model]=blocks
        map_by_group={(x['entity_group'],x['variant']):bool(pred[i])
                      for i,x in enumerate(rows)}
        comparisons={}
        for other in ('exact','active','passive','neutral_after',
                      'reverse_negation_after','reverse_negation_before'):
            base=[map_by_group[(f'entity-{i:02d}','active')]
                  for i in range(len(NAME_PAIRS))]
            new=[map_by_group[(f'entity-{i:02d}',other)]
                 for i in range(len(NAME_PAIRS))]
            comparisons[other]={
                'active_support_to_other_support_switches':sum(x!=y for x,y in zip(base,new)),
                'active_accepted_count':sum(base),
                'other_accepted_count':sum(new),
            }
        pair_effects[model]=comparisons
    return {
        'case_sha256':sha_cases(rows),
        'responses':len(rows),
        'entity_groups':len(NAME_PAIRS),
        'variants':list(VARIANTS),
        'states':{v:'supported' if v in SUPPORT else
                  'contradicted' if v in CONTRA else 'unknown' for v in VARIANTS},
        'source_words_by_variant':{
            var:round(statistics.mean(len(row['doc'].split())
                    for row in rows if row['variant']==var),2)
            for var in VARIANTS},
        'model_cost':model_info,'archive':archive,
        'score_by_variant':outputs,
        'paired_support_surface_changes':pair_effects,
        'limitations':[
            'fixture-derived semantic labels, not independently human-reviewed claims or natural generated responses',
            'templates are visible and 10 entity substitutions do not imply 100 independent semantic trials',
            'supportive reverse negation has same surface names and opposite direction but may trigger generic NLI contradiction lexical cues',
            'sentence ordering, length and distractors are only partially controlled; neutral_after serves as simple extra-sentence control',
            'model training corpora and tokenizer contexts differ; measured CPU costs not directly comparable as architecture-only effects',
            'short sources, source identity supplied by oracle; archive bytes do not validate claim support or retrieval',
            'base pretrained thresholds fixed at 0.50; supplementary FactCG diagnostic threshold was chosen post-hoc on R80 fixture labels and transferred without R81 retuning, not deployable calibration',
            'FactCG implementation reproduces official single-chunk template for short documents, not full long-context inference',
            'no answer generator, human adjudication, out-of-domain validation or factual improvement attributable to compression',
        ],
    }


def run():
    rows=sample()
    docs,archive=archived_docs(rows)
    lex=lexical_scores(rows,docs)
    nli,nli_info=nli_scores(rows,docs)
    mc,mc_info=minicheck_scores(rows,docs)
    factcg,factcg_info=factcg_scores(rows,docs)
    lettuce,lettuce_info=lettuce_scores(rows,docs)
    models={
        'lexical':lex,
        'nli':[int(x>=.5) for x in nli],
        'minicheck':[int(x>.5) for x in mc],
        'factcg':[int(x>.5) for x in factcg],
        'factcg_R80_diagnostic_cutoff':[int(x>FACTCG_R80_DIAGNOSTIC_CUTOFF) for x in factcg],
        'lettuce':lettuce,
    }
    infos={'lexical':{'cost':'token overlap only'},'nli':nli_info,
           'minicheck':mc_info,'factcg':factcg_info,
           'factcg_R80_diagnostic_cutoff':{
               'threshold':FACTCG_R80_DIAGNOSTIC_CUTOFF,
               'source':'post-hoc R80 fixture labels, only tests surface transfer to R81; shared entity names/template constraints',
               'inference_cost':'reuses FactCG model forward, no additional inference'},
           'lettuce':lettuce_info}
    result=by_variant(rows,models,infos,archive)
    print('ROUND81',json.dumps({
        'sample_sha256':result['case_sha256'],
        'all_support_accepts':{
            name:{v:score['predicted_supported']
                  for v,score in scores.items()}
            for name,scores in result['score_by_variant'].items()},
        'model_cost':infos,'source_words':result['source_words_by_variant'],
    },sort_keys=True))
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=ap.parse_args()
    Path(args.out).write_text(json.dumps(run(),indent=2)+'\n')
