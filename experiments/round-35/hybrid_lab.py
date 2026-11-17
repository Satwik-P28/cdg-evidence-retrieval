#!/usr/bin/env python3
"""Deterministic classical/quantum-inspired CDG pilot: shared-frame cover and exact period coding.
All labels and costs are synthetic; no quantum hardware or natural-language QA.
"""
import argparse, bz2, itertools, json, math, random, statistics, time, zlib
from collections import Counter
from pathlib import Path

N=12; FACETS=7

def cost(mask, inst):
    frame_mask=0; cover=0; txt=0
    for i,(facets,frames,tokens) in enumerate(inst['spans']):
        if mask>>i&1:
            cover|=facets;frame_mask|=frames;txt+=tokens
    c=txt
    for f,price in enumerate(inst['frame_prices']):
        if frame_mask>>f&1:c+=price
    return c,cover

def instance(seed):
    rng=random.Random(seed);F=8
    prices=[rng.randint(2,14) for _ in range(F)]
    spans=[]
    # Include all facets without making the optimum trivial.
    for i in range(N):
        k=rng.randint(1,3); fs=0
        for j in rng.sample(range(F),rng.randint(1,2)):fs|=1<<j
        es=0
        for j in rng.sample(range(FACETS),k):es|=1<<j
        spans.append((es,fs,rng.randint(1,7)))
    for j in range(FACETS):
        if not any(s[0]>>j&1 for s in spans):
            a=rng.randrange(N);p=spans[a];spans[a]=(p[0]|(1<<j),p[1],p[2])
    return dict(spans=spans,frame_prices=prices)

def exact(inst):
    target=(1<<FACETS)-1;best=float('inf');arg=0
    for mask in range(1,1<<N):
        c,cov=cost(mask,inst)
        if cov==target and (c<best or c==best and mask<arg):best,arg=c,mask
    return arg,best

def greedy(inst):
    target=(1<<FACETS)-1;mask=0;cover=0
    while cover!=target:
        base=cost(mask,inst)[0];cands=[]
        for i in range(N):
            if mask>>i&1:continue
            cm,co=cost(mask|1<<i,inst);gain=((co & ~cover)).bit_count()
            if gain:cands.append(((cm-base)/gain,cm,i))
        if not cands:raise RuntimeError('uncovered')
        _,_,i=min(cands);mask|=1<<i;cover=cost(mask,inst)[1]
    return mask

def prune(mask,inst):
    target=(1<<FACETS)-1
    again=True
    while again:
        again=False
        for i in range(N):
            if mask>>i&1 and cost(mask^(1<<i),inst)[1]==target:
                mask^=1<<i;again=True
    return mask

def local(mask,inst):
    target=(1<<FACETS)-1;mask=prune(mask,inst);best=cost(mask,inst)[0]
    while True:
        cand=(best,mask)
        # Replace at most two selected candidates with at most two unselected candidates.
        on=[i for i in range(N) if mask>>i&1];off=[i for i in range(N) if not mask>>i&1]
        for a in itertools.chain(((),),((i,) for i in on),itertools.combinations(on,2)):
            removed=mask
            for i in a:removed&=~(1<<i)
            for b in itertools.chain(((),),((i,) for i in off),itertools.combinations(off,2)):
                nxt=removed
                for i in b:nxt|=1<<i
                c,cover=cost(nxt,inst)
                if cover==target and c<cand[0]:cand=(c,nxt)
        if cand[0]>=best:return mask
        mask=prune(cand[1],inst);best=cost(mask,inst)[0]

def anneal(inst,seed,steps=1000):
    # Fully classical stochastic approximation of Ising/QUBO-like energy search.
    rng=random.Random(seed);target=(1<<FACETS)-1;penalty=sum(inst['frame_prices'])+sum(s[2] for s in inst['spans'])+1
    def energy(mask):
        c,cover=cost(mask,inst);return c+penalty*(target&~cover).bit_count()
    mask=greedy(inst);best=mask;E=energy(mask);bestE=E
    for t in range(steps):
        # Mostly single-spin flips; occasional non-local two-spin changes.
        jump=rng.sample(range(N),2) if rng.random()<.25 else [rng.randrange(N)]
        cand=mask
        for i in jump:cand^=1<<i
        ce=energy(cand);temp=.2+18*(1-t/steps)**2
        if ce<=E or rng.random()<math.exp((E-ce)/temp):mask,E=cand,ce
        if E<bestE:best,bestE=mask,E
    return best

def optimize(n=100,steps=1000):
    records=[];elapsed=Counter()
    for seed in range(n):
        inst=instance(seed); start=time.perf_counter_ns();_,opt=exact(inst);elapsed['exact']+=(time.perf_counter_ns()-start)
        out={}
        for name,fn in [('greedy',lambda:greedy(inst)),('local',lambda:local(greedy(inst),inst)),('anneal',lambda:anneal(inst,seed+20000,steps)),('anneal_local',lambda:local(anneal(inst,seed+20000,steps),inst))]:
            st=time.perf_counter_ns();mask=fn();elapsed[name]+=time.perf_counter_ns()-st
            price,covered=cost(mask,inst)
            if covered!=(1<<FACETS)-1:raise AssertionError('Incomplete witness')
            if price<opt:raise AssertionError('Below exact optimum')
            out[name]=price
        records.append({'seed':seed,'opt':opt,**out})
    summary={}
    for key in ['greedy','local','anneal','anneal_local']:
        ratios=[r[key]/r['opt'] for r in records]
        summary[key]={'mean_ratio':round(statistics.mean(ratios),5),'max_ratio':round(max(ratios),5),'exact_matches':sum(r[key]==r['opt'] for r in records),'mean_runtime_ms':round(elapsed[key]/1e6/n,3)}
    summary['exact']={'exact_matches':n,'mean_runtime_ms':round(elapsed['exact']/1e6/n,3)}
    return summary,records

def period_encode(data):
    # Unambiguous exact period representation, total bytes include header+period.
    n=len(data)
    if not n:return b'P'+(0).to_bytes(4,'big')+(0).to_bytes(4,'big')
    for p in range(1,n+1):
        if n%p==0 and data==data[:p]*(n//p):
            return b'P'+n.to_bytes(4,'big')+p.to_bytes(4,'big')+data[:p]
    raise AssertionError

def period_decode(code):
    if code[:1]!=b'P' or len(code)<9:raise ValueError
    n=int.from_bytes(code[1:5],'big');p=int.from_bytes(code[5:9],'big')
    if (n,p)==(0,0) and len(code)==9:return b''
    if p==0 or n%p or len(code)!=9+p:raise ValueError
    return code[9:]*(n//p)

def symmetry():
    rng=random.Random(911);out={}
    cases={
        'periodic':bytes([i%16 for i in range(8192)]),
        'periodic_with_mutations':bytearray([i%16 for i in range(8192)]),
        'random':bytes(rng.randrange(256) for _ in range(8192)),
        'textual_repetition':(b'Claim A depends on fact B. Source version verified.\n'*150)[:8192]
    }
    for i in rng.sample(range(8192),16):cases['periodic_with_mutations'][i]^=1
    for name,blob in cases.items():
        blob=bytes(blob);p=period_encode(blob)
        if period_decode(p)!=blob:raise AssertionError('nonlossless')
        out[name]={'raw':len(blob),'period':len(p),'zlib9':len(zlib.compress(blob,9)),'bz2':len(bz2.compress(blob)),'raw_fallback':len(blob)+1,'best_bytes':min(len(blob)+1,len(p),len(zlib.compress(blob,9)),len(bz2.compress(blob))),'best_method':min([('raw_fallback',len(blob)+1),('period',len(p)),('zlib9',len(zlib.compress(blob,9))),('bz2',len(bz2.compress(blob)))],key=lambda x:x[1])[0]}
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--instances',type=int,default=100);ap.add_argument('--steps',type=int,default=1000)
    x=ap.parse_args();st=time.perf_counter_ns();summary,records=optimize(x.instances,x.steps)
    result={'experiment':'round35: classical hybrid optimizer + symmetry encoder','simulated':True,'quantum_hardware':False,'instances':x.instances,'candidates':N,'facets':FACETS,'anneal_steps':x.steps,'optimization':summary,'symmetry':symmetry(),'elapsed_seconds':round((time.perf_counter_ns()-st)/1e9,3),'limitations':['Synthetic predicted-perfect evidence labels','Small N permits exponential exact search','Ising-inspired annealing is classical, not quantum','No direct RAG answer, compressed SSD, or held-out workload','Period encoder O(n^2) naive equality comparisons, unsuitable for general data']}
    x.output.parent.mkdir(parents=True,exist_ok=True);x.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='limitations'},indent=2))
if __name__=='__main__':main()
