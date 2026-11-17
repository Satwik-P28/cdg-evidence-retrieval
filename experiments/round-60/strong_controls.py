#!/usr/bin/env python3
"""Round 60: conventional Zstandard and Git pack baselines on R58's real corpus.

Source inputs are exactly the 12 uv README versions plus 1,276 HotpotQA
paragraphs used by R58. Compare Zlib6 and Zstd3/9 on whole and 512-byte gear
frames, with shared SHA CAS and same complete compressed binary manifests.
Add an online compressed-storage-and-read heuristic under Zstd3 and an
honestly reported Git pack+idx/full-repository size control.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
R58=HERE.parent/'round-58'/'mixed_archive.py'
R54=HERE.parent/'round-54'/'heldout_dev.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
CONTROLS=(
    ('whole_zlib6','whole','zlib6'),
    ('gear_zlib6','gear512','zlib6'),
    ('whole_zstd3','whole','zstd3'),
    ('gear_zstd3','gear512','zstd3'),
    ('whole_zstd9','whole','zstd9'),
    ('gear_zstd9','gear512','zstd9'),
    ('known_cohort_zstd3','cohort','zstd3'),
    ('online_read_weighted_zstd3','online','zstd3'),
)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def sha(data):
    return hashlib.sha256(data).hexdigest()


def codec_api(kind):
    if kind=='zlib6':
        return lambda x:zlib.compress(x,6),zlib.decompress
    import zstandard
    level=int(kind[4:])
    compressor=zstandard.ZstdCompressor(level=level,write_content_size=True)
    decompressor=zstandard.ZstdDecompressor()
    return compressor.compress,decompressor.decompress


class Archive:
    def __init__(self,sources,method,codec,frame_func,manifest_module):
        self.sources=sources;self.method=method;self.codec=codec
        self.frame=frame_func;self.manifest_module=manifest_module
        self.compress,self.decompress=codec_api(codec)
        self.frames={}
        self.manifests=[]
        self.method_choices=[]
        begin=time.perf_counter_ns()
        for group,doc in sources:
            if method=='cohort':
                selected='gear512' if group=='history' else 'whole'
            elif method=='online':
                candidates=[]
                for choice in ('whole','gear512'):
                    chunks=self.frame(doc,choice)
                    unique={sha(x):x for x in chunks}
                    new=sum(len(self.compress(value))
                            for digest,value in unique.items()
                            if digest not in self.frames)
                    # Same frozen R58 approximate metadata and single midspan
                    # read cost objective, applied under this stronger codec.
                    start=max(0,(len(doc)-128)//2)
                    stop=min(len(doc),start+128)
                    offset=0;traffic=0
                    for chunk in chunks:
                        end=offset+len(chunk)
                        if end>start and offset<stop:
                            traffic+=len(self.compress(chunk))
                        offset=end
                    candidates.append((new+35+12*len(chunks)+.5*traffic,
                                       0 if choice=='whole' else 1,choice))
                selected=min(candidates)[2]
            else:
                selected=method
            entries=[]
            for chunk in self.frame(doc,selected):
                key=sha(chunk)
                if key not in self.frames:
                    self.frames[key]=self.compress(chunk)
                entries.append({'sha':key,'len':len(chunk)})
            self.manifests.append({'sha':sha(doc),'size':len(doc),'frames':entries})
            self.method_choices.append(selected)
        self.manifest_bytes=self.manifest_module.encode(self.manifests,'binary-zlib')
        if self.manifest_module.decode(self.manifest_bytes,'binary-zlib')!=self.manifests:
            raise ValueError('manifest roundtrip mismatch')
        self.build_ms=(time.perf_counter_ns()-begin)/1e6

    def size(self):
        return sum(len(x) for x in self.frames.values())+len(self.manifest_bytes)

    def read(self,source,start,end):
        m=self.manifests[source]
        if not 0<=start<=end<=m['size']:
            raise ValueError('invalid requested source span')
        offset=0;result=bytearray();traffic=0
        for f in m['frames']:
            stop=offset+f['len']
            if stop>start and offset<end:
                packed=self.frames[f['sha']]
                blob=self.decompress(packed)
                if sha(blob)!=f['sha'] or len(blob)!=f['len']:
                    raise ValueError('source frame digest mismatch')
                result.extend(blob[max(0,start-offset):min(f['len'],end-offset)])
                traffic+=len(packed)
            offset=stop
        if offset!=m['size']:
            raise ValueError('source span map does not cover source size')
        output=bytes(result)
        if start==0 and end==m['size'] and sha(output)!=m['sha']:
            raise ValueError('source digest mismatch')
        return output,traffic

    def evaluate(self,spans_per_source=2):
        traffic=[]
        for idx,(_,blob) in enumerate(self.sources):
            rebuilt,_=self.read(idx,0,len(blob))
            if rebuilt!=blob:raise ValueError('full lossless readback failed')
            for j in range(spans_per_source):
                length=min(128,len(blob))
                mod=max(1,len(blob)-length+1)
                offset=int.from_bytes(hashlib.sha256(
                    f'R58|{sha(blob)}|{j}'.encode()).digest()[:8],'big')%mod
                received,bytes_read=self.read(idx,offset,offset+length)
                if received!=blob[offset:offset+length]:
                    raise ValueError('partial source mismatch')
                traffic.append(bytes_read)
        return {
            'archive_bytes':self.size(),
            'payload_bytes':sum(map(len,self.frames.values())),
            'manifest_bytes':len(self.manifest_bytes),
            'unique_objects':len(self.frames),
            'method_choices':{
                'whole':self.method_choices.count('whole'),
                'gear512':self.method_choices.count('gear512')},
            'build_ms':round(self.build_ms,3),
            'span_queries':len(traffic),
            'mean_compressed_span_traffic':round(statistics.mean(traffic),3),
            'p50_compressed_span_traffic':round(statistics.median(traffic),3)}


def git_run(argv,repo,**kwargs):
    return subprocess.run(['git','-C',str(repo),*argv],
                          check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          **kwargs).stdout


def git_pack_control(history,independent):
    with tempfile.TemporaryDirectory() as location:
        repo=Path(location)/'repo'
        repo.mkdir()
        git_run(['init','-q'],repo)
        git_run(['config','user.email','test@example.invalid'],repo)
        git_run(['config','user.name','CDG Research'],repo)
        docs=repo/'docs'
        docs.mkdir()
        for i,(_,raw) in enumerate(independent):
            (docs/f'{i:04d}.txt').write_bytes(raw)
        git_run(['add','docs'],repo)
        git_run(['commit','-q','-m','Independent source blobs'],repo)
        revisions=[]
        for i,(_,raw) in enumerate(history):
            (repo/'README.md').write_bytes(raw)
            git_run(['add','README.md'],repo)
            git_run(['commit','-q','-m',f'Historical revision {i}'],repo)
            revisions.append(git_run(['rev-parse','HEAD'],repo).strip().decode())
        git_run(['gc','--aggressive','--prune=now'],repo)
        object_pack=repo/'.git'/'objects'/'pack'
        packs=sum(x.stat().st_size for x in object_pack.glob('*.pack'))
        indices=sum(x.stat().st_size for x in object_pack.glob('*.idx'))
        total=sum(x.stat().st_size for x in (repo/'.git').rglob('*') if x.is_file())
        # Verify genuine historical source reconstruction and 24 representative
        # independent files, not just that pack objects exist.
        for i,(_,raw) in enumerate(history):
            reconstructed=git_run(['show',revisions[i]+':README.md'],repo)
            if reconstructed!=raw:
                raise ValueError('Git historic blob fails exact readback')
        for i in list(range(min(12,len(independent))))+list(range(max(0,len(independent)-12),len(independent))):
            rebuilt=git_run(['show',revisions[-1]+f':docs/{i:04d}.txt'],repo)
            if rebuilt!=independent[i][1]:
                raise ValueError('Git independent blob readback failed')
        return {'pack_bytes':packs,'pack_index_bytes':indices,
                'pack_and_index_bytes':packs+indices,
                'entire_git_metadata_bytes':total,
                'commits':len(history)+1,
                'independent_files':len(independent),
                'historical_versions':len(history),
                'readback_verified':True,
                'boundary_note':'Git pack+idx excludes tree object checkouts, full .git includes refs and config; Git commits and trees are included in the pack'}


def experiment(history,independent):
    r46=load('cdg46_for60',R46)
    r47=load('cdg47_for60',R47)
    source=history+independent
    methods={}
    for name,layout,codec in CONTROLS:
        archive=Archive(source,layout,codec,r46.frame,r47)
        methods[name]=archive.evaluate()
    control=git_pack_control(history,independent)
    return {'sources':len(source),'history_versions':len(history),
            'independent_documents':len(independent),
            'methods':methods,'git':control,
            'limitations':[
                'one authentic README revision family and one short HotpotQA dev source family',
                'existing Zlib and Zstandard codecs with existing gear-style chunking, no new compressor',
                'Git has actual commit/tree semantics and all source blobs, unlike compact custom CAS',
                'Git pack/index bytes vs custom CAS+manifest bytes are different storage system boundaries',
                'Python decompression and logical frame traffic are not measured physical SSD I/O',
                'Git show subprocess costs cannot be directly compared with in-memory Python span reader',
                'no indexing, embeddings, model tokens, verifier or full RAG QA in this compression control',
                'online objective is frozen R58 heuristic, not tuned on evaluation results']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    r54=load('cdg54_for60',R54)
    r58=load('cdg58_for60',R58)
    history,independent=r58.sources(r54.locked_sample(r54.load_development())[:128])
    result=experiment(history,independent)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND60',json.dumps({
        'sources':result['sources'],
        'archives':{k:{f:v[f] for f in
            ('archive_bytes','mean_compressed_span_traffic','method_choices')}
                    for k,v in result['methods'].items()},
        'git':result['git']},sort_keys=True))


if __name__=='__main__':
    main()
