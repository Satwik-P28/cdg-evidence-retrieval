#!/usr/bin/env python3
"""R71: source-only hallucination discrimination bound + exact archive receipts.

For each RAGTruth QA test source, multiple model responses share exactly the
same evidence bytes. If their human hallucination labels differ, ANY
deterministic source-only decision rule must misclassify at least the smaller
class in that group. This is a conditional bound, not a model or a new theorem.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import tempfile
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R69=HERE.parent/'round-69'/'ragtruth_grounding.py'
R70=HERE.parent/'round-70'/'calibrated_grounding.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
SOURCE_PROBE_WIDTH=128
METHODS=('whole_zlib','gear512')
QA_TEST_GROUP_LIMIT=150


def dynamic(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def group_stats(responses,sources):
    r69=dynamic('cdg69_r71',R69)
    source_map={str(s['source_id']):s for s in sources}
    groups=defaultdict(list)
    annotation_faults=Counter()
    for row in responses:
        sid=str(row.get('source_id'))
        if (row.get('split')!='test' or sid not in source_map or
                source_map[sid].get('task_type')!='QA'):
            continue
        gold,strict,bad=r69.annotated_masks(row)
        for issue in bad:annotation_faults[issue]+=1
        groups[sid].append({
            'human_unsupported':bool(any(gold)),
            'strict_unsupported':bool(any(strict)),
            'quality_good':row.get('quality')=='good',
        })
    return groups,source_map,annotation_faults


def source_only_ceiling(groups,field='human_unsupported',only_good=False):
    counters=Counter()
    statuses=[]
    for sid,rows in groups.items():
        valid=[r for r in rows if (not only_good or r['quality_good'])]
        if not valid:continue
        positives=sum(bool(row[field]) for row in valid)
        negatives=len(valid)-positives
        counters['source_groups']+=1
        counters['responses']+=len(valid)
        counters['human_positive_responses']+=positives
        counters['human_clean_responses']+=negatives
        counters['mixed_truth_source_groups']+=int(positives>0 and negatives>0)
        counters['unavoidable_source_only_errors']+=min(positives,negatives)
        counters['source_only_oracle_correct']+=max(positives,negatives)
        counters['always_accept_correct']+=negatives
        counters['always_reject_correct']+=positives
        statuses.append((positives,negatives))
    n=counters['responses']
    if n<=0:raise ValueError('empty source-only evaluation')
    result={key:int(value) for key,value in counters.items()}
    result.update({
        'conditional_source_only_oracle_accuracy':round(
            result['source_only_oracle_correct']/n,5),
        'always_accept_accuracy':round(result['always_accept_correct']/n,5),
        'always_reject_accuracy':round(result['always_reject_correct']/n,5),
        'mixed_source_fraction':round(
            result['mixed_truth_source_groups']/result['source_groups'],5),
        'source_positive_count_histogram':{
            str(k):int(v) for k,v in
            sorted(Counter(positive for positive,negative in statuses).items())
        }})
    return result


def archive_costs(source_map,qa_ids):
    r69=dynamic('cdg69_source_r71',R69)
    r48=dynamic('cdg48_for_r71',R48)
    ordered=sorted(qa_ids)
    texts=[r69.source_text(source_map[sid]).encode('utf8') for sid in ordered]
    if not all(texts):raise ValueError('unexpected empty QA source passages')
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/'source_lines.sqlite'
        index=r48.EvidenceFTS(texts,db)
        readers={
            'whole_zlib':r48.VersionedReader(texts,'whole','binary-zlib'),
            'gear512':r48.VersionedReader(texts,'gear512','binary-zlib'),
        }
        try:
            traffic={key:[] for key in readers}
            sampled_spans=0
            for index_id,blob in enumerate(texts):
                for method,reader in readers.items():
                    receipt=reader.receipt(index_id,0,len(blob))
                    materialized,compressed=reader.read(
                        receipt,pin_generation=index_id)
                    if materialized!=blob:
                        raise AssertionError('source compression corrupted full QA passage')
                # Two immutable hash-keyed source spans are the same under both codecs.
                for j in range(2):
                    width=min(SOURCE_PROBE_WIDTH,len(blob))
                    modulus=max(1,len(blob)-width+1)
                    offset=int.from_bytes(hashlib.sha256(
                        f'R71_SOURCE_SPAN|{hashlib.sha256(blob).hexdigest()}|{j}'.encode()
                    ).digest()[:8],'big')%modulus
                    for method,reader in readers.items():
                        receipt=reader.receipt(index_id,offset,offset+width)
                        materialized,compressed=reader.read(receipt,pin_generation=index_id)
                        if materialized!=blob[offset:offset+width]:
                            raise AssertionError('source receipt range diverged from original')
                        traffic[method].append(compressed)
                    sampled_spans+=1
            # Validate real FTS5 postings against corresponding original source lines.
            retrieved=0
            for generation,blob in enumerate(texts):
                if b'\n' not in blob:continue
                # No claimed retrieval quality here; use one fixed ordinary probe.
                for lo,hi in index.query(generation,'the',k=2):
                    original=blob[lo:hi]
                    if lo<0 or hi>len(blob) or not original:
                        raise AssertionError('fulltext index source offset invalid')
                    retrieved+=1
            return {
                'source_count':len(ordered),
                'sum_source_utf8_bytes':sum(map(len,texts)),
                'fts_index_bytes':index.index_bytes(),
                'archive_bytes':{key:reader.size() for key,reader in readers.items()},
                'archive_plus_fts_index_bytes':{
                    key:reader.size()+index.index_bytes()
                    for key,reader in readers.items()},
                'exact_full_source_receipts_verified':len(ordered)*len(readers),
                'exact_source_span_reads_verified':sampled_spans*len(readers),
                'fts_source_spans_verified':retrieved,
                'mean_compressed_source_probe_bytes':{
                    key:round(statistics.mean(values),3)
                    for key,values in traffic.items()},
            }
        finally:
            index.close()


def evaluate(responses,sources):
    r69=dynamic('cdg69_loader_r71',R69)
    groups,source_map,faults=group_stats(responses,sources)
    if len(groups)<QA_TEST_GROUP_LIMIT:
        raise ValueError('RAGTruth official QA test split has fewer sources than expected')
    # Exact disjoint source-group split from R69: first SHA-ranked 128
    # evaluated then, remaining ~22 first examined in R70.
    order=sorted(groups,key=lambda sid:(hashlib.sha256(
        (r69.SAMPLE_SALT+'|'+sid).encode()).hexdigest(),sid))
    old_ids=set(order[:r69.MAX_TEST_SOURCE_GROUPS])
    new_ids=set(order[r69.MAX_TEST_SOURCE_GROUPS:])
    if len(old_ids)!=128 or not new_ids:raise AssertionError('bad group partition')
    results={}
    for split,ids in (
        ('R69_inspected_128',old_ids),('R70_untouched_22',new_ids),
        ('all_qa_test_groups',set(order))
    ):
        subset={sid:groups[sid] for sid in ids}
        results[split]={
            'official_human_annotations':source_only_ceiling(subset),
            'strict_implicit_true_excluded':source_only_ceiling(
                subset,field='strict_unsupported'),
            'quality_good_only':source_only_ceiling(subset,only_good=True),
        }
    storage=archive_costs(source_map,set(order))
    return {
        'sample':'all official QA test source groups; separate previously inspected and heldout R70 partitions',
        'all_qa_source_groups':len(order),
        'response_labels_not_a_property_of_source_bytes':True,
        'annotation_offset_faults':dict(faults),
        'source_id_hash':hashlib.sha256(
            '\n'.join(sorted(order)).encode()).hexdigest(),
        'group_bound':results,
        'exact_source_provenance_costs':storage,
        'limitations':[
            'source-only oracle uses human labels to calculate a mathematical upper bound; not deployable classifier',
            'bound applies only to deterministic methods that see source content/ID but not response text or model identity',
            'human-labeled unsupported includes semantic disagreements and absent information, not all are objectively false',
            'implicit_true handling is reported separately rather than hidden',
            'QA task of the RAGTruth test split, not other tasks or generated CDG answers',
            'all 150 source groups share original per-source context across six model outputs, enabling controlled within-source contrast',
            'archive source receipts guarantee exact source bytes only, not response grounding, causal provenance or human truth',
            'FTS5 index size charged; partial-read traffic is compressed logical frame bytes, not measured disk I/O',
            'no model inference or generated-answer suppression in this diagnostic',
        ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r69=dynamic('cdg69_source_main71',R69)
    records,_=r69.download('dataset/response.jsonl')
    sources,_=r69.download('dataset/source_info.jsonl')
    output=evaluate(records,sources)
    Path(args.out).write_text(json.dumps(output,indent=2)+'\n')
    print('ROUND71',json.dumps({
        'groups':output['all_qa_source_groups'],
        'bounds':output['group_bound'],
        'physical':output['exact_source_provenance_costs'],
        'annotation_faults':output['annotation_offset_faults']},sort_keys=True))


if __name__=='__main__':main()
