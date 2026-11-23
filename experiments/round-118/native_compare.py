"""R118: C FTS5 count comparator and cutoff pushdown.
R117 cohort is intentionally reused for a matched implementation comparison.
"""
import argparse, json, random, sqlite3, statistics, sys, tempfile, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-117"))
from rank_replay import (setup,append,generation,order,oracle,control,plan_queries,quote,
    expression,materialize_ledger,load_ledger,inverse_counts,positional_counts,rank_counts,
    heads,prefix_index,native_rank,verify,SALT,PIN,sha,load,select)

METHODS=("inverse","positions","native_full","native_cutoff","prefix_native")

def extension(db,path):
    db.enable_load_extension(True)
    try: db.load_extension(str(Path(path).resolve()))
    finally: db.enable_load_extension(False)

def counts(db,phrase,lengths,cutoff=None):
    sql="SELECT rowid,cdg_count(docs),cdg_length(docs) FROM docs WHERE docs MATCH ?"
    args=(quote(phrase),)
    if cutoff is not None:
        sql+=" AND rowid<=?";args+=(cutoff,)
    result={}
    for g,tf,dl in db.execute(sql,args):
        if dl!=lengths[g] or not 1<=tf<=dl:
            raise AssertionError("native length/frequency disagrees with ledger")
        result[g]=tf
    return result

def rank(db,phrases,op,c,lengths,totals,allowed,method,native):
    q=expression(phrases,op)
    if method=="prefix_native":return native_rank(native,q,allowed)
    if method=="inverse":freq=[inverse_counts(db,p,lengths,totals) for p in phrases]
    elif method=="positions":freq=[positional_counts(db,p) for p in phrases]
    elif method=="native_full":freq=[counts(db,p,lengths) for p in phrases]
    elif method=="native_cutoff":freq=[counts(db,p,lengths,c) for p in phrases]
    else:raise ValueError("unknown method")
    return rank_counts(freq,op,c,lengths,totals,allowed)

def pct95(values):return sorted(values)[int(.95*(len(values)-1))]

def experiment(folder,events,ext,repetitions=5):
    db=setup(folder/"archive.sqlite")
    extension(db,ext)
    for a,i,raw in events:append(db,a,raw,"bounded_anchor")
    n=generation(db);materialize_ledger(db,n)
    lengths,totals=load_ledger(db,n)
    for g,(_,_,raw) in enumerate(events,1):
        text=raw.decode("utf8")
        if db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0]!=lengths[g]:
            raise AssertionError("unicode61 scalar count does not match actual FTS index")
    cuts=sorted(set([max(1,n//4),max(1,n//2),max(1,3*n//4),n]))
    ref=oracle(events[:cuts[0]]);queries=plan_queries(ref);ref.close()
    # Predeclare 8 high-DF terms in the first prefix, not from final outcomes.
    freq=db.execute("SELECT term,count(DISTINCT doc) df FROM temp.rank_vocab WHERE doc<=? GROUP BY term ORDER BY df DESC,term LIMIT 8",(cuts[0],)).fetchall()
    existing=set(queries)
    for term,_ in freq:
        item=((term,),"AND")
        if item not in existing:queries.append(item);existing.add(item)
    unique=sorted({p for phrases,_ in queries for p in phrases})
    full_checks=0
    for p in unique:
        a=counts(db,p,lengths);b=positional_counts(db,p);c=inverse_counts(db,p,lengths,totals)
        if a!=b or a!=c:raise AssertionError("native count differential")
        full_checks+=len(a)
    rng=random.Random(118);results=[]
    for c in cuts:
        ref=oracle(events[:c])
        native,sz=prefix_index(folder/("prefix-"+str(c)+".sqlite"),events[:c])
        head=heads(db,c)
        checks=0;maxerr={m:0.0 for m in METHODS}
        cutoff_rows=0;full_rows=0
        for p in unique:
            f=counts(db,p,lengths);h=counts(db,p,lengths,c)
            if h!={g:tf for g,tf in f.items() if g<=c}:raise AssertionError("cutoff frequency parity")
            cutoff_rows+=len(h);full_rows+=len(f)
        timings={m:[] for m in METHODS}
        common={m:[] for m in METHODS}
        requests=[(scope,p,op) for scope in ("all","heads") for p,op in queries]
        for scope,phrases,op in requests:
            allowed=None if scope=="all" else head
            expected=control(ref,expression(phrases,op),scope)
            for method in METHODS:
                got=rank(db,phrases,op,c,lengths,totals,allowed,method,native)
                maxerr[method]=max(maxerr[method],verify(got,expected))
            checks+=1
        for _ in range(repetitions):
            rng.shuffle(requests)
            for scope,phrases,op in requests:
                allowed=None if scope=="all" else head
                methods=list(METHODS);rng.shuffle(methods)
                for method in methods:
                    start=time.perf_counter_ns()
                    rank(db,phrases,op,c,lengths,totals,allowed,method,native)
                    elapsed=(time.perf_counter_ns()-start)/1000
                    timings[method].append(elapsed)
                    if len(phrases)==1 and phrases[0] in {t for t,_ in freq}:common[method].append(elapsed)
        results.append({"cutoff":c,"query_checks_per_method":checks,"max_error":maxerr,
            "full_unique_phrase_match_rows":full_rows,"cutoff_unique_phrase_match_rows":cutoff_rows,
            "warm_median_us":{m:statistics.median(t) for m,t in timings.items()},
            "warm_p95_us":{m:pct95(t) for m,t in timings.items()},
            "common_term_warm_median_us":{m:statistics.median(t) for m,t in common.items() if t},
            "timed_requests_per_method":len(timings[METHODS[0]]),
            "prefix_native_index_bytes":sz})
        ref.close();native.close()
    db.close()
    return {"revisions":n,"native_tokenizer_length_checks":n,"unique_phrase_count":len(unique),
        "full_integer_count_checks":full_checks,"query_count_per_scope":len(queries),
        "high_df_terms":[[t,df] for t,df in freq],"repetitions":repetitions,"cutoffs":results}

def run(root,ext,n=100,repetitions=5):
    a,manifest=load(root);ranked=select(a,300+n,SALT)
    if len(ranked)!=300+n:raise ValueError("insufficient corpus")
    cohort=ranked[300:]
    with tempfile.TemporaryDirectory() as tmp:
        r=experiment(Path(tmp),order(cohort),ext,repetitions)
    return {"round":118,"upstream_commit":PIN,"full_corpus_sha256":manifest,
        "article_sha256":sha("\n".join(a for a,_ in cohort).encode()).hex(),
        "sqlite_version":sqlite3.sqlite_version,"articles":len(cohort),"results":r,
        "limits":["R117 cohort reused, not independent data",
        "prefix-generated term and phrase probes; synthetic ingestion order",
        "one-column full-detail Unicode61 FTS5; AND/OR only",
        "cutoff row reduction is SQL result cardinality, not measured posting traversal or disk reads",
        "warm rank-only timings randomized across methods, one CI machine, not cold latency",
        "native count comparator still enumerates eligible phrase matches and ranks in Python",
        "offline ledger only; token-count scalar tested but not yet atomic ingestion",
        "no novelty claim for native auxiliary API or historical BM25"]}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--articles",type=int,default=100);p.add_argument("--repetitions",type=int,default=5)
    a=p.parse_args();r=run(a.root,a.extension,a.articles,a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
