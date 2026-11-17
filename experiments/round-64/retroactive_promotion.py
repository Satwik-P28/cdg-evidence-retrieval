#!/usr/bin/env python3
"""Round 64: online retroactive promotion of related sources to lossless frames.

The storage policy is deliberately conventional: store an unlinked source whole;
when a sufficiently similar second source appears, re-encode the linked earlier
source plus the new one as content-defined frames. Charge archive and rewritten
payload/manifests. Test two *new* upstream source families (vLLM/Pydantic).
No source-type labels are visible to the migrating policy.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, statistics, sys, time, zlib
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
R62=HERE.parent/'round-62'/'independent_histories.py'
R63=HERE.parent/'round-63'/'relatedness_gate.py'
R58=HERE.parent/'round-58'/'mixed_archive.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
PINNED_UNSEEN={
    'vllm':{'repo':'vllm-project/vllm','cutoff':'935f87de846980dc16c54ac1996595fc12eb3f9e','path':'README.md','license':'Apache-2.0'},
    'pydantic':{'repo':'pydantic/pydantic','cutoff':'e56f60fd32273d1d7c397a3ac46bba05e6a73454','path':'README.md','license':'MIT'},
}
PINNED_PREVIOUS=('ruff','transformers','flask')
THRESHOLD=0.20
INDEPENDENT_COUNTS=(0,128,512)
POLICIES=('whole','gear','cohort','threshold_nomigration','threshold_migration')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def nearest_prior(documents,window_fn):
    posting=defaultdict(set)
    scores=[];previous=[]
    for i,(_,blob) in enumerate(documents):
        hashes=window_fn(blob)
        matches=defaultdict(int)
        for h in hashes:
            for j in posting[h]:
                matches[j]+=1
        best=sorted(matches, key=lambda j:(-matches[j],j))
        prior=best[0] if best else None
        score=matches[prior]/max(1,len(hashes)) if prior is not None else 0.0
        scores.append(score)
        previous.append(prior)
        for h in hashes:posting[h].add(i)
    return scores,previous


class StreamingArchive:
    """CAS frames, online source manifests, counted rewrites, reference-count GC.

    No claim of transaction atomicity, fsync durability, on-disk cache, actual
    SSD I/O, or optimal online recoding.
    """
    def __init__(self,data,policy,frame_fn,packer,window_fn,threshold=THRESHOLD):
        if policy not in POLICIES:raise ValueError(policy)
        self.data=data;self.policy=policy
        self.frame_fn=frame_fn;self.packer=packer
        self.payloads={}
        self.references={}
        self.manifests=[]
        self.assignments=[]
        self.payload_write_bytes=0
        self.manifest_rewrite_bytes=0
        self.recompression_source_plain_bytes=0
        self.recompression_source_compressed_read_bytes=0
        self.migrated_prior_sources=0
        self.peak_transient_payload_bytes=0
        self.scores,self.nearest=nearest_prior(data,window_fn)
        start=time.perf_counter_ns()
        for i,(group,blob) in enumerate(data):
            related=(self.nearest[i] is not None and self.scores[i]>=threshold)
            if policy=='whole': mode='whole'
            elif policy=='gear': mode='gear512'
            elif policy=='cohort': mode='gear512' if group=='history' else 'whole'
            elif policy=='threshold_nomigration': mode='gear512' if related else 'whole'
            else:
                mode='gear512' if related else 'whole'
                if related:
                    earlier=self.nearest[i]
                    if self.assignments[earlier]=='whole':
                        self._migrate(earlier,'gear512')
            self._append_source(blob,mode)
            self.manifest_blob=self.packer.encode(self.manifests,'binary-zlib')
            self.manifest_rewrite_bytes+=len(self.manifest_blob)
            self.peak_transient_payload_bytes=max(
                self.peak_transient_payload_bytes,
                sum(map(len,self.payloads.values())))
        self.manifest_sha=sha(self.manifest_blob)
        self.decoded_manifests=self.packer.decode(self.manifest_blob,'binary-zlib')
        if self.decoded_manifests!=self.manifests:
            raise AssertionError('latest archive manifest is not serializable')
        self.build_ms=(time.perf_counter_ns()-start)/1e6

    def _make_manifest(self,blob,mode):
        frames=[]
        for chunk in self.frame_fn(blob,mode):
            key=sha(chunk)
            if key not in self.payloads:
                packed=zlib.compress(chunk,6)
                self.payloads[key]=packed
                self.references[key]=0
                self.payload_write_bytes+=len(packed)
            self.references[key]+=1
            frames.append({'sha':key,'len':len(chunk)})
        return {'sha':sha(blob),'size':len(blob),'frames':frames}

    def _drop_manifest(self,manifest):
        for frame in manifest['frames']:
            key=frame['sha']
            self.references[key]-=1
            if self.references[key]<0:raise AssertionError('negative CAS refcount')
            if self.references[key]==0:
                del self.references[key]
                del self.payloads[key]

    def _append_source(self,blob,mode):
        self.assignments.append(mode)
        self.manifests.append(self._make_manifest(blob,mode))

    def _migrate(self,index,mode):
        before=self.manifests[index]
        compressed_read=sum(len(self.payloads[x['sha']]) for x in before['frames'])
        self.recompression_source_compressed_read_bytes+=compressed_read
        self.recompression_source_plain_bytes+=len(self.data[index][1])
        # Keep old content alive while materializing new CAS frames, then GC.
        after=self._make_manifest(self.data[index][1],mode)
        self.peak_transient_payload_bytes=max(
            self.peak_transient_payload_bytes,sum(map(len,self.payloads.values())))
        self._drop_manifest(before)
        self.manifests[index]=after
        self.assignments[index]=mode
        self.migrated_prior_sources+=1

    def archive_bytes(self):
        return sum(len(v) for v in self.payloads.values())+len(self.manifest_blob)

    def read(self,index,start,end):
        if sha(self.manifest_blob)!=self.manifest_sha:
            raise ValueError('serialized manifest digest mismatch')
        m=self.decoded_manifests[index]
        if not 0<=start<=end<=m['size']:
            raise ValueError('invalid source byte span')
        result,traffic=self.packer.read_span(self.payloads,m,start,end)
        if start==0 and end==m['size'] and sha(result)!=m['sha']:
            raise ValueError('source digest mismatch')
        return result,traffic

    def stats(self):
        compressed=[]
        for i,(_,blob) in enumerate(self.data):
            got,_=self.read(i,0,len(blob))
            if got!=blob:raise AssertionError('archive reconstruction differed')
            for j in range(2):
                width=min(128,len(blob))
                denom=max(1,len(blob)-width+1)
                begin=int.from_bytes(hashlib.sha256(
                    f'R58|{sha(blob)}|{j}'.encode()).digest()[:8],'big')%denom
                portion,traffic=self.read(i,begin,begin+width)
                if portion!=blob[begin:begin+width]:
                    raise AssertionError('exact source span readback differed')
                compressed.append(traffic)
        return {
            'archive_bytes':self.archive_bytes(),
            'payload_write_bytes':self.payload_write_bytes,
            'manifest_rewrite_upper_bound_bytes':self.manifest_rewrite_bytes,
            'migration_count':self.migrated_prior_sources,
            'migration_plain_source_bytes_read':self.recompression_source_plain_bytes,
            'migration_compressed_source_bytes_read':self.recompression_source_compressed_read_bytes,
            'peak_transient_payload_bytes':self.peak_transient_payload_bytes,
            'mean_compressed_span_bytes':round(statistics.mean(compressed),3),
            'source_methods':{
                'whole':self.assignments.count('whole'),
                'gear512':self.assignments.count('gear512')},
            'source_readback_count':len(self.data),
            'compressed_span_queries':len(compressed),
            'build_ms':round(self.build_ms,3)}


def experiment(histories,independent):
    r58=load('cdg58_r64',R58)
    r46=load('cdg46_r64',R46)
    r47=load('cdg47_r64',R47)
    r63=load('cdg63_r64',R63)
    results=[]
    for family,records in histories.items():
        versions=[('history',x['data']) for x in records]
        for n in INDEPENDENT_COUNTS:
            sources=versions+independent[:n]
            row={'family':family,'known_in_prior_rounds':family in PINNED_PREVIOUS,
                 'history_versions':len(records),'independent_sources':n,'methods':{}}
            for policy in POLICIES:
                obj=StreamingArchive(sources,policy,r46.frame,r47,
                                     r63.windows,THRESHOLD)
                row['methods'][policy]=obj.stats()
            ungated=r58.MixedStore(sources,'online_read_weighted',r46.frame,r47)
            ctrl=ungated.read_statistics()
            row['methods']['R58_ungated']={
                'archive_bytes':ungated.archive_bytes(),
                'mean_compressed_span_bytes':ctrl['mean_compressed_frame_bytes'],
                'source_methods':{
                    'whole':ungated.methods.count('whole'),
                    'gear512':ungated.methods.count('gear512')}}
            base=row['methods']['whole']
            for obj in row['methods'].values():
                obj['size_delta_pct_vs_whole']=round(
                    100*(obj['archive_bytes']/base['archive_bytes']-1),3)
                obj['read_delta_pct_vs_whole']=round(
                    100*(obj['mean_compressed_span_bytes']/
                         base['mean_compressed_span_bytes']-1),3)
            results.append(row)
    return {
        'history_provenance':{
            k:{'versions':len(records),
               'identity_sha256':sha('\n'.join(x['sha256'] for x in records).encode())}
            for k,records in histories.items()},
        'threshold':THRESHOLD,'schemes':POLICIES,'mixtures':INDEPENDENT_COUNTS,
        'scenarios':results,
        'limitations':[
            'family promotion was developed after R62/R63 observed on three histories; new vLLM/Pydantic histories are additional first-pass transfer tests, not a blinded statistical trial',
            'relatedness threshold 0.20 was selected from prior experiments and is frozen here',
            'online similarity index lives in Python RAM and its memory/time is not included in archive bytes',
            'all commits are SHA-pinned; no external source bytes are redistributed',
            'migration payload bytes and full-manifest rewrite bytes counted, but no fsync or atomic publication protocol',
            'upper-bound manifest rewriting assumes full serialized manifest rewritten every appended source',
            'migration source reads counted as compressed/raw bytes, not physical I/O; R58 baseline does not report analogous incremental write counts',
            'no FTS index, model tokens, semantic entailment, correctness of generated answers or independent evidence queries',
            'non-unique history source counts and uneven version scales prevent direct aggregation into one universal claim']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r62=load('cdg62_source_r64',R62)
    known={k:r62.download_history(r62.PINNED[k]) for k in PINNED_PREVIOUS}
    new={k:r62.download_history(spec) for k,spec in PINNED_UNSEEN.items()}
    independent,_=r62.input_sources(known)
    out=experiment({**known,**new},independent)
    Path(args.out).write_text(json.dumps(out,indent=2)+'\n')
    print('ROUND64',json.dumps({
        'histories':out['history_provenance'],
        'results':[{ 'family':x['family'],'independent':x['independent_sources'],
                     'known_family':x['known_in_prior_rounds'],
                     'whole':x['methods']['whole']['archive_bytes'],
                     'unguarded':x['methods']['R58_ungated']['archive_bytes'],
                     'migration':x['methods']['threshold_migration']}
                   for x in out['scenarios']]},sort_keys=True))


if __name__=='__main__':main()
