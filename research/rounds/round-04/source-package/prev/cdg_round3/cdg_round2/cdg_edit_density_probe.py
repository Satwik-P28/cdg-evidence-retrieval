#!/usr/bin/env python3
"""Lossless compression crossover as version edits become dense.
Source: 150 real local documentation files; variants include controlled line edits.
All codecs count encoded payloads and a minimal manifest; this is NOT a searchable index.
"""
from cdg_experiment_suite import collect_base_docs, Z, build_store, recover
import hashlib, json, random, statistics, time
from pathlib import Path

RATES=[0.0,0.01,0.05,0.20,0.50]
SEED=35198

def run_one(rate,versions=7):
    orig=collect_base_docs()
    bundles=[];patch_files=[];base_compressed=[];ids=[]
    for f,(_,b) in enumerate(orig):
        text=b.decode('utf8')
        lines=text.splitlines(keepends=True)
        base_compressed.append(Z.compress(b,3))
        for v in range(versions):
            rr=random.Random(SEED+f*987+v*701)
            chosen=set(rr.sample(range(len(lines)),k=min(len(lines),round(rate*len(lines))))) if v else set()
            newlines=lines[:];patch=[]
            for li in sorted(chosen):
                old=lines[li]
                # Changing a line's content, while preserving the original line ending.
                ending='\n' if old.endswith('\n') else ''
                updated=old.rstrip('\n')+f' [experiment edit family={f} revision={v} field={li} value={rr.randrange(10000000)}]'+ending
                newlines[li]=updated
                patch.append((li,updated))
            db=''.join(newlines).encode('utf8')
            bundles.append((f,v,db))
            patch_raw=json.dumps(patch,separators=(',',':')).encode()
            patch_files.append(Z.compress(patch_raw,3) if patch else b'')
            # Verify direct overlay reconstructs the original bytes.
            t=lines[:]
            for j,updated in patch:t[j]=updated
            assert ''.join(t).encode()==db
    raw=sum(len(x[2]) for x in bundles)
    independent=sum(len(Z.compress(b,3)) for _,_,b in bundles)
    solid=len(Z.compress(b''.join(b for _,_,b in bundles),9))
    # encoded patch mapping (file positions) includes a compact fixed family id / revision
    patch_index=Z.compress(json.dumps([(f,v,len(cp)) for (f,v,_),cp in zip(bundles,patch_files)],separators=(',',':')).encode())
    overlay=sum(map(len,base_compressed))+sum(map(len,patch_files))+len(patch_index)
    store=build_store(bundles)
    chunk_bytes=store['storage']
    # one integrity check per doc, all docs on 0% and 5%, sampled 30% other cases
    rr=random.Random(SEED)
    sample=list(range(len(bundles))) if rate<=0.05 else rr.sample(range(len(bundles)),min(100,len(bundles)))
    for i in sample:assert recover(store,i)==bundles[i][2]
    return {'edit_fraction':rate,'base_docs':len(orig),'versions_per_base':versions,
            'total_docs':len(bundles),'raw_bytes':raw,
            'independent_zstd3_bytes':independent,
            'solid_zstd9_bytes':solid,
            'base_plus_line_overlay_zstd_bytes':overlay,
            'deduplicated_1024b_chunks_zstd_bytes':chunk_bytes,
            'overlay_vs_independent_ratio':round(independent/overlay,3),
            'chunk_vs_independent_ratio':round(independent/chunk_bytes,3),
            'integrity_checks':len(sample)}

def run():
    results=[]
    for r in RATES:
        t=time.perf_counter()
        d=run_one(r)
        d['experiment_seconds']=round(time.perf_counter()-t,2)
        results.append(d)
        print(json.dumps(d),flush=True)
    out={'description':'Controlled line-revision density stress test using real local documentation bases. No indexes included.',
         'results':results,
         'limitations':['Controlled added revision text, not actual revision histories.',
                        'Line overlays require known family grouping; storage includes per-version patch size metadata.',
                        'Source-storage results alone are not RAG speedups.',
                        'Deduplicated chunk manifests and hashes included via first-round implementation.',
                        'Solid zstd9 cannot independently access a document without additional mechanism.']}
    p='/mnt/data/cdg_round2/cdg_edit_density_results.json'
    Path(p).write_text(json.dumps(out,indent=2))
if __name__=='__main__':run()
