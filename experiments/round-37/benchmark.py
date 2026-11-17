#!/usr/bin/env python3
"""Round 37: deterministic synthetic temporal multi-hop retrieval stress test.

All evidence labels originate in a fixture builder and are used ONLY after policies
have made their choices. The policies see question text, candidate text, version,
links and an intentionally imperfect verifier. No natural-language entailment.
"""
import argparse, hashlib, json, math, random, statistics, time
from collections import Counter

SEED = 20261116

def toks(s):
    import re
    return set(re.findall(r'[a-z0-9]+',s.lower()))

def make_case(n, rng, shift=False, misleading=False):
    x=f'locator{n}'; y=f'destination{n}'; alias=f'archive{n}'
    prior=rng.randrange(10000,99999); current=rng.randrange(10000,99999)
    while current==prior:current=rng.randrange(10000,99999)
    # The true graph has one bridge, and the current answer is in the current target.
    docs=[
      {'id':'start','version':2,'text':f'{x} routes through {y}. Reference guide for {x}.', 'links':[y], 'title':x,'valid':True,'span':2},
      {'id':'target-new','version':2,'text':f'{y} reference code {current}. {y} current update.', 'links':[], 'title':y,'valid':True,'span':3},
      {'id':'target-old','version':1,'text':f'{y} reference code {prior}. {y} detailed reference history.', 'links':[], 'title':y,'valid':False,'span':3},
      {'id':'decoy','version':2,'text':f'{x} reference guide {alias}. Code for {alias} historical.', 'links':[], 'title':alias,'valid':True,'span':4},
      {'id':'noise','version':2,'text':f'unrelated register {rng.randrange(1000)} general revision.', 'links':[], 'title':f'noise{n}','valid':True,'span':2}
    ]
    if shift:
        # Stronger obsolete candidate and misplaced new title. Targets intentionally harder.
        docs[2]['text'] += f' {x} {y} latest current reference code update ' * 2
        docs[1]['text'] = f'{y} reference code {current}. obsolete record warning applies to archived snapshots.'
    if misleading:
        # Revision ordering is inconsistent with semantic validity: metadata is insufficient.
        docs[2]['version']=3
    rng.shuffle(docs)
    return {'query':f'What is the current reference code reached through {x}?',
            'docs':docs,'gold':{'start','target-new'},'current_code':current,'old_code':prior,'case_id':n}

def rank(query, docs):
    q=toks(query)
    scored=[]
    for d in docs:
        terms=toks(d['text'])
        overlap=len(q & terms)
        # lexical repeated tokens plus overlap; old can outrank current in shifted set
        frequency=sum(d['text'].lower().split().count(k) for k in q)
        scored.append((-(overlap+.25*frequency),d['id'],d))
    return [d for _,__,d in sorted(scored)]

def select(case,policy,budget=3):
    docs=case['docs']; ordered=rank(case['query'],docs)
    acquired=[]; cost=0; verification_calls=0
    def add(d):
        nonlocal cost
        if d['id'] in {x['id'] for x in acquired} or len(acquired)>=budget:return False
        acquired.append(d);cost+=d['span'];return True
    # A deliberately limited deterministic query parser, not a gold evidence label.
    # All policies can access the same public title, version and link metadata.
    import re
    m=re.search(r'through (locator[0-9]+)',case['query'].lower())
    lookup_title=m.group(1) if m else ''
    if policy=='fixed':
        for d in ordered:add(d)
    elif policy in ('title_version','adaptive'):
        head=next((d for d in docs if d['title']==lookup_title),None)
        if head:
            add(head)
            for title in head['links']:
                versions=[d for d in docs if d['title']==title]
                if versions:add(max(versions,key=lambda d:d['version']))
        if policy=='adaptive':
            # A deterministic structural check, not a semantic verifier; it
            # cannot increase coverage versus title_version on this fixture.
            verification_calls+=1
        for d in ordered:add(d)
    else:
        add(ordered[0]);initial=acquired[0]
        if initial['links']:
            target_docs=[d for d in docs if d['title'] in initial['links']]
            if target_docs:
                if policy=='iterative':
                    nxt=max(target_docs,key=lambda d:(len(toks(d['text'])&toks(case['query'])),len(d['text'])))
                else:
                    nxt=max(target_docs,key=lambda d:d['version'])
                add(nxt)
        for d in ordered:add(d)
    ids={d['id'] for d in acquired}
    complete=case['gold']<=ids
    stale=('target-old' in ids) and ('target-new' not in ids)
    # Acceptance without ground truth: require both a start and some target,
    # and for versioned policies check that acquired target is newest.
    head_selected=next((d for d in acquired if d['title']==lookup_title),None)
    targets=[d for d in acquired if head_selected and d['title'] in head_selected['links']]
    if policy in ('title_version','adaptive'):
        latest=max((d['version'] for d in docs if head_selected and d['title'] in head_selected['links']), default=-1)
        accepted=bool(targets and any(d['version']==latest for d in targets))
    else:
        accepted=bool(targets)
    return {'selected':[d['id'] for d in acquired], 'complete':complete,
            'stale_citation':stale,'accepted':accepted,'false_accept':accepted and not complete,
            'read_cost':cost,'verification_cost':verification_calls*4,'total_cost':cost+verification_calls*4,
            'source_hashes':{d['id']:hashlib.sha256(d['text'].encode()).hexdigest() for d in acquired}}

def run(n=300,seed=SEED,budget=3):
    rng=random.Random(seed);out={'seed':seed,'n_per_split':n,'budget':budget,'splits':{},'software':'Python standard library only','scope':'fully synthetic versioned graph fixtures, oracle fixture labels for scoring only; no real entailment, no storage I/O, deterministic title parsing; newest revision may be semantically invalid'}
    for mode,shift,misleading in [('standard',False,False),('shifted',True,False),('misleading_versions',True,True)]:
        cases=[make_case(i,rng,shift,misleading) for i in range(n)]
        out['splits'][mode]={}
        for policy in ('fixed','iterative','version_filtered','title_version','adaptive'):
            rr=[select(c,policy,budget) for c in cases]
            out['splits'][mode][policy]={
              'complete':sum(x['complete'] for x in rr),
              'false_accept':sum(x['false_accept'] for x in rr),
              'accepted':sum(x['accepted'] for x in rr),
              'stale_citation':sum(x['stale_citation'] for x in rr),
              'mean_total_cost':round(statistics.mean(x['total_cost'] for x in rr),3),
              'mean_read_cost':round(statistics.mean(x['read_cost'] for x in rr),3),
              'records':rr[:1]
            }
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--n',type=int,default=300);opt=ap.parse_args()
    t=time.perf_counter();res=run(opt.n);res['wall_seconds']=round(time.perf_counter()-t,3)
    with open(opt.output,'w') as f:json.dump(res,f,indent=2);f.write('\n')
    for split,methods in res['splits'].items():
        print(split,[(p,v['complete'],v['false_accept'],v['mean_total_cost']) for p,v in methods.items()])
if __name__=='__main__':main()
