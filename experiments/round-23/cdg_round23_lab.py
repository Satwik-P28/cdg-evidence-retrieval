#!/usr/bin/env python3
"""Round 23: controlled two-hop evidence-acquisition failure injection.

Synthetic, template-derived corpus. No neural model, external QA benchmark,
semantic entailment classifier, calibrated confidence, or SSD measurement.

Use `python experiments/round-23/cdg_round23_lab.py --output FILE`.
"""
import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

SEED = 23026
CASES_PER_MODE = 120
MODES = ('clean', 'conflicting_anchors', 'stale_version', 'scope_collision', 'missing_second_hop')


def tokens(s):
    return re.findall(r'[a-z0-9]+', s.lower())


def search(query, docs, limit=3):
    """Small independently implemented BM25, deterministic ties by corpus order."""
    words = [Counter(tokens(d['text'])) for d in docs]
    avg = sum(map(lambda c: sum(c.values()), words)) / len(words)
    df = Counter()
    for c in words:
        df.update(c.keys())
    q = set(tokens(query))
    ranked = []
    for i, c in enumerate(words):
        length = sum(c.values())
        score = sum(math.log(1 + (len(docs) - df[t] + .5) / (df[t] + .5)) *
                    (2.2 * c[t] / (c[t] + 1.2 * (.25 + .75 * length / avg)))
                    for t in q if c[t])
        ranked.append((score, i))
    return [i for value, i in sorted(ranked, key=lambda v: (-v[0], v[1])) if value > 0][:limit]


def make_case(seed, mode):
    rng = random.Random(seed)
    subject = 'subject' + str(seed)
    bridge = 'route' + str(seed)
    result = 'result' + str(seed)
    scope = 'scope' + str(seed)
    docs = []
    def put(kind, text, *, sid=None, version=1, scope_id=None):
        docs.append({'kind': kind, 'text': text, 'sid': sid or 'doc' + str(len(docs)),
                     'version': version, 'scope': scope_id or scope})
    first_text = f'Entry {subject} connects to route {bridge}. The linked route contains the recorded outcome.'
    second_text = f'Route {bridge} records outcome {result}.'
    if mode == 'stale_version':
        put('anchor', f'Entry {subject} connects to route oldroute{seed}. The linked route contains the recorded outcome.', sid='anchor', version=1)
        put('anchor', first_text, sid='anchor', version=2)
        put('bridge', f'Route oldroute{seed} records outcome obsolete{seed}.', sid='oldbridge')
    elif mode == 'conflicting_anchors':
        put('anchor', first_text, sid='anchor-A')
        put('anchor', f'Entry {subject} connects to route alternate{seed}. The linked route contains the recorded outcome.', sid='anchor-B')
        put('bridge', f'Route alternate{seed} records outcome conflicting{seed}.', sid='bridge-B')
    else:
        put('anchor', first_text, sid='anchor')
    if mode == 'scope_collision':
        put('bridge', f'Route {bridge} records outcome unrelated{seed}.', sid='foreign-bridge', scope_id='foreign')
    if mode != 'missing_second_hop':
        put('bridge', second_text, sid='bridge', scope_id=scope)
    # Distractors contain similarly structured statements; none has the target subject.
    for j in range(18):
        d = seed * 100 + j
        put('anchor', f'Entry subject{d} connects to route route{d}. The linked route contains the recorded outcome.', sid=f'distractor-a{j}')
        put('bridge', f'Route route{d} records outcome result{d}.', sid=f'distractor-b{j}')
    return {
        'query': f'For entry {subject}, which outcome is listed on the linked route?',
        'docs': docs,
        'subject': subject,
        'bridge': bridge,
        'scope': scope,
        'expected': result if mode in ('clean', 'stale_version', 'scope_collision') else None,
        'scenario': mode,
    }


def parse_subject(text):
    m = re.search(r'Entry ([a-z0-9]+) connects to route', text)
    return m.group(1) if m else None


def parse_route(text):
    m = re.search(r'connects to route ([a-z0-9]+)', text)
    return m.group(1) if m else None


def parse_outcome(text):
    m = re.search(r'records outcome ([a-z0-9]+)', text)
    return m.group(1) if m else None


def source_hash(doc):
    return hashlib.sha256(doc['text'].encode('utf-8')).hexdigest()


def attempt(case, policy):
    docs, q = case['docs'], case['query']
    ranked = search(q, docs, limit=2)
    seen = []
    def inspect(i):
        if i not in seen:
            seen.append(i)
    if policy == 'static':
        for i in ranked: inspect(i)
        anchors = [docs[i] for i in ranked if docs[i]['kind'] == 'anchor' and parse_subject(docs[i]['text']) == case['subject']]
        routes = [parse_route(a['text']) for a in anchors]
        choices = [parse_outcome(docs[i]['text']) for i in ranked if docs[i]['kind'] == 'bridge' and any(re.search(r'^Route ([a-z0-9]+) records outcome', docs[i]['text']).group(1) == r for r in routes)]
        answer = choices[0] if len(choices) == 1 else None
        return answer, seen
    # First hop is a general BM25 query, without accessing gold labels.
    anchors = [i for i in ranked if docs[i]['kind'] == 'anchor' and parse_subject(docs[i]['text']) == case['subject']]
    if not anchors:
        return None, seen
    if policy == 'naive':
        a = anchors[0]
        inspect(a)
        route = parse_route(docs[a]['text'])
        targets = [i for i, d in enumerate(docs) if d['kind'] == 'bridge' and re.search(r'^Route ([a-z0-9]+) records outcome', d['text']).group(1) == route]
        if not targets:
            return None, seen
        inspect(targets[0]); return parse_outcome(docs[targets[0]]['text']), seen
    # Metadata-aware and conflict-sensitive variant. Scanning the index and metadata
    # is not charged as a source read; that makes this a deliberately optimistic cost proxy.
    candidate_anchors = [i for i,d in enumerate(docs) if d['kind']=='anchor' and parse_subject(d['text']) == case['subject']]
    max_version_by_sid = {}
    for i in candidate_anchors:
        d=docs[i]; max_version_by_sid[d['sid']]=max(d['version'],max_version_by_sid.get(d['sid'],0))
    current = [i for i in candidate_anchors if docs[i]['version']==max_version_by_sid[docs[i]['sid']]]
    unique_routes = set(parse_route(docs[i]['text']) for i in current)
    if len(unique_routes)!=1:
        for i in current: inspect(i)
        return None, seen
    a = current[0]; inspect(a)
    route = next(iter(unique_routes))
    candidates=[i for i,d in enumerate(docs) if d['kind']=='bridge' and re.search(r'^Route ([a-z0-9]+) records outcome', d['text']).group(1) == route and d['scope']==docs[a]['scope']]
    if len(candidates)!=1:
        for i in candidates: inspect(i)
        return None, seen
    b=candidates[0]; inspect(b)
    return parse_outcome(docs[b]['text']), seen


def receipt_checks():
    original = 'αβ source: evidence 🚀'.encode('utf-8')
    target='evidence'.encode('utf-8'); start=original.index(target)
    receipt=(hashlib.sha256(original).hexdigest(), start, start+len(target))
    shifted = b'x' + original
    return {'utf8_span_roundtrip': original[receipt[1]:receipt[2]] == target,
            'source_version_changed': hashlib.sha256(shifted).hexdigest()!=receipt[0],
            'old_offset_invalid_after_shift': shifted[receipt[1]:receipt[2]]!=target}


def run():
    results={}; examples=[]
    for mode_index,mode in enumerate(MODES):
        cases=[make_case(SEED+mode_index*10000+i,mode) for i in range(CASES_PER_MODE)]
        results[mode]={}
        for policy in ('static','naive','guarded'):
            correct=invalid=abstained=reads=bytes_read=0
            for i,case in enumerate(cases):
                answer,seen=attempt(case,policy)
                expected=case['expected']
                correct+=answer==expected
                invalid+=answer is not None and answer!=expected
                abstained+=answer is None
                reads+=len(seen)
                bytes_read+=sum(len(case['docs'][j]['text'].encode('utf-8')) for j in seen)
                if i==0:
                    examples.append({'scenario':mode,'policy':policy,'predicted':answer,'expected':expected,'read_count':len(seen)})
            results[mode][policy]={
                'correct_cases':correct,'invalid_answers':invalid,'abstentions':abstained,
                'total_cases':len(cases),'mean_source_materializations':round(reads/len(cases),4),
                'mean_materialized_source_bytes':round(bytes_read/len(cases),2)}
    return {'date':'2026-11-12','seed':SEED,'cases_per_mode':CASES_PER_MODE,
            'dataset':'programmatically generated two-hop fixtures; no external natural-language dataset',
            'methods':['static BM25 top-2','naive exact bridge lookup','version/scope/conflict guarded bridge lookup'],
            'cost_exclusions':['index build and scan','metadata lookup','CPU time','compression','cache','network','neural model'],
            'results':results,'receipt_checks':receipt_checks(),'first_case_examples':examples,
            'limitations':'Templates expose exact bridge identifiers; guarded method assumes trustworthy source IDs, version metadata and scope. Not a realistic or fair comparison with trained SOTA systems.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='experiments/round-23/results.json')
    args=parser.parse_args()
    data=run(); dest=Path(args.output); dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:{p:v['correct_cases'] for p,v in x.items()} for k,x in data['results'].items()},indent=2))
