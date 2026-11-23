"""R114: byte-exact historical revision archive controls, on pinned processed
Wikipedia Versions corpus. Order within article is real; no timestamps or
observed accesses. Not a reproduction of WikECD.
"""
import argparse, hashlib, json, random, sqlite3, statistics, tempfile, time
from pathlib import Path
import zstandard as zstd

PIN = "06b32f753c4ac6fd154ffa8b5a9af2cd11b777c0"
POLICIES = ("snapshot", "delta2", "delta4", "delta8", "adaptive4",
            "fixed512", "fixed2048", "cdc1024")
C = zstd.ZstdCompressor(level=6)
D = zstd.ZstdDecompressor()
GEAR = [int.from_bytes(hashlib.sha256(bytes([i])).digest()[:8], "little") for i in range(256)]
MASK64 = (1 << 64) - 1

def sha(x):
    return hashlib.sha256(x).digest()

def partition(data, mode):
    if mode.startswith("fixed"):
        step = int(mode[5:])
        return [data[i:i+step] for i in range(0,len(data),step)]
    out = []
    start = h = 0
    for i,b in enumerate(data,1):
        h = ((h << 1) + GEAR[b]) & MASK64
        if i-start >= 4096 or (i-start >= 256 and h & 1023 == 0):
            out.append(data[start:i]); start=i; h=0
    if start < len(data):
        out.append(data[start:])
    return out

def delta_encode(raw, prev):
    # A previous-revision dictionary is a real Zstandard frame, not a
    # byte-count approximation or standalone self-contained snapshot.
    if not prev:
        return None
    dictionary = zstd.ZstdCompressionDict(prev, dict_type=zstd.DICT_TYPE_RAWCONTENT)
    return zstd.ZstdCompressor(level=6,dict_data=dictionary).compress(raw)

def delta_decode(payload, prev, n):
    dictionary = zstd.ZstdCompressionDict(prev, dict_type=zstd.DICT_TYPE_RAWCONTENT)
    return zstd.ZstdDecompressor(dict_data=dictionary).decompress(payload,max_output_size=n+1)

def load(root):
    articles=[]
    manifest=hashlib.sha256()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir(): continue
        files=sorted((f for f in folder.glob("*.txt") if f.stem.isdecimal()),key=lambda f:int(f.stem))
        if len(files)<2: continue
        revisions=[]
        for f in files:
            raw=f.read_bytes()
            rel=f.relative_to(root).as_posix().encode("utf8")
            manifest.update(len(rel).to_bytes(4,"little")+rel+sha(raw))
            revisions.append(raw)
        articles.append((folder.name,revisions))
    if not articles: raise ValueError("no revision articles")
    return articles,manifest.hexdigest()

def select(articles, n, salt):
    return sorted(articles,key=lambda a:(sha((salt+"|"+a[0]).encode()),a[0]))[:n]

def setup(path):
    db=sqlite3.connect(path)
    db.executescript("""
    PRAGMA page_size=4096;
    CREATE TABLE versions(article TEXT NOT NULL, ord INTEGER NOT NULL,
      n INTEGER NOT NULL, digest BLOB NOT NULL, mode INTEGER NOT NULL,
      depth INTEGER NOT NULL, payload BLOB NOT NULL,
      PRIMARY KEY(article,ord)) WITHOUT ROWID;
    CREATE TABLE chunks(digest BLOB PRIMARY KEY, n INTEGER NOT NULL,
      payload BLOB NOT NULL) WITHOUT ROWID;
    """)
    db.commit()
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    return db

def append(db, title, i, raw, prev, depth, chain_decoded, policy):
    full=C.compress(raw)
    mode=0; payload=full; new_depth=0; new_chain=len(raw)
    if policy.startswith("delta") or policy=="adaptive4":
        limit=4 if policy=="adaptive4" else int(policy[5:])
        if i and depth<limit:
            diff=delta_encode(raw,prev)
            # Adaptive uses only current/past raw bytes. Thresholds frozen.
            good=diff is not None and len(diff)<len(full)
            if policy=="adaptive4":
                good=good and len(diff)*2<=len(full) and chain_decoded+len(raw)<=3*max(1,len(raw))
            if good:
                mode=1; payload=diff; new_depth=depth+1; new_chain=chain_decoded+len(raw)
    with db:
        if policy.startswith("fixed") or policy=="cdc1024":
            mode=2; parts=partition(raw,policy)
            keys=[]
            for chunk in parts:
                key=sha(chunk); keys.append(key)
                db.execute("INSERT OR IGNORE INTO chunks VALUES(?,?,?)",(key,len(chunk),C.compress(chunk)))
            payload=b"".join(keys)
        db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",
                   (title,i,len(raw),sha(raw),mode,new_depth,payload))
    return new_depth,new_chain

def recover(db,title,i,expected_depth=None):
    if i<0: raise ValueError("invalid parent ordinal")
    row=db.execute("SELECT n,digest,mode,depth,payload FROM versions WHERE article=? AND ord=?",(title,i)).fetchone()
    if row is None: raise ValueError("missing revision")
    n,digest,mode,depth,payload=row
    if expected_depth is not None and depth!=expected_depth:
        raise ValueError("invalid dependency depth")
    activated=len(payload); decoded=0
    if mode==0:
        if depth: raise ValueError("invalid snapshot depth")
        raw=D.decompress(payload,max_output_size=n+1)
    elif mode==1:
        if not 1<=depth<=8: raise ValueError("invalid chain depth")
        prev,prior_bytes,prior_decoded=recover(db,title,i-1,depth-1)
        raw=delta_decode(payload,prev,n)
        activated+=prior_bytes; decoded+=prior_decoded
    elif mode==2:
        if depth or len(payload)%32: raise ValueError("invalid chunk manifest")
        parts=[]
        cache={}
        for j in range(0,len(payload),32):
            key=payload[j:j+32]
            if key not in cache:
                c=db.execute("SELECT n,payload FROM chunks WHERE digest=?",(key,)).fetchone()
                if c is None: raise ValueError("missing chunk")
                length,blob=c
                part=D.decompress(blob,max_output_size=length+1)
                if len(part)!=length or sha(part)!=key: raise ValueError("corrupt chunk")
                cache[key]=part; activated+=len(blob); decoded+=length
            parts.append(cache[key])
        raw=b"".join(parts)
    else: raise ValueError("invalid mode")
    if len(raw)!=n or sha(raw)!=digest: raise ValueError("source receipt mismatch")
    if mode!=2: decoded+=len(raw)
    return raw,activated,decoded

def benchmark(path,articles,policy):
    db=setup(path)
    start=time.perf_counter()
    refs=[]
    for title,revisions in articles:
        prev=b""; depth=chain=0
        for i,raw in enumerate(revisions):
            depth,chain=append(db,title,i,raw,prev,depth,chain,policy)
            refs.append((title,i,raw))
            prev=raw
    wal=Path(str(path)+"-wal").stat().st_size
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("VACUUM")
    size=path.stat().st_size
    build=time.perf_counter()-start
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise AssertionError("SQLite integrity")
    payloads=db.execute("SELECT COALESCE(sum(length(payload)),0) FROM versions").fetchone()[0]
    chunk_bytes=db.execute("SELECT COALESCE(sum(length(payload)),0) FROM chunks").fetchone()[0]
    modes=dict(db.execute("SELECT mode,count(*) FROM versions GROUP BY mode"))
    # Deterministically shuffle *all* source revisions. Equal weights,
    # no access log or pageviews; no decompression cache across requests.
    random.Random(114).shuffle(refs)
    activated=decoded=original=0; durations=[]
    for title,i,want in refs:
        t=time.perf_counter_ns()
        raw,a,d=recover(db,title,i)
        durations.append((time.perf_counter_ns()-t)/1000)
        if raw!=want: raise AssertionError("exact historical source mismatch")
        original+=len(want); activated+=a; decoded+=d
    db.close()
    return {"sqlite_bytes":size,"wal_bytes_append_all":wal,
            "payload_bytes":payloads+chunk_bytes,"versions":len(refs),
            "raw_bytes":original,"activated_compressed_bytes":activated,
            "decoded_source_bytes":decoded,"mean_activation_bytes":activated/len(refs),
            "decode_amplification":decoded/max(1,original),
            "warm_lookup_median_us_exploratory":statistics.median(durations),
            "warm_lookup_p95_us_exploratory":sorted(durations)[int(.95*(len(durations)-1))],
            "build_seconds_exploratory":build,"mode_counts":modes,
            "all_revision_receipts_verified":True}

def run(root, n):
    articles,manifest=load(root)
    cohort=select(articles,n,"CDG-R114-independent-v1")
    result={"round":114,"upstream_commit":PIN,"full_corpus_sha256":manifest,
            "eligible_articles":len(articles),"eligible_revisions":sum(len(r) for _,r in articles),
            "selected_articles":len(cohort),"selected_revisions":sum(len(r) for _,r in cohort),
            "selected_article_names_sha256":sha("\n".join(x[0] for x in cohort).encode()).hex(),
            "selection":"hash order, frozen before outcomes; no tuning",
            "limitations":["processed and sampled historical versions, not full raw edit stream",
                           "chronological order within article only; no actual time stamps or access counts",
                           "WAL file growth is SQLite logical journal bytes, not SSD writes",
                           "no query index, FTS ranking, RAG answers or WikECD reproduction",
                           "warm timing is exploratory, no hardware isolation"],
            "policies":{}}
    with tempfile.TemporaryDirectory() as d:
        for policy in POLICIES:
            result["policies"][policy]=benchmark(Path(d)/(policy+".sqlite"),cohort,policy)
            print(policy,json.dumps(result["policies"][policy]),flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--articles",type=int,default=100)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.articles<1: p.error("--articles must be positive")
    a.out.write_text(json.dumps(run(a.root,a.articles),indent=2,sort_keys=True)+"\n")
