"""R116: atomic source + historical FTS5 + version-bound evidence receipts.
The ingestion generation is a synthetic round-robin order preserving each
article's observed revision order, not historical wall-clock time.
"""
import argparse, hashlib, json, os, random, sqlite3, subprocess, sys, tempfile
from pathlib import Path
from dataclasses import dataclass, replace, asdict
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-115"))
from anchor_bench import choose,recover,setup as setup_archive,C,PIN,sha,load,select

POLICIES=("snapshot","prev2","bounded_anchor")
SALT="CDG-R114-independent-v1"
QUERY_SALT="CDG-R116-prefix-queries-v1"

def setup(path):
    db=setup_archive(path)
    db.executescript("""
    CREATE TABLE meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                      generation INTEGER NOT NULL CHECK(generation>=0));
    INSERT INTO meta VALUES(1,0);
    CREATE TABLE revisions(generation INTEGER PRIMARY KEY CHECK(generation>0),
      article TEXT NOT NULL, ord INTEGER NOT NULL,
      UNIQUE(article,ord),
      FOREIGN KEY(article,ord) REFERENCES versions(article,ord));
    CREATE TABLE heads(article TEXT PRIMARY KEY, ord INTEGER NOT NULL,
      FOREIGN KEY(article,ord) REFERENCES versions(article,ord)) WITHOUT ROWID;
    CREATE VIRTUAL TABLE docs USING fts5(body, content='');
    """)
    db.commit()
    return db

def connect(path):
    db=sqlite3.connect(path,timeout=15)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    return db

def generation(db):
    return db.execute("SELECT generation FROM meta WHERE singleton=1").fetchone()[0]

def die(stage,fault):
    if stage==fault:
        os._exit(77)

def append(db,article,raw,policy,fault=None):
    if db.in_transaction: raise ValueError("nested writer")
    text=raw.decode("utf8",errors="strict")
    db.execute("BEGIN IMMEDIATE")
    try:
        rows=db.execute("SELECT ord,length(payload),depth FROM versions WHERE article=? ORDER BY ord",(article,)).fetchall()
        history=[]
        for i,(ord_,size,depth) in enumerate(rows):
            if ord_!=i: raise ValueError("non-contiguous version sequence")
            old,_,_,actual_depth=recover(db,article,i)
            if actual_depth!=depth: raise ValueError("invalid historical depth")
            history.append((old,size,depth))
        i=len(history); g=generation(db)+1
        parent,depth,payload=choose(raw,i,history,policy)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(article,i,len(raw),sha(raw),depth,parent,payload))
        die("source",fault)
        db.execute("INSERT INTO revisions VALUES(?,?,?)",(g,article,i))
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,text))
        die("index",fault)
        db.execute("INSERT INTO heads VALUES(?,?) ON CONFLICT(article) DO UPDATE SET ord=excluded.ord",(article,i))
        db.execute("UPDATE meta SET generation=? WHERE singleton=1",(g,))
        die("meta",fault)
        db.commit()
        die("commit",fault)
        return g,i
    except BaseException:
        db.rollback()
        raise

@dataclass(frozen=True)
class Receipt:
    observed_generation:int
    indexed_generation:int
    article:str
    ordinal:int
    digest:str

def require_snapshot(db):
    if not db.in_transaction: raise ValueError("explicit reader transaction required")

def search(db,query,scope="all",cutoff=None,k=10):
    require_snapshot(db)
    g=generation(db)
    if scope not in ("all","heads"): raise ValueError("bad scope")
    if cutoff is not None and (cutoff<0 or cutoff>g): raise ValueError("bad cutoff")
    c=g if cutoff is None else cutoff
    sql="""SELECT r.generation,r.article,r.ord,bm25(docs),v.digest
           FROM docs JOIN revisions r ON r.generation=docs.rowid
           JOIN versions v ON v.article=r.article AND v.ord=r.ord
           WHERE docs MATCH ? AND r.generation<=?"""
    if scope=="heads":
        sql+=" AND NOT EXISTS(SELECT 1 FROM revisions newer WHERE newer.article=r.article AND newer.ord>r.ord AND newer.generation<=?)"
    sql+=" ORDER BY bm25(docs),r.generation LIMIT ?"
    args=(query,c,k) if scope=="all" else (query,c,c,k)
    return [(Receipt(g,int(r),a,int(i),bytes(d).hex()),float(score)) for r,a,i,score,d in db.execute(sql,args)]

def read_receipt(db,receipt):
    require_snapshot(db)
    g=generation(db)
    if not 1<=receipt.indexed_generation<=receipt.observed_generation<=g:
        raise ValueError("receipt generation invalid")
    row=db.execute("SELECT r.article,r.ord,v.digest FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord WHERE r.generation=?",(receipt.indexed_generation,)).fetchone()
    if row is None or (row[0],row[1],bytes(row[2]).hex())!=(receipt.article,receipt.ordinal,receipt.digest):
        raise ValueError("receipt identity mismatch")
    raw,a,d,_=recover(db,receipt.article,receipt.ordinal)
    if sha(raw).hex()!=receipt.digest: raise ValueError("receipt hash mismatch")
    return raw,a,d

def order(articles):
    # A deterministic ingestion schedule, NOT global original edit time.
    return [(a,i,v[i]) for i in range(max(len(v) for _,v in articles)) for a,v in articles if i<len(v)]

def oracle(events):
    db=sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE fulltext USING fts5(body)")
    db.execute("CREATE TABLE versions(g INTEGER PRIMARY KEY, article TEXT, ord INTEGER)")
    db.executemany("INSERT INTO fulltext(rowid,body) VALUES(?,?)",
                   ((g,raw.decode("utf8")) for g,(_,_,raw) in enumerate(events,1)))
    db.executemany("INSERT INTO versions VALUES(?,?,?)",
                   ((g,a,i) for g,(a,i,_) in enumerate(events,1)))
    db.commit()
    return db

def control(db,q,scope,k=10):
    sql="SELECT v.g,bm25(fulltext) FROM fulltext JOIN versions v ON v.g=fulltext.rowid WHERE fulltext MATCH ?"
    if scope=="heads":
        sql+=" AND NOT EXISTS(SELECT 1 FROM versions newer WHERE newer.article=v.article AND newer.ord>v.ord)"
    return db.execute(sql+" ORDER BY bm25(fulltext),v.g LIMIT ?",(q,k)).fetchall()

def plan(db):
    # Fixed hash-minimal terms, two DF bands, and genuine adjacent-token phrases.
    db.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(fulltext,'row')")
    rows=db.execute("SELECT term,doc FROM vocab WHERE doc>=2").fetchall()
    def key(x): return sha((QUERY_SALT+"|"+x).encode())
    quote=lambda x:'"'+x.replace('"','""')+'"'
    terms=[]
    for lo,hi in ((2,10),(11,10**9)):
        terms.extend(sorted((t for t,df in rows if lo<=df<=hi),key=key)[:24])
    db.execute("CREATE VIRTUAL TABLE inst USING fts5vocab(fulltext,'instance')")
    phrases=set()
    last=None
    for t,doc,pos in db.execute("SELECT term,doc,offset FROM inst ORDER BY doc,offset LIMIT 100000"):
        if last and doc==last[1] and pos==last[2]+1: phrases.add(last[0]+" "+t)
        last=(t,doc,pos)
    return [quote(t) for t in terms]+[quote(p) for p in sorted(phrases,key=key)[:16]]

def compare(db,reference,queries,events,policy):
    require_snapshot(db)
    count=reads=activated=decoded=requested=0
    maxerr=0.0
    for scope in ("all","heads"):
        for q in queries:
            got=search(db,q,scope)
            expected=control(reference,q,scope)
            if [r.indexed_generation for r,_ in got]!=[g for g,_ in expected]:
                raise AssertionError("rank identity mismatch")
            for (r,score),(_,expected_score) in zip(got,expected):
                maxerr=max(maxerr,abs(score-expected_score))
                if abs(score-expected_score)>1e-11: raise AssertionError("BM25 score mismatch")
                a,i,want=events[r.indexed_generation-1]
                raw,ab,dd=read_receipt(db,r)
                if (r.article,r.ordinal,raw)!=(a,i,want): raise AssertionError("receipt mismatch")
                if policy=="bounded_anchor" and (2*ab>3*len(C.compress(want)) or 2*dd>5*len(want)):
                    raise AssertionError("bounded receipt read failed")
                reads+=1; activated+=ab; decoded+=dd; requested+=len(want)
            count+=1
    return dict(queries=count,receipts=reads,activated_payload_bytes=activated,
                decoded_bytes=decoded,requested_bytes=requested,
                decode_amplification=decoded/max(1,requested),max_score_error=maxerr)

def rank_signature(results):
    return [(r.indexed_generation,s) for r,s in results]

def physical_audit(path,events,policy,queries,prefix):
    writer=setup(path)
    for a,i,raw in events[:prefix]:
        g,j=append(writer,a,raw,policy)
        if j!=i: raise AssertionError("ordinal drift")
    old=connect(path)
    old.execute("BEGIN")
    before=generation(old)
    ref_old=oracle(events[:prefix])
    first=compare(old,ref_old,queries,events,policy)
    pinned=[rank_signature(search(old,q)) for q in queries]
    receipts=[r for q in queries for r,_ in search(old,q)]
    for a,i,raw in events[prefix:]:
        g,j=append(writer,a,raw,policy)
        if j!=i: raise AssertionError("ordinal drift")
    if generation(old)!=before or [rank_signature(search(old,q)) for q in queries]!=pinned:
        raise AssertionError("reader snapshot drift")
    for r in receipts: read_receipt(old,r)
    old.rollback(); old.close()
    reader=connect(path); reader.execute("BEGIN")
    ref_new=oracle(events)
    final=compare(reader,ref_new,queries,events,policy)
    for r in receipts:
        raw,_,_=read_receipt(reader,r)
        if raw!=events[r.indexed_generation-1][2]: raise AssertionError("stale receipt drift")
    rank_changes=score_changes=0
    for q,prior in zip(queries,pinned):
        filtered=rank_signature(search(reader,q,cutoff=before))
        if [g for g,_ in filtered]!=[g for g,_ in prior]: rank_changes+=1
        if len(filtered)!=len(prior) or any(g!=h or abs(s-t)>1e-11 for (g,s),(h,t) in zip(filtered,prior)): score_changes+=1
    for g,(a,i,raw) in enumerate(events,1):
        r=Receipt(len(events),g,a,i,sha(raw).hex())
        got,_,_=read_receipt(reader,r)
        if got!=raw: raise AssertionError("full archive readback mismatch")
    reader.rollback(); reader.close(); ref_old.close(); ref_new.close()
    if writer.execute("PRAGMA foreign_key_check").fetchall(): raise AssertionError("foreign key error")
    if writer.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise AssertionError("SQLite integrity")
    writer.execute("INSERT INTO docs(docs) VALUES('integrity-check')")
    writer.commit()
    wal=Path(str(path)+"-wal").stat().st_size
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.execute("PRAGMA journal_mode=DELETE")
    writer.execute("VACUUM")
    size=path.stat().st_size
    payload=writer.execute("SELECT sum(length(payload)) FROM versions").fetchone()[0]
    writer.close()
    return dict(sqlite_bytes=size,source_payload_bytes=payload,wal_bytes=wal,
                initial_generation=before,final_generation=len(events),
                prefix=first,final=final,pinned_queries=len(queries),
                old_receipts_replayed=len(receipts),all_revision_readbacks=len(events),
                historical_cutoff_rank_changes=rank_changes,historical_cutoff_score_or_rank_changes=score_changes)

def crash_audit(folder,policy):
    checks=[]
    for stage in ("source","index","meta","commit"):
        path=folder/(policy+"-"+stage+".sqlite")
        db=setup(path); append(db,"fixture",b"oldword common "*100,policy); db.close()
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--crash",str(path),policy,stage],capture_output=True,timeout=30)
        if result.returncode!=77: raise AssertionError("fault not reached "+str(result.stderr[-500:]))
        db=connect(path); db.execute("BEGIN")
        committed=stage=="commit"
        g=2 if committed else 1
        if generation(db)!=g: raise AssertionError("generation after crash")
        for table in ("versions","revisions","docs"):
            if db.execute("SELECT count(*) FROM "+table).fetchone()[0]!=g: raise AssertionError("partial rows after crash "+table)
        if db.execute("SELECT ord FROM heads WHERE article='fixture'").fetchone()[0]!=g-1: raise AssertionError("head after crash")
        matches=search(db,'"newword"')
        if len(matches)!=int(committed): raise AssertionError("partial FTS after crash")
        if committed and read_receipt(db,matches[0][0])[0]!=b"newword common "*100: raise AssertionError("committed source lost")
        db.rollback()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise AssertionError("post-crash integrity")
        db.close()
        checks.append(stage)
    return checks

def run(root,n):
    articles,manifest=load(root)
    # Third disjoint sample, after R114/115 development + evaluation.
    ranked=select(articles,200+n,SALT)
    if len(ranked)<200+n: raise ValueError("not enough disjoint articles")
    cohort=ranked[200:]
    events=order(cohort)
    prefix=max(1,len(events)//2)
    ref=oracle(events[:prefix]); queries=plan(ref); ref.close()
    if not queries: raise ValueError("empty query plan")
    result={"round":116,"upstream_commit":PIN,"full_corpus_sha256":manifest,
      "articles":n,"revisions":len(events),"prefix":prefix,"query_count":len(queries),
      "article_sha256":sha("\n".join(a for a,_ in cohort).encode()).hex(),"policies":{},
      "limits":["filtered processed source revisions; article-local chronology only",
      "synthetic round-robin global ingestion order and deterministic lexical/phrase probes",
      "heads filter retains whole historical index BM25 corpus statistics, not head-only statistics",
      "no power-loss or adversarial database integrity guarantee; os._exit process crashes",
      "cutoff filtering is not historical rank reconstruction; score drift is measured",
      "same full positional contentless FTS5 for all policies, no RAG quality claim"]}
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        for policy in POLICIES:
            result["policies"][policy]=physical_audit(folder/(policy+".sqlite"),events,policy,queries,prefix)
            result["policies"][policy]["crash_stages_passed"]=crash_audit(folder,policy)
    return result

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,path,policy,stage=sys.argv
        db=connect(path); append(db,"fixture",b"newword common "*100,policy,stage)
        raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--articles",type=int,default=100);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();result=run(a.root,a.articles)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(result,separators=(",",":")),flush=True)
