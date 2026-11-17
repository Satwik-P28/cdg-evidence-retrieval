#!/usr/bin/env python3
"""Round 47: fully serialized compressed version manifests, cold and warm reads.

Records SHA-256 digests for complete source versions and frames. Hashes only
prove consistency with trusted local metadata, not origin authenticity.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import statistics
import time
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parent/'round-46'/'version_chunks.py'


def prior():
    spec=importlib.util.spec_from_file_location('cdg_round46',PRIOR)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(m)
    return m


def enc_int(x):
    if x<0:raise ValueError('negative')
    out=bytearray()
    while x>=128:
        out.append((x&127)|128)
        x>>=7
    out.append(x)
    return bytes(out)


def dec_int(data,p):
    x=0
    for shift in range(0,70,7):
        if p>=len(data):raise ValueError('truncated integer')
        c=data[p];p+=1
        x|=(c&127)<<shift
        if not c&128:return x,p
    raise ValueError('integer too long')


def pack_binary(manifests,dictionary=False):
    out=bytearray()
    if dictionary:
        hashes=sorted(set(frame['sha'] for m in manifests for frame in m['frames']))
        addresses={x:i for i,x in enumerate(hashes)}
        out.extend(enc_int(len(hashes)))
        for x in hashes:out.extend(bytes.fromhex(x))
    out.extend(enc_int(len(manifests)))
    for m in manifests:
        out.extend(bytes.fromhex(m['sha']))
        out.extend(enc_int(m['size']))
        out.extend(enc_int(len(m['frames'])))
        for f in m['frames']:
            if dictionary:
                out.extend(enc_int(addresses[f['sha']]))
            else:
                out.extend(bytes.fromhex(f['sha']))
            out.extend(enc_int(f['len']))
    return bytes(out)


def unpack_binary(blob,dictionary=False):
    pos=0
    hashes=[]
    if dictionary:
        amount,pos=dec_int(blob,pos)
        if amount>1000000:raise ValueError('too many frame IDs')
        for _ in range(amount):
            if pos+32>len(blob):raise ValueError('truncated SHA')
            hashes.append(blob[pos:pos+32].hex());pos+=32
    count,pos=dec_int(blob,pos)
    if count>100000:raise ValueError('too many versions')
    manifests=[]
    for _ in range(count):
        if pos+32>len(blob):raise ValueError('truncated version hash')
        digest=blob[pos:pos+32].hex();pos+=32
        size,pos=dec_int(blob,pos)
        frame_count,pos=dec_int(blob,pos)
        if frame_count>1000000:raise ValueError('too many frames')
        frames=[]
        for _ in range(frame_count):
            if dictionary:
                index,pos=dec_int(blob,pos)
                if index>=len(hashes):raise ValueError('unknown frame ID')
                sha=hashes[index]
            else:
                if pos+32>len(blob):raise ValueError('truncated frame hash')
                sha=blob[pos:pos+32].hex();pos+=32
            length,pos=dec_int(blob,pos)
            frames.append({'sha':sha,'len':length})
        manifests.append({'sha':digest,'size':size,'frames':frames})
    if pos!=len(blob):raise ValueError('trailing bytes')
    return manifests


FORMATS=('json','json-zlib','binary','binary-zlib','dictionary','dictionary-zlib')


def encode(manifests,method):
    if method.startswith('json'):
        payload=json.dumps(manifests,separators=(',',':'),sort_keys=True).encode()
    else:
        payload=pack_binary(manifests,dictionary=method.startswith('dictionary'))
    if method.endswith('-zlib'):
        payload=zlib.compress(payload,6)
    # Detect corruption of serialized on-disk metadata. Not an authenticated signature.
    return hashlib.sha256(payload).digest()+payload


def decode(stored,method):
    if len(stored)<32:raise ValueError('missing manifest digest')
    claimed,payload=stored[:32],stored[32:]
    if hashlib.sha256(payload).digest()!=claimed:
        raise ValueError('manifest data corruption')
    if method.endswith('-zlib'):
        payload=zlib.decompress(payload)
    if method.startswith('json'):
        return json.loads(payload)
    return unpack_binary(payload,dictionary=method.startswith('dictionary'))


def read_span(frames,manifest,start,end):
    if not (0<=start<=end<=manifest['size']):
        raise ValueError('bad span')
    pos=0;out=bytearray();read_traffic=0
    for descriptor in manifest['frames']:
        next_pos=pos+descriptor['len']
        if next_pos>start and pos<end:
            if descriptor['sha'] not in frames:
                raise ValueError('missing payload frame')
            packed=frames[descriptor['sha']]
            decoded=zlib.decompress(packed)
            if hashlib.sha256(decoded).hexdigest()!=descriptor['sha'] or len(decoded)!=descriptor['len']:
                raise ValueError('corrupted frame')
            out.extend(decoded[max(0,start-pos):min(descriptor['len'],end-pos)])
            read_traffic+=len(packed)
        pos=next_pos
    if pos!=manifest['size']:
        raise ValueError('frame map does not match source length')
    result=bytes(out)
    if start==0 and end==manifest['size'] and hashlib.sha256(result).hexdigest()!=manifest['sha']:
        raise ValueError('full source hash mismatch')
    return result,read_traffic


def measure(sources,modes=('whole','fixed512','gear512','gear1024'),
            queries_per_version=12):
    old=prior()
    output={}
    for mode in modes:
        archive=old.FramedArchive(sources,mode)
        sampled=[]
        for i,doc in enumerate(sources):
            for j in range(queries_per_version):
                width=min(256,len(doc))
                start=(j*379+i*47)%max(1,len(doc)-width+1)
                sampled.append((i,start,start+width))
        output[mode]={}
        for format in FORMATS:
            stored=encode(archive.manifests,format)
            parsed=decode(stored,format)
            if parsed!=archive.manifests:
                raise AssertionError('decoded metadata differs')
            for i,blob in enumerate(sources):
                decoded,_=read_span(archive.frames,parsed[i],0,len(blob))
                if decoded!=blob:
                    raise AssertionError(f'exact full version fails {mode}:{format}:{i}')
            warm=[];cold=[];traffic=[]
            for i,a,b in sampled:
                begin=time.perf_counter_ns()
                portion,amount=read_span(archive.frames,parsed[i],a,b)
                warm.append((time.perf_counter_ns()-begin)/1000)
                begin=time.perf_counter_ns()
                recreated=decode(stored,format)
                second,second_bytes=read_span(archive.frames,recreated[i],a,b)
                cold.append((time.perf_counter_ns()-begin)/1000)
                if portion!=sources[i][a:b] or portion!=second or amount!=second_bytes:
                    raise AssertionError('bad exact span readback')
                traffic.append(amount)
            output[mode][format]={
                'archive_bytes':archive.payload_bytes()+len(stored),
                'payload_bytes':archive.payload_bytes(),
                'serialized_manifest_bytes':len(stored),
                'read_traffic_mean_bytes':round(statistics.mean(traffic),2),
                'warm_p50_us':round(statistics.median(warm),3),
                'cold_manifest_p50_us':round(statistics.median(cold),3)}
    pareto=[]
    for mode,variants in output.items():
        for format,stats in variants.items():
            dominated=False
            for altmode,alts in output.items():
                for altformat,other in alts.items():
                    if (other['archive_bytes']<=stats['archive_bytes'] and
                        other['read_traffic_mean_bytes']<=stats['read_traffic_mean_bytes'] and
                        (other['archive_bytes']<stats['archive_bytes'] or
                         other['read_traffic_mean_bytes']<stats['read_traffic_mean_bytes'])):
                        dominated=True
            if not dominated:
                pareto.append({'frames':mode,'manifest':format,
                               'archive_bytes':stats['archive_bytes'],
                               'mean_compressed_traffic':stats['read_traffic_mean_bytes']})
    return {'input_versions':len(sources),
            'queries_per_version':queries_per_version,
            'results':output,'size_vs_traffic_pareto':pareto,
            'limitations':['one README revision sequence; duplicated controls across manifest formats',
                           'cold metadata decoding occurs in Python memory, not disk IO',
                           'metadata SHA-256 is consistency, not source authenticity',
                           'zlib codec; no full Git pack read-traffic baseline',
                           'manifest corruption failures are not crash-safety validation']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(ROOT/'results.json'))
    args=p.parse_args()
    data=measure(prior().load_source())
    print('ROUND47',json.dumps(data,sort_keys=True))
    Path(args.out).write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    main()
