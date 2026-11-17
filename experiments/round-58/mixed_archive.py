#!/usr/bin/env python3
"""Round 58: online mixed-source lossless archive policy with exact byte reads.

Mix 12 genuinely timestamped README versions with question-local independent
HotpotQA development paragraphs. Compare always-whole, always-gear512,
known-cohort oracle, and two *online* greedy policies that charge newly
compressed CAS payloads and approximate manifest and read traffic.
Do not claim novelty or superiority over Git pack / Zstd / production stores.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import sys
import time
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
R54=HERE.parent/'round-54'/'heldout_dev.py'
METHODS=('whole','gear512')
POLICIES=('all_whole','all_gear512','known_cohort',
          'online_min_bytes','online_read_weighted')
ORDERS=('history_first','independent_first','interleaved')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


class MixedStore:
    def __init__(self,data,policy,frame_fn,manifest_module,gear_allowed=None):
        if gear_allowed is not None and len(gear_allowed)!=len(data):
            raise ValueError('gear_allowed must have exactly one decision per source')
        self.data=data
        self.policy=policy
        self.frame_fn=frame_fn
        self.m=manifest_module
        self.payloads={}
        self.manifests=[]
        self.methods=[]
        self.storage_predictions=[]
        begin=time.perf_counter_ns()
        for i,(group,blob) in enumerate(data):
            if policy=='all_whole': method='whole'
            elif policy=='all_gear512': method='gear512'
            elif policy=='known_cohort':
                method='gear512' if group=='history' else 'whole'
            elif policy in ('online_min_bytes','online_read_weighted'):
                contenders=[]
                for candidate in METHODS:
                    if candidate=='gear512' and gear_allowed is not None and not gear_allowed[i]:
                        continue
                    chunks=frame_fn(blob,candidate)
                    unique={sha(x):x for x in chunks}
                    payload_cost=sum(len(zlib.compress(chunk,6))
                                     for digest,chunk in unique.items()
                                     if digest not in self.payloads)
                    approx_manifest_cost=12*len(chunks)+35
                    read_cost=0
                    if policy=='online_read_weighted':
                        # Predict one 128-byte evidence read based on deterministic
                        # corpus-agnostic positions, not gold retrieval labels.
                        lo=max(0,(len(blob)-128)//2)
                        hi=min(len(blob),lo+128)
                        offset=0
                        for chunk in chunks:
                            stop=offset+len(chunk)
                            if stop>lo and offset<hi:
                                read_cost+=len(zlib.compress(chunk,6))
                            offset=stop
                    estimated=payload_cost+approx_manifest_cost+.5*read_cost
                    contenders.append((estimated,0 if candidate=='whole' else 1,candidate))
                predicted,_,method=min(contenders)
                self.storage_predictions.append(predicted)
            else:
                raise ValueError(policy)
            ids=[]
            for chunk in frame_fn(blob,method):
                key=sha(chunk)
                if key not in self.payloads:
                    self.payloads[key]=zlib.compress(chunk,6)
                ids.append({'sha':key,'len':len(chunk)})
            self.manifests.append({'sha':sha(blob),'size':len(blob),'frames':ids})
            self.methods.append(method)
        self.serialized=self.m.encode(self.manifests,'binary-zlib')
        self.serialized_sha=sha(self.serialized)
        self.build_ms=(time.perf_counter_ns()-begin)/1e6
        self.decoded=self.m.decode(self.serialized,'binary-zlib')
        if self.decoded!=self.manifests:
            raise AssertionError('serialized manifest mismatch')

    def archive_bytes(self):
        return len(self.serialized)+sum(len(x) for x in self.payloads.values())

    def read(self,source,start,end):
        if sha(self.serialized)!=self.serialized_sha:
            raise ValueError('manifest altered')
        record=self.decoded[source]
        if not 0<=start<=end<=record['size']:
            raise ValueError('invalid source span')
        content,cost=self.m.read_span(self.payloads,record,start,end)
        if start==0 and end==record['size'] and sha(content)!=record['sha']:
            raise ValueError('full source mismatch')
        return content,cost

    def read_statistics(self,questions_per_source=2):
        costs=[]
        for i,(_,blob) in enumerate(self.data):
            full,_=self.read(i,0,len(blob))
            if full!=blob:
                raise AssertionError('complete source not reconstructed')
            for j in range(questions_per_source):
                width=min(128,len(blob))
                limit=max(1,len(blob)-width+1)
                lo=int.from_bytes(hashlib.sha256(
                    f'R58|{sha(blob)}|{j}'.encode()).digest()[:8],'big')%limit
                hi=lo+width
                fragment,traffic=self.read(i,lo,hi)
                if fragment!=blob[lo:hi]:
                    raise AssertionError('exact evidence span not reconstructed')
                costs.append(traffic)
        return {
            'queries':len(costs),
            'mean_compressed_frame_bytes':round(statistics.mean(costs),3),
            'p50_compressed_frame_bytes':round(statistics.median(costs),3)}


def sources(dev_sample):
    r46=load('cdg46_r58',R46)
    historical=[('history',blob) for blob in r46.load_source()]
    independent=[('independent',''.join(sents).encode('utf8'))
                 for row in dev_sample for _,sents in row['context']]
    return historical,independent


def ordered_sources(history,independent,name):
    if name=='history_first':return history+independent
    if name=='independent_first':return independent+history
    if name=='interleaved':
        result=[]
        idx=0
        for item in history:
            result.append(item)
            result.extend(independent[idx:idx+max(1,len(independent)//len(history))])
            idx+=max(1,len(independent)//len(history))
        result.extend(independent[idx:])
        return result
    raise ValueError(name)


def exercise(history,independent):
    r46=load('cdg46_archive_r58',R46)
    r47=load('cdg47_r58',R47)
    metrics=[]
    for order in ORDERS:
        docs=ordered_sources(history,independent,order)
        for policy in POLICIES:
            store=MixedStore(docs,policy,r46.frame,r47)
            counts={method:store.methods.count(method) for method in METHODS}
            traffic=store.read_statistics()
            metrics.append({
                'order':order,'policy':policy,
                'sources':len(docs),'history_sources':len(history),
                'independent_sources':len(independent),
                'method_counts':counts,
                'archive_bytes':store.archive_bytes(),
                'manifest_bytes':len(store.serialized),
                'unique_compressed_objects':len(store.payloads),
                'build_ms':round(store.build_ms,3),
                **traffic})
    return {
        'total_sources':len(history)+len(independent),
        'history_sources':len(history),
        'independent_sources':len(independent),
        'strategies':metrics,
        'limitations':[
            'two specific source families: one uv README version history and a 128-question HotpotQA dev subset',
            'online policy compares actual compressed candidate bytes using existing Zlib, not a new codec',
            'known-cohort policy has metadata oracle and is an upper-bound architectural control',
            'approximate 12-byte descriptor and .5 read charge are frozen heuristic weights, not optimized',
            'source input order affects online policy and is explicitly ablated',
            'partial reads are seeded random 128-byte spans, not actual RAG evidence spans',
            'logical compressed frame bytes exclude FTS index, cache, physical SSD, verifier and model',
            'Git packing and stronger Zstd archives are still mandatory storage-only baselines',
        ]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'results.json'))
    args=p.parse_args()
    m54=load('cdg54_data_r58',R54)
    history,independent=sources(m54.locked_sample(m54.load_development())[:128])
    result=exercise(history,independent)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND58',json.dumps({
        'sources':result['total_sources'],'history':result['history_sources'],
        'independent':result['independent_sources'],
        'results':[{k:row[k] for k in
            ('order','policy','archive_bytes','mean_compressed_frame_bytes','method_counts')}
            for row in result['strategies']]},sort_keys=True))


if __name__=='__main__':
    main()
