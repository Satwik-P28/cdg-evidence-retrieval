#!/usr/bin/env python3
"""R63: online byte-shingle relatedness gate for R58 adaptive framing.

This is deliberately conventional, label-blind approximate relatedness,
not a new codec or novelty claim. All thresholds (0.20,0.50,0.80)
are fixed before upstream history results are inspected.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R62=HERE.parent/'round-62'/'independent_histories.py'
R58=HERE.parent/'round-58'/'mixed_archive.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
THRESHOLDS=(.20,.50,.80)
SHINGLE_BYTES=96
SHINGLE_STRIDE=48
WINDOW_LIMIT=8192
IND_COUNTS=(128,512)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def windows(blob,width=SHINGLE_BYTES,stride=SHINGLE_STRIDE):
    if not blob:return set()
    if len(blob)<=width:return {hashlib.blake2b(blob,digest_size=12).digest()}
    positions=list(range(0,max(1,len(blob)-width+1),stride))
    end=len(blob)-width
    if positions[-1]!=end:positions.append(end)
    if len(positions)>WINDOW_LIMIT:
        step=math.ceil(len(positions)/WINDOW_LIMIT)
        positions=positions[::step]
    return {hashlib.blake2b(blob[pos:pos+width],digest_size=12).digest()
            for pos in positions}


def online_relatedness(documents):
    """Observed fraction of current shingle fingerprints in its nearest prior doc.

    Inverted fingerprints are built strictly from earlier sources.
    No labels, future blobs, candidate compression results, or gold answers used.
    """
    posting=defaultdict(set)
    results=[]
    for source_id,(_,blob) in enumerate(documents):
        fingerprints=windows(blob)
        intersections=defaultdict(int)
        for h in fingerprints:
            for previous in posting[h]:
                intersections[previous]+=1
        score=max(intersections.values(),default=0)/max(1,len(fingerprints))
        results.append(score)
        for h in fingerprints:
            posting[h].add(source_id)
    return results


def evaluate(histories,independent):
    r58=load('cdg58_r63',R58)
    r46=load('cdg46_r63',R46)
    r47=load('cdg47_r63',R47)
    summaries=[]
    for name,versions in histories.items():
        for count in IND_COUNTS:
            documents=[('history',x['data']) for x in versions]+independent[:count]
            score=online_relatedness(documents)
            base=r58.MixedStore(documents,'all_whole',r46.frame,r47)
            ungated=r58.MixedStore(documents,'online_read_weighted',r46.frame,r47)
            oracle=r58.MixedStore(documents,'known_cohort',r46.frame,r47)
            for threshold in THRESHOLDS:
                eligible=[value>=threshold for value in score]
                obj=r58.MixedStore(documents,'online_read_weighted',r46.frame,r47,
                                   gear_allowed=eligible)
                if any(method=='gear512' and not allow
                       for method,allow in zip(obj.methods,eligible)):
                    raise AssertionError('ineligible source used gear compression')
                probe=obj.read_statistics(questions_per_source=2)
                baseline=base.read_statistics(questions_per_source=2)
                summary={
                    'history':name,'history_count':len(versions),
                    'independent_count':count,'threshold':threshold,
                    'all_whole_bytes':base.archive_bytes(),
                    'ungated_bytes':ungated.archive_bytes(),
                    'known_cohort_bytes':oracle.archive_bytes(),
                    'guarded_archive_bytes':obj.archive_bytes(),
                    'size_delta_pct_vs_whole':round(
                        100*(obj.archive_bytes()/base.archive_bytes()-1),3),
                    'size_delta_pct_vs_ungated':round(
                        100*(obj.archive_bytes()/ungated.archive_bytes()-1),3),
                    'mean_source_read_bytes':probe['mean_compressed_frame_bytes'],
                    'read_delta_pct_vs_whole':round(
                        100*(probe['mean_compressed_frame_bytes']/
                             baseline['mean_compressed_frame_bytes']-1),3),
                    'history_eligible':sum(eligible[:len(versions)]),
                    'independent_eligible':sum(eligible[len(versions):]),
                    'history_gear_selected':obj.methods[:len(versions)].count('gear512'),
                    'independent_gear_selected':obj.methods[len(versions):].count('gear512'),
                    'mean_historical_overlap':round(
                        statistics.mean(score[:len(versions)]),4),
                    'mean_independent_overlap':round(
                        statistics.mean(score[len(versions):]),4)
                }
                summaries.append(summary)
    return {
        'shingle_bytes':SHINGLE_BYTES,'shingle_stride':SHINGLE_STRIDE,
        'thresholds':THRESHOLDS,'total_scenarios':len(summaries),
        'scenarios':summaries,
        'limitations':[
            'no source family labels in gate, but corpus includes only three fixed upstream README histories and HotpotQA dev paragraphs',
            'source-dependent shingle containment is not a probability or confidence score',
            'thresholds are prespecified exploration, not optimized on R62 target metrics',
            'history always arrives before independent documents; separate interleaving/order tests needed',
            'online shingle index uses Python RAM which is not charged to archive storage',
            'positive archive effects may reflect false negatives that suppress valuable content-defined deduplication',
            'logical frame reads on sampled 128-byte spans; no physical I/O, query/embedding indexes, or model answer quality',
            'compression is existing Zlib and gear-style content-defined chunking, relatedness gate is classical approximate byte matching']
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r62=load('cdg62_r63',R62)
    histories={name:r62.download_history(spec) for name,spec in r62.PINNED.items()}
    independent,source_hash=r62.input_sources(histories)
    data=evaluate(histories,independent)
    data['source_question_id_sha256']=source_hash
    Path(args.out).write_text(json.dumps(data,indent=2)+'\n')
    print('ROUND63',json.dumps({
        'scenario_count':data['total_scenarios'],
        'rows':data['scenarios']},sort_keys=True))


if __name__=='__main__':main()
