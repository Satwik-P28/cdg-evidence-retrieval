#!/usr/bin/env python3
"""R107 real SQLite FTS5 *derived docID-gap streams*, NOT native FTS5 segment rewriting.

Build a contentless SQLite FTS5 index over paragraphs in checked-in Markdown files,
extract term->distinct rowid posting lists using fts5vocab('instance'), encode exact
positive row-ID gaps with experimental BARM and conventional reference codecs.
No claims about native SQLite posting compression, random-access search speed,
or whole-index improvement are warranted from this test.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zlib
from barm import (
    BLOCK_SIZE, encode_block, decode_block, encode_golomb_block,
    decode_golomb_block, encode_elias, decode_elias, encode_varint,
    decode_varint, encode_block_bitpack, decode_block_bitpack,
    estimate_beta,
)
import math


def load_paragraphs(root: Path, patterns: list[str], max_files: int, max_docs: int):
    if not root.is_dir():
        raise ValueError('corpus root must be a directory')
    files = sorted({p for pattern in patterns for p in root.glob(pattern)
                    if p.is_file() and p.suffix.lower() in {'.md', '.txt'}})
    files = files[:max_files]
    docs = []
    manifest = []
    for p in files:
        raw = p.read_bytes()
        manifest.append({'path':p.relative_to(root).as_posix(), 'sha256':hashlib.sha256(raw).hexdigest()})
        text = raw.decode('utf-8')
        for paragraph in text.split('\n\n'):
            if len(paragraph.strip()) >= 10:
                docs.append(paragraph.strip())
                if len(docs) >= max_docs:
                    return docs, manifest
    if not docs:
        raise ValueError('empty paragraph corpus')
    return docs, manifest


def postings_from_docs(docs):
    db = sqlite3.connect(':memory:')
    try:
        db.execute("CREATE VIRTUAL TABLE docs USING fts5(body, content='')")
        db.executemany('INSERT INTO docs(rowid, body) VALUES (?,?)', enumerate(docs,1))
        db.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(docs, 'instance')")
        postings=defaultdict(list)
        last_term=None
        last_doc=-1
        for term, doc_id in db.execute('SELECT term,doc FROM vocab ORDER BY term,doc'):
            if term != last_term or doc_id != last_doc:
                postings[term].append(doc_id)
            last_term, last_doc = term,doc_id
        return postings
    finally:
        db.close()


def sizes_for_list(doc_ids):
    gaps=[]
    prev=0
    for value in doc_ids:
        if value <= prev:
            raise ValueError('posting ids must increase strictly')
        gaps.append(value-prev)
        prev=value
    total = defaultdict(int)
    for i in range(0,len(gaps),BLOCK_SIZE):
        a=gaps[i:i+BLOCK_SIZE]
        # The same 4-byte frame-length accounting is applied to every framed codec.
        beta = estimate_beta(a)
        m=min(1<<20,max(1,math.ceil(1/(beta-1))))
        encoders={
          'barm_r':(encode_block(a),decode_block),
          'barm_g':(encode_golomb_block(a,m),decode_golomb_block),
          'gamma':(encode_elias(a),decode_elias),
          'delta':(encode_elias(a,True),lambda b:decode_elias(b,True)),
          'varint':(encode_varint(a),decode_varint),
          'fixed_bitpack':(encode_block_bitpack(a),decode_block_bitpack),
        }
        for label, (blob,decode) in encoders.items():
            if decode(blob)!=a:
                raise AssertionError('codec not lossless: '+label)
            total[label]+=4+len(blob)
        total['zlib_varint_block']+=4+len(zlib.compress(encoders['varint'][0],9))
    # Global zlib has a different random-access contract; never compare as equal.
    encoded_varints=b''.join(encode_varint(gaps[i:i+BLOCK_SIZE]) for i in range(0,len(gaps),BLOCK_SIZE))
    total['zlib_varint_global']=len(zlib.compress(encoded_varints,9))
    return total


def run(root:Path, patterns:list[str], max_files:int=30, max_docs:int=5000,
        max_terms:int=3000, min_df:int=3):
    docs,manifest=load_paragraphs(root,patterns,max_files,max_docs)
    postings=postings_from_docs(docs)
    eligible=sorted((term, ids) for term,ids in postings.items() if len(ids)>=min_df)
    eligible=eligible[:max_terms]
    if not eligible:
        raise ValueError('no terms meet min_df')
    grand=defaultdict(int)
    for term,ids in eligible:
        costs=sizes_for_list(ids)
        for name,value in costs.items():grand[name]+=value
    # Index overhead, term dictionary and source archive are not part of these numbers.
    return {
        'contract':'SQLite FTS5-derived logical posting rowid gap stream, not FTS5 native segment encoding',
        'input_manifest':manifest,
        'n_documents':len(docs), 'n_all_index_terms':len(postings),
        'n_measured_terms':len(eligible),
        'n_postings':sum(len(p) for _,p in eligible),
        'selection':{'min_df':min_df,'max_terms':max_terms,'sort':'lexical term'},
        'sizes_bytes':dict(grand),
        'bpi':{k:round(8*v/sum(len(p) for _,p in eligible),5) for k,v in grand.items()},
        'limitations':'No native FTS5 postings replaced; no full SQLite size or retrieval latency; global zlib is not random seekable',
    }


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',required=True)
    ap.add_argument('--pattern',action='append',default=[])
    ap.add_argument('--max-files',type=int,default=30)
    ap.add_argument('--max-docs',type=int,default=5000)
    ap.add_argument('--max-terms',type=int,default=3000)
    ap.add_argument('--min-df',type=int,default=3)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    path=Path(args.root)
    r=run(path,args.pattern or ['research/rounds/round-*/report.md'],args.max_files,args.max_docs,args.max_terms,args.min_df)
    Path(args.out).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'docs':r['n_documents'],'terms':r['n_measured_terms'], 'gaps':r['n_postings'],'bytes':r['sizes_bytes']},indent=2))