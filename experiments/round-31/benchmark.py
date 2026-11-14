#!/usr/bin/env python3
"""Single-writer snapshot and online retrieval trial on local CDG reports.

Source data: five local round reports (24–28), not HotpotQA; queries come from
those reports. Build/read timings are warm single-process exploratory timings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path
from snapshot_store import SnapshotReader,publish

TERMS=('evidence','retrieval','source','compression','index','research','bridge',
       'frame','cost','result','document','accuracy','model','version','storage')

def profile(paths:list[Path],root:Path)->dict:
    original=sum(p.stat().st_size for p in paths)
    input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    start=time.perf_counter_ns();old=publish(root,paths,frame_size=512)
    initial_build_ms=(time.perf_counter_ns()-start)/1e6
    costs=[];counts=[];results=[]
    pinned=SnapshotReader(root)
    try:
        for term in TERMS:
            st=time.perf_counter_ns()
            hits=pinned.search(term,5)
            costs.append((time.perf_counter_ns()-st)/1000)
            counts.append(sum(x['compressed_bytes'] for x in hits))
            results.append({'term':term,'hits':len(hits),'bytes':counts[-1]})
        old_receipt=pinned.search('evidence',5)[0]['receipt']
        old_bytes=pinned.read_receipt(old_receipt)
        # Mutate exactly one source, in same position (source filename preserved).
        original_blob=paths[0].read_bytes()
        paths[0].write_bytes(original_blob+b'\nRound31 independent version sentinel.\n')
        try:
            update_start=time.perf_counter_ns();new=publish(root,paths,frame_size=512)
            update_ms=(time.perf_counter_ns()-update_start)/1e6
            with SnapshotReader(root) as reader:
                stale_rejected=False
                try:reader.read_receipt(old_receipt)
                except ValueError:stale_rejected=True
                new_hits=reader.search('sentinel',5)
                new_recovers=any('sentinel' in h['text'] for h in new_hits)
            old_reader_retains_bytes=pinned.read_receipt(old_receipt)==old_bytes
            disk=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        finally:
            paths[0].write_bytes(original_blob)
    finally:
        pinned.close()
    def q95(arr):return sorted(arr)[int(.95*(len(arr)-1))]
    return {
        'source_files':[str(p) for p in paths],
        'source_sha256_before':input_hashes,
        'original_bytes':original,
        'initial_build_ms':round(initial_build_ms,2),
        'update_full_rebuild_ms':round(update_ms,2),
        'first_snapshot_total_bytes':old['index_bytes']+old['payload_bytes'],
        'first_snapshot_sqlite_bytes':old['index_bytes'],
        'first_snapshot_payload_bytes':old['payload_bytes'],
        'first_snapshot_link_edges':old['links'],
        'second_snapshot_total_bytes':new['index_bytes']+new['payload_bytes'],
        'two_generations_plus_manifests_and_current_bytes':disk,
        'query_count':len(TERMS),
        'mean_compressed_bytes_at_top5':round(statistics.mean(counts),1),
        'warm_median_search_and_decode_us':round(statistics.median(costs),1),
        'warm_p95_search_and_decode_us':round(q95(costs),1),
        'stale_receipt_rejected_by_new_reader':stale_rejected,
        'old_reader_retained_snapshot':old_reader_retains_bytes,
        'new_generation_search_retrieves_update':new_recovers,
        'queries':results,
        'scope':'Local five reports, source-derived keyword queries, one appended update; warm single-process timings, full rebuild and retained snapshots; no HotpotQA/ACL/authenticated source freshness/cold cache'
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--files',type=Path,nargs='+',required=True)
    ap.add_argument('--output',type=Path,required=True)
    opts=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='cdg-r31-') as td:
        # Safeguard original inputs: use dedicated scratch copies.
        scratch=Path(td)/'sources';scratch.mkdir()
        copied=[]
        for n,p in enumerate(opts.files):
            c=scratch/f'round{24+n}_{p.name}';c.write_bytes(p.read_bytes());copied.append(c)
        data=profile(copied,Path(td)/'archive')
    data['source_files']=[str(p) for p in opts.files]
    data['source_sha256_before']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in opts.files}
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in ('queries','source_files','source_sha256_before')},indent=2))
if __name__=='__main__':main()