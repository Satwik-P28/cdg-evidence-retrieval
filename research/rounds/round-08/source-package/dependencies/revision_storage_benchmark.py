#!/usr/bin/env python3
"""CDG round 3: interior-edit lossless source-storage stress test.

Uses real local technical-document bodies, with synthetic edits applied in the
middle of documents. Compares independent zstd, per-family patch, a hybrid
per-family selector, and solid archive (not independently accessible).
Full source filenames & bytes intentionally not embedded in package.
"""
from __future__ import annotations
import json, hashlib, random, difflib, statistics, struct, time, collections
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'cdg_round2'))
from cdg_experiment_suite import collect_base_docs, Z, chunk_lines
OUT=Path(__file__).parent
R=random.Random(638492)


def edit_doc(raw, rate, seed, mode):
    r=random.Random(seed)
    lines=raw.decode('utf8').splitlines(keepends=True)
    # Edits inside document, excluding first and last 5 lines.
    n=max(1, round(len(lines)*rate)) if rate else 0
    where=sorted(r.sample(range(5,len(lines)-5),min(n,len(lines)-10)),reverse=True) if n else []
    for i,idx in enumerate(where):
        original=lines[idx]
        new=f'CDG SYNTHETIC REVISION field_{i:04d} status_{["valid","retracted","updated"][i%3]} number_{seed%10000+i*31}.\n'
        op=mode if mode!='mixed' else ['replace','insert','delete'][i%3]
        if op=='replace': lines[idx]=new
        elif op=='insert':lines.insert(idx,new)
        else:lines.pop(idx)
    return ''.join(lines).encode('utf8')


def patch(base,modified):
    a=base.splitlines(keepends=True);b=modified.splitlines(keepends=True)
    sm=difflib.SequenceMatcher(None,a,b,autojunk=False)
    ops=[]
    for tag,i0,i1,j0,j1 in sm.get_opcodes():
        if tag!='equal':ops.append((i0,i1,b''.join(b[j0:j1]).decode('utf8')))
    enc=json.dumps(ops,ensure_ascii=False,separators=(',',':')).encode('utf8')
    return enc


def apply_patch(base,payload):
    ops=json.loads(payload)
    a=base.splitlines(keepends=True)
    out=[];pos=0
    for i0,i1,text in ops:
        out.extend(a[pos:i0]);out.append(text.encode('utf8'));pos=i1
    out.extend(a[pos:]);return b''.join(out)


def test_case(bases,rate,mode):
    compressed_independent=[];compressed_patches=[];compressed_hybrid=[]
    orig_total=0; raw_total=0
    lat_ind=[];lat_patch=[];hybrid_used=0
    for fi,base in enumerate(bases):
        base_z=Z.compress(base,3)
        variants=[base]+[edit_doc(base,rate,638492+fi*131+v,mode) for v in range(1,7)]
        raw_total+=sum(len(x) for x in variants)
        # Patch stream includes exact metadata, and standalone doc compressed alternative.
        patches=[];ind=[]
        for v in variants:
            z=Z.compress(v,3)
            ind.append(z)
            p=Z.compress(patch(base,v),3)
            patches.append(p)
            assert apply_patch(base,Z.decompress(p,len(patch(base,v))))==v
        original_ind=sum(map(len,ind))
        original_patch=len(base_z)+sum(len(x)+4 for x in patches)
        # Explicit family selector flag + independent or base-patch payload.
        choice=min(original_ind,original_patch)+1
        hybrid_used+=int(original_patch<=original_ind)
        compressed_independent.append(original_ind)
        compressed_patches.append(original_patch)
        compressed_hybrid.append(choice)
        # Check random read for one version, medians are descriptive only.
        j=3
        t=time.perf_counter_ns();d=Z.decompress(ind[j],len(variants[j]));lat_ind.append(time.perf_counter_ns()-t)
        assert d==variants[j]
        pp=patch(base,variants[j]);t=time.perf_counter_ns()
        de=Z.decompress(base_z,len(base));pd=Z.decompress(patches[j],len(pp))
        d=apply_patch(de,pd);lat_patch.append(time.perf_counter_ns()-t)
        assert d==variants[j]
    solid=Z.compress(b''.join(struct.pack('<I',len(v))+v for fi,b in enumerate(bases) for v in [b]+[edit_doc(b,rate,638492+fi*131+x,mode) for x in range(1,7)]),9)
    return {'edit_density':rate,'mode':mode,'families':len(bases),'versions_per_family':7,'raw_bytes':raw_total,
     'independent_zstd_bytes':sum(compressed_independent),'base_plus_diff_bytes':sum(compressed_patches),
     'per_family_hybrid_bytes':sum(compressed_hybrid),'families_selecting_patch':hybrid_used,
     'solid_zstd9_bytes':len(solid),
     'median_independent_read_ms':round(statistics.median(lat_ind)/1e6,4),
     'median_patch_read_ms':round(statistics.median(lat_patch)/1e6,4)}

def run():
    seeds=[d[1] for d in collect_base_docs() if len(d[1].splitlines())>=30][:48]
    results=[test_case(seeds,r,m) for r in [0.001,0.01,0.05,0.20] for m in ['mixed','replace']]
    obj={'method':'Real local doc bodies, controlled *interior* edits; 48 families × 7 versions. zstd 3, solid zstd 9; patch encoding SequenceMatcher JSON opcodes. Median decode in Python on warm cache; not SSD or production latency.', 'results':results}
    (OUT/'revision_storage_results.json').write_text(json.dumps(obj,indent=2))
    print(json.dumps(obj,indent=2))
if __name__=='__main__':run()
