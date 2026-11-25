"""R150: exact-content quotient positional index, with multiplicity-correct BM25.
Index-only physical comparison, not integrated archive or receipt validation.
"""
import argparse,collections,heapq,json,random,re,sqlite3,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
sys.path.insert(0,str(HERE.parent/"round-141"))
import news_retrieval as nr
import heldout_archive as h
import active_rank as ar

def connect(path,ext):
    db=sqlite3.connect(path)
    db.enable_load_extension(True);db.load_extension(str(ext));db.enable_load_extension(False)
    return db

def build(path,ext,events,quotient):
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE VIRTUAL TABLE docs USING fts5(body,content='');
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
    """)
    if quotient:db.execute("CREATE TABLE content_catalog(digest BLOB PRIMARY KEY,cid INTEGER NOT NULL,dl INTEGER NOT NULL) WITHOUT ROWID")
    known={};heads={};total=0;index_rows=0
    start=time.perf_counter_ns()
    for g,(article,i,raw) in enumerate(events,1):
        digest=h.sha(raw)
        item=known.get(digest) if quotient else None
        if item is None:
            text=raw.decode("utf8");dl=db.execute("SELECT cdg_token_count(?)",(text,)).fetchone()[0];cid=g
            db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(cid,text));index_rows+=1
            if quotient:
                db.execute("INSERT INTO content_catalog VALUES(?,?,?)",(digest,cid,dl))
                known[digest]=(cid,dl)
        else:
            cid,dl=item;assert events[cid-1][2]==raw
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
    return db,dict(index_rows=index_rows,sqlite_bytes=path.stat().st_size,
        fts_bytes=sum(v for k,v in sizes.items() if k.startswith("docs_")),
        catalog_bytes=sizes.get("content_catalog",0),build_us=elapsed)

def prepare(db,c):
    active=collections.defaultdict(list);lengths={};cid_lengths={}
    for g,cid,dl in db.execute("SELECT g,cid,dl FROM revisions WHERE g<=? AND (end_g IS NULL OR end_g>?) ORDER BY g",(c,c)):
        active[cid].append(g);lengths[g]=dl
        if cid in cid_lengths:assert cid_lengths[cid]==dl
        cid_lengths[cid]=dl
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    assert n==len(lengths) and total==sum(lengths.values())
    return active,lengths,cid_lengths,n,total

def frequencies(db,p,active,cid_lengths):
    out={}
    for cid,tf,dl in db.execute("SELECT rowid,cdg_count(docs),cdg_length(docs) FROM docs WHERE docs MATCH ?",(ar.quote(p),)):
        if cid in active:
            assert 1<=tf<=dl and dl==cid_lengths[cid]
            out[cid]=tf
    return out

def rank(db,p,o,prepared,grouped=False):
    ar.expression(p,o)
    active,lengths,cid_lengths,n,total=prepared
    freq=[frequencies(db,t,active,cid_lengths) for t in p]
    if not grouped:
        expanded=[{g:tf for cid,tf in m.items() for g in active[cid]} for m in freq]
        hits,df=ar.score(expanded,o,n,total,lengths)
        sets=[set(m) for m in expanded]
        candidates=set.intersection(*sets) if o=="AND" else set.union(*sets)
        return hits,df,len(candidates)
    df=[sum(len(active[cid]) for cid in m) for m in freq]
    assert all(d<=n for d in df)
    sets=[set(m) for m in freq]
    candidates=set.intersection(*sets) if o=="AND" else set.union(*sets)
    if not candidates:return [],df,0
    avg=total/n;weights=[ar.idf(n,d) for d in df]
    # Equal content => equal counts, lengths and scores. Only the first k
    # generation IDs per group can enter the global deterministic top k.
    scored=[]
    for cid in candidates:
        score=-sum(ar.positive_score(m.get(cid,0),cid_lengths[cid],avg,w) for m,w in zip(freq,weights))
        scored.extend((g,score) for g in active[cid][:10])
    hits=heapq.nsmallest(10,scored,key=lambda x:(x[1],x[0]))
    return hits,df,len(candidates)

def query_plan(events,cut,ref):
    qs=nr.plan(ref)
    # Fixed additional two-token phrase probes from first-cutoff source text.
    candidates=set()
    for _,_,raw in events[:cut]:
        words=re.findall(rb"[a-z]{3,20}",raw.lower())
        for a,b in zip(words[:32],words[1:33]):
            candidates.add((a+b" "+b).decode("ascii"))
    phrases=sorted(candidates,key=lambda s:h.sha(("R150-phrase|"+s).encode()))[:16]
    qs+= [((p,),"AND") for p in phrases]
    return list(dict.fromkeys(qs))

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    results={};signatures={};rng=random.Random(150)
    for name,quotient in (("revision",False),("content",True)):
        path=folder/(name+".sqlite");db,size=build(path,ext,events,quotient)
        methods=["expanded","grouped"] if quotient else ["expanded"]
        for method in methods:
            prep_times=[];query_times=[];scored=0;checks=0;err=0.
            for c in cuts:
                start=time.perf_counter_ns();prepared=prepare(db,c);prep_times.append((time.perf_counter_ns()-start)/1000)
                ordered=list(queries);rng.shuffle(ordered)
                for p,o in ordered:
                    start=time.perf_counter_ns();hits,df,work=rank(db,p,o,prepared,method=="grouped")
                    query_times.append((time.perf_counter_ns()-start)/1000)
                    err=max(err,h.verify(hits,expected[c,p,o]))
                    sig=(hits,df)
                    if (c,p,o) in signatures:assert signatures[c,p,o]==sig
                    else:signatures[c,p,o]=sig
                    scored+=work;checks+=1
            results[name+"_"+method]=dict(**size,prepare=h.quant(prep_times),query=h.quant(query_times),
                rank_checks=checks,max_score_error=err,scored_candidates=scored)
        db.close()
    for ref in refs.values():ref.close()
    return dict(round=150,corpus=corpus,revisions=len(events),manifest_sha256=manifest,
        cutoffs=cuts,query_count=len(queries),query_plan_sha256=h.sha(h.canonical(queries)).hex(),
        policies=results,limitations=["physical index-only comparison; common revision mapping and active statistics charged, source/provenance/receipt archive not built",
          "offline construction, no transactional update or end-to-end retrieval latency claim",
          "exact raw source equivalence only, no near-duplicate or fragment indexing",
          "prepared snapshot mapping cost reported separately, query timings descriptive",
          "active multiplicity retained in df/N/total; grouped scores use same native phrase counts",
          "AP synthetic ordinal schedule; CLARK sampled generation cutoffs not time-label benchmark"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark"),required=True);p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        if a.corpus=="ap":
            events,_,m=nr.load(a.source,a.target,folder);n=len(events)
            old=json.loads((HERE.parent/"round-148"/("results-"+str(n)+".json")).read_text())
            manifest=m["source_manifest_sha256"];assert manifest==old["manifest_sha256"]
            cuts=old["policies"]["snapshot"].get("cutoffs")
            if cuts is None:
                first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
        else:
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex();n=len(events)
            assert manifest=="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f"
            cuts=[max(1,n//4),n//2,3*n//4,n]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
