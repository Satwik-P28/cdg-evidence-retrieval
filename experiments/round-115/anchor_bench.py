"""R115: causal one-hop anchors versus previous-version delta chains.
Uses actual processed revision bytes; no query index or real access logs.
"""
import argparse, hashlib, json, random, sqlite3, statistics, sys, tempfile, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-114"))
from revision_bench import C,D,PIN,sha,delta_encode,delta_decode,load,select

POLICIES=("snapshot","prev2","prev4","prev8","anchor4","anchor8","bounded_anchor")
SALT="CDG-R114-independent-v1"

def setup(path):
    db=sqlite3.connect(path)
    db.execute("PRAGMA page_size=4096")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""CREATE TABLE versions(
      article TEXT NOT NULL, ord INTEGER NOT NULL CHECK(ord>=0),
      n INTEGER NOT NULL CHECK(n>=0), digest BLOB NOT NULL CHECK(length(digest)=32),
      depth INTEGER NOT NULL CHECK(depth BETWEEN 0 AND 8), parent_ord INTEGER,
      payload BLOB NOT NULL,
      CHECK((depth=0 AND parent_ord IS NULL) OR (depth>0 AND parent_ord>=0 AND parent_ord<ord)),
      PRIMARY KEY(article,ord),
      FOREIGN KEY(article,parent_ord) REFERENCES versions(article,ord)
    ) WITHOUT ROWID""")
    db.commit()
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    return db

def choose(raw,i,history,policy):
    """Each previous history tuple is (raw, compressed-size, depth).
    No future revision or query weight is consulted."""
    full=C.compress(raw)
    if not history or policy=="snapshot":
        return None,0,full
    if policy.startswith("prev"):
        last=history[-1]
        if last[2]<int(policy[4:]):
            diff=delta_encode(raw,last[0])
            if diff is not None and len(diff)<len(full):
                return i-1,last[2]+1,diff
    elif policy.startswith("anchor") or policy=="bounded_anchor":
        anchors=[j for j in range(i-1,-1,-1) if history[j][2]==0]
        if policy=="bounded_anchor":
            feasible=[]
            for j in anchors[:4]:
                old,encoded,_=history[j]
                # Exact logical activation bound relative to independent
                # compressed snapshot, plus decoded-source byte bound.
                if 2*(len(old)+len(raw))>5*len(raw): continue
                diff=delta_encode(raw,old)
                if diff is None: continue
                if 5*len(diff)<=4*len(full) and 2*(encoded+len(diff))<=3*len(full):
                    feasible.append((len(diff),-j,diff))
            if feasible:
                _,neg,payload=min(feasible)
                return -neg,1,payload
        elif anchors and i-anchors[0]<=int(policy[6:]):
            j=anchors[0]
            diff=delta_encode(raw,history[j][0])
            if diff is not None and len(diff)<len(full):
                return j,1,diff
    else:
        raise ValueError("invalid policy")
    return None,0,full

def recover(db,title,i,expected=None):
    row=db.execute("SELECT n,digest,depth,parent_ord,payload FROM versions WHERE article=? AND ord=?",(title,i)).fetchone()
    if row is None: raise ValueError("missing dependency")
    n,digest,depth,parent,payload=row
    if not 0<=depth<=8 or (expected is not None and depth!=expected):
        raise ValueError("invalid dependency depth")
    if depth==0:
        if parent is not None: raise ValueError("snapshot with parent")
        raw=D.decompress(payload,max_output_size=n+1)
        a=len(payload); d=len(raw)
    else:
        if parent is None or not 0<=parent<i: raise ValueError("invalid parent")
        base,a,d,_=recover(db,title,parent,depth-1)
        raw=delta_decode(payload,base,n)
        a+=len(payload); d+=len(raw)
    if len(raw)!=n or sha(raw)!=digest: raise ValueError("source receipt mismatch")
    return raw,a,d,depth

def benchmark(path,articles,policy):
    if policy not in POLICIES: raise ValueError("unknown policy")
    db=setup(path)
    refs=[]
    started=time.perf_counter()
    for title,versions in articles:
        history=[]
        for i,raw in enumerate(versions):
            parent,depth,payload=choose(raw,i,history,policy)
            with db:
                db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",
                           (title,i,len(raw),sha(raw),depth,parent,payload))
            history.append((raw,len(payload),depth))
            refs.append((title,i,raw))
    wal=Path(str(path)+"-wal").stat().st_size
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("VACUUM")
    physical=path.stat().st_size
    elapsed=time.perf_counter()-started
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise AssertionError("SQLite integrity")
    if db.execute("PRAGMA foreign_key_check").fetchall(): raise AssertionError("foreign keys")
    payload_bytes=db.execute("SELECT sum(length(payload)) FROM versions").fetchone()[0]
    depths=dict(db.execute("SELECT depth,count(*) FROM versions GROUP BY depth"))
    random.Random(115).shuffle(refs)
    raw_bytes=activation=decode_bytes=0
    max_activation=0.0; max_decode=0.0; timing=[]
    for title,i,want in refs:
        full=C.compress(want)
        t=time.perf_counter_ns()
        got,a,d,depth=recover(db,title,i)
        timing.append((time.perf_counter_ns()-t)/1000)
        if got!=want: raise AssertionError("incorrect historical source")
        if policy in ("anchor4","anchor8","bounded_anchor") and depth>1:
            raise AssertionError("one-hop guarantee")
        if policy=="bounded_anchor":
            if 2*a>3*len(full) or 2*d>5*len(want):
                raise AssertionError("logical activation bound failed")
        raw_bytes+=len(want); activation+=a; decode_bytes+=d
        max_activation=max(max_activation,a/len(full))
        if want: max_decode=max(max_decode,d/len(want))
    db.close()
    return {"sqlite_bytes":physical,"payload_bytes":payload_bytes,
        "wal_bytes":wal,"versions":len(refs),"raw_bytes":raw_bytes,
        "activated_compressed_bytes":activation,"decoded_source_bytes":decode_bytes,
        "decode_amplification":decode_bytes/max(1,raw_bytes),
        "max_activation_relative_to_snapshot_frame":max_activation,
        "max_decode_relative_to_requested_nonempty_revision":max_decode,
        "max_dependency_depth":max(depths),"depth_counts":depths,
        "median_warm_lookup_us_exploratory":statistics.median(timing),
        "p95_warm_lookup_us_exploratory":sorted(timing)[int(.95*(len(timing)-1))],
        "build_seconds_exploratory":elapsed,"all_exact":True}

def run(root,n=100):
    articles,manifest=load(root)
    ordered=select(articles,2*n,SALT)
    if len(ordered)!=2*n: raise ValueError("insufficient articles for disjoint cohorts")
    out={"round":115,"upstream_commit":PIN,"full_corpus_sha256":manifest,
         "selection_salt":SALT,
         "cohorts":{},
         "limitations":["processed sampled Wikipedia texts; within-article order only",
                        "first cohort is R114 development sample; second article-disjoint sample not independent corpus",
                        "logical payload read bounds are not disk I/O, latency, or SQLite page bounds",
                        "synthetic equal-weight read order; no actual access history or timestamps",
                        "same SQLite schema across policies; no search index or RAG outcomes",
                        "anchor and base-selection methods are established prior art, not WikECD reproduction",
                        "source SHA checks detect accidental inconsistency, not malicious rewrite of all trusted metadata"]}
    with tempfile.TemporaryDirectory() as tmp:
        for name,cohort in (("development",ordered[:n]),("article_disjoint",ordered[n:])):
            data={"articles":len(cohort),"revisions":sum(len(v) for _,v in cohort),
                  "article_sha256":sha("\n".join(t for t,_ in cohort).encode()).hex(),"policies":{}}
            for policy in POLICIES:
                data["policies"][policy]=benchmark(Path(tmp)/(name+"-"+policy+".sqlite"),cohort,policy)
                print(name,policy,json.dumps(data["policies"][policy]),flush=True)
            out["cohorts"][name]=data
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--articles-per-cohort",type=int,default=100)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.articles_per_cohort<1: p.error("positive sample required")
    a.out.write_text(json.dumps(run(a.root,a.articles_per_cohort),indent=2,sort_keys=True)+"\n")
