"""R117: historical BM25 replay using a single append-only native FTS5 index.
Score inversion is restricted to single unweighted quoted phrases. Boolean
AND/OR queries are explicitly decomposed into such phrases. No early top-k
truncation. Independent positions and rebuilt native prefix indexes are controls.
"""
import argparse, json, math, sqlite3, statistics, sys, tempfile, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-116"))
from versioned_evidence import setup,append,connect,generation,order,oracle,control,plan,Receipt,read_receipt,SALT,PIN,sha,load,select

K1=1.2; B=.75

def idf(n,df):
    if not 0<=df<=n or n<=0: raise ValueError("invalid document frequency")
    x=math.log((n-df+.5)/(df+.5))
    return 1e-6 if x<=0 else x

def positive_score(tf,dl,avg,idf_value):
    return idf_value*((tf*(K1+1.0))/(tf+K1*(1-B+B*dl/avg))) if tf else 0.0

def invert(score,dl,avg,idf_value):
    if not all(map(math.isfinite,(score,avg,idf_value))) or not (score<0 and dl>0 and avg>0 and idf_value>0):
        raise ValueError("invalid BM25 input")
    x=-score/idf_value
    denominator=K1+1.0-x
    if denominator<=0: raise ValueError("saturated score")
    guess=x*K1*(1-B+B*dl/avg)/denominator
    if not math.isfinite(guess): raise ValueError("nonfinite frequency")
    tf=round(guess)
    # Conservative local uniqueness test against the native floating score.
    tol=64*math.ulp(score)
    if not 1<=tf<=dl or abs(positive_score(tf,dl,avg,idf_value)+score)>tol:
        raise ValueError("score does not roundtrip to integer frequency")
    for near in (tf-1,tf+1):
        if 1<=near<=dl and abs(positive_score(near,dl,avg,idf_value)+score)<=tol:
            raise ValueError("ambiguous frequency near saturation")
    return tf

def quote(phrase):
    if not phrase or '"' in phrase: raise ValueError("expected nonempty native vocabulary phrase")
    return '"'+phrase+'"'

def expression(phrases,op):
    if not phrases or len(set(phrases))!=len(phrases) or op not in ("AND","OR"):
        raise ValueError("unsupported query")
    return (" "+op+" ").join(map(quote,phrases))

def materialize_ledger(db,n):
    db.execute("CREATE VIRTUAL TABLE temp.rank_vocab USING fts5vocab(main,docs,'instance')")
    lens=dict(db.execute("SELECT doc,count(*) FROM temp.rank_vocab GROUP BY doc"))
    db.execute("CREATE TABLE rank_ledger(g INTEGER PRIMARY KEY,dl INTEGER NOT NULL,total INTEGER NOT NULL)")
    total=0
    for g in range(1,n+1):
        dl=lens.get(g,0); total+=dl
        db.execute("INSERT INTO rank_ledger VALUES(?,?,?)",(g,dl,total))
    db.commit()

def load_ledger(db,n):
    lengths=[0]; totals=[0]
    for g,dl,total in db.execute("SELECT g,dl,total FROM rank_ledger ORDER BY g"):
        if g!=len(lengths) or dl<0 or total!=totals[-1]+dl: raise ValueError("bad ledger")
        lengths.append(dl); totals.append(total)
    if len(lengths)!=n+1 or totals[-1]==0: raise ValueError("invalid ledger size")
    return lengths,totals

def inverse_counts(db,phrase,lengths,totals):
    n=len(lengths)-1
    hits=db.execute("SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ?",(quote(phrase),)).fetchall()
    if not hits: return {}
    weight=idf(n,len(hits)); avg=totals[n]/n
    return {g:invert(score,lengths[g],avg,weight) for g,score in hits}

def positional_counts(db,phrase):
    # Independent count of actual phrase instances from native positions.
    maps=[]
    for tok in phrase.split(" "):
        m={}
        for doc,offset in db.execute("SELECT doc,offset FROM temp.rank_vocab WHERE term=?",(tok,)):
            m.setdefault(doc,set()).add(offset)
        maps.append(m)
    docs=set.intersection(*(set(m) for m in maps))
    out={}
    for doc in docs:
        places=set.intersection(*({p-i for p in m[doc]} for i,m in enumerate(maps)))
        if places: out[doc]=len(places)
    return out

def replay(db,phrases,op,cutoff,lengths,totals,allowed=None,method="inverse"):
    expression(phrases,op)
    if not 1<=cutoff<len(lengths) or totals[cutoff]<=0: raise ValueError("invalid replay cutoff")
    counts=[inverse_counts(db,p,lengths,totals) if method=="inverse" else positional_counts(db,p) for p in phrases]
    return rank_counts(counts,op,cutoff,lengths,totals,allowed)

def rank_counts(counts,op,cutoff,lengths,totals,allowed):
    eligible=[{g:tf for g,tf in m.items() if g<=cutoff} for m in counts]
    sets=[set(m) for m in eligible]
    candidates=set.intersection(*sets) if op=="AND" else set.union(*sets)
    if allowed is not None: candidates &= allowed
    avg=totals[cutoff]/cutoff
    weights=[idf(cutoff,len(m)) for m in eligible]
    return sorted(((g,-sum(positive_score(m.get(g,0),lengths[g],avg,w) for m,w in zip(eligible,weights))) for g in candidates),key=lambda x:(x[1],x[0]))[:10]

def heads(db,cutoff):
    return {g for (g,) in db.execute("SELECT max(generation) FROM revisions WHERE generation<=? GROUP BY article",(cutoff,))}

def plan_queries(ref):
    quoted=plan(ref)
    phrases=[x[1:-1] for x in quoted]
    queries=[((p,),"AND") for p in phrases]
    # deterministic mixed queries using distinct native phrases; no labels.
    for i in range(min(8,len(phrases)//2)):
        a,b=phrases[i],phrases[-1-i]
        if a!=b:
            queries.append(((a,b),"AND")); queries.append(((a,b),"OR"))
    return queries

def prefix_index(path,events):
    db=sqlite3.connect(path)
    db.execute("PRAGMA page_size=4096")
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(body,content='')")
    db.executemany("INSERT INTO docs(rowid,body) VALUES(?,?)",((g,raw.decode("utf8")) for g,(_,_,raw) in enumerate(events,1)))
    db.commit();db.execute("VACUUM")
    return db,path.stat().st_size

def native_rank(db,q,allowed):
    hits=db.execute("SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs),rowid",(q,))
    return [(g,s) for g,s in hits if allowed is None or g in allowed][:10]

def verify(got,expected):
    if [x[0] for x in got]!=[x[0] for x in expected]: raise AssertionError("ordered rank mismatch")
    err=max((abs(x[1]-y[1]) for x,y in zip(got,expected)),default=0.0)
    if err>1e-11: raise AssertionError("score mismatch")
    return err

def timed(fn):
    start=time.perf_counter_ns(); v=fn()
    return v,(time.perf_counter_ns()-start)/1000

def experiment(folder,events):
    path=folder/"archive.sqlite"
    db=setup(path)
    for a,i,raw in events: append(db,a,raw,"bounded_anchor")
    n=generation(db)
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("VACUUM")
    base_bytes=path.stat().st_size
    materialize_ledger(db,n)
    db.execute("VACUUM")
    final_bytes=path.stat().st_size
    lengths,totals=load_ledger(db,n)
    cuts=sorted(set([max(1,n//4),max(1,n//2),max(1,3*n//4),n]))
    qref=oracle(events[:cuts[0]])
    queries=plan_queries(qref);qref.close()
    # Full-index inversion is independently checked on every constituent phrase.
    unique=sorted(set(p for phrases,_ in queries for p in phrases))
    freq_checks=0
    for phrase in unique:
        x=inverse_counts(db,phrase,lengths,totals)
        y=positional_counts(db,phrase)
        if x!=y: raise AssertionError("inverted integer frequency differs from actual FTS positions")
        freq_checks+=len(x)
    stats=[]
    for c in cuts:
        ref=oracle(events[:c])
        if c<n: native,sz=prefix_index(folder/("prefix-"+str(c)+".sqlite"),events[:c])
        else: native,sz=db,0
        allowed_heads=heads(db,c)
        data={"cutoff":c,"additional_native_index_bytes":sz,"queries":0,"queries_with_hits":0,"ranked_hits":0,
              "max_inverse_score_error":0.0,"max_positions_score_error":0.0,"naive_cutoff_rank_changes":0,"naive_cutoff_score_or_rank_changes":0}
        timings={m:[] for m in ("inverse","positions","native")}
        for scope in ("all","heads"):
            allowed=None if scope=="all" else allowed_heads
            for phrases,op in queries:
                q=expression(phrases,op)
                expected=control(ref,q,scope)
                x,tx=timed(lambda:replay(db,phrases,op,c,lengths,totals,allowed,"inverse"))
                y,ty=timed(lambda:replay(db,phrases,op,c,lengths,totals,allowed,"positions"))
                z,tz=timed(lambda:native_rank(native,q,allowed))
                timings["inverse"].append(tx);timings["positions"].append(ty);timings["native"].append(tz)
                data["max_inverse_score_error"]=max(data["max_inverse_score_error"],verify(x,expected))
                data["max_positions_score_error"]=max(data["max_positions_score_error"],verify(y,expected))
                verify(z,expected)
                naive=[(g,s) for g,s in db.execute("SELECT rowid,bm25(docs) FROM docs WHERE docs MATCH ? AND rowid<=? ORDER BY bm25(docs),rowid",(q,c)) if allowed is None or g in allowed][:10]
                if [g for g,_ in naive]!=[g for g,_ in expected]: data["naive_cutoff_rank_changes"]+=1
                if len(naive)!=len(expected) or any(g!=h or abs(s-t)>1e-11 for (g,s),(h,t) in zip(naive,expected)): data["naive_cutoff_score_or_rank_changes"]+=1
                data["queries"]+=1;data["queries_with_hits"]+=bool(expected);data["ranked_hits"]+=len(expected)
        data["warm_median_rank_us_exploratory"]={m:statistics.median(ts) for m,ts in timings.items()}
        stats.append(data)
        ref.close()
        if native is not db: native.close()
    db.close()
    return {"final_archive_without_ledger_bytes":base_bytes,"final_archive_with_ledger_bytes":final_bytes,
            "ledger_physical_increment_bytes":final_bytes-base_bytes,
            "retained_native_prefix_index_bytes":sum(s["additional_native_index_bytes"] for s in stats),
            "checked_distinct_phrases":len(unique),"integer_frequency_differentials":freq_checks,
            "query_count_per_scope":len(queries),"cutoffs":stats}

def run(root,n=100):
    articles,manifest=load(root)
    selected=select(articles,300+n,SALT)
    if len(selected)!=300+n: raise ValueError("not enough articles")
    cohort=selected[300:]
    events=order(cohort)
    with tempfile.TemporaryDirectory() as tmp:
        result=experiment(Path(tmp),events)
    return {"round":117,"upstream_commit":PIN,"full_corpus_sha256":manifest,
      "articles":len(cohort),"revisions":len(events),"article_sha256":sha("\n".join(a for a,_ in cohort).encode()).hex(),
      "results":result,"limits":["processed Wikipedia revisions; synthetic cross-article ingestion order",
        "native Unicode61 one-column unweighted BM25; exact phrases and distinct phrase AND/OR only",
        "all candidates are enumerated; no top-k pruning, NEAR, prefix, NOT, weights or deletion support",
        "ledger built offline from native vocabulary; no atomic incremental ledger maintenance or rank receipts",
        "position control uses native fts5vocab, not a tuned native FTS5 auxiliary function",
        "retained prefix comparator counts only additional standalone contentless native indexes, shared final source/metadata excluded",
        "warm one-runner rank-only timing; no concurrent workload, cold I/O or RAG quality",
        "known temporal scoring prior art; no novelty or performance superiority asserted"]}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--articles",type=int,default=100);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();r=run(a.root,a.articles)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
