#!/usr/bin/env python3
"""R83 official SciFact release provenance and schema audit.

Downloads the official AI2/SciFact S3 release tarball only, extracts two
explicitly named public JSONL members IN MEMORY with byte-size caps, checks
schemas, emits source SHA256 and label counts. Never persists corpus text.
"""
from __future__ import annotations
import argparse,hashlib,io,json,tarfile
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
UPSTREAM='https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz'
MAX_ARCHIVE_BYTES=75_000_000
MAX_MEMBER_BYTES=30_000_000
MEMBERS={'data/corpus.jsonl','data/claims_dev.jsonl'}
# Fill from initial official-source probe, then require immutable SHA before
# any model or comparative test is promoted.
LOCK=HERE/'upstream_lock.json'


def digests(blob):
    return {'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob)}


def fetch(fetcher=None):
    if fetcher is None:
        with urlopen(Request(UPSTREAM,headers={'User-Agent':'CDG-SciFact-source-audit/1.0'}),
                     timeout=120) as resp:
            archive=resp.read(MAX_ARCHIVE_BYTES+1)
    else:
        archive=fetcher(UPSTREAM)
    if len(archive)>MAX_ARCHIVE_BYTES:
        raise ValueError('unbounded source archive')
    if not archive.startswith(b'\x1f\x8b'):
        raise ValueError('not official tar gzip payload')
    raw={}
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tf:
        names={m.name for m in tf.getmembers()}
        for name in MEMBERS:
            if name not in names:
                raise ValueError(f'missing {name}, sample members {sorted(names)[:8]}')
            m=tf.getmember(name)
            if not m.isfile() or not 0<m.size<=MAX_MEMBER_BYTES:
                raise ValueError('invalid source tar member size or type')
            fileobj=tf.extractfile(m)
            if fileobj is None:raise ValueError('unreadable tar member')
            data=fileobj.read(MAX_MEMBER_BYTES+1)
            if len(data)!=m.size:
                raise ValueError('partial upstream member')
            raw[name]=data
    if LOCK.exists():
        lock=json.loads(LOCK.read_text())
        if lock.get('archive_sha256')!=digests(archive)['sha256']:
            raise ValueError('SciFact source release changed vs lock')
        for name in MEMBERS:
            if lock.get('members',{}).get(name)!=digests(raw[name])['sha256']:
                raise ValueError(f'SciFact {name} changed vs lock')
    return archive,raw


def parse(raw):
    rows={}
    for name,blob in raw.items():
        records=[json.loads(x) for x in blob.splitlines() if x.strip()]
        if not records:raise ValueError('empty corpus or claims')
        rows[name]=records
    corpus=rows['data/corpus.jsonl']
    dev=rows['data/claims_dev.jsonl']
    if len({str(x['doc_id']) for x in corpus})!=len(corpus):
        raise ValueError('duplicate corpus doc_id')
    if len({str(x['id']) for x in dev})!=len(dev):
        raise ValueError('duplicate dev claim ID')
    for row in corpus:
        if not isinstance(row.get('title'),str) or not isinstance(row.get('abstract'),list) or not all(isinstance(t,str) for t in row['abstract']):
            raise ValueError('unexpected corpus schema')
    counts=Counter()
    refs=Counter()
    for row in dev:
        if not isinstance(row.get('claim'),str) or not isinstance(row.get('evidence'),dict):
            raise ValueError('unexpected claim schema')
        for docid,rationales in row['evidence'].items():
            if not rationales:continue
            labels={r['label'] for r in rationales}
            if labels-{'SUPPORT','CONTRADICT'}:raise ValueError('unexpected label')
            if len(labels)!=1:raise ValueError('ambiguous gold label')
            counts[next(iter(labels))]+=1
            refs['annotated_doc_claim_pairs']+=1
        refs['claims_with_evidence']+=int(bool(row['evidence']))
    return corpus,dev,{'labels':dict(counts),
                       'claims_total':len(dev),'corpus_docs':len(corpus),
                       'claims_with_evidence':refs['claims_with_evidence'],
                       'annotated_doc_claim_pairs':refs['annotated_doc_claim_pairs']}


def inspect(fetcher=None):
    tar,members=fetch(fetcher)
    _,_,counts=parse(members)
    return {'official_release_url':UPSTREAM,'archive':digests(tar),
            'members':{k:digests(v) for k,v in members.items()},
            'schema_counts':counts,
            'license_note':'SciFact claims and annotations CC BY 4.0, underlying abstracts ODC-By 1.0 per official allenai/scifact/LICENSE.md',
            'status':'data source provenance only; no pretrained model or new comparison executed'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(HERE/'probe-results.json'))
    args=parser.parse_args()
    result=inspect()
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND83_SOURCE_PROBE',json.dumps(result,sort_keys=True))
