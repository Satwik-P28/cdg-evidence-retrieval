#!/usr/bin/env python3
"""Round 10: held-out stronger changed-evidence retrieval and physical-cost-aware selection.
Real noVNC commit histories, human commit titles; multi-query targets synthetically paired.
Non-neural, non-QA proxy. Train/test splits and indexes independent of target-label selection.
"""
import contextlib,io,json,collections,statistics,time,random,itertools,hashlib
from pathlib import Path
import numpy as np
with contextlib.redirect_stdout(io.StringIO()):
    import round9_multi_intent as m
r=m.r; HERE=Path(__file__).resolve().parent
N=r.N
# BM25 indexed over the *changed regions*, unlike prior Round9 full-document-only BM25.
changes=[s['changed'].encode() for s in r.SAMPLES]
counts=[collections.Counter(r.toks_bytes(x)) for x in changes]
length=np.array([sum(c.values()) for c in counts],dtype=np.float64)
avg=max(float(length.mean()),1.0)
df=collections.Counter(term for c in counts for term in c)
idf={t:float(np.log1p((N-v+.5)/(v+.5))) for t,v in df.items()}
k1=1.2;b=.75
norm=k1*(1-b+b*length/avg)

def change_score(q):
    terms=set(r.toks_query(q))
    out=np.zeros(N,dtype=np.float64)
    for t in terms:
        if t not in idf:continue
        tf=np.array([c.get(t,0) for c in counts],dtype=np.float64)
        out+=idf[t]*(k1+1)*tf/(tf+norm)
    return out

# Require both correct revisions, and count marginal compressed *passage* payload.
# Each candidate has a five-line query-matched snippet as in Round 9.

def make_task(pair,pcost):
    i,j=pair
    q1,q2=r.QUERIES[i],r.QUERIES[j]
    f1,f2=m.score(q1),m.score(q2)
    d1,d2=change_score(q1),change_score(q2)
    def renorm(s):return s/max(1e-9,float(s.max()))
    s1=.65*renorm(d1)+.35*renorm(f1)
    s2=.65*renorm(d2)+.35*renorm(f2)
    sf=renorm(f1+f2)
    sc=renorm(d1+d2)
    combined=.65*sc+.35*sf
    o1=np.argsort(-s1,kind='stable');o2=np.argsort(-s2,kind='stable');oc=np.argsort(-combined,kind='stable')
    qterms=(set(r.toks_query(q1)),set(r.toks_query(q2)))
    overlaps=[{d:(set(counts[d])&ts) for d in range(N)} for ts in qterms]
    totals=[sum(idf.get(w,0.0) for w in ts) or 1.0 for ts in qterms]
    return {'targets':(i,j),'s1':s1,'s2':s2,'combined':combined,'o1':o1,'o2':o2,'oc':oc,'pc':pcost,'q_terms':qterms,'overlaps':overlaps,'totals':totals}

# Same query-selected physical five-line source passage cost as Round 9, now
# implemented locally to avoid a side-effecting dependency on prior artifacts.
DOC_LINES=[d.splitlines(keepends=True) for d in r.DOCS]
TOK_LINES=[[set(r.toks_bytes(line)) for line in ls] for ls in DOC_LINES]
SPANS=[]
for di,ls in enumerate(DOC_LINES):
    ends=r.boundaries(ls)
    SPANS.append(list(zip([0]+ends[:-1],ends,r.doc_maps[di])))

def cost_prepare(task):
    o1,o2,_,_=task['o']
    docs=list(dict.fromkeys([*map(int,o1[:20]),*map(int,o2[:20])]))
    q=task['qt'];out={}
    for di in docs:
        lines=TOK_LINES[di]
        if not lines:out[di]=set();continue
        best=max(range(len(lines)),key=lambda j:(len(lines[j]&q),-j))
        a=max(0,min(max(0,len(lines)-5),best-2));b=min(a+5,len(lines))
        out[di]={cid for lo,hi,cid in SPANS[di] if lo<b and hi>a}
    return out

def selection(t,method,k=10,lam=0.,gamma=0.):
    o1,o2,oc=t['o1'],t['o2'],t['oc']
    if method=='combined':return list(map(int,oc[:k]))
    if method=='round_robin':
        ans=[];seen=set()
        for a,b in zip(o1,o2):
            for v in (int(a),int(b)):
                if v not in seen:ans.append(v);seen.add(v)
                if len(ans)>=k:return ans
        return ans
    if method not in ('cost','coverage','diversity'):raise ValueError(method)
    pools=[list(map(int,o1[:max(25,k*3)])),list(map(int,o2[:max(25,k*3)]))]
    scores=[t['s1'],t['s2']]
    selected=[];used=set();seen_chunks=set();covered=[set(),set()];used_paths=set()
    for step in range(k):
        branch=step%2
        options=[d for d in pools[branch] if d not in used]
        if not options:options=[d for d in pools[1-branch] if d not in used]
        if not options:break
        def utility(d):
            extra=sum(m.corpus_lengths[c] for c in t['pc'].get(d,set())-seen_chunks)/1024
            novel=sum(idf.get(w,0.0) for w in (t['overlaps'][branch][d]-covered[branch]))
            bonus=novel/t['totals'][branch]
            penalty_path=1.0 if r.PATHS[d] in used_paths else 0.0
            value=float(scores[branch][d])-lam*extra
            if method=='coverage':value+=gamma*bonus
            if method=='diversity':value-=gamma*penalty_path
            return (value,-d)
        pick=max(options,key=utility)
        selected.append(pick);used.add(pick);used_paths.add(r.PATHS[pick]);seen_chunks.update(t['pc'].get(pick,set()))
        covered[branch].update(t['overlaps'][branch][pick])
    return selected

pairs_train=m.train[:];pairs_test=m.test[:]
print('build passage maps...',flush=True)
tr_pc=[cost_prepare(task) for task in m.train_tasks]
te_pc=[cost_prepare(task) for task in m.test_tasks]
train=[make_task(pair,pc) for pair,pc in zip(pairs_train,tr_pc)]
test=[make_task(pair,pc) for pair,pc in zip(pairs_test,te_pc)]
assert len(train)==50 and len(test)==75
print('evaluate...',flush=True)

def evaluate(tasks,method,lam=0.,gamma=0.):
    n=len(tasks);hits=[];half=[];payload=[];sources=[];query_overlap=[]
    for t in tasks:
        chosen=selection(t,method,10,lam,gamma)
        h=len(set(t['targets'])&set(chosen))
        hits.append(int(h==2));half.append(h/2)
        chunks=set().union(*(t['pc'].get(d,set()) for d in chosen))
        payload.append(sum(m.corpus_lengths[c] for c in chunks))
        sources.append(len({r.PATHS[d] for d in chosen}))
    return {'complete_at10':round(statistics.mean(hits),4),
            'partial_at10':round(statistics.mean(half),4),
            'mean_compressed_passage_bytes':round(statistics.mean(payload),1),
            'mean_distinct_paths':round(statistics.mean(sources),2),
            'successes':int(sum(hits))}

controls={s:evaluate(test,s) for s in ('combined','round_robin')}
# Train-only parameter selection. Prioritize completeness then cost, do not use held-out.
grid=[(0.,0.),(.05,0.),(.2,0.),(.4,0.),(.05,.1),(.2,.1),(.4,.1),(.05,.3),(.2,.3),(.4,.3)]
train_sweep={}
for method in ('cost','coverage','diversity'):
    train_sweep[method]=[]
    for lam,gamma in grid:
        if method=='cost' and gamma:continue
        if method=='cost' and lam==0:continue
        if method in ('coverage','diversity') and gamma==0:continue
        res=evaluate(train,method,lam,gamma)
        train_sweep[method].append((lam,gamma,res))
selected={}
for method,vals in train_sweep.items():
    # avoid overfitting to cost: primary full recall, then partial, then lower cost
    lam,gamma,train_result=max(vals,key=lambda z:(z[2]['complete_at10'],z[2]['partial_at10'],-z[2]['mean_compressed_passage_bytes']))
    selected[method]={'lambda':lam,'gamma':gamma,'train':train_result,'test':evaluate(test,method,lam,gamma)}

# A stronger model-free query decomposition benchmark: changed-region BM25 alone.
def changes_only(t,balanced=True,k=10):
    i,j=t['targets'];a=change_score(r.QUERIES[i]);b=change_score(r.QUERIES[j]);
    if not balanced:return list(map(int,np.argsort(-(a/max(float(a.max()),1e-9)+b/max(float(b.max()),1e-9)),kind='stable')[:k]))
    x=np.argsort(-a,kind='stable');y=np.argsort(-b,kind='stable');ans=[]
    for xx,yy in zip(x,y):
        for u in (int(xx),int(yy)):
            if u not in ans:ans.append(u)
            if len(ans)>=k:return ans
    return ans

def eval_selection(tasks,selector):
    hits=[];partial=[];cost=[]
    for t in tasks:
        chosen=selector(t);h=len(set(chosen)&set(t['targets']));hits.append(int(h==2));partial.append(h/2)
        chunks=set().union(*(t['pc'].get(d,set()) for d in chosen))
        cost.append(sum(m.corpus_lengths[c] for c in chunks))
    return {'complete_at10':round(statistics.mean(hits),4),'partial_at10':round(statistics.mean(partial),4),'mean_compressed_passage_bytes':round(statistics.mean(cost),1),'successes':sum(hits)}
controls['change_combined']=eval_selection(test,lambda t:changes_only(t,False))
controls['change_round_robin']=eval_selection(test,lambda t:changes_only(t,True))
controls['old_round9_passage_cost']={'complete_at10':0.1333,'mean_compressed_passage_bytes':2974,'source':'Reported prior experiment, not rerun here'}

# Robustness: counts from boots on held-out tasks, paired to strong change round robin.
base=[int(set(t['targets']).issubset(changes_only(t,True))) for t in test]
boot=random.Random(10101)
boot_ci={}
for label,fun in [('hybrid_round_robin',lambda t:selection(t,'round_robin'))]+[(key,lambda t,meth=key,cfg=cfg:selection(t,meth,10,cfg['lambda'],cfg['gamma'])) for key,cfg in selected.items()]:
    vals=[int(set(t['targets']).issubset(fun(t))) for t in test]
    d=[a-b for a,b in zip(vals,base)];samples=sorted(sum(d[boot.randrange(len(d))] for _ in d)/len(d) for z in range(1500))
    boot_ci[label]={'difference_vs_changed_round_robin':round(float(np.mean(d)),4),'paired_bootstrap95':[round(samples[37],4),round(samples[1462],4)]}

out={'metadata':{'real_doc_versions':N,'real_queries':len(r.QUERIES),'heldout_paired_queries':len(test),'train_pairs':len(train),'neural_retriever':False,'task':'retrieval of two exact real code revisions from combined commit subjects (synthetic combination)','source':'noVNC Git history, local checkout'},'controls':controls,'selected_train_only':selected,'bootstrap':boot_ci,'notes':['All query terms supplied by user-like real commit subjects; two-part questions are synthetic pairs','Exact revision associated with commit is an automated noisy proxy qrel, not human QA evidence label','Change BM25 includes removed lines, appropriate for history queries but not for current-state questions','Candidate pool top 30 per branch, cost uses query-selected five-line passage chunks; no disk IO','Search costs, true model token costs, accuracy of final generation not measured','Methods tuned on 50 training pairs and only final settings scored on 75 held-out pairs']}
(HERE/'round10_strong_retrieval_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'controls':controls,'selected':selected,'bootstrap':boot_ci},indent=2),flush=True)
