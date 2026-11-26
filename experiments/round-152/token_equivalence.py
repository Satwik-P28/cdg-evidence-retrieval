"""R152: exact native tokenizer quotient; efficient revision query control."""
import argparse,json,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-150"))
from quotient_index import connect,query_plan,h,nr,ar
def build(path,ext,events,mode):
    quotient=mode!='revision'
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE VIRTUAL TABLE docs USING fts5(body,content='');
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
    """)
    if quotient:db.execute("CREATE TABLE content_catalog(digest BLOB PRIMARY KEY,cid INTEGER NOT NULL,dl INTEGER NOT NULL) WITHOUT ROWID")
    known={};heads={};total=0;index_rows=0;raw_unique=set();token_unique=set();byte_distinct_reuses=0
    start=time.perf_counter_ns()
    for g,(article,i,raw) in enumerate(events,1):
        raw_digest=h.sha(raw);raw_unique.add(raw_digest)
        text=raw.decode("utf8")
        stream=db.execute("SELECT cdg_token_stream(?)",(text,)).fetchone()[0]
        assert isinstance(stream,bytes)
        token_digest=h.sha(b"CDG-unicode61-stream-v1\0"+stream)
        token_unique.add(token_digest)
        digest=token_digest if mode=="token" else raw_digest
        item=known.get(digest) if quotient else None
        if item is None:
            dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0];cid=g
            db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(cid,text));index_rows+=1
            if quotient:
                db.execute("INSERT INTO content_catalog VALUES(?,?,?)",(digest,cid,dl))
                known[digest]=(cid,dl)
        else:
            cid,dl=item;previous=events[cid-1][2]
            if mode=="token":
                other=db.execute("SELECT cdg_token_stream(?)",(previous.decode("utf8"),)).fetchone()[0]
                assert other==stream
                if previous!=raw:byte_distinct_reuses+=1
            else:assert previous==raw
        if article in heads:
            old_g,old_i,old_dl=heads[article];assert i==old_i+1
            db.execute("UPDATE revisions SET end_g=? WHERE g=?",(g,old_g));total-=old_dl
        else:assert i==0
        db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,NULL)",(g,article,i,cid,dl))
        heads[article]=(g,i,dl);total+=dl
        db.execute("INSERT INTO active_stats VALUES(?,?,?)",(g,len(heads),total))
    db.commit();db.execute("INSERT INTO docs(docs) VALUES('optimize')");db.commit();db.execute("VACUUM")
    elapsed=(time.perf_counter_ns()-start)/1000
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert db.execute("SELECT count(*) FROM docs").fetchone()[0]==index_rows
    assert db.execute("SELECT count(*) FROM revisions").fetchone()[0]==len(events)
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return db,dict(raw_unique=len(raw_unique),token_unique=len(token_unique),byte_distinct_reuses=byte_distinct_reuses,index_rows=index_rows,sqlite_bytes=path.stat().st_size,
        fts_bytes=sum(v for k,v in sizes.items() if k.startswith("docs_")),
        catalog_bytes=sizes.get("content_catalog",0),build_us=elapsed)

def rank(db,p,o,c):
    # Match the query structure in every arm, with no full ledger/snapshot scan.
    ar.expression(p,o)
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    freq=[];lengths={}
    for phrase in p:
        matches={}
        for g,tf,dl,stored in db.execute("""WITH matches AS MATERIALIZED (
          SELECT rowid AS cid,cdg_count(docs) AS tf,cdg_length(docs) AS dl
          FROM docs WHERE docs MATCH ?
        ) SELECT r.g,q.tf,q.dl,r.dl FROM matches q JOIN revisions r ON r.cid=q.cid
          WHERE r.g<=? AND (r.end_g IS NULL OR r.end_g>?)""",(ar.quote(phrase),c,c)):
            assert dl==stored and 1<=tf<=dl
            matches[g]=tf;lengths[g]=dl
        freq.append(matches)
    return ar.score(freq,o,n,total,lengths)

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(152);results={};sigs={}
    for mode in ("revision","raw","token"):
        db,size=build(folder/(mode+".sqlite"),ext,events,mode)
        # Give every arm the same mapping index; charge physical pages.
        db.execute("CREATE INDEX revision_cid ON revisions(cid,g)");db.commit();db.execute("VACUUM")
        size["sqlite_bytes"]=(folder/(mode+".sqlite")).stat().st_size
        times=[];err=0.
        for repeat in range(3):
            plan=list(expected);rng.shuffle(plan)
            for c,p,o in plan:
                t=time.perf_counter_ns();hits,df=rank(db,p,o,c)
                times.append((time.perf_counter_ns()-t)/1000)
                err=max(err,h.verify(hits,expected[c,p,o]))
                sig=hits,df
                if (c,p,o) in sigs:assert sig==sigs[c,p,o]
                else:sigs[c,p,o]=sig
        results[mode]=dict(**size,query=h.quant(times),rank_checks=len(times),max_score_error=err)
        db.close()
    for ref in refs.values():ref.close()
    assert results["raw"]["index_rows"]==results["raw"]["raw_unique"]
    assert results["token"]["index_rows"]==results["token"]["token_unique"]
    return dict(round=152,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
      query_count=len(queries),query_plan_sha256=h.sha(h.canonical(queries)).hex(),policies=results,
      limitations=["index-only, shared mapping index charged, no source or provenance writer",
       "native default unicode61 only; no synonyms, custom tokenization, highlighting or byte-offset equivalence",
       "matching native phrase frequencies and exact rank identity, not semantic equivalence",
       "all arms use same SQL join and expanded per-revision scoring, no full ledger scan",
       "three shuffled warm query passes; timings descriptive; synthetic variants not real corpus"])

def variants(events):
    # Separate, openly synthetic stress: alter only selected punctuation/case.
    # Native token equality is checked empirically, not assumed by transformation.
    out=[]
    for a,i,raw in events:
        out.append((a,i,raw))
        if i==0:
            text=raw.decode("utf8");changed=("  "+text.upper()+" !!!").encode()
            out.append(("synthetic-variant:"+a,0,changed))
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark","variants"),required=True)
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
            if a.corpus=="variants":
                events=variants(events);manifest=h.sha(h.canonical([(x,i,h.sha(raw).hex()) for x,i,raw in events])).hex();first*=2;n=len(events)
            cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
