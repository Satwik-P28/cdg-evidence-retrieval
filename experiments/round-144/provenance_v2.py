"""R144: transactional provenance commitments over the R137 archive.

Trusted receipt digest is external. Prefix verification scans metadata, not
all source frames; returned sources are verified by the underlying reader.
"""
import argparse,collections,hashlib,json,os,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
import news_retrieval as nr
import transactional_pack as tp
import heldout_archive as h

FORMAT="cdg-origin-receipt-v2"
DOMAIN=b"CDG-R144-origin-v2\0"
def manifest_seed(raw):
    return h.sha(DOMAIN+b"manifest\0"+raw)
def entry(previous,g,a,i,digest,commit,timestamp,blob,rank_prefix):
    return h.sha(DOMAIN+b"entry\0"+previous+h.canonical(
        [g,a,i,digest.hex(),commit,timestamp,blob,rank_prefix.hex()]))
def register(db):
    db.create_function("cdg_origin_seed",1,manifest_seed,deterministic=True)
    db.create_function("cdg_origin_entry",9,entry,deterministic=True)
    return db
def setup(path,ext,manifest):
    db=register(tp.setup(path,ext,manifest))
    db.executescript("""
    CREATE TABLE origin_ledger(g INTEGER PRIMARY KEY REFERENCES revisions(generation),
        prefix_sha BLOB NOT NULL CHECK(length(prefix_sha)=32));
    CREATE TRIGGER origin_after_rank AFTER INSERT ON rank_ledger BEGIN
      INSERT INTO origin_ledger
      SELECT NEW.g,cdg_origin_entry(
          CASE WHEN NEW.g=1 THEN cdg_origin_seed((SELECT v FROM corpus WHERE k='manifest'))
          ELSE (SELECT prefix_sha FROM origin_ledger WHERE g=NEW.g-1) END,
          NEW.g,r.article,r.ord,v.digest,o.commit_sha1,o.committer_unix,o.blob_sha1,NEW.prefix_sha)
      FROM revisions r JOIN versions v ON v.article=r.article AND v.ord=r.ord
      JOIN origin o ON o.g=r.generation WHERE r.generation=NEW.g;
      SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM origin_ledger WHERE g=NEW.g)
          THEN RAISE(ABORT,'missing origin commitment') END;
    END;
    """)
    db.commit();return db
def connect(path,ext):return register(h.connect(path,ext))
def metadata_prefix(db,c):
    if not db.in_transaction or not 1<=c<=h.generation(db):raise ValueError("invalid prefix snapshot")
    row=db.execute("SELECT v FROM corpus WHERE k='manifest'").fetchone()
    if row is None:raise ValueError("missing manifest")
    raw=row[0];prev=manifest_seed(raw);n=0
    for g,a,i,digest,commit,stamp,blob,rank,stored in db.execute("""
        SELECT r.generation,r.article,r.ord,v.digest,o.commit_sha1,o.committer_unix,o.blob_sha1,
        l.prefix_sha,p.prefix_sha FROM revisions r
        JOIN versions v ON v.article=r.article AND v.ord=r.ord
        JOIN origin o ON o.g=r.generation JOIN rank_ledger l ON l.g=r.generation
        JOIN origin_ledger p ON p.g=r.generation WHERE r.generation<=? ORDER BY r.generation""",(c,)):
        n+=1
        if g!=n:raise ValueError("origin prefix gap")
        prev=entry(prev,g,a,i,digest,commit,stamp,blob,rank)
        if prev!=stored:raise ValueError("origin prefix mismatch")
    if n!=c:raise ValueError("origin prefix cardinality")
    return h.sha(raw).hex(),prev.hex()

def issue(db,fd,p,o,c):
    manifest,root=metadata_prefix(db,c)
    body,_=tp.issue(db,fd,p,o,c)
    origins=[]
    for hit in body["hits"]:
        row=db.execute("SELECT commit_sha1,committer_unix,blob_sha1 FROM origin WHERE g=?",(hit["g"],)).fetchone()
        if row is None:raise ValueError("missing hit origin")
        commit,stamp,blob=row
        raw,*_=tp.recover(db,fd,hit["article"],hit["ordinal"])
        if hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()!=blob:raise ValueError("origin blob mismatch")
        origins.append(dict(g=hit["g"],commit_sha1=commit,committer_unix=stamp,blob_sha1=blob))
    result=dict(format=FORMAT,manifest_sha256=manifest,origin_prefix_sha256=root,ranking=body,hit_origins=origins)
    return result,h.sha(h.canonical(result)).hex()

def replay(db,fd,body,trusted):
    if body.get("format")!=FORMAT or h.sha(h.canonical(body)).hex()!=trusted:raise ValueError("untrusted receipt")
    rank=body["ranking"];got,digest=issue(db,fd,tuple(rank["phrases"]),rank["op"],rank["cutoff"])
    if got!=body or digest!=trusted:raise ValueError("provenance replay mismatch")
    return got

def audit(db,fd):
    n=tp.audit(db,fd)
    if db.execute("SELECT count(*) FROM origin_ledger").fetchone()[0]!=n:raise ValueError("origin ledger cardinality")
    if n:metadata_prefix(db,n)
    return n

def experiment(source,target,folder,ext):
    events,origins,m=nr.load(source,target,folder);n=len(events)
    frozen=json.loads((HERE.parent/"round-138"/("results-"+str(n)+".json")).read_text())["result"]
    assert m["source_manifest_sha256"]==frozen["manifest"]
    cuts=frozen["cuts"];ref=h.active_oracle(events,cuts[0]);all_q=nr.plan(ref);ref.close()
    assert h.sha(h.canonical([dict(phrases=p,op=o) for p,o in all_q])).hex()==frozen["query_plan_sha256"]
    # Fixed subset, independent of outcome; preserve low/mid/high DF bands.
    queries=all_q[::4]
    results={};old_bodies={};new_bodies={}
    for arm in ("v1","v2"):
        path=folder/(arm+".sqlite")
        db=setup(path,ext,m) if arm=="v2" else tp.setup(path,ext,m)
        db.execute("PRAGMA wal_autocheckpoint=1000")
        fd=os.open(tp.side(path),os.O_RDWR);append_times=[];issued={}
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            t=time.perf_counter_ns();assert tp.append(db,fd,a,raw,origin)==(g,i)
            append_times.append((time.perf_counter_ns()-t)/1000)
            if g in cuts:
                db.execute("BEGIN")
                for p,o in queries:
                    value=issue(db,fd,p,o,g) if arm=="v2" else tp.issue(db,fd,p,o,g)
                    issued[g,p,o]=value
                db.rollback()
            if g%10000==0:print("INGEST",arm,g,flush=True)
        db.execute("BEGIN");assert (audit(db,fd) if arm=="v2" else tp.audit(db,fd))==n
        end=tp.state(db,fd);db.rollback();assert end==os.fstat(fd).st_size
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM");db.close()
        db=connect(path,ext) if arm=="v2" else h.connect(path,ext);db.execute("BEGIN")
        checks=0;times=[];maxerr=0.
        for c in cuts:
            ref=h.active_oracle(events,c)
            for p,o in queries:
                body,digest=issued[c,p,o];t=time.perf_counter_ns()
                if arm=="v2":
                    got=replay(db,fd,body,digest);rank=got["ranking"]
                    assert rank==old_bodies[c,p,o]
                else:
                    got,d=tp.issue(db,fd,p,o,c);assert (got,d)==(body,digest);rank=got
                    old_bodies[c,p,o]=rank
                times.append((time.perf_counter_ns()-t)/1000)
                maxerr=max(maxerr,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in rank["hits"]],h.native(ref,p,o)))
                checks+=1
            ref.close()
        assert (audit(db,fd) if arm=="v2" else tp.audit(db,fd))==n
        db.rollback();db.close();os.close(fd)
        result=dict(total_archive_bytes=path.stat().st_size+end,payload_bytes=end-tp.HEADER,
            append=h.quant(append_times),replay=h.quant(times),rank_checks=checks,max_score_error=maxerr,
            audited_sources=n)
        assert result["payload_bytes"]==frozen["policies"]["bounded_anchor"]["payload_bytes"]
        if arm=="v1":assert result["total_archive_bytes"]==frozen["policies"]["bounded_anchor"]["total_archive_bytes"]
        results[arm]=result
    return dict(revisions=n,source_manifest=m["source_manifest_sha256"],query_count=len(queries),
        cutoffs=cuts,policies=results,
        limitations=["prefix metadata scan O(c), no cached verification claim",
        "trusted external receipt digest required; no signature or publisher authentication",
        "synthetic ordinal schedule and derived text",
        "only hit source bytes checked by replay; full audit verifies all source bytes",
        "same runner sequential arms, timings descriptive"])

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--crash":
        _,_,p,e,fault=sys.argv;path=Path(p);db=connect(path,Path(e));fd=os.open(tp.side(path),os.O_RDWR)
        raw=b"new evidence "*100;tp.append(db,fd,"a",raw,tp.fixture(raw,"new"),fault=fault)
        raise AssertionError("fault not reached")
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=experiment(a.source,a.target,Path(d),a.extension.resolve())
    result=dict(round=144,result=x);a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
