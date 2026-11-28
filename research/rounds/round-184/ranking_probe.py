import collections, math, random, sqlite3, time, json

def count(s,p):return sum(s[i:i+len(p)]==p for i in range(len(s)-len(p)+1))
def idf(n,df):return max(1e-6,math.log((n-df+.5)/(df+.5)))
def score(tf,dl,avg,w):return w*tf*2.2/(tf+1.2*(.25+.75*dl/avg)) if tf else 0.
def solve(base,corrections,lengths,windows,queries,op,lazy):
    n=len(base);avg=sum(lengths)/n; cache={};work=collections.Counter();freq=[];bounds=[]
    for p in queries:
        bc=[count(a,p) for a in base];work['base_counts']+=n
        maxima={i:min([max(0,len(w)-len(p)+1)]+[windows[i][1][t] for t in set(p)]) for i,(w,_) in enumerate(windows)}
        # Same exact unigram envelope available to both policies.
        edges=[[(i,c) for i,c in row.items() if maxima[i]] for row in corrections]
        memo={};work['eligible_rows']+=len({i for es in edges for i,_ in es})
        def get(i):
            if i not in memo:
                memo[i]=count(windows[i][0],p);assert memo[i]<=maxima[i];work['exact_window_evals']+=1
            return memo[i]
        def interval(j):
            lo=hi=bc[j]
            for i,c in edges[j]:
                if i in memo:lo+=c*memo[i];hi+=c*memo[i]
                elif c<0:lo+=c*maxima[i]
                else:hi+=c*maxima[i]
            assert hi>=0
            return max(0,lo),min(max(0,lengths[j]-len(p)+1),hi)
        def exact(j):
            for i,_ in edges[j]:get(i)
            l,u=interval(j);assert l==u;return l
        if not lazy:
            vals=[exact(j) for j in range(n)];freq.append(vals);continue
        # Capture bound/resolve with independent query-local context.
        def make(bc,edges,memo,maxima,p):
            def get(i):
                if i not in memo:memo[i]=count(windows[i][0],p);assert memo[i]<=maxima[i];work['exact_window_evals']+=1
            def interval(j):
                lo=hi=bc[j]
                for i,c in edges[j]:
                    if i in memo:lo+=c*memo[i];hi+=c*memo[i]
                    elif c<0:lo+=c*maxima[i]
                    else:hi+=c*maxima[i]
                assert hi>=0
                return max(0,lo),min(max(0,lengths[j]-len(p)+1),hi)
            def exact(j):
                for i,_ in edges[j]:get(i)
                l,u=interval(j);assert l==u;return l
            return interval,exact
        interval,exact=make(bc,edges,memo,maxima,p)
        present=[]
        for j in range(n):
            l,u=interval(j);assert l<=u
            if l>0:present.append(True);work['positive_certificates']+=1
            elif not u:present.append(False);work['zero_certificates']+=1
            else:present.append(bool(exact(j)));work['ambiguous_df']+=1
        freq.append(present);bounds.append((interval,exact))
    df=[sum(bool(v) for v in row) for row in freq];ws=[idf(n,d) for d in df]
    cands=[j for j in range(n) if (all if op=='AND' else any)(row[j] for row in freq)]
    if not lazy:return sorted(((-sum(score(row[j],lengths[j],avg,w) for row,w in zip(freq,ws)),j) for j in cands))[:10],df,work
    upper=[(-sum(score(iv(j)[1],lengths[j],avg,w) for (iv,_),w in zip(bounds,ws)),j) for j in cands];upper.sort();hits=[]
    for neg,j in upper:
        if len(hits)==10 and neg>hits[-1][0]+1e-12*max(1.,abs(hits[-1][0])):work['pruned_candidates']+=1;continue
        s=-sum(score(ex(j),lengths[j],avg,w) for (_,ex),w in zip(bounds,ws));hits=sorted(hits+[(s,j)])[:10];work['exact_scored']+=1
    return hits,df,work

def run(regime):
    rng=random.Random(184);base=[];target=[];corrections=[];wins=[];wid={}
    for j in range(320):
        a=tuple(rng.choices(range(40),weights=[20 if i<4 else 1 for i in range(40)],k=160));b=list(a)
        changes=1 if regime=='sparse' else 5
        positions=rng.sample(range(8,152,24),changes)
        row=collections.Counter()
        for i in positions:
            b[i]=rng.randrange(40)
            for w,c in ((a[i-7:i+8],-1),(tuple(b[i-7:i+8]),1)):
                if w not in wid:wid[w]=len(wins);wins.append((w,collections.Counter(w)))
                row[wid[w]]+=c
        base.append(a);target.append(tuple(b));corrections.append({i:c for i,c in row.items() if c})
    lengths=list(map(len,target));qs=set()
    for _ in range(50):
        s=rng.choice(target);i=rng.randrange(150);q=s[i:i+rng.randrange(2,6)];qs.add(((q,), 'AND'))
    for _ in range(35):
        p=tuple(rng.choices(range(4),k=rng.randrange(2,5)));q=tuple(rng.choices(range(4),k=2));
        if p!=q:qs.add(((p,q),rng.choice(('AND','OR'))))
    qs=sorted(qs);oracle=sqlite3.connect(':memory:');oracle.execute('CREATE VIRTUAL TABLE docs USING fts5(body)');oracle.executemany('INSERT INTO docs(rowid,body) VALUES(?,?)',[(j+1,' '.join('t'+str(t) for t in d)) for j,d in enumerate(target)])
    work=[collections.Counter(),collections.Counter()];timing=[0.,0.]
    for q,op in qs:
        for j,(a,b,row) in enumerate(zip(base,target,corrections)):
            for p in q:assert count(a,p)+sum(c*count(wins[i][0],p) for i,c in row.items())==count(b,p)
        got=[]
        for i,lazy in enumerate((False,True)):
            t=time.perf_counter();r,df,w=solve(base,corrections,lengths,wins,q,op,lazy);timing[i]+=time.perf_counter()-t;work[i].update(w);got.append((r,df))
        assert got[0]==got[1],(q,op,got)
        expr=(' '+op+' ').join('"'+ ' '.join('t'+str(t) for t in p)+'"' for p in q);native=oracle.execute('SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs),rowid LIMIT 10',(expr,)).fetchall();assert [j+1 for _,j in got[0][0]]==[j for j,_ in native];assert all(abs(s-v)<1e-12 for (s,_),(_,v) in zip(got[0][0],native));assert got[0][1]==[oracle.execute('SELECT count(*) FROM docs WHERE docs MATCH ?',('"'+ ' '.join('t'+str(t) for t in p)+'"',)).fetchone()[0] for p in q]
    return dict(regime=regime,docs=len(base),windows=len(wins),queries=len(qs),eager=dict(work[0]),certified=dict(work[1]),seconds=timing)
if __name__=='__main__':print(json.dumps([run(r) for r in ('sparse','scattered')],indent=2))
