#!/usr/bin/env python3
"""Round 59: frozen allocation confirmation on last 256 SHA-locked dev rows.

Primary comparison fixed before seeing these sentence-allocation outcomes:
FTS5 BM25 sentence rank, original R25 title-bridge top-five document rank,
10-sentence global budget, 4/3/1/1/1 vs 2/2/2/2/2 with unused-slot recycle.
Other allocation rules are secondary controls. Compute paired outcomes, seeded
bootstrap interval, exact discordance test and verified compressed frame bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R55=HERE.parent/'round-55'/'heldout_frames.py'
R56=HERE.parent/'round-56'/'sentence_policy.py'
R57=HERE.parent/'round-57'/'budget_router.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
ALLOCATORS=('uniform2','uniform_recycle','front_4_3_1_1_1',
            'balanced_3_3_2_1_1','reverse_1_1_2_3_3','random')
PRIMARY='front_4_3_1_1_1'
REFERENCE='uniform_recycle'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def exact_pvalue(a_only,b_only):
    discord=a_only+b_only
    if not discord:return 1.0
    less=min(a_only,b_only)
    return min(1.0,2*sum(math.comb(discord,i) for i in range(less+1)) / (2**discord))


def paired_interval(left,right,reps=4000,seed=5911):
    if len(left)!=len(right) or not left:raise ValueError('paired outcomes missing')
    differences=[a-b for a,b in zip(left,right)]
    rng=random.Random(seed)
    sim=[]
    for _ in range(reps):
        sim.append(sum(differences[rng.randrange(len(differences))]
                       for _ in differences)/len(differences))
    sim.sort()
    n=len(differences)
    a_only=sum(a==1 and b==0 for a,b in zip(left,right))
    b_only=sum(a==0 and b==1 for a,b in zip(left,right))
    return {
        'n':n,
        'left_only':a_only,'right_only':b_only,
        'both':sum(a==1 and b==1 for a,b in zip(left,right)),
        'neither':sum(a==0 and b==0 for a,b in zip(left,right)),
        'net_gain_count':sum(differences),
        'gain_fraction':round(sum(differences)/n,5),
        'percentile_bootstrap_95_ci':[
            round(sim[int(.025*(reps-1))],5),
            round(sim[int(.975*(reps-1))],5)],
        'discordance_two_sided_exact_p':round(exact_pvalue(a_only,b_only),9)}


def frame_ids(reader,source,lo,hi):
    record=reader.manifests[source]
    offset=0;found=set()
    for frame in record['frames']:
        stop=offset+frame['len']
        if stop>lo and offset<hi:found.add(frame['sha'])
        offset=stop
    if offset!=record['size']:
        raise AssertionError('source manifest size mismatch')
    return found


def evaluate(rows):
    r54=load('cdg54_for59',R54)
    r55=load('cdg55_for59',R55)
    r56=load('cdg56_for59',R56)
    r57=load('cdg57_for59',R57)
    r48=load('cdg48_for59',R48)
    with tempfile.TemporaryDirectory() as tmp:
        index=r55.SentenceIndex(Path(tmp)/'index.sqlite',rows)
        readers={
            'whole':r48.VersionedReader(index.original_blobs,'whole','json-zlib'),
            'gear512':r48.VersionedReader(index.original_blobs,'gear512','binary-zlib')}
        cases={method:[] for method in ALLOCATORS}
        audited=set()
        try:
            for qid,row in enumerate(rows):
                if r54.support_reference_issue(row):
                    raise ValueError('unscorable support row in fixed validation tranche')
                chosen_docs=r54.select(row,'bridge')[:5]
                gold=set((t,sid) for t,sid in row['supporting_facts'])
                full=set(t for t,s in gold).issubset(
                    set(row['context'][d][0] for d in chosen_docs))
                orders={}
                for d in chosen_docs:
                    sentences=row['context'][d][1]
                    orders[d]=[sid for sid,lo,hi in index.choose(
                        qid,d,row['question'],limit=len(sentences))]
                    if set(orders[d])!=set(range(len(sentences))):
                        raise AssertionError('full ranking dropped sentence IDs')
                for method in ALLOCATORS:
                    selected=r57.allocation(method,chosen_docs,orders,{},qid,budget=10)
                    if len(selected)>10 or len(selected)!=len(set(selected)):
                        raise AssertionError('budget violation')
                    recovered={(row['context'][did][0],sid) for did,sid in selected}
                    raw=0
                    touched={k:set() for k in readers}
                    for did,sid in selected:
                        source=index.records[(qid,did)]
                        sentence=row['context'][did][1][sid].encode('utf8')
                        _,lo,hi=r56.spans(row['context'][did][1])[sid]
                        if index.original_blobs[source][lo:hi]!=sentence:
                            raise AssertionError('incorrect source sentence receipt')
                        raw+=len(sentence)
                        for variant,reader in readers.items():
                            touched[variant].update(frame_ids(reader,source,lo,hi))
                            key=(variant,source,sid)
                            if key not in audited:
                                verified,_=reader.read(reader.receipt(source,lo,hi),
                                                       pin_generation=source)
                                if verified!=sentence:
                                    raise AssertionError('incorrect archived source bytes')
                                audited.add(key)
                    cases[method].append({
                        'qid':qid,'type':row['type'],
                        'complete_docs':int(full),
                        'complete_support':int(gold.issubset(recovered)),
                        'sentences':len(selected),'plain_bytes':raw,
                        'whole_traffic':sum(len(readers['whole'].archive.frames[f])
                                            for f in touched['whole']),
                        'gear_traffic':sum(len(readers['gear512'].archive.frames[f])
                                           for f in touched['gear512'])})
            summary={}
            for method,items in cases.items():
                breakdown={}
                for typ in ('bridge','comparison'):
                    subset=[x for x in items if x['type']==typ]
                    breakdown[typ]={'n':len(subset),
                                    'complete_support':sum(x['complete_support'] for x in subset)}
                summary[method]={
                    'n':len(items),
                    'doc_upper_bound':sum(x['complete_docs'] for x in items),
                    'complete_support':sum(x['complete_support'] for x in items),
                    'mean_sentences':round(statistics.mean(x['sentences'] for x in items),3),
                    'mean_plain_bytes':round(statistics.mean(x['plain_bytes'] for x in items),3),
                    'mean_gear_frame_bytes':round(statistics.mean(x['gear_traffic'] for x in items),3),
                    'mean_whole_frame_bytes':round(statistics.mean(x['whole_traffic'] for x in items),3),
                    'type_breakdown':breakdown}
            comparisons={}
            for method in ALLOCATORS:
                if method==REFERENCE:continue
                comparisons[method+'_vs_'+REFERENCE]=paired_interval(
                    [x['complete_support'] for x in cases[method]],
                    [x['complete_support'] for x in cases[REFERENCE]])
            return {
                'questions':len(rows),
                'source_ids_sha256':hashlib.sha256(
                    '\n'.join(sorted(row['_id'] for row in rows)).encode()).hexdigest(),
                'sample_definition':'indices 256:512 from the prespecified R54 SHA-sorted 512-question sample',
                'primary_comparison':PRIMARY+'_vs_'+REFERENCE,
                'source_index_bytes':index.db_bytes,
                'archive_bytes':{k:v.size() for k,v in readers.items()},
                'unique_verified_representation_spans':len(audited),
                'methods':summary,'paired':comparisons,
                'limitations':[
                    'same official HotpotQA dev split as earlier rounds, not entirely independent domain',
                    'primary allocation chosen after R57 discovery partitions, before this tranche was scored',
                    'both policies see complete question-local candidate texts for document BM25',
                    'FTS5 sentence rank uses already-built and fully charged index',
                    'per-query frame traffic assumes ideal within-query duplicate frame reuse',
                    'bootstrap resamples correlated question units, not source-domain distributions',
                    'gold annotation match does not test generated answers or semantic entailment']}
        finally:
            index.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    helper=load('cdg54_source_r59',R54)
    sample=helper.locked_sample(helper.load_development())
    rows=sample[256:512]
    result=evaluate(rows)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND59',json.dumps({
        'questions':result['questions'],'sample_hash':result['source_ids_sha256'],
        'methods':result['methods'],
        'primary':result['paired'][result['primary_comparison']],
        'other_paired':result['paired']},sort_keys=True))


if __name__=='__main__':
    main()
