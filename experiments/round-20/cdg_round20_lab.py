#!/usr/bin/env python3
"""Round 20 local reproducibility laboratory. Synthetic data, not SciFact.

Tests exact normalized-character to UTF-8 raw-byte mapping, ambiguous-span refusal,
noncontiguous reconstruction, frame-union cost, and incomplete-evidence risk.
"""
import hashlib
import json
import random
import statistics
import unicodedata

REPLACE = {'\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': '-'}

def canonical_with_map(raw: bytes):
    """Controlled character-local normalization, intentionally NOT general NFC/NFKC.
    Returns canonical string and one raw byte interval per emitted character.
    Whitespace collapse carries the entire source whitespace-run interval.
    """
    original = raw.decode('utf-8', 'strict')
    chars=[]; ranges=[]; position=0
    for char in original:
        b=char.encode('utf8'); span=(position,position+len(b)); position += len(b)
        if char.isspace():
            if chars and chars[-1]==' ':
                old=ranges[-1]; ranges[-1]=(old[0],span[1])
            else:
                chars.append(' '); ranges.append(span)
        else:
            chars.append(REPLACE.get(char,char)); ranges.append(span)
    return ''.join(chars), ranges

def occurrences(text, term):
    if not term: raise ValueError('empty query')
    matches=[]; i=0
    while True:
        pos=text.find(term,i)
        if pos<0:return matches
        matches.append((pos,pos+len(term))); i=pos+1

def locate_unique(raw, quote):
    text, mapping=canonical_with_map(raw)
    q,_=canonical_with_map(quote.encode('utf8'))
    hits=occurrences(text,q)
    if len(hits)!=1: raise ValueError(f'not uniquely located: {len(hits)} matches')
    a,b=hits[0]
    return (mapping[a][0],mapping[b-1][1]), text[a:b]

def exact_spans(raw, fragments):
    """Unique ordered matching of provided fragments, reject ambiguous combinations."""
    canonical, mapping=canonical_with_map(raw)
    cursor=0; result=[]
    for fragment in fragments:
        query,_=canonical_with_map(fragment.encode('utf8'))
        candidates=[(a,b) for a,b in occurrences(canonical,query) if a>=cursor]
        if len(candidates)!=1: raise ValueError('ambiguous or absent ordered fragment')
        a,b=candidates[0]
        result.append((mapping[a][0], mapping[b-1][1])); cursor=b
    return result

def frames_for(spans, frame_size):
    return {i for a,b in spans for i in range(a//frame_size,(b-1)//frame_size+1)}

def union_cost(spans, frame_size, source_len):
    return sum(min(source_len,(i+1)*frame_size)-i*frame_size for i in frames_for(spans,frame_size))

def evidence_complete(selected, required):
    return all(part in selected for part in required)

def run():
    checks=[]
    # Explicit UTF-8, normalized dash and whitespace: raw byte coordinates differ from characters.
    raw='前言  α\t\tβ — result.\nConclude: Δ increased.'.encode('utf8')
    rng,normalized=locate_unique(raw,'α β - result.')
    assert normalized=='α β - result.' and raw[rng[0]:rng[1]].decode()=='α\t\tβ — result.'
    checks.append({'case':'multibyte Unicode, dash substitution, collapsed whitespace', 'status':'PASS','raw_interval':rng})
    try: locate_unique(b'alpha gamma alpha', 'alpha')
    except ValueError: checks.append({'case':'repeated fragment refused', 'status':'PASS'})
    else: raise AssertionError('ambiguity accepted')
    spans=exact_spans(b'Support A. '+b'irrelevant '*100+b'Support B.', ['Support A.','Support B.'])
    assert len(spans)==2 and spans[1][0]-spans[0][1]>900
    checks.append({'case':'noncontiguous evidence is two exact source intervals','status':'PASS','gap_bytes':spans[1][0]-spans[0][1]})
    try: exact_spans(b'one twice twice then', ['twice','then'])
    except ValueError:checks.append({'case':'ambiguous ordered fragment refused','status':'PASS'})
    else:raise AssertionError('ambiguous disjoint matched')
    raw2=b'abcdefghij'*100
    assert union_cost([(2,8),(4,9)],16,len(raw2))==16
    assert union_cost([(2,8),(24,29)],16,len(raw2))==32
    checks.append({'case':'frame union avoids double charging','status':'PASS'})
    assert not evidence_complete({'a'},{'a','b'}) and evidence_complete({'a','b'},{'a','b'})
    checks.append({'case':'partial witness is not complete','status':'PASS'})
    # Monte Carlo: compare independent top-score choice to full AND-witness completion.
    # A score-only policy chooses the highest-scoring half the pieces and may miss prerequisites.
    rng=random.Random(20261111)
    n=20000; independent=0; witness=0; admissible=0
    for _ in range(n):
        # 4 pieces, two valid pairs. Each piece has iid relevance score; budget = 2 pieces.
        scores=[rng.random() for _ in range(4)]
        top=set(sorted(range(4),key=lambda i:scores[i],reverse=True)[:2])
        independent+=int(top in ({0,1},{2,3}))
        # Witness-aware chooses a pair, by summed available scores, and is complete by construction.
        pair={0,1} if scores[0]+scores[1]>=scores[2]+scores[3] else {2,3}
        witness+=int(pair in ({0,1},{2,3}))
        admissible+=1
    # Exact probability: two complete pairs among 6 possible top-two subsets -> 1/3.
    assert abs(independent/n-1/3)<0.02
    mc={'n':n,'seed':20261111,'independent_top_two_complete':independent,'witness_aware_complete':witness,'denominator':admissible,'note':'Synthetic structural oracle; witness identities known to witness-aware policy. Not predictive of deployable retrieval.'}
    return {'protocol':'round20-synthetic-v1','sha256_script':None,'checks':checks,'synthetic_experiment':mc}

if __name__=='__main__':
    result=run()
    print(json.dumps(result,indent=2,ensure_ascii=False))
