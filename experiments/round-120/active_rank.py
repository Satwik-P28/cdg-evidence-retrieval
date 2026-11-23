"""R120: active-version-only historical BM25, interval and scan controls."""
import argparse,json,random,sqlite3,statistics,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-119"))
from atomic_receipts import setup as base_setup,connect,append_atomic,audit_ledger,finalize,canonical,sha
from atomic_receipts import STAGES
from rank_replay import load_ledger,positive_score,idf,heads,plan_queries,expression,quote,verify
from native_compare import counts
from versioned_evidence import generation,order,load,select,SALT,PIN,Receipt,read_receipt

METHODS=("scan","prepared","interval","native")
FORMAT="cdg-active-rank-v1"
SCORER="fts5-unicode61-one-column-bm25-active-k1=1.2-b=.75"

def install(db):
    if generation(db)!=0:raise ValueError("install on empty archive")
    db.executescript("""
    CREATE TABLE validity(start_g INTEGER PRIMARY KEY REFERENCES revisions(generation),
      end_g INTEGER REFERENCES revisions(generation), CHECK(end_g IS NULL OR end_g>start_g));
    CREATE TABLE active_stats(g INTEGER PRIMARY KEY REFERENCES rank_ledger(g),
      n INTEGER NOT NULL CHECK(n>0), tokens INTEGER NOT NULL CHECK(tokens>=0));
    CREATE TRIGGER active_after_ledger AFTER INSERT ON rank_ledger BEGIN
      UPDATE validity SET end_g=NEW.g
        WHERE start_g=(SELECT old.generation FROM revisions cur JOIN revisions old
           ON old.article=cur.article AND old.ord=cur.ord-1 WHERE cur.generation=NEW.g)
        AND end_g IS NULL;
      INSERT INTO validity VALUES(NEW.g,NULL);
      INSERT INTO active_stats
        SELECT NEW.g,
          COALESCE((SELECT n FROM active_stats WHERE g=NEW.g-1),0)
              + CASE WHEN cur.ord=0 THEN 1 ELSE 0 END,
          COALESCE((SELECT tokens FROM active_stats WHERE g=NEW.g-1),0)+NEW.dl
              - COALESCE((SELECT l.dl FROM revisions old JOIN rank_ledger l ON l.g=old.generation
                WHERE old.article=cur.article AND old.ord=cur.ord-1),0)
        FROM revisions cur WHERE cur.generation=NEW.g;
    END;
    """)
    db.commit()
    return db

def setup(path,ext):
    return install(base_setup(path,ext))

def audit(db):
    n=audit_ledger(db)
    rows=db.execute("SELECT r.generation,r.article,r.ord,l.dl FROM revisions r JOIN rank_ledger l ON l.g=r.generation ORDER BY r.generation").fetchall()
    active={};ends={};stats=[];total=0
    for g,a,i,dl in rows:
        old=active.get(a)
        if old:
            if old[1]+1!=i:raise ValueError("noncontiguous version")
            ends[old[0]]=g;total-=old[2]
        elif i!=0:raise ValueError("missing first revision")
        active[a]=(g,i,dl);ends[g]=None;total+=dl
        stats.append((g,len(active),total))
    if db.execute("SELECT start_g,end_g FROM validity ORDER BY start_g").fetchall()!=sorted(ends.items()):
        raise ValueError("validity audit mismatch")
    if db.execute("SELECT g,n,tokens FROM active_stats ORDER BY g").fetchall()!=stats:
        raise ValueError("active statistic audit mismatch")
    return n

def prepare(db,c,lengths):
    active=heads(db,c)
    return active,len(active),sum(lengths[g] for g in active)

def interval_counts(db,p,c,lengths):
    rows=db.execute("""SELECT docs.rowid,cdg_count(docs),cdg_length(docs)
      FROM docs JOIN validity v ON v.start_g=docs.rowid
      WHERE docs MATCH ? AND docs.rowid<=? AND (v.end_g IS NULL OR v.end_g>?)""",(quote(p),c,c))
    out={}
    for g,tf,dl in rows:
        if dl!=lengths[g] or not 1<=tf<=dl:raise ValueError("native count mismatch")
        out[g]=tf
    return out

def score(freq,op,n,total,lengths):
    if n<1:raise ValueError("empty active document set")
    df=[len(m) for m in freq]
    if any(d>n for d in df):raise ValueError("active frequency exceeds corpus")
    sets=[set(m) for m in freq]
    candidates=set.intersection(*sets) if op=="AND" else set.union(*sets)
    if not candidates:return [],df
    if total<=0:raise ValueError("invalid active token total")
    avg=total/n;weights=[idf(n,d) for d in df]
    hits=sorted(((g,-sum(positive_score(m.get(g,0),lengths[g],avg,w)
                           for m,w in zip(freq,weights))) for g in candidates),key=lambda p:(p[1],p[0]))[:10]
    return hits,df

def rank(db,phrases,op,c,lengths,method,prepared=None):
    expression(phrases,op)
    if not 1<=c<len(lengths):raise ValueError("bad cutoff")
    if method=="interval":
        n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
        freq=[interval_counts(db,p,c,lengths) for p in phrases]
    elif method in ("scan","prepared"):
        active,n,total=prepare(db,c,lengths) if method=="scan" else prepared
        freq=[{g:tf for g,tf in counts(db,p,lengths,c).items() if g in active} for p in phrases]
    else:raise ValueError("bad rank method")
    hits,df=score(freq,op,n,total,lengths)
    return hits,n,total,df

def active_oracle(events,c,path=None):
    active={}
    for g,(a,i,raw) in enumerate(events[:c],1):active[a]=(g,raw)
    db=sqlite3.connect(":memory:" if path is None else path)
    db.execute("PRAGMA page_size=4096")
    db.execute("CREATE VIRTUAL TABLE fulltext USING fts5(body,content='')")
    db.executemany("INSERT INTO fulltext(rowid,body) VALUES(?,?)",
                   ((g,raw.decode("utf8")) for g,raw in sorted(active.values())))
    db.commit();db.execute("VACUUM")
    return db

def native(ref,phrases,op):
    return ref.execute("SELECT rowid,bm25(fulltext) FROM fulltext WHERE fulltext MATCH ? ORDER BY bm25(fulltext),rowid LIMIT 10",
                       (expression(phrases,op),)).fetchall()

def issue(db,phrases,op,c):
    if not db.in_transaction:raise ValueError("explicit snapshot required")
    lens,_=load_ledger(db,generation(db))
    hits,n,total,df=rank(db,phrases,op,c,lens,"interval")
    prefix=db.execute("SELECT prefix_sha FROM rank_ledger WHERE g=?",(c,)).fetchone()[0]
    rows=[]
    for g,s in hits:
        a,i,d=db.execute("""SELECT r.article,r.ord,v.digest FROM revisions r JOIN versions v
            ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?""",(g,)).fetchone()
        raw,_,_=read_receipt(db,Receipt(c,g,a,i,d.hex()))
        if sha(raw)!=d:raise ValueError("receipt source mismatch")
        rows.append(dict(g=g,article=a,ordinal=i,source_sha256=d.hex(),score_hex=s.hex()))
    body=dict(format=FORMAT,scorer=SCORER,cutoff=c,phrases=list(phrases),op=op,k=10,
              prefix_sha256=prefix.hex(),active_documents=n,active_tokens=total,phrase_df=df,hits=rows)
    return body,sha(canonical(body)).hex()

def replay(db,body,digest):
    if sha(canonical(body)).hex()!=digest:raise ValueError("commitment mismatch")
    got,h=issue(db,body["phrases"],body["op"],body["cutoff"])
    if got!=body or h!=digest:raise ValueError("active rank receipt mismatch")

def crash_audit(folder,ext):
    results=[]
    script=HERE.parent/"round-119"/"atomic_receipts.py"
    for stage in STAGES:
        path=folder/("crash-"+stage+".sqlite")
        db=setup(path,ext);append_atomic(db,"fixture",b"old word "*80);db.close()
        p=subprocess.run([sys.executable,str(script),"--crash",str(path),str(ext),stage],capture_output=True,timeout=30)
        if p.returncode!=77:raise AssertionError("fault not reached "+str(p.stderr[-500:]))
        db=connect(path,ext);db.execute("BEGIN");n=2 if stage=="commit" else 1
        if audit(db)!=n:raise AssertionError("partial active state")
        body,_=issue(db,("new",),"AND",n)
        if bool(body["hits"])!=(stage=="commit"):raise AssertionError("wrong active hits")
        db.rollback()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AssertionError("integrity")
        db.close();results.append(stage)
    return results

def run_experiment(folder,events,ext,repeats):
    path=folder/"active.sqlite";db=setup(path,ext)
    n=len(events);cuts=sorted(set(max(1,n*k//4) for k in range(1,5)))
    first=cuts[0]
    for a,i,raw in events[:first]:
        if append_atomic(db,a,raw)[1]!=i:raise AssertionError("ordinal")
    reader=connect(path,ext);reader.execute("BEGIN")
    if audit(reader)!=first:raise AssertionError("prefix")
    ref=active_oracle(events,first)
    queries=plan_queries(ref)
    if not queries:raise ValueError("empty query plan")
    ref.execute("CREATE VIRTUAL TABLE temp.active_vocab USING fts5vocab(main,fulltext,'row')")
    common=[t for t, in ref.execute("SELECT term FROM temp.active_vocab ORDER BY doc DESC,term LIMIT 8")]
    for t in common:
        if ((t,),"AND") not in queries:queries.append(((t,),"AND"))
    receipts=[]
    for p,op in queries:
        body,d=issue(reader,p,op,first)
        verify([(h["g"],float.fromhex(h["score_hex"])) for h in body["hits"]],native(ref,p,op))
        receipts.append((body,d))
    ref.close()
    for a,i,raw in events[first:]:
        if append_atomic(db,a,raw)[1]!=i:raise AssertionError("ordinal")
    if generation(reader)!=first:raise AssertionError("pinned generation")
    for b,d in receipts:replay(reader,b,d)
    reader.rollback();reader.close()
    if audit(db)!=n:raise AssertionError("final audit")
    db.execute("BEGIN")
    for b,d in receipts:replay(db,b,d)
    lengths,totals=load_ledger(db,n);rng=random.Random(120);results=[]
    for c in cuts:
        pth=folder/("native-"+str(c)+".sqlite");ref=active_oracle(events,c,pth)
        prepared=prepare(db,c,lengths)
        interval=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
        if tuple(prepared[1:])!=interval:raise AssertionError("active total")
        maxerr={m:0.0 for m in METHODS};naive_rank=naive_any=hits=0
        old_rows=active_rows=0
        for phrases,op in queries:
            expected=native(ref,phrases,op);hits+=len(expected)
            for method in METHODS[:-1]:
                got=rank(db,phrases,op,c,lengths,method,prepared)[0]
                maxerr[method]=max(maxerr[method],verify(got,expected))
            for p in phrases:
                full=counts(db,p,lengths,c);active=interval_counts(db,p,c,lengths)
                if active!={g:tf for g,tf in full.items() if g in prepared[0]}:raise AssertionError("active frequency mismatch")
                old_rows+=len(full);active_rows+=len(active)
            # R117/119 historical all-prefix statistics with active candidates.
            from rank_replay import rank_counts
            freq=[counts(db,p,lengths,c) for p in phrases]
            naive=rank_counts(freq,op,c,lengths,totals,prepared[0])
            if [g for g,_ in naive]!=[g for g,_ in expected]:naive_rank+=1
            if naive!=expected:naive_any+=1
        timings={m:[] for m in METHODS}
        common_times={m:[] for m in METHODS}
        for _ in range(repeats):
            req=list(queries);rng.shuffle(req)
            for phrases,op in req:
                methods=list(METHODS);rng.shuffle(methods)
                for method in methods:
                    start=time.perf_counter_ns()
                    if method=="native":native(ref,phrases,op)
                    else:rank(db,phrases,op,c,lengths,method,prepared)
                    us=(time.perf_counter_ns()-start)/1000
                    timings[method].append(us)
                    if len(phrases)==1 and phrases[0] in common:common_times[method].append(us)
        results.append(dict(cutoff=c,active_documents=prepared[1],active_tokens=prepared[2],
            query_checks=len(queries),ranked_hits=hits,max_error=maxerr,
            naive_rank_changes=naive_rank,naive_score_or_rank_changes=naive_any,
            prefix_phrase_match_rows=old_rows,active_phrase_match_rows=active_rows,
            active_native_index_bytes=pth.stat().st_size,
            warm_median_us={m:statistics.median(t) for m,t in timings.items()},
            warm_p95_us={m:sorted(t)[int(.95*(len(t)-1))] for m,t in timings.items()},
            common_median_us={m:statistics.median(t) for m,t in common_times.items() if t}))
        ref.close()
    for g,(a,i,raw) in enumerate(events,1):
        if read_receipt(db,Receipt(n,g,a,i,sha(raw).hex()))[0]!=raw:raise AssertionError("source")
    db.rollback()
    metrics=finalize(db,path)
    basepath=folder/"base.sqlite";base=base_setup(basepath,ext)
    for a,i,raw in events:
        if append_atomic(base,a,raw)[1]!=i:raise AssertionError("baseline ordinal")
    baseline=finalize(base,basepath)
    return dict(revisions=n,queries_per_cutoff=len(queries),receipts_replayed_pinned=len(receipts),
        receipts_replayed_fresh=len(receipts),all_source_readbacks=n,cutoffs=results,
        atomic_intervals=metrics,base_atomic_ledger=baseline,crash_stages_passed=crash_audit(folder,ext),repetitions=repeats)

def run(root,ext,repeats):
    articles,manifest=load(root);cohort=select(articles,len(articles),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=run_experiment(Path(tmp),order(cohort),ext,repeats)
    return dict(round=120,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),
        result=r,limitations=["all existing processed Versions articles, not fresh holdout",
        "synthetic cross-article ingestion order; no deletions or timestamped workload",
        "single column Unicode61 exact phrase AND/OR; all eligible candidates enumerated",
        "interval filtering is result cardinality not internal posting I/O",
        "prepared head set excludes once-per-cutoff preparation; scan includes it",
        "warm rank-only single CI machine; receipt reconstruction not timed",
        "process death not power loss; receipt digest not authenticated",
        "native copies are simple controls; interval temporal search established prior art"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
