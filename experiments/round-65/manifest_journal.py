#!/usr/bin/env python3
"""Round 65: bounded append-only source manifest journal versus full rewrites.

Honest physical-design control for R64: a compact binary manifest rewritten
after *every* append is an intentionally weak update strategy. Replayable
hash-checked event packets plus periodic compact checkpoints can reduce write
amplification but may worsen retained footprint, replay latency and durability.
This is simulated write accounting, not actual fsync or crash-atomic storage.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, statistics, sys, time, zlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
R64=HERE.parent/'round-64'/'retroactive_promotion.py'
R62=HERE.parent/'round-62'/'independent_histories.py'
R63=HERE.parent/'round-63'/'relatedness_gate.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
CHECKPOINT_INTERVALS=(None,32,128,512)
POLICIES=('whole','threshold_migration')
INDEPENDENT_COUNTS=(128,512)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m


def packet(event):
    raw=json.dumps(event,sort_keys=True,separators=(',',':')).encode()
    compressed=zlib.compress(raw,6)
    digest=hashlib.sha256(compressed).digest()[:16]
    return len(compressed).to_bytes(4,'big')+digest+compressed


def apply(state,event):
    op=event['op']
    index=event['index']
    manifest=event['manifest']
    if not isinstance(index,int) or index<0:
        raise ValueError('invalid manifest source index')
    if not isinstance(manifest,dict) or not all(x in manifest for x in ('sha','size','frames')):
        raise ValueError('invalid source manifest')
    if op=='append':
        if index!=len(state):raise ValueError('non-sequential source append')
        state.append(manifest)
    elif op=='replace':
        if index>=len(state):raise ValueError('replace prior to source append')
        state[index]=manifest
    else:
        raise ValueError('unknown manifest journal event')


def replay(snapshot,tail,packer):
    if snapshot:
        state=packer.decode(snapshot,'binary-zlib')
    else:
        state=[]
    offset=0
    while offset<len(tail):
        if len(tail)-offset<20:
            raise ValueError('truncated event header')
        length=int.from_bytes(tail[offset:offset+4],'big')
        digest=tail[offset+4:offset+20]
        offset+=20
        if length==0 or length>len(tail)-offset:
            raise ValueError('invalid/truncated event packet length')
        payload=tail[offset:offset+length]
        offset+=length
        if hashlib.sha256(payload).digest()[:16]!=digest:
            raise ValueError('source-manifest journal event checksum mismatch')
        event=json.loads(zlib.decompress(payload))
        apply(state,event)
    return state


def pack_journal(events,packer,interval):
    if interval is not None and interval<=0:
        raise ValueError('invalid checkpoint interval')
    state=[];checkpoint=b'';tail=b''
    event_writes=0
    checkpoint_writes=0
    checkpoints=0
    peak_transient=0
    for n,event in enumerate(events,1):
        apply(state,event)
        blob=packet(event)
        tail+=blob
        event_writes+=len(blob)
        if interval is not None and n%interval==0:
            new_checkpoint=packer.encode(state,'binary-zlib')
            # Old snapshot, unapplied tail, new snapshot may coexist.
            peak_transient=max(peak_transient,len(checkpoint)+len(tail)+len(new_checkpoint))
            checkpoint_writes+=len(new_checkpoint)
            checkpoint=new_checkpoint
            tail=b''
            checkpoints+=1
        peak_transient=max(peak_transient,len(checkpoint)+len(tail))
    times=[]
    for _ in range(3):
        start=time.perf_counter_ns()
        rebuilt=replay(checkpoint,tail,packer)
        times.append((time.perf_counter_ns()-start)/1000)
        if rebuilt!=state:
            raise AssertionError('append-only journal replay changed source manifests')
    return {
        'checkpoint_interval':interval if interval is not None else 'none',
        'event_count':len(events),
        'checkpoints':checkpoints,
        'latest_checkpoint_bytes':len(checkpoint),
        'remaining_journal_bytes':len(tail),
        'persistent_metadata_bytes':len(checkpoint)+len(tail),
        'event_written_bytes':event_writes,
        'checkpoint_written_bytes':checkpoint_writes,
        'total_metadata_written_bytes':event_writes+checkpoint_writes,
        'peak_migration_metadata_bytes':peak_transient,
        'median_cold_replay_us':round(statistics.median(times),3),
        'snapshot':checkpoint,
        'tail':tail,
        'final_state':state}


def experiment(histories,independent):
    r64=load('cdg64_for65',R64)
    r46=load('cdg46_for65',R46)
    r47=load('cdg47_for65',R47)
    r63=load('cdg63_for65',R63)
    summaries=[]
    for family,versions in histories.items():
        for count in INDEPENDENT_COUNTS:
            sources=[('history',x['data']) for x in versions]+independent[:count]
            for policy in POLICIES:
                archive=r64.StreamingArchive(sources,policy,r46.frame,r47,r63.windows)
                baseline_size=archive.archive_bytes()
                payload_bytes=sum(map(len,archive.payloads.values()))
                for interval in CHECKPOINT_INTERVALS:
                    journal=pack_journal(archive.events,r47,interval)
                    if journal['final_state']!=archive.manifests:
                        raise AssertionError('replay is not lossless historical source metadata')
                    output={
                        'family':family,'source_count':len(sources),
                        'independent_count':count,'policy':policy,
                        'migration_count':archive.migrated_prior_sources,
                        'payload_bytes':payload_bytes,
                        'baseline_full_snapshot_metadata_bytes':len(archive.manifest_blob),
                        'baseline_full_manifest_rewrite_written_bytes':archive.manifest_rewrite_bytes,
                        'baseline_full_snapshot_total_archive_bytes':baseline_size,
                        'checkpoint_interval':journal['checkpoint_interval'],
                        'manifest_journal_persistent_bytes':journal['persistent_metadata_bytes'],
                        'manifest_journal_written_bytes':journal['total_metadata_written_bytes'],
                        'journal_event_written_bytes':journal['event_written_bytes'],
                        'journal_checkpoint_written_bytes':journal['checkpoint_written_bytes'],
                        'journal_checkpoints':journal['checkpoints'],
                        'journal_cold_replay_us':journal['median_cold_replay_us'],
                        'journal_total_archive_bytes':payload_bytes+journal['persistent_metadata_bytes'],
                        'metadata_write_reduction_pct':round(
                            100*(1-journal['total_metadata_written_bytes']/
                                 archive.manifest_rewrite_bytes),3),
                        'metadata_storage_delta_pct':round(
                            100*(journal['persistent_metadata_bytes']/
                                 len(archive.manifest_blob)-1),3),
                    }
                    summaries.append(output)
    return {
        'rows':summaries,
        'checkpoint_intervals':CHECKPOINT_INTERVALS,
        'limitations':[
            'Journal event frames use JSON Zlib and 16-byte checksum; checkpoint uses prior binary-Zlib compact format',
            'Every source append and every prior source migration has an immutable append/replace event',
            'Write counts measure encoded user-space bytes, not kernel/fsync/storage-device page writes',
            'No crash-atomic checkpoint rotation; torn events are rejected by replay but recovery point not durable',
            'No source-identity index for random access to one manifest after replay and no on-disk cache',
            'Uncompacted journal can consume more retained bytes than latest full manifest',
            'The full manifest rewrite baseline intentionally rewrites entire metadata after every append; compare against SQLite WAL/LSM alternatives before deployment',
            'Existing mature log-structured storage, WAL and CAS techniques, no new manifest theory',
            'Same five actual pinned histories used in R64; no further untouched family confirmation']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=parser.parse_args()
    r64=load('cdg64_source65',R64)
    r62=load('cdg62_source65',R62)
    histories={name:r62.download_history(r62.PINNED[name])
               for name in r64.PINNED_PREVIOUS}
    histories.update({name:r62.download_history(spec)
                      for name,spec in r64.PINNED_UNSEEN.items()})
    independent,_=r62.input_sources(histories)
    result=experiment(histories,independent)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    focus=[x for x in result['rows'] if x['policy']=='threshold_migration'
           and x['independent_count']==512]
    print('ROUND65',json.dumps({'rows':focus},sort_keys=True))


if __name__=='__main__':main()
