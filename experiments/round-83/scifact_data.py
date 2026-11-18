#!/usr/bin/env python3
"""R83 SciFact source-locked profile: prepare human-annotated gold document pairs.

Upstream SciFact (Wadden et al. EMNLP 2020) publishes expert-written scientific
claim evidence annotations. We use official train for threshold calibration
and official dev for evaluation, never their hidden-label test split. All source
texts remain transient; published artifacts contain only derived aggregates.
"""
from __future__ import annotations

import hashlib
import io
import json
import random
import statistics
import tarfile
import time
import urllib.request
import zlib
from collections import Counter,defaultdict
from pathlib import Path

URL="https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
# Official AllenAI SciFact release URL from allenai/scifact Git commit:
UPSTREAM_CODE_SHA="68b98a56d93e0f9da0d2aab4e6c3294699a0f72e"
# Update once the first exact tarball hash is observed, so reruns are immutable.
ARCHIVE_SHA256='11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be'
SALT="CDG-R83-HUMAN-SCIFACT-SOURCE-DISJOINT-v1"
PER_STATE_PER_SPLIT=32
LABELS={"SUPPORT":1,"CONTRADICT":0}
REQUIRED=("corpus.jsonl","claims_train.jsonl","claims_dev.jsonl")


def decode_release(payload: bytes):
    if len(payload)>35_000_000:
        raise RuntimeError("Unexpected SciFact bundle length")
    actual_sha=hashlib.sha256(payload).hexdigest()
    if ARCHIVE_SHA256 is not None and actual_sha!=ARCHIVE_SHA256:
        raise AssertionError("SciFact upstream archive drift; do not silently resample")
    files={}
    with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as tar:
        members=[m for m in tar.getmembers() if m.isfile()]
        for basename in REQUIRED:
            matched=[m for m in members if Path(m.name).name==basename]
            if len(matched)!=1:
                raise ValueError(f"SciFact archive expected one {basename}, got {len(matched)}")
            fh=tar.extractfile(matched[0])
            if fh is None:
                raise AssertionError(f"Cannot read {basename}")
            content=fh.read(20_000_000)
            if len(content)>=20_000_000:
                raise ValueError("unexpected oversized JSONL")
            files[basename]=[json.loads(line) for line in content.decode("utf8").splitlines()
                             if line.strip()]
    return files,actual_sha


def load_release():
    request=urllib.request.Request(URL,headers={"User-Agent":"CDG-Research-Verification/1.0"})
    start=time.perf_counter()
    with urllib.request.urlopen(request,timeout=120) as response:
        content=response.read(35_000_001)
    if len(content)>35_000_000:
        raise ValueError("upstream archive exceeds cap")
    files,actual_sha=decode_release(content)
    return files,{'source_url':URL,'archive_sha256':actual_sha,
                  'upstream_code_git_sha':UPSTREAM_CODE_SHA,
                  'download_wall_seconds':round(time.perf_counter()-start,3),
                  'archive_bytes':len(content),
                  'release_sha_lock_enabled':ARCHIVE_SHA256 is not None}


def extract_pairs(rows,corpus,split):
    pairs=[]
    invalid=Counter()
    for row in rows:
        claim=row.get('claim')
        evidence=row.get('evidence') or {}
        if not isinstance(evidence,dict):
            raise ValueError('SciFact evidence schema changed')
        for doc_id, annotations in evidence.items():
            doc=corpus.get(str(doc_id))
            if not doc:
                invalid['missing_abstract']+=1
                continue
            annotations=[a for a in annotations if a.get('label') in LABELS]
            states={a['label'] for a in annotations}
            if len(states)!=1:
                invalid['ambiguous_label']+=1
                continue
            label=next(iter(states))
            inds=sorted({int(i) for a in annotations for i in a.get('sentences',[])})
            abstract=doc.get('abstract') or []
            if not inds or any(i<0 or i>=len(abstract) for i in inds):
                invalid['invalid_rationale']+=1
                continue
            if not claim or not isinstance(claim,str):
                invalid['bad_claim']+=1
                continue
            title=str(doc.get('title') or '')
            full='Title: '+title+'\n'+'Abstract: '+' '.join(abstract)
            rationale=' '.join(abstract[i] for i in inds)
            key=f"{split}:{row['id']}:{doc_id}:{label}"
            pairs.append({
                'key':key,'split':split,'claim_id':str(row['id']),
                'doc_id':str(doc_id),'claim':claim,'gold':LABELS[label],
                'gold_label':label,'doc':full,'rationale':rationale,
                'sentences':list(abstract),'title':title,
                'evidence_sentence_count':len(inds),
            })
    unique={}
    for x in pairs:
        if x['key'] in unique:
            raise AssertionError('duplicate case key')
        unique[x['key']]=x
    return list(unique.values()),invalid


def selection_key(row):
    return hashlib.sha256((SALT+'|'+row['key']).encode()).hexdigest()


def select_pairs(files,limit=PER_STATE_PER_SPLIT):
    corpus={str(x['doc_id']):x for x in files['corpus.jsonl']}
    if len(corpus)!=len(files['corpus.jsonl']):
        raise AssertionError('duplicate corpus ID')
    train,invalid_t=extract_pairs(files['claims_train.jsonl'],corpus,'train')
    dev,invalid_d=extract_pairs(files['claims_dev.jsonl'],corpus,'dev')
    if not train or not dev:
        raise AssertionError('SciFact source documents have no evidence labels')
    # Choose train documents first, then disallow those source document IDs in
    # the frozen evaluation sample. Source-disjoint model input does NOT imply
    # the published model itself was never trained on SciFact material.
    picks=[]
    for label in (1,0):
        chosen=sorted((x for x in train if x['gold']==label),key=selection_key)[:limit]
        if len(chosen)<16:
            raise AssertionError(f"insufficient calibration examples label={label}")
        picks+=chosen
    train_doc_ids={x['doc_id'] for x in picks}
    train_claim_ids={x['claim_id'] for x in picks}
    selected_dev=[]
    for label in (1,0):
        chosen=sorted(
            (x for x in dev if x['gold']==label and x['doc_id'] not in train_doc_ids
             and x['claim_id'] not in train_claim_ids),key=selection_key)[:limit]
        if len(chosen)<16:
            raise AssertionError(f"insufficient source-disjoint evaluation examples label={label}")
        selected_dev+=chosen
    if set(x['doc_id'] for x in selected_dev)&train_doc_ids:
        raise AssertionError('source overlap')
    if set(x['claim_id'] for x in selected_dev)&train_claim_ids:
        raise AssertionError('claim overlap')
    picks=sorted(picks,key=selection_key)
    selected_dev=sorted(selected_dev,key=selection_key)
    source_keys='\n'.join(x['key'] for x in picks+selected_dev)
    info={
        'total_release_corpus_docs':len(corpus),
        'available_raw_evidence_pairs':{'train':len(train),'dev':len(dev)},
        'available_gold_label_counts':{
            split:dict(Counter(x['gold_label'] for x in cases))
            for split,cases in [('train',train),('dev',dev)]},
        'rejected_cases':{'train':dict(invalid_t),'dev':dict(invalid_d)},
        'selected':{
            split:{
                'cases':len(cases),
                'supported':sum(x['gold'] for x in cases),
                'contradicted':sum(1-x['gold'] for x in cases),
                'distinct_docs':len({x['doc_id'] for x in cases}),
                'distinct_claims':len({x['claim_id'] for x in cases}),
                'mean_abstract_words':round(statistics.mean(len(x['doc'].split()) for x in cases),2),
                'mean_rationale_words':round(statistics.mean(len(x['rationale'].split()) for x in cases),2),
                'multi_sentence_evidence':sum(x['evidence_sentence_count']>1 for x in cases),
            }
            for split,cases in [('train',picks),('dev',selected_dev)]},
        'selected_key_sha256':hashlib.sha256(source_keys.encode()).hexdigest(),
        'pair_sampling_salt':SALT,
        'calibration_selection_uses_no_dev_labels':True,
        'dev_exclusion_uses_doc_and_claim_identifiers':True,
        'oracle_gold_evidence_source':True,
    }
    return picks,selected_dev,corpus,info


def profile():
    files,source=load_release()
    train,dev,corpus,selected=select_pairs(files)
    original_bytes=sum(len(('Title: '+str(x.get('title') or '')+'\nAbstract: '+
                            ' '.join(x.get('abstract') or [])).encode('utf8'))
                       for x in corpus.values())
    compressed_bytes=sum(len(zlib.compress(('Title: '+str(x.get('title') or '')+
                '\nAbstract: '+' '.join(x.get('abstract') or [])).encode('utf8'),6))
                       for x in corpus.values())
    report={
        'upstream':source,
        'selection':selected,
        'compression':{
            'corpus_uncompressed_utf8_bytes':original_bytes,
            'whole_per_doc_zlib6_bytes':compressed_bytes,
            'ratio_zlib_over_original':round(compressed_bytes/original_bytes,5),
            'excludes_doc_id_index_and_source_manifest':True,
        },
        'limitations':[
            'ground-truth gold source document ID used for each claim; no retrieval evaluation yet',
            'experts annotated scientific support/contradiction, not arbitrary unknown-source truth',
            'dev labels never used for source selection threshold fitting; they are used for stratified evaluation sampling and scoring',
            'sampled dev cases are balanced on known labels, so prevalence metrics do not reflect deployment base rate',
            'rationale-only evidence is an oracle selected by expert annotations and is not a deployable retrieval result',
            'SciFact code reference is fixed; release tarball must be SHA-locked after first verified download',
            'SciFact claims CC BY 4.0, S2ORC corpus ODC-By 1.0 per official release; HuggingFace repackaging has different card license',
            'model vendors may have used SciFact in pretraining; source split does not establish model-training independence',
            'data and abstracts are never redistributed through artifact outputs',
        ],
    }
    return report


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default=str(Path(__file__).resolve().parent/"profile.json"))
    args=ap.parse_args()
    rep=profile()
    Path(args.out).write_text(json.dumps(rep,indent=2)+"\n")
    print("ROUND83_PROFILE",json.dumps(rep,sort_keys=True))
