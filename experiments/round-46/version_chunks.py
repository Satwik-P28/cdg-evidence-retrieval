#!/usr/bin/env python3
"""Round 46: exact versioned lossless storage of 12 authentic uv README revisions.

Compare segmentation and simple delta designs; include complete manifest overhead,
exact source-byte reconstruction, and random evidence span read amplification.
This is NOT a new compression algorithm or independent RAG benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import statistics
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent.parent/'research'/'rounds'/'round-38'/'uv_readme_revisions.json'
GEAR=random.Random(262626)
GEAR_TABLE=[GEAR.getrandbits(32) for _ in range(256)]


def digest(x):
    return hashlib.sha256(x).hexdigest()


def load_source(path=SOURCE):
    dataset=json.loads(path.read_text())
    return [entry['text'].encode('utf8') for entry in dataset['rows']]


def frame(data,method):
    if method=='whole':
        return [data]
    if method.startswith('fixed'):
        width=int(method[5:])
        return [data[i:i+width] for i in range(0,len(data),width)] or [b'']
    if method.startswith('gear'):
        avg=int(method[4:])
        lo,hi=avg//2,avg*4
        mask=avg-1
        chunks=[];start=0;value=0
        for i,b in enumerate(data):
            value=((value<<1)+GEAR_TABLE[b])&0xffffffff
            span=i+1-start
            if span>=lo and (value&mask)==0 or span>=hi:
                chunks.append(data[start:i+1])
                start=i+1;value=0
        if start<len(data) or not chunks:chunks.append(data[start:])
        return chunks
    if method=='line512':
        chunks=[];buf=bytearray()
        for line in data.splitlines(keepends=True):
            if buf and len(buf)+len(line)>512:
                chunks.append(bytes(buf));buf.clear()
            if len(line)>2048:
                if buf:chunks.append(bytes(buf));buf.clear()
                chunks.extend(frame(line,'fixed512'))
            else:buf.extend(line)
        if buf or not chunks:chunks.append(bytes(buf))
        return chunks
    raise ValueError(method)


class FramedArchive:
    def __init__(self,versions,method):
        self.method=method
        self.frames={}
        self.manifests=[]
        self.raw_sha=[]
        begin=time.perf_counter_ns()
        for data in versions:
            ids=[]
            for chunk in frame(data,method):
                key=digest(chunk)
                if key not in self.frames:
                    self.frames[key]=zlib.compress(chunk,6)
                ids.append({'sha':key,'len':len(chunk)})
            self.manifests.append({'sha':digest(data),'size':len(data),'frames':ids})
        self.build_ms=(time.perf_counter_ns()-begin)/1e6

    def payload_bytes(self):
        return sum(len(x) for x in self.frames.values())

    def metadata_bytes(self):
        return len(json.dumps(self.manifests,separators=(',',':'),sort_keys=True).encode())

    def size(self):
        return self.payload_bytes()+self.metadata_bytes()

    def read(self,version,start=None,end=None):
        manifest=self.manifests[version]
        lo=0 if start is None else start
        hi=manifest['size'] if end is None else end
        if lo<0 or hi<lo or hi>manifest['size']:
            raise ValueError('bad read span')
        out=bytearray();offset=0;traffic=0
        for item in manifest['frames']:
            stop=offset+item['len']
            if stop>lo and offset<hi:
                compressed=self.frames[item['sha']]
                decoded=zlib.decompress(compressed)
                if digest(decoded)!=item['sha'] or len(decoded)!=item['len']:
                    raise ValueError('frame corruption')
                traffic+=len(compressed)
                out.extend(decoded[max(0,lo-offset):min(item['len'],hi-offset)])
            offset=stop
        if offset!=manifest['size']:
            raise ValueError('incomplete manifest')
        result=bytes(out)
        if lo==0 and hi==manifest['size'] and digest(result)!=manifest['sha']:
            raise ValueError('source corruption')
        return result,traffic


class DeltaArchive:
    """Whole-document snapshots every N revisions, prefix+suffix patch otherwise."""
    def __init__(self,versions,checkpoint):
        self.checkpoint=checkpoint
        self.objects={}
        self.entries=[]
        begin=time.perf_counter_ns()
        prior=b''
        for index,cur in enumerate(versions):
            if index%checkpoint==0:
                mid=cur;pre=0;post=0;kind='snapshot'
            else:
                pre=0
                while pre<min(len(prior),len(cur)) and prior[pre]==cur[pre]:
                    pre+=1
                post=0
                while post<len(prior)-pre and post<len(cur)-pre and prior[-1-post]==cur[-1-post]:
                    post+=1
                mid=cur[pre:len(cur)-post if post else len(cur)]
                kind='delta'
            key=digest(mid)
            if key not in self.objects:
                self.objects[key]=zlib.compress(mid,6)
            self.entries.append({'kind':kind,'sha':digest(cur),'patch':key,
                                 'prefix':pre,'suffix':post,'size':len(cur)})
            prior=cur
        self.build_ms=(time.perf_counter_ns()-begin)/1e6

    def payload_bytes(self):
        return sum(len(x) for x in self.objects.values())

    def metadata_bytes(self):
        return len(json.dumps(self.entries,separators=(',',':'),sort_keys=True).encode())

    def size(self):
        return self.payload_bytes()+self.metadata_bytes()

    def _full(self,version):
        start=version
        while self.entries[start]['kind']!='snapshot':
            start-=1
        whole=b''
        traffic=0
        for step in range(start,version+1):
            entry=self.entries[step]
            compressed=self.objects[entry['patch']]
            fragment=zlib.decompress(compressed)
            if digest(fragment)!=entry['patch']:
                raise ValueError('bad delta fragment')
            traffic+=len(compressed)
            if entry['kind']=='snapshot':
                whole=fragment
            else:
                tail=whole[len(whole)-entry['suffix']:] if entry['suffix'] else b''
                whole=whole[:entry['prefix']]+fragment+tail
            if len(whole)!=entry['size'] or digest(whole)!=entry['sha']:
                raise ValueError('reconstructed version mismatch')
        return whole,traffic

    def read(self,version,start=None,end=None):
        complete,traffic=self._full(version)
        return complete[slice(start,end)],traffic


def git_control(versions):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        subprocess.run(['git','init','-q',str(root)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(root),'config','user.name','CDG Test'],check=True)
        subprocess.run(['git','-C',str(root),'config','user.email','test@example.invalid'],check=True)
        for i,blob in enumerate(versions):
            (root/'README.md').write_bytes(blob)
            subprocess.run(['git','-C',str(root),'add','README.md'],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['git','-C',str(root),'commit','-q','--allow-empty','-m',f'v{i}'],check=True)
        subprocess.run(['git','-C',str(root),'gc','--aggressive','--prune=now','-q'],check=True)
        packs=root/'.git'/'objects'/'pack'
        pack_bytes=sum(p.stat().st_size for p in packs.glob('*') if p.is_file())
        git_total=sum(p.stat().st_size for p in (root/'.git').rglob('*') if p.is_file())
        return {'pack_and_index_bytes':pack_bytes,'full_git_metadata_bytes':git_total}


METHODS=['whole','fixed512','fixed2048','gear512','gear1024','line512','delta3','delta5']


def evaluate(versions,span_size=256,queries_per_version=16):
    outputs={}
    rng=random.Random(20261117)
    queries=[]
    for i,blob in enumerate(versions):
        for _ in range(queries_per_version):
            if len(blob)<span_size:
                left=0;right=len(blob)
            else:
                left=rng.randrange(0,len(blob)-span_size+1);right=left+span_size
            queries.append((i,left,right))
    for name in METHODS:
        engine=(DeltaArchive(versions,int(name[5:])) if name.startswith('delta')
                else FramedArchive(versions,name))
        reads=[];times=[]
        for i,blob in enumerate(versions):
            result,_=engine.read(i)
            if result!=blob:
                raise AssertionError(f'{name} failed full readback v{i}')
        for i,left,right in queries:
            start=time.perf_counter_ns()
            content,compressed=engine.read(i,left,right)
            times.append((time.perf_counter_ns()-start)/1000)
            if content!=versions[i][left:right]:
                raise AssertionError(f'{name} failed evidence readback {i} {left}:{right}')
            reads.append(compressed)
        outputs[name]={'total_archive_bytes':engine.size(),
                       'payload_bytes':engine.payload_bytes(),
                       'manifest_bytes':engine.metadata_bytes(),
                       'build_ms':round(engine.build_ms,3),
                       'read_p50_us':round(statistics.median(times),3),
                       'compressed_read_p50_bytes':round(statistics.median(reads),2),
                       'compressed_read_mean_bytes':round(statistics.mean(reads),2),
                       'unique_payload_objects':len(engine.objects if name.startswith('delta') else engine.frames)}
    return {'versions':len(versions),'total_raw_bytes':sum(map(len,versions)),
            'sampled_span_queries':len(queries),
            'strategies':outputs,'git_control':git_control(versions),
            'caveats':['12 authentic but closely related snapshots of one upstream README',
                       'random byte spans, not real RAG questions',
                       'compressed traffic counts whole frames, not physical OS I/O',
                       'zlib level 6; not a Zstandard or Git-optimized archive comparison',
                       'Git pack/index and total .git footprint are reported separately',
                       'no warm/cold cache isolation, no SSD fsync accounting']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    args=p.parse_args()
    data=evaluate(load_source())
    print('ROUND46',json.dumps(data,sort_keys=True))
    Path(args.out).write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    main()
