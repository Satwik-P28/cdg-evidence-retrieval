"""Independent synthetic model check, not a run of repository R120."""
import sqlite3,random,math,json
rng=random.Random(120)
terms=['alpha','beta','gamma','delta','epsilon']
checks=hits=interval_checks=drift=0
maxerr=0.
for seed in range(25):
    events=[]; head={}; intervals={}; stats={}; total=0
    for g in range(1,41):
        a=rng.randrange(9)
        tokens=[rng.choice(terms) for _ in range(rng.randrange(30))]
        if a in head:
            prev=head[a]; intervals[prev][1]=g; total-=len(events[prev-1][1])
        head[a]=g; intervals[g]=[g,None]; total+=len(tokens)
        events.append((a,tokens));stats[g]=(len(head),total)
    for c in (1,8,16,24,32,40):
        latest={a:g for g,(a,_) in enumerate(events[:c],1)}
        active={g:events[g-1][1] for g in latest.values()}
        assert set(active)=={g for g,(s,e) in intervals.items() if s<=c and (e is None or c<e)}
        assert (len(active),sum(map(len,active.values())))==stats[c]
        interval_checks+=1
        db=sqlite3.connect(':memory:'); db.execute('CREATE VIRTUAL TABLE ft USING fts5(body)')
        db.executemany('INSERT INTO ft(rowid,body) VALUES(?,?)',[(g,' '.join(t)) for g,t in active.items()])
        n,total=stats[c]; avg=total/n
        for phrases,op in [(('alpha',),'AND'),(('beta',),'AND'),(('alpha beta',),'AND'),(('alpha alpha',),'AND'),(('alpha','beta'),'OR'),(('alpha','beta'),'AND'),(('alpha beta','gamma'),'OR'),(('alpha beta','gamma'),'AND'),(('missing','alpha'),'OR'),(('missing','alpha'),'AND')]:
            q=(' '+op+' ').join('"'+p+'"' for p in phrases)
            expected=db.execute('SELECT rowid,bm25(ft) FROM ft WHERE ft MATCH ? ORDER BY bm25(ft),rowid LIMIT 10',(q,)).fetchall()
            counts=[]
            for p in phrases:
                parts=p.split(); count={}
                for g,t in active.items():
                    f=sum(t[i:i+len(parts)]==parts for i in range(len(t)-len(parts)+1))
                    if f:count[g]=f
                counts.append(count)
            candidates=(set.intersection if op=='AND' else set.union)(*(set(m) for m in counts))
            weights=[max(math.log((n-len(m)+.5)/(len(m)+.5)),0) or 1e-6 for m in counts]
            got=sorted(((g,-sum(w*(m.get(g,0)*2.2)/(m.get(g,0)+1.2*(.25+.75*len(active[g])/avg)) for m,w in zip(counts,weights) if m.get(g,0))) for g in candidates),key=lambda x:(x[1],x[0]))[:10]
            assert [g for g,s in got]==[g for g,s in expected],(seed,c,q,got,expected)
            err=max((abs(s-t) for (_,s),(_,t) in zip(got,expected)),default=0)
            assert err<1e-12
            maxerr=max(maxerr,err); checks+=1;hits+=len(got)
        db.close()
print(json.dumps({'kind':'independent synthetic model; not R120 repository CI','histories':25,'events':1000,'validity_and_stats_checks':interval_checks,'query_checks':checks,'ranked_hits':hits,'max_abs_score_error':maxerr},indent=2))