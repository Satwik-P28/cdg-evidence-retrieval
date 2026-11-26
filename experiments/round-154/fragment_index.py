"""R154: exact phrase TF over deduplicated core + right-context fragments.
Physical index-only; no source reconstruction or transaction guarantee.
"""
import argparse,collections,functools,json,random,struct,sys,tempfile,time,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-152"))
import token_equivalence as te
from token_equivalence import connect,h,nr,ar,query_plan
MAX_PHRASE=8
POLICIES=("fixed32","cdc32","cdc64")

def tokens(db,text):
    stream=db.execute("SELECT cdg_token_stream(?)",(text,)).fetchone()[0]
    i=0;out=[]
    while i<len(stream):
        n=struct.unpack_from(">I",stream,i)[0];i+=4
        assert n>0 and i+n<=len(stream)
        out.append(stream[i:i+n]);i+=n
    return out

def encode(ts):
    return b"".join(struct.pack(">I",len(t))+t for t in ts)

@functools.lru_cache(maxsize=131072)
def fingerprint(t):return zlib.crc32(t)

def spans(ts,policy):
    if policy.startswith("fixed"):
        width=int(policy[5:]);return [(i,min(i+width,len(ts))) for i in range(0,len(ts),width)]
    target=int(policy[3:]);lo=target//2;hi=target*2
    # Gear-style content-defined boundary; hash reset after each cut.
    start=0;acc=0;out=[]
    for i,t in enumerate(ts,1):
        acc=((acc<<1)+fingerprint(t))&0xffffffff
        if i-start>=lo and ((acc&(target-1))==0 or i-start>=hi):
            out.append((start,i));start=i;acc=0
    if start<len(ts):out.append((start,len(ts)))
    return out

def build(path,ext,events,policy):
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE VIRTUAL TABLE docs USING fts5(body,content='');
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
      CREATE TABLE content_catalog(digest BLOB PRIMARY KEY,cid INTEGER NOT NULL,dl INTEGER NOT NULL) WITHOUT ROWID;
      CREATE TABLE fragments(fid INTEGER PRIMARY KEY,digest BLOB NOT NULL UNIQUE,core INTEGER NOT NULL);
      CREATE TABLE uses(fid INTEGER NOT NULL,cid INTEGER NOT NULL,m INTEGER NOT NULL,PRIMARY KEY(fid,cid)) WITHOUT ROWID;
    """)
    known={};frags={};heads={};total=0;occurrences=0;halo_tokens=0;unique_tokens=0;start=time.perf_counter_ns()
    for g,(article,i,raw) in enumerate(events,1):
        digest=h.sha(raw);item=known.get(digest)
        if item is not None:
            cid,dl=item;assert events[cid-1][2]==raw
        else:
            cid=g;ts=tokens(db,raw.decode("utf8"));dl=len(ts)
            assert dl==db.execute("SELECT cdg_token_count(?)",(raw.decode("utf8"),)).fetchone()[0]
            known[digest]=(cid,dl);db.execute("INSERT INTO content_catalog VALUES(?,?,?)",(digest,cid,dl))
            counts=collections.Counter();reassembled=[]
            for a,b in spans(ts,policy):
                core=b-a;part=ts[a:min(dl,b+MAX_PHRASE-1)]
                reassembled.extend(part[:core]);payload=encode(part)
                key=h.sha(struct.pack(">I",core)+payload)
                if key in frags:
                    fid,old_core,old_payload=frags[key];assert (old_core,old_payload)==(core,payload)
                else:
                    fid=len(frags)+1;frags[key]=(fid,core,payload)
                    body=b" ".join(part).decode("utf8")
                    # Check exact token sequence after retokenizing fragment.
                    assert db.execute("SELECT cdg_token_stream(?)",(body,)).fetchone()[0]==payload
                    db.execute("INSERT INTO fragments VALUES(?,?,?)",(fid,key,core))
                    db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(fid,body))
                    halo_tokens+=len(part)-core;unique_tokens+=len(part)
                counts[fid]+=1;occurrences+=1
            assert reassembled==ts
            db.executemany("INSERT INTO uses VALUES(?,?,?)",((f,cid,m) for f,m in counts.items()))
        if article in heads:
            old_g,old_i,old_dl=heads[article];assert i==old_i+1
            db.execute("UPDATE revisions SET end_g=? WHERE g=?",(g,old_g));total-=old_dl
        else:assert i==0
        db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,NULL)",(g,article,i,cid,dl))
        heads[article]=(g,i,dl);total+=dl
        db.execute("INSERT INTO active_stats VALUES(?,?,?)",(g,len(heads),total))
    db.execute("CREATE INDEX revision_cid ON revisions(cid,g)")
    db.commit();db.execute("INSERT INTO docs(docs) VALUES('optimize')");db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return db,dict(sqlite_bytes=path.stat().st_size,fts_bytes=sum(v for k,v in sizes.items() if k.startswith("docs_")),
        content_rows=len(known),index_rows=len(frags),fragment_occurrences=occurrences,
        mapping_rows=db.execute("SELECT count(*) FROM uses").fetchone()[0],halo_tokens=halo_tokens,
        unique_indexed_tokens=unique_tokens,physical_table_bytes=sizes,build_us=(time.perf_counter_ns()-start)/1000)

def rank(db,p,o,c):
    ar.expression(p,o)
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    freq=[];lengths={}
    for phrase in p:
        if not 1<=len(tokens(db,phrase))<=MAX_PHRASE:raise ValueError("unsupported phrase length")
        matches={}
        for g,tf,dl in db.execute("""WITH matches AS MATERIALIZED (
          SELECT docs.rowid AS fid,cdg_owned_count(docs,f.core) AS tf
          FROM docs JOIN fragments f ON f.fid=docs.rowid WHERE docs MATCH ?
        ), summed AS MATERIALIZED (
          SELECT u.cid,SUM(q.tf*u.m) AS tf FROM matches q JOIN uses u ON u.fid=q.fid
          WHERE q.tf>0 GROUP BY u.cid
        ) SELECT r.g,s.tf,r.dl FROM summed s JOIN revisions r ON r.cid=s.cid
          WHERE r.g<=? AND (r.end_g IS NULL OR r.end_g>?)""",(ar.quote(phrase),c,c)):
            assert 1<=tf<=dl
            matches[g]=tf;lengths[g]=dl
        freq.append(matches)
    return ar.score(freq,o,n,total,lengths)

def boundary_plan(ext,events,cut):
    db=connect(":memory:",ext);pool=set()
    for _,_,raw in events[:min(cut,256)]:
        ts=tokens(db,raw.decode("utf8"))
        for policy in POLICIES:
            for _,b in spans(ts,policy)[:-1]:
                for n in (2,4,8):
                    a=b-n//2
                    if a>=0 and a+n<=len(ts):pool.add(b" ".join(ts[a:a+n]).decode("utf8"))
    db.close()
    return [((p,),"AND") for p in sorted(pool,key=lambda p:h.sha(("R154-boundary|"+p).encode()))[:24]]

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=list(dict.fromkeys(query_plan(events,cuts[0],refs[cuts[0]])+boundary_plan(ext,events,cuts[0])))
    check=connect(":memory:",ext)
    queries=[(p,o) for p,o in queries if all(1<=len(tokens(check,t))<=MAX_PHRASE for t in p)]
    check.close()
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(154);results={};sigs={}
    for mode in ("raw",)+POLICIES:
        path=folder/(mode+".sqlite")
        if mode=="raw":
            db,size=te.build(path,ext,events,"raw")
            db.execute("CREATE INDEX revision_cid ON revisions(cid,g)");db.commit();db.execute("VACUUM")
            size["sqlite_bytes"]=path.stat().st_size;fn=te.rank
        else:db,size=build(path,ext,events,mode);fn=rank
        times=[];err=0.
        for repeat in range(2):
            plan=list(expected);rng.shuffle(plan)
            for c,p,o in plan:
                t=time.perf_counter_ns();hits,df=fn(db,p,o,c)
                times.append((time.perf_counter_ns()-t)/1000)
                err=max(err,h.verify(hits,expected[c,p,o]))
                sig=hits,df
                if (c,p,o) in sigs:assert sig==sigs[c,p,o]
                else:sigs[c,p,o]=sig
        results[mode]=dict(**size,query=h.quant(times),rank_checks=len(times),max_score_error=err)
        print("ARM_JSON="+json.dumps(results[mode]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=154,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
      query_count=len(queries),query_plan_sha256=h.sha(h.canonical(queries)).hex(),policies=results,
      limitations=["index-only, no raw reconstruction or transactional integration",
       "exact one-column unicode61 phrases 1..8 tokens, AND/OR; longer phrases rejected",
       "ordered core spans checked at ingestion; stored uses are a multiset sufficient for bounded phrase TF, not a source representation",
       "right halo of seven tokens, match-start ownership avoids double counting",
       "physical catalog, mapping and metadata charged; two warm shuffled repeats, descriptive timing",
       "no novelty claim over established fragment indexing; AP synthetic global order"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="clark":
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex()
            assert manifest=="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f"
            n=len(events);cuts=[n//4,n//2,3*n//4,n]
        else:
            events,_,m=nr.load(a.source,a.target,folder);manifest=m["source_manifest_sha256"]
            first=len(m["retained_paths"]);n=len(events)
            old=json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())
            assert old["manifest_sha256"]==manifest
            cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
