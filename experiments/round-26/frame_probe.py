#!/usr/bin/env python3
"""Round 26: exact UTF-8 receipt, frame activation, and compressed frame benchmark.

Run with pinned Round 25 HotpotQA-derived source:
 python frame_probe.py --data qa_train.json --output results_reproduced.json

The data input is never selected using gold evidence annotations. Gold facts
are consulted only in evaluate(). The supplied corpus is a closed-world,
curated set, not an official held-out benchmark. This script actually compresses
independent frames with zlib or an optional system libzstd when data is present.
Do not call Python process timing here an SSD cold-read latency measurement.
"""
from __future__ import annotations
import argparse
from collections import Counter
import ctypes
import ctypes.util
import hashlib
import json
import math
from pathlib import Path
import re
import zlib

SOURCE_COMMIT = 'fdab15b3929d2ee40dfcdd388f90233096a6afc9'
SOURCE_BLOB = '7dbdf068a437f0577043667ffee3a20f0a602154'
SOURCE_URL = ('https://raw.githubusercontent.com/OpenSPG/KAG/' + SOURCE_COMMIT +
              '/kag/open_benchmark/hotpotqa/data/qa_train.json')
FRAME_SIZES = (128, 256, 512, 1024, 2048)
BUDGETS = (2, 3, 5)
POLICIES = ('full', 'top2', 'top3', 'top2+link')


def words(s: str) -> list[str]:
    return re.findall(r'[^\W_]+', s.lower(), re.UNICODE)


def canon(s: str) -> str:
    return ' '.join(words(s))


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def load_source(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if git_blob_sha(raw) != SOURCE_BLOB:
        raise ValueError('pinned upstream Git blob mismatch; no results accepted')
    rows = json.loads(raw)
    if len(rows) != 100:
        raise ValueError('unexpected number of source questions')
    for row in rows:
        ctx = dict(row['context'])
        for title, sent_id in row['supporting_facts']:
            if title not in ctx or not (0 <= sent_id < len(ctx[title])):
                raise ValueError('missing annotated source sentence')
    return rows


def bm25(question: str, documents: list[str]) -> list[float]:
    ts = [words(d) for d in documents]
    if not ts or not any(ts):
        raise ValueError('BM25 documents have no tokens')
    df = Counter(w for t in ts for w in set(t))
    avg = sum(len(t) for t in ts) / len(ts)
    n = len(ts)
    out = []
    for terms in ts:
        f = Counter(terms)
        score = 0.0
        for w in set(words(question)):
            v = f[w]
            if v:
                idf = math.log(1+(n-df[w]+0.5)/(df[w]+0.5))
                score += idf*(2.2*v)/(v+1.2*(0.25+0.75*len(terms)/avg))
        out.append(score)
    return out


def rank_bridge(row: dict, count: int = 5, bonus: float = 2.0) -> list[int]:
    context = row['context']
    scores = bm25(row['question'], [t+' '+' '.join(s) for t, s in context])
    titles = [' '+canon(t)+' ' for t, _ in context]
    bodies = [' '+canon(' '.join(s))+' ' for _, s in context]
    chosen: list[int] = []
    while len(chosen) < min(len(context), count):
        best, best_score = -1, -math.inf
        for i, (title, _) in enumerate(context):
            if i in chosen:
                continue
            value = scores[i]
            if chosen and len(titles[i]) > 4 and any(titles[i] in bodies[j] for j in chosen):
                value += bonus
            if value > best_score+1e-10 or (abs(value-best_score) < 1e-10 and
                (best < 0 or title < context[best][0])):
                best, best_score = i, value
        chosen.append(best)
    return chosen


def source_bytes_and_receipts(title: str, sentences: list[str]) -> tuple[bytes, list[tuple[int,int]]]:
    """Exact UTF-8 byte offsets into the explicitly declared source serialization.

    Not offsets in the original HotpotQA source JSON. Source bytes are defined
    as title + newline + every sentence + newline. No normalization of source.
    """
    raw = bytearray((title+'\n').encode('utf-8'))
    spans = []
    for sentence in sentences:
        start = len(raw)
        raw.extend(sentence.encode('utf-8'))
        spans.append((start, len(raw)))
        raw.extend(b'\n')
    return bytes(raw), spans


def selected_sentence_ids(row: dict, document_ids: list[int], policy: str) -> dict[int,set[int]]:
    if policy not in POLICIES:
        raise ValueError(policy)
    context = row['context']
    chosen: dict[int,set[int]] = {}
    for i in document_ids:
        sentences = context[i][1]
        if policy == 'full':
            chosen[i] = set(range(len(sentences)))
        else:
            scores = bm25(row['question'], sentences)
            ordered = sorted(range(len(sentences)), key=lambda j: (-scores[j], j))
            chosen[i] = set(ordered[:3 if policy=='top3' else 2])
    if policy == 'top2+link':
        for n in range(1,len(document_ids)):
            title = ' '+canon(context[document_ids[n]][0])+' '
            if len(title) <= 4:
                continue
            for prior_id in document_ids[:n]:
                for j,s in enumerate(context[prior_id][1]):
                    if title in ' '+canon(s)+' ':
                        chosen[prior_id].add(j)
    return chosen


def activated_frame_ids(spans: list[tuple[int,int]], frame_size: int) -> set[int]:
    if frame_size < 1:
        raise ValueError('frame size must be positive')
    out = set()
    for start, end in spans:
        if start < 0 or end < start:
            raise ValueError('invalid span')
        if start < end:
            out.update(range(start//frame_size,(end-1)//frame_size+1))
    return out


def frame_payload_bytes(source: bytes, frames: set[int], size: int) -> int:
    return sum(len(source[i*size:(i+1)*size]) for i in frames)


class Codec:
    def __init__(self, name='zlib'):
        self.name = name
        if name == 'zstd':
            libname = ctypes.util.find_library('zstd')
            if not libname:
                raise RuntimeError('libzstd unavailable')
            self.lib = ctypes.CDLL(libname)
            self.lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
            self.lib.ZSTD_compressBound.restype = ctypes.c_size_t
            self.lib.ZSTD_compress.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
            self.lib.ZSTD_compress.restype = ctypes.c_size_t
            self.lib.ZSTD_decompress.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
            self.lib.ZSTD_decompress.restype = ctypes.c_size_t
            self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
            self.lib.ZSTD_isError.restype = ctypes.c_uint
        elif name != 'zlib':
            raise ValueError(name)

    def compress(self, data: bytes) -> bytes:
        if self.name == 'zlib':
            return zlib.compress(data,6)
        size = self.lib.ZSTD_compressBound(len(data))
        out = ctypes.create_string_buffer(size)
        src = ctypes.create_string_buffer(data)
        n = self.lib.ZSTD_compress(out,size,src,len(data),3)
        if self.lib.ZSTD_isError(n):
            raise RuntimeError('zstd compress error')
        return out.raw[:n]

    def decompress(self, data: bytes, length: int) -> bytes:
        if self.name == 'zlib':
            return zlib.decompress(data)
        out = ctypes.create_string_buffer(length)
        src = ctypes.create_string_buffer(data)
        n = self.lib.ZSTD_decompress(out,length,src,len(data))
        if self.lib.ZSTD_isError(n) or n != length:
            raise RuntimeError('zstd decompress error')
        return out.raw[:n]


def materialize_frames(raw: bytes, size: int, codec: Codec) -> list[bytes]:
    parts = [raw[i:i+size] for i in range(0,len(raw),size)]
    packed = [codec.compress(p) for p in parts]
    for i,compressed in enumerate(packed):
        if codec.decompress(compressed,len(parts[i])) != parts[i]:
            raise RuntimeError('lossless frame roundtrip failed')
    return packed


def exact_receipts(raw: bytes, spans: list[tuple[int,int]]) -> list[dict]:
    return [{'start_byte':a,'end_byte':b,'sha256':hashlib.sha256(raw[a:b]).hexdigest()} for a,b in spans]


def evaluate(data: list[dict], codec_name='zstd', frame_sizes=FRAME_SIZES) -> dict:
    """Fresh real-data calculation; CPU used for BM25 indexing is not charged.

    Full archive includes all per-question candidate documents, stored as
    separate source occurrences. Frame metadata is *modeled* 16 B per frame.
    The actual compressed frame sizes are measured via codec calls here.
    """
    codec = Codec(codec_name)
    result = {str(k):{p:{'n':0,'complete_gold_sentences':0,'complete_docs':0,'selected_utf8_bytes':0,
                     'full_selected_source_bytes':0,'physical':{str(B):{'read_raw_bytes':0,'read_compressed_bytes':0} for B in frame_sizes}}
                       for p in POLICIES} for k in BUDGETS}
    archive = {str(B):{'uncompressed_bytes':0,'compressed_frame_bytes':0,'frame_count':0,
                       'modeled_frame_metadata_bytes':0} for B in frame_sizes}
    paired={str(k):{'top2_only':0,'link_only':0,'both':0,'neither':0} for k in BUDGETS}
    for row in data:
        layout=[source_bytes_and_receipts(t,s) for t,s in row['context']]
        rank=rank_bridge(row)
        compressed={B:[materialize_frames(raw,B,codec) for raw, _ in layout] for B in frame_sizes}
        for B in frame_sizes:
            ar=archive[str(B)]
            ar['uncompressed_bytes']+=sum(len(raw) for raw,_ in layout)
            ar['compressed_frame_bytes']+=sum(sum(map(len,frames)) for frames in compressed[B])
            count=sum(len(frames) for frames in compressed[B]);ar['frame_count']+=count
            ar['modeled_frame_metadata_bytes']+=16*count
        gold=[(next(i for i,(title,_) in enumerate(row['context']) if title==t),sent)
              for t,sent in row['supporting_facts']]
        for k in BUDGETS:
            selected=rank[:k]
            complete={}
            for policy in POLICIES:
                picks=selected_sentence_ids(row,selected,policy)
                out=result[str(k)][policy];out['n']+=1
                out['complete_docs']+=int(all(i in picks for i,j in gold))
                correct=all(j in picks.get(i,set()) for i,j in gold)
                complete[policy]=correct
                out['complete_gold_sentences']+=int(correct)
                for i,indices in picks.items():
                    raw,receipt=layout[i]
                    spans=[receipt[j] for j in sorted(indices)]
                    out['selected_utf8_bytes']+=sum(b-a for a,b in spans)
                    out['full_selected_source_bytes']+=len(raw)
                    for B in frame_sizes:
                        chosen=activated_frame_ids(spans,B)
                        cell=out['physical'][str(B)]
                        cell['read_raw_bytes']+=frame_payload_bytes(raw,chosen,B)
                        cell['read_compressed_bytes']+=sum(len(compressed[B][i][j]) for j in chosen)
            label=('both' if complete['top2'] and complete['top2+link'] else
                   'top2_only' if complete['top2'] else 'link_only' if complete['top2+link'] else 'neither')
            paired[str(k)][label]+=1
    return {'status':'real-data calculation only if source hash verified; no SSD/LLM evaluation',
            'data_source':SOURCE_URL,'git_blob_sha':SOURCE_BLOB,'codec':codec_name,
            'frame_metadata_model_bytes_per_frame':16,'archive':archive,
            'summary':result,'paired':paired}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--codec',choices=('zlib','zstd'),default='zstd')
    args=ap.parse_args()
    results=evaluate(load_source(args.data),args.codec)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'archive':results['archive'],'at_k5':results['summary']['5'],'paired':results['paired']['5']},indent=2))

if __name__=='__main__':
    main()
