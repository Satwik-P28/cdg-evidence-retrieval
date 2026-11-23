"""R119: atomic native token ledger and reproducible historical rank receipts.
Receipt hashes are consistency commitments, not signatures or trust anchors.
"""
import argparse, hashlib, json, os, sqlite3, subprocess, sys, tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-118"))
from native_compare import extension,counts
from rank_replay import (load_ledger,rank_counts,expression,heads,plan_queries,verify,
    generation,oracle,control,order,load,select,SALT,PIN,sha,Receipt,read_receipt)
from versioned_evidence import setup as base_setup,append as base_append,connect as base_connect,choose,recover

POLICY="bounded_anchor"
FORMAT="cdg-rank-receipt-v1"
SCORER="sqlite-fts5-unicode61-one-column-unweighted-bm25-prefix-k1=1.2-b=.75"
SEED=sha(b"CDG-R119-prefix-commitment-v1")
STAGES=("source","index","ledger","meta","commit")

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")

def chain(previous,g,article,ordinal,digest,dl,total):
    return sha(b"CDG-R119-entry-v1\0"+previous+canonical([g,article,ordinal,digest.hex(),dl,total]))

def setup(path,ext):
    db=base_setup(path)
    extension(db,ext)
    db.execute("""CREATE TABLE rank_ledger(
        g INTEGER PRIMARY KEY REFERENCES revisions(generation),
        dl INTEGER NOT NULL CHECK(dl>=0),
        total INTEGER NOT NULL CHECK(total>=dl),
        prefix_sha BLOB NOT NULL CHECK(length(prefix_sha)=32)
    )""")
    db.commit()
    return db

def connect(path,ext):
    db=base_connect(path);extension(db,ext)
    return db

def die(stage,fault):
    if stage==fault:os._exit(77)

def append_atomic(db,article,raw,fault=None):
    if db.in_transaction:raise ValueError("nested writer")
    text=raw.decode("utf8",errors="strict")
    db.execute("BEGIN IMMEDIATE")
    try:
        prior=generation(db);g=prior+1
        row=db.execute("SELECT total,prefix_sha FROM rank_ledger WHERE g=?",(prior,)).fetchone()
        if prior:
            if row is None:raise ValueError("missing previous ledger")
            prev_total,prev_hash=row
        else:
            if row is not None:raise ValueError("unexpected zero ledger")
            prev_total,prev_hash=0,SEED
        history=[]
        for i,(ordinal,n,depth) in enumerate(db.execute("SELECT ord,length(payload),depth FROM versions WHERE article=? ORDER BY ord",(article,)).fetchall()):
            if ordinal!=i:raise ValueError("noncontiguous revision")
            old,_,_,d=recover(db,article,i)
            if d!=depth:raise ValueError("history depth")
            history.append((old,n,depth))
        i=len(history);parent,depth,payload=choose(raw,i,history,POLICY);digest=sha(raw)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(article,i,len(raw),digest,depth,parent,payload))
        die("source",fault)
        db.execute("INSERT INTO revisions VALUES(?,?,?)",(g,article,i))
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text))
        die("index",fault)
        dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0]
        total=prev_total+dl
        prefix=chain(prev_hash,g,article,i,digest,dl,total)
        db.execute("INSERT INTO rank_ledger VALUES(?,?,?,?)",(g,dl,total,prefix))
        die("ledger",fault)
        db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(article) DO UPDATE SET ord=excluded.ord",(article,i))
        db.execute("UPDATE meta SET generation=? WHERE singleton=1",(g,))
        die("meta",fault)
        db.commit()
        die("commit",fault)
        return g,i
    except BaseException:
        db.rollback();raise

def audit_ledger(db):
    """Independent indexed token counts + complete chain audit."""
    n=generation(db)
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.audit_vocab USING fts5vocab(main,docs,'instance')")
    actual=dict(db.execute("SELECT doc,count(*) FROM temp.audit_vocab GROUP BY doc"))
    rows=db.execute("""SELECT l.g,l.dl,l.total,l.prefix_sha,r.article,r.ord,v.digest
        FROM rank_ledger l JOIN revisions r ON r.generation=l.g
        JOIN versions v ON v.article=r.article AND v.ord=r.ord ORDER BY l.g""").fetchall()
    total=0;prior=SEED
    if len(rows)!=n:raise ValueError("ledger cardinality")
    for expected,(g,dl,cumulative,prefix,a,i,digest) in enumerate(rows,1):
        total+=dl
        if g!=expected or dl!=actual.get(g,0) or cumulative!=total:raise ValueError("ledger length mismatch")
        prior=chain(prior,g,a,i,digest,dl,total)
        if prefix!=prior:raise ValueError("prefix chain mismatch")
    for table in ("docs","versions","revisions","rank_ledger"):
        if db.execute("SELECT count(*) FROM "+table).fetchone()[0]!=n:raise ValueError("partial archive "+table)
    if db.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("foreign key")
    return n

def issue(db,phrases,op,cutoff,scope):
    if not db.in_transaction:raise ValueError("explicit reader transaction required")
    n=generation(db)
    if not 1<=cutoff<=n or scope not in ("all","heads"):raise ValueError("invalid historical request")
    expression(phrases,op)
    lengths,totals=load_ledger(db,n)
    prefix=db.execute("SELECT prefix_sha FROM rank_ledger WHERE g=?",(cutoff,)).fetchone()
    if prefix is None:raise ValueError("missing prefix")
    freq=[counts(db,p,lengths,cutoff) for p in phrases]
    allowed=None if scope=="all" else heads(db,cutoff)
    ranked=rank_counts(freq,op,cutoff,lengths,totals,allowed)
    hits=[]
    for g,score in ranked:
        a,i,digest=db.execute("""SELECT r.article,r.ord,v.digest FROM revisions r
          JOIN versions v ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?""",(g,)).fetchone()
        # Bind the ranking to exact reconstructed sources, not just row IDs.
        rec=Receipt(cutoff,g,a,i,digest.hex())
        raw,_,_=read_receipt(db,rec)
        if sha(raw)!=digest:raise ValueError("rank receipt source mismatch")
        hits.append({"generation":g,"article":a,"ordinal":i,"source_sha256":digest.hex(),
                    "score_hex":score.hex()})
    body={"format":FORMAT,"scorer":SCORER,"cutoff":cutoff,"scope":scope,"phrases":list(phrases),
        "op":op,"k":10,"prefix_sha256":prefix[0].hex(),"documents":cutoff,
        "total_tokens":totals[cutoff],"phrase_df":[len(m) for m in freq],"hits":hits}
    return body,sha(canonical(body)).hex()

def replay(db,body,expected_digest):
    if not isinstance(expected_digest,str) or sha(canonical(body)).hex()!=expected_digest:
        raise ValueError("receipt commitment mismatch")
    actual,digest=issue(db,body["phrases"],body["op"],body["cutoff"],body["scope"])
    if digest!=expected_digest or actual!=body:raise ValueError("receipt replay mismatch")
    return actual

def signature(body):
    return [(h["generation"],float.fromhex(h["score_hex"])) for h in body["hits"]]

def finalize(db,path):
    wal=Path(str(path)+"-wal").stat().st_size
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("VACUUM")
    size=path.stat().st_size
    db.close()
    return {"sqlite_bytes":size,"wal_bytes_before_checkpoint":wal}

def crash_audit(folder,ext):
    checks=[]
    for stage in STAGES:
        path=folder/("crash-"+stage+".sqlite")
        db=setup(path,ext);append_atomic(db,"fixture",b"old word "*80);db.close()
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--crash",str(path),str(ext),stage],
                         timeout=30,capture_output=True)
        if p.returncode!=77:raise AssertionError("fault not reached "+str(p.stderr[-500:]))
        db=connect(path,ext);db.execute("BEGIN")
        committed=stage=="commit";n=2 if committed else 1
        if generation(db)!=n or audit_ledger(db)!=n:raise AssertionError("partial ledger after death")
        h=db.execute("SELECT ord FROM heads WHERE article='fixture'").fetchone()[0]
        if h!=n-1:raise AssertionError("partial head")
        body,_=issue(db,("new",),"AND",n,"heads")
        if len(body["hits"])!=int(committed):raise AssertionError("partial index")
        db.rollback()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AssertionError("SQLite integrity")
        db.close();checks.append(stage)
    return checks

def experiment(folder,events,ext):
    path=folder/"atomic.sqlite";writer=setup(path,ext)
    prefix=max(1,len(events)//2)
    for a,i,raw in events[:prefix]:
        _,ord_=append_atomic(writer,a,raw)
        if i!=ord_:raise AssertionError("wrong ordinal")
    old=connect(path,ext);old.execute("BEGIN")
    if generation(old)!=prefix or audit_ledger(old)!=prefix:raise AssertionError("prefix audit")
    ref=oracle(events[:prefix]);queries=plan_queries(ref)
    if not queries:raise ValueError("empty query set")
    receipts=[];maxerr=0.;hits=0
    for scope in ("all","heads"):
        for phrases,op in queries:
            body,digest=issue(old,phrases,op,prefix,scope)
            maxerr=max(maxerr,verify(signature(body),control(ref,expression(phrases,op),scope)))
            receipts.append((body,digest));hits+=len(body["hits"])
    ref.close()
    for a,i,raw in events[prefix:]:
        _,ord_=append_atomic(writer,a,raw)
        if i!=ord_:raise AssertionError("wrong ordinal")
    if generation(old)!=prefix:raise AssertionError("pinned snapshot drift")
    for body,digest in receipts:replay(old,body,digest)
    old.rollback();old.close()
    fresh=connect(path,ext);fresh.execute("BEGIN")
    n=len(events)
    if generation(fresh)!=n or audit_ledger(fresh)!=n:raise AssertionError("final audit")
    for body,digest in receipts:replay(fresh,body,digest)
    final=oracle(events);final_hits=0
    for scope in ("all","heads"):
        for phrases,op in queries:
            body,_=issue(fresh,phrases,op,n,scope)
            maxerr=max(maxerr,verify(signature(body),control(final,expression(phrases,op),scope)))
            final_hits+=len(body["hits"])
    final.close()
    for g,(a,i,raw) in enumerate(events,1):
        source,_,_=read_receipt(fresh,Receipt(n,g,a,i,sha(raw).hex()))
        if source!=raw:raise AssertionError("original bytes drift")
    fresh.rollback();fresh.close()
    atomic=finalize(writer,path)
    basepath=folder/"baseline.sqlite";base=base_setup(basepath)
    for a,i,raw in events:
        _,ord_=base_append(base,a,raw,POLICY)
        if i!=ord_:raise AssertionError("wrong baseline ordinal")
    baseline=finalize(base,basepath)
    return {"revisions":n,"prefix":prefix,"queries_per_scope":len(queries),
        "prefix_rank_receipts":len(receipts),"prefix_ranked_hits":hits,"final_ranked_hits":final_hits,
        "pinned_snapshot_receipt_replays":len(receipts),"later_snapshot_receipt_replays":len(receipts),
        "max_score_error":maxerr,"all_source_readbacks":n,"ledger_rows_audited":n,
        "receipt_body_bytes_external_not_persisted":sum(len(canonical(b)) for b,_ in receipts),
        "receipt_digest_bytes_external_not_persisted":sum(len(d)//2 for _,d in receipts),
        "atomic":atomic,"archive_without_ledger":baseline,"crash_stages_passed":crash_audit(folder,ext)}

def run(root,ext,n=45):
    articles,manifest=load(root);ranked=select(articles,400+n,SALT)
    if len(ranked)!=400+n:raise ValueError("not enough unused articles")
    cohort=ranked[400:]
    with tempfile.TemporaryDirectory() as tmp:result=experiment(Path(tmp),order(cohort),ext)
    return {"round":119,"upstream_commit":PIN,"full_corpus_sha256":manifest,"articles":len(cohort),
        "article_sha256":sha("\n".join(a for a,_ in cohort).encode()).hex(),"result":result,
        "limits":["last 45 unused hash-ranked articles in same processed Versions corpus, not a new corpus",
          "synthetic round-robin ingestion and prefix-generated queries, no actual time-stamped workload",
          "receipt digest is not a signature; requires separately trusted expected digest and scorer configuration",
          "replay assumes same scoring arithmetic, tokenization and append-only index; no arbitrary FTS syntax",
          "ledger hash chain audited, not authenticated storage or adversarial database proof",
          "receipt output bytes charged separately, not persisted in measured archive",
          "process death is not power loss; no device write or latency claims",
          "baseline has no replay ledger and is a marginal overhead comparator, not a feature-equivalent system"]}
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,path,ext,stage=sys.argv
        db=connect(path,ext);append_atomic(db,"fixture",b"new word "*80,stage)
        raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--articles",type=int,default=45);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.articles)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
