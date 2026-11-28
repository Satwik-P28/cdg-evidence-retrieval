"""R184: exact DF certification followed by upper-bound top-k pruning.

Control: R168 native phrase query on the same signed archive. Candidate bounds
are read from existing native unigram postings, no extra persistent data.
The experimental row-at-a-time path is deliberately not claimed to be faster.
"""
import argparse,collections,json,random,tempfile,time
from pathlib import Path
import signed_phrase as sp
from signed_phrase import f,h,nr,ar,connect,tokens,query_plan,recover

HERE=Path(__file__).resolve().parent

def native_counts(db,table,phrase):
    return dict(db.execute(f"SELECT rowid,cdg_count({table}) FROM {table} WHERE {table} MATCH ?",(ar.quote(phrase),)))

def native_one(db,rid,phrase):
    row=db.execute("SELECT cdg_count(patch_fts) FROM patch_fts WHERE patch_fts MATCH ? AND rowid=?",(ar.quote(phrase),rid)).fetchone()
    return row[0] if row else 0

class PhraseCertificate:
    def __init__(self,db,phrase,prep,work):
        (active,lens,_,_),children,mapping=prep
        self.db=db;self.phrase=phrase;self.active=active;self.lens=lens;self.work=work
        self.length=len(q:=tokens(db,phrase))
        if not 1<=self.length<=sp.L:raise ValueError("unsupported phrase length")
        self.base=collections.Counter();self.edges=collections.defaultdict(list);self.memo={}
        for base,tf in native_counts(db,"base_fts",phrase).items():
            work["base_hits"]+=1
            for cid in children.get(base,()):self.base[cid]+=tf
        if len(q)==1:
            for rid,tf in native_counts(db,"patch_fts",phrase).items():
                work["unigram_exact_rows"]+=1
                for cid,coeff in mapping.get(rid,()):
                    if cid in active:self.base[cid]+=coeff*tf
            self.cids=set(self.base);self.upper={};return
        lists=[]
        for term in dict.fromkeys(q):
            counts=native_counts(db,"patch_fts",term.decode("utf8"))
            work["unigram_posting_hits"]+=len(counts)
            lists.append(counts)
        candidates=set.intersection(*(set(m) for m in lists))
        self.upper={}
        for rid in candidates:
            b=min(m[rid] for m in lists)
            for cid,coeff in mapping.get(rid,()):
                if cid in active:
                    self.edges[cid].append((rid,coeff));self.upper[rid]=b
        self.cids=set(self.base)|set(self.edges)
        work["eligible_rows"]+=len(self.upper)
        for es in self.edges.values():es.sort(key=lambda r:(-abs(r[1])*self.upper[r[0]],r[0]))

    def interval(self,cid):
        lo=hi=self.base[cid]
        for rid,coeff in self.edges.get(cid,()):
            if rid in self.memo:lo+=coeff*self.memo[rid];hi+=coeff*self.memo[rid]
            elif coeff<0:lo+=coeff*self.upper[rid]
            else:hi+=coeff*self.upper[rid]
        limit=max(0,self.lens[self.active[cid][0]]-self.length+1)
        lo=max(0,lo);hi=min(limit,hi)
        assert lo<=hi
        return lo,hi

    def resolve(self,rid):
        if rid not in self.memo:
            tf=native_one(self.db,rid,self.phrase)
            assert 0<=tf<=self.upper[rid]
            self.memo[rid]=tf;self.work["exact_window_evals"]+=1

    def present(self,cid):
        lo,hi=self.interval(cid)
        if lo>0:self.work["positive_certificates"]+=1;return True
        if hi==0:self.work["zero_certificates"]+=1;return False
        self.work["ambiguous_df"]+=1
        for rid,_ in self.edges.get(cid,()):
            self.resolve(rid);lo,hi=self.interval(cid)
            if lo>0:return True
            if hi==0:return False
        assert lo==hi
        return bool(lo)

    def exact(self,cid):
        lo,hi=self.interval(cid)
        if lo==hi:return lo
        for rid,_ in self.edges.get(cid,()):self.resolve(rid)
        lo,hi=self.interval(cid);assert lo==hi;return lo

def rank_certified(db,p,o,prep,prune=True):
    ar.expression(p,o)
    (active,lens,n,total),_,_=prep;work=collections.Counter()
    certs=[PhraseCertificate(db,q,prep,work) for q in p]
    present=[{cid for cid in c.cids if c.present(cid)} for c in certs]
    dfs=[sum(len(active[cid]) for cid in ids) for ids in present]
    candidates=set.intersection(*present) if o=="AND" else set.union(*present)
    if not candidates:return [],dfs,work
    avg=total/n;weights=[ar.idf(n,d) for d in dfs];ordered=[]
    for cid in candidates:
        upper=[c.interval(cid)[1] for c in certs]
        for g in active[cid]:
            ub=sum(ar.positive_score(tf,lens[g],avg,w) for tf,w in zip(upper,weights))
            ordered.append((-ub,g,cid))
    ordered.sort();hits=[];exact_counts={}
    for neg,g,cid in ordered:
        # Conservative separation; do not prune near floating point ties.
        # This guard is not a general certified binary64 error theorem.
        if prune and len(hits)==10 and neg>hits[-1][0]+1e-12*max(1.,abs(hits[-1][0])):
            work["pruned_candidates"]+=1;continue
        if cid not in exact_counts:exact_counts[cid]=[c.exact(cid) for c in certs]
        s=-sum(ar.positive_score(tf,lens[g],avg,w) for tf,w in zip(exact_counts[cid],weights))
        hits=sorted(hits+[(s,g)])[:10];work["exact_scored"]+=1
    return [(g,s) for s,g in hits],dfs,work

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    checker=connect(":memory:",ext)
    qs=[(p,o) for p,o in qs if all(1<=len(tokens(checker,x))<=sp.L for x in p)]
    # Include phrases drawn from actual changed windows rather than anchor choice.
    pool=set();prior={}
    for a,_,raw in events:
        ts=tokens(checker,raw.decode("utf8"))
        if a in prior:
            for x,y in sp.windows(prior[a],ts,False):
                for w in (x,y):
                    for l in (2,4,8):
                        if len(w)>=l:
                            i=(len(w)-l)//2;pool.add(b" ".join(w[i:i+l]).decode("utf8"))
        prior[a]=ts
        if len(pool)>=1024:break
    checker.close()
    qs=list(dict.fromkeys(qs+[((p,),"AND") for p in sorted(pool,key=lambda p:h.sha(("R184|"+p).encode()))[:24]]))
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    path=folder/"archive.sqlite";db,size=f.build(path,ext,events,"marginal",False)
    size.update(sp.build_delta(db,path,events,"independent_adaptive_weighted_adjusted_multi"));db.close()
    db=connect(path,ext);mapping=sp.load_patch_map(db)
    for g,(_,_,want) in enumerate(events,1):
        raw,dd,ab=recover(db,g);assert raw==want
        assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
    preps={c:sp.prepare_delta(db,c,mapping) for c in cuts}
    sigs={};out={}
    for mode in ("eager_native","certified_df","certified_topk"):
        times=[];work=collections.Counter();err=0.;plan=list(expected);rng=random.Random(184)
        # Two paired, shuffled warm passes per policy.
        for _ in range(2):
            rng.shuffle(plan)
            for c,p,o in plan:
                t=time.perf_counter_ns()
                if mode=="eager_native":hits,df,w=sp.rank_delta(db,p,o,preps[c])
                else:hits,df,w=rank_certified(db,p,o,preps[c],mode=="certified_topk")
                times.append((time.perf_counter_ns()-t)/1000);work.update(w)
                err=max(err,h.verify(hits,expected[c,p,o]))
                if mode=="eager_native":sigs[c,p,o]=(hits,df)
                else:assert sigs[c,p,o]==(hits,df)
        out[mode]=dict(query=h.quant(times),rank_checks=len(times),max_score_error=err,work=dict(work))
        print("ARM_JSON="+json.dumps(dict(mode=mode,**out[mode])),flush=True)
    db.close()
    for ref in refs.values():ref.close()
    return dict(round=184,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),archive=size,policies=out,
        limitations=["same finalized signed archive for all policies, no new storage","unigram row intersection plus row-at-a-time MATCH is not equivalent in cost to native phrase MATCH",
        "exact DF, exact top-k and score signature checks; floating guard conservative, no general binary64 certification theorem",
        "query plan is content-derived, warm timings, no physical I/O or theorem from RH used"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="clark":
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex()
            assert manifest=="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f"
            n=len(events);cuts=[n//4,n//2,3*n//4,n]
        else:
            events,_,m=nr.load(a.source,a.target,folder);manifest=m["source_manifest_sha256"]
            n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            assert manifest==json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
