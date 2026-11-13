#!/usr/bin/env python3
"""Round 25: per-query HotpotQA full-context document and sentence retrieval probe.

No gold labels are passed to the selection policies. The provided HotpotQA
candidate contexts DO contain gold documents, so this is a closed-world
retrieval diagnostic, not open-corpus QA or a physical storage benchmark.

Requires Python 3.10+, standard library only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.request import urlopen

REVISION = 'fdab15b3929d2ee40dfcdd388f90233096a6afc9'
BLOB_SHA = '7dbdf068a437f0577043667ffee3a20f0a602154'
RELATIVE = 'kag/open_benchmark/hotpotqa/data/qa_train.json'
URL = f'https://raw.githubusercontent.com/OpenSPG/KAG/{REVISION}/{RELATIVE}'
K_VALUES = (2, 3, 5)
METHODS = ('bm25', 'bridge', 'mmr')


def words(text: str) -> list[str]:
    return re.findall(r'[^\W_]+', text.lower(), flags=re.UNICODE)


def canon(text: str) -> str:
    return ' '.join(words(text))


def git_blob_sha(blob: bytes) -> str:
    return hashlib.sha1(f'blob {len(blob)}\0'.encode('ascii') + blob).hexdigest()


def get_data(path: Path, download: bool = False) -> list[dict]:
    if download:
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(URL, timeout=90) as response:
            blob = response.read()
        if git_blob_sha(blob) != BLOB_SHA:
            raise ValueError('Git blob SHA mismatch from upstream download')
        path.write_bytes(blob)
    else:
        blob = path.read_bytes()
    if git_blob_sha(blob) != BLOB_SHA:
        raise ValueError('Git blob SHA mismatch: refuse unverified benchmark data')
    data = json.loads(blob)
    validate(data)
    return data


def validate(data: list[dict]) -> None:
    for ex in data:
        if not ex.get('question') or not ex.get('context') or not ex.get('supporting_facts'):
            raise ValueError('missing benchmark field')
        ctx = {title: sents for title, sents in ex['context']}
        for title, sid in ex['supporting_facts']:
            if title not in ctx or sid < 0 or sid >= len(ctx[title]):
                raise ValueError('gold sentence is missing from the candidate pool')


def bm25_scores(query: str, documents: list[str]) -> list[float]:
    # Per-question candidate-set BM25, not global IDF.
    terms = [words(doc) for doc in documents]
    avg = sum(map(len, terms)) / len(terms)
    df = Counter(word for ts in terms for word in set(ts))
    scores = []
    for ts in terms:
        freqs = Counter(ts)
        score = 0.0
        for word in set(words(query)):
            f = freqs[word]
            if f:
                idf = math.log(1.0 + (len(terms) - df[word] + .5)/(df[word] + .5))
                score += idf * 2.2 * f / (f + 1.2 * (.25 + .75 * len(ts)/avg))
        scores.append(score)
    return scores


def jaccard(x: set[str], y: set[str]) -> float:
    return len(x & y) / (len(x | y) or 1)


def rank(row: dict, method: str, limit: int = 5) -> list[int]:
    """Return source IDs. The bridge policy uses only selected source text.

    It assumes a prebuilt per-question BM25 index and a title dictionary.
    Its additional exact-title mention lookup is a conventional, precomputed
    string-index operation, not new semantic inference.
    """
    ctx = row['context']
    texts = [title + ' ' + ' '.join(sents) for title, sents in ctx]
    scores = bm25_scores(row['question'], texts)
    bodies = [' ' + canon(' '.join(sents)) + ' ' for _, sents in ctx]
    titles = [' ' + canon(title) + ' ' for title, _ in ctx]
    bags = [set(words(text)) for text in texts]
    max_score = max(1e-6, *scores)
    selected: list[int] = []
    while len(selected) < min(limit, len(ctx)):
        best = -1
        best_score = -math.inf
        for i in range(len(ctx)):
            if i in selected:
                continue
            value = scores[i]
            if method == 'bridge' and selected:
                # Pad with whitespace to avoid substring prefix collisions.
                if len(titles[i]) > 4 and any(titles[i] in bodies[j] for j in selected):
                    value += 2.0
            elif method == 'mmr' and selected:
                redundancy = max(jaccard(bags[i], bags[j]) for j in selected)
                value = .75 * value / max_score - .25 * redundancy
            elif method not in METHODS:
                raise ValueError(f'unknown method {method}')
            if value > best_score + 1e-10 or (abs(value-best_score) < 1e-10 and (best < 0 or ctx[i][0] < ctx[best][0])):
                best, best_score = i, value
        selected.append(best)
    return selected


def evaluate(data: list[dict]) -> dict:
    counts = {method: {str(k): {typ: {'n': 0, 'any': 0, 'complete_docs': 0, 'complete_sentences_top1': 0, 'complete_sentences_top2': 0, 'complete_sentences_top3': 0, 'selected_chars': 0} for typ in ('all', 'bridge', 'comparison')} for k in K_VALUES} for method in METHODS}
    paired = {str(k): {'both': 0, 'bm25_only': 0, 'bridge_only': 0, 'neither': 0} for k in K_VALUES}
    rows = []
    for ex in data:
        chosen = {method: rank(ex, method) for method in METHODS}
        titles = set(title for title, _ in ex['supporting_facts'])
        result = {'id': ex.get('_id'), 'type': ex['type'], 'question': ex['question'], 'methods': {}}
        for method in METHODS:
            result['methods'][method] = {}
            for k in K_VALUES:
                indices = chosen[method][:k]
                docs = {ex['context'][i][0] for i in indices}
                complete = titles <= docs
                retrieved_sentences = {t: set() for t in (1, 2, 3)}
                for i in indices:
                    title, sents = ex['context'][i]
                    sentence_scores = bm25_scores(ex['question'], sents)
                    ordering = sorted(range(len(sents)), key=lambda sid: (-sentence_scores[sid], sid))
                    for t in (1, 2, 3):
                        retrieved_sentences[t].update((title, sid) for sid in ordering[:t])
                allfacts = [all((title, sid) in retrieved_sentences[t] for title, sid in ex['supporting_facts']) for t in (1, 2, 3)]
                chars = sum(len(ex['context'][i][0] + ' ' + ' '.join(ex['context'][i][1])) for i in indices)
                result['methods'][method][str(k)] = {'titles': [ex['context'][i][0] for i in indices], 'complete_docs': complete, 'complete_sentences': allfacts, 'selected_chars': chars}
                for typ in ('all', ex['type']):
                    out = counts[method][str(k)][typ]
                    out['n'] += 1
                    out['any'] += int(bool(titles & docs))
                    out['complete_docs'] += int(complete)
                    out['selected_chars'] += chars
                    for t in (1, 2, 3):
                        out[f'complete_sentences_top{t}'] += int(allfacts[t-1])
        for k in K_VALUES:
            b = result['methods']['bm25'][str(k)]['complete_docs']
            g = result['methods']['bridge'][str(k)]['complete_docs']
            paired[str(k)]['both' if b and g else 'bm25_only' if b else 'bridge_only' if g else 'neither'] += 1
        rows.append(result)
    for byk in counts.values():
        for typstats in byk.values():
            for out in typstats.values():
                out['mean_selected_chars'] = round(out.pop('selected_chars') / out['n'], 2) if out['n'] else 0
    return {'status': 'real-text closed-world exploratory retrieval proxy, NOT answer QA or SSD benchmark', 'source': {'url': URL, 'revision': REVISION, 'git_blob_sha': BLOB_SHA}, 'questions': len(data), 'methods': counts, 'paired': paired, 'per_question': rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    result = evaluate(get_data(args.data, download=args.download))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'questions': result['questions'], 'paired': result['paired'], 'k2': {method: result['methods'][method]['2']['all'] for method in METHODS}}, indent=2))

if __name__ == '__main__':
    main()