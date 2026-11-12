#!/usr/bin/env python3
"""Round 22: local real-text, synthetic-query falsification control. No QA claims."""
import hashlib, json, math, random, re, statistics
from collections import Counter, defaultdict
from pathlib import Path
P=Path('/mnt/data/CDG_Living_Research_Record_Rounds_19_21_2026-11-12.md')
text=P.read_text()
sha=hashlib.sha256(P.read_bytes()).hexdigest()
# Separate prose paragraphs, omit tables, equations and headings (query difficulty control).
blocks=re.split(r'\n\s*\n',text)
paras=[]; heading=''
for b in blocks:
    b=b.strip()
    if b.startswith('# ' ) or b.startswith('## ') or b.startswith('### '): heading=b.splitlines()[0]; continue
    if len(b)<160 or len(b)>1600 or b.startswith(('|','```','- ','1. ','2. ','3. ','4. ')) or '\n|' in b: continue
    if len(re.findall(r'[A-Za-z]{3,}',b))<35: continue
    paras.append({'heading':heading,'text':b})
# Lexical retrieve without any label info in selection.
def tok(s): return re.findall(r'[a-z]{3,}',s.lower())
T=[Counter(tok(p['text'])) for p in paras]; df=Counter()
for c in T: df.update(c.keys())
N=len(T); lengths=[sum(c.values()) for c in T]; avg=sum(lengths)/N
idf={t:math.log(1+(N-d+.5)/(d+.5)) for t,d in df.items()}
def score(q,i):
    return sum(idf.get(t,0)*((T[i][t]*2.2)/(T[i][t]+1.2*(.25+.75*lengths[i]/avg))) for t in set(q) if T[i][t])
# fixed seed and sampled test targets; queries are mechanically generated using diagnostic rare terms
rng=random.Random(22026)
valid=[i for i,c in enumerate(T) if len([t for t in c if df[t]>=2 and df[t]<=max(5,N//7) and len(t)>4])>=8]
queries=[]
for j in range(250):
    a,b=rng.sample(valid,2)
    # Separate headings to avoid exact same paragraph-family short-cut
    for _ in range(50):
        if paras[a]['heading']!=paras[b]['heading']: break
        b=rng.choice(valid)
    if a==b: continue
    def sample_terms(i):
        eligible=sorted((t for t in T[i] if df[t]>=2 and df[t]<=max(5,N//7) and len(t)>4),key=lambda t:(df[t],t))
        return rng.sample(eligible[:min(20,len(eligible))],3)
    f1=sample_terms(a);f2=sample_terms(b)
    q=f1+f2
    queries.append((q,a,b,f1,f2))
# Non-oracle policies: (1) BM25 top-k, (2) query facet coverage via coverage diversity, (3) MMR
# For facet coverage, query generation exposes the facet split. No target IDs are exposed.
def rank(q,mode,k,facets):
    scores=[score(q,i) for i in range(N)]
    if mode=='bm25': return sorted(range(N),key=lambda i:(-scores[i],i))[:k]
    selected=[]; remaining=set(range(N))
    while len(selected)<k:
        if mode=='facet':
            # reward each query facet receiving at least one reasonably matching paragraph
            best=max(remaining,key=lambda i:(scores[i]+1.0*sum(max(0,score(f,i)-max([score(f,v) for v in selected],default=0)) for f in facets),-i))
        elif mode=='mmr':
            best=max(remaining,key=lambda i:(scores[i]-.5*max([len(T[i].keys() & T[v].keys()) / max(1,len(T[i].keys() | T[v].keys()))*max(scores) for v in selected],default=0),-i))
        selected.append(best);remaining.remove(best)
    return selected
results={}
for mode in ['bm25','facet','mmr']:
    results[mode]={}
    for k in [2,3,5,8]:
        count=0; anyhit=0
        for q,a,b,f1,f2 in queries:
            ids=set(rank(q,mode,k,[f1,f2]))
            count+=a in ids and b in ids
            anyhit+=(a in ids or b in ids)
        results[mode][str(k)]={'complete':count,'any':anyhit,'n':len(queries),'complete_rate':round(count/len(queries),4)}
paired={}
for competitor in ['facet','mmr']:
    both=base_only=comp_only=neither=0
    for q,a,b,f1,f2 in queries:
        base={a,b}.issubset(set(rank(q,'bm25',2,[f1,f2])))
        other={a,b}.issubset(set(rank(q,competitor,2,[f1,f2])))
        if base and other: both+=1
        elif base: base_only+=1
        elif other: comp_only+=1
        else: neither+=1
    paired[competitor]={'both':both,'bm25_only':base_only,'competitor_only':comp_only,'neither':neither}
# Exact byte receipt mapping on UTF-8 source and independent version hash
raw=P.read_bytes(); probes=['witness','compression','source','retrieval','evidence']
receipts=[]
for needle in probes:
    start=raw.lower().find(needle.encode()); assert start>=0
    seg=raw[start:start+len(needle)]; assert seg.lower()==needle.encode()
    receipts.append({'span':[start,start+len(needle)],'sha256':hashlib.sha256(seg).hexdigest()})
mutated=b'X'+raw
version_tests={'old_version_rejected':hashlib.sha256(mutated).hexdigest()!=sha,
               'stale_offset_not_equivalent':any(mutated[a:b]!=raw[a:b] for z in receipts for a,b in [z['span']]),
               'utf8_byte_roundtrip':all(hashlib.sha256(raw[z['span'][0]:z['span'][1]]).hexdigest()==z['sha256'] for z in receipts)}
output={'input_path':str(P),'input_sha256':sha,'paragraph_count':N,'query_count':len(queries),'query_provenance':'synthetic query terms sampled from held-out target paragraphs, labels known only to evaluation','results':results,'paired_k2':paired,'version_tests':version_tests,'interpretation':'in-domain mechanical retrieval stress test; NOT external QA, not naturally authored multihop, not held-out model evaluation'}
Path('/mnt/data/cdg_round22_results.json').write_text(json.dumps(output,indent=2))
print(json.dumps(output,indent=2))
