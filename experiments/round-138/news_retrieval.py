"""R138: NewsEdits integrated historical retrieval, exact evidence packets.

Derived sentence text, per-document version order, deterministic synthetic
round-robin ingestion (not real wall-clock chronology). No generated answers.
"""
import argparse,collections,hashlib,json,os,re,sqlite3,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-136"))
sys.path.insert(0,str(HERE.parent/"round-137"))
import newsedits_scale as ns
import transactional_pack as tp
import heldout_archive as h

SOURCE_SHA="005cf42b35f6b42700e16bf69d9a9e7cbd541d74faa0cd3b4c5b666e5c319e1e"
SALT="CDG-R138-query-v1|"

def load(source,target,folder):
    if ns.file_sha(source)!=SOURCE_SHA:raise ValueError("frozen AP database mismatch")
    db=sqlite3.connect("file:"+str(source.resolve())+"?mode=ro",uri=True)
    selected,count,eligible=ns.sample(db,target)
    db.execute("CREATE TEMP TABLE selected(entry_id PRIMARY KEY)")
    db.executemany("INSERT INTO selected VALUES(?)",((a,) for a,_ in selected))
    scratch=sqlite3.connect(folder/"scratch.sqlite")
    scratch.execute("CREATE TABLE split_sentences(entry_id,version,sent_idx,sentence)")
    cur=db.execute("SELECT s.entry_id,s.version,s.sent_idx,s.sentence FROM split_sentences s JOIN selected q ON q.entry_id=s.entry_id")
    while True:
        rows=cur.fetchmany(20000)
        if not rows:break
        scratch.executemany("INSERT INTO split_sentences VALUES(?,?,?,?)",rows)
    scratch.execute("CREATE INDEX by_entry ON split_sentences(entry_id,version,sent_idx)");scratch.commit();db.close()
    histories=[];digest=hashlib.sha256()
    for a,n in selected:
        vs=ns.read_article(scratch,a,n)
        for i,(v,raw) in enumerate(vs):
            digest.update(h.canonical([str(a),i,v,h.sha(raw).hex(),len(raw)]));digest.update(b"\n")
        histories.append((str(a),vs))
    scratch.close()
    # Round-robin by ordinal, preserving per-article order. All initial heads first.
    events=[];origins=[]
    for i in range(max(len(vs) for _,vs in histories)):
        for a,vs in histories:
            if i>=len(vs):continue
            v,raw=vs[i]
            # Synthetic stable provenance ID, not a real Git commit or timestamp.
            identity=hashlib.sha1(h.canonical(["NewsEdits/AP",SOURCE_SHA,a,v])).hexdigest()
            blob=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
            events.append((a,i,raw));origins.append((identity,0,blob))
    assert len(events)==count
    manifest=dict(source="NewsEdits AP split_sentences",source_sha256=SOURCE_SHA,
        provenance="synthetic SHA1 of source hash, entry ID and upstream version; zero timestamp, NOT Git history",
        derived_text="sentence-index ordered newline join",schedule="round-robin ordinal; synthetic global order",
        upstream_versions={a:[v for v,_ in vs] for a,vs in histories},
        source_manifest_sha256=digest.hexdigest(),requested_revisions=target,
        retained_paths=[a for a,_ in histories],eligible_documents=eligible)
    if count==74364:
        assert digest.hexdigest()=="e12f3c397333e78a5ab3394dbb119bbab95985161e53dadf9eef71b6b5508319"
    return events,origins,manifest

def plan(ref):
    ref.execute("CREATE VIRTUAL TABLE temp.r138_vocab USING fts5vocab(main,fulltext,'row')")
    rows=ref.execute("SELECT term,doc FROM temp.r138_vocab WHERE doc>=2").fetchall()
    key=lambda s:h.sha((SALT+s).encode())
    queries=[]
    for lo,hi in ((2,10),(11,100),(101,10**12)):
        words=sorted((t for t,df in rows if lo<=df<=hi),key=key)[:16]
        queries.extend([((t,),"AND") for t in words])
    terms=[p[0] for p,_ in queries]
    for i in range(min(8,len(terms)//2)):
        a,b=terms[i],terms[-1-i]
        if a!=b:queries.extend([((a,b),"AND"),((a,b),"OR")])
    return queries

def quote_span(raw,phrases):
    # Frozen deterministic extraction rule, not a semantic answer or relevance label.
    # Prefer the first nonempty line containing one exact token/phrase under casefold.
    lines=raw.split(b"\n")
    for line in lines:
        if line and any(re.search(r"(?<!\w)"+re.escape(p.casefold())+r"(?!\w)",line.decode("utf8").casefold()) for p in phrases):
            return line,True
    return next((l for l in lines if l),b""),False

def drift(events,cut,queries,old,final):
    latest={}
    for g,(a,i,raw) in enumerate(events,1):latest[a]=(g,raw)
    stats=collections.Counter();per=[]
    for ps,op in queries:
        a=old[ps,op];b=final[ps,op]
        old_g=[g for g,_ in a];new_g=[g for g,_ in b]
        old_ids=[events[g-1][0] for g in old_g];new_ids=[events[g-1][0] for g in new_g]
        row=dict(phrases=list(ps),op=op,old_hits=len(a),new_hits=len(b),
            rank_order_changed=old_ids!=new_ids,revision_order_changed=old_g!=new_g,
            rank_score_changed=old_g==new_g and any(x[1]!=y[1] for x,y in zip(a,b)),
            same_article_overlap=len(set(old_ids)&set(new_ids)),same_revision_overlap=len(set(old_g)&set(new_g)))
        stats.update(queries=1,nonempty_old_queries=bool(a),rank_order_changed=row["rank_order_changed"],
            revision_order_changed=row["revision_order_changed"],score_only_changed=row["rank_score_changed"],
            historical_hits=len(a),same_article_overlap=row["same_article_overlap"],same_revision_overlap=row["same_revision_overlap"])
        count=collections.Counter()
        for g,_ in a:
            article,_,raw=events[g-1];new_g,new_raw=latest[article]
            span,matched=quote_span(raw,ps)
            count.update(citations=1,latest_version_changed=new_g!=g,latest_source_changed=new_raw!=raw)
            if span and matched:
                count.update(query_matched_spans=1,span_missing_from_latest=span not in new_raw.split(b"\n"))
        stats.update(count);row.update(count);per.append(row)
    return dict(cutoff=cut,counts=dict(stats),per_query=per)

def run(source,target,folder,ext):
    events,origins,manifest=load(source,target,folder)
    n=len(events);initial=len(manifest["retained_paths"])
    cuts=sorted(set([initial,initial+(n-initial)//3,initial+2*(n-initial)//3,n]))
    ref=h.active_oracle(events,cuts[0]);queries=plan(ref);ref.close()
    if not queries:raise ValueError("no queries")
    expected={}
    for c in cuts:
        ref=h.active_oracle(events,c)
        expected[c]={(p,o):h.native(ref,p,o) for p,o in queries};ref.close()
    comparisons=[drift(events,c,queries,expected[c],expected[n]) for c in cuts[:-1]]
    results={};bodies={}
    for policy in ("snapshot","bounded_anchor"):
        path=folder/(policy+".sqlite");db=tp.setup(path,ext,manifest)
        # Short checkpoints avoid a permanently pinned full-build WAL; R137
        # separately validates concurrent pinned readers across writes.
        db.execute("PRAGMA wal_autocheckpoint=1000")
        fd=os.open(tp.side(path),os.O_RDWR);ingest=[];published={}
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            st=time.perf_counter_ns();assert tp.append(db,fd,a,raw,origin,policy)==(g,i)
            ingest.append((time.perf_counter_ns()-st)/1000)
            if g in cuts:
                db.execute("BEGIN")
                for p,o in queries:
                    body,d=tp.issue(db,fd,p,o,g)
                    h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],expected[g][p,o])
                    published[g,p,o]=(body,d)
                db.rollback()
            if g%5000==0:print("INGEST",policy,g,flush=True)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM");db.close()
        db=h.connect(path,ext);db.execute("BEGIN")
        assert tp.audit(db,fd)==n
        rank_error=0.;rank_times=[];source_times=[];source_bytes=decoded=activated=0;maxd=maxa=0.;packet_count=0
        for (c,p,o),(old,d) in published.items():
            st=time.perf_counter_ns();body,d2=tp.issue(db,fd,p,o,c);rank_times.append((time.perf_counter_ns()-st)/1000)
            assert (body,d2)==(old,d)
            key=c,p,o
            if key in bodies:assert bodies[key]==(body,d2)
            else:bodies[key]=(body,d2)
            rank_error=max(rank_error,h.verify([(x["g"],float.fromhex(x["score_hex"])) for x in body["hits"]],expected[c][p,o]))
            for hit in body["hits"]:
                a,i,want=events[hit["g"]-1]
                raw,*_=tp.recover(db,fd,a,i);assert raw==want
                # Exact source-bound extractive evidence packet, not an LLM response.
                assert quote_span(raw,p)==quote_span(want,p)
                packet_count+=1
        for a,i,want in events:
            st=time.perf_counter_ns();raw,ab,dd,depth=tp.recover(db,fd,a,i);source_times.append((time.perf_counter_ns()-st)/1000)
            assert raw==want
            full=len(h.C.compress(raw));source_bytes+=len(raw);decoded+=dd;activated+=ab
            if policy=="bounded_anchor":assert depth<=1 and 2*ab<=3*full and 2*dd<=5*len(raw)
            maxa=max(maxa,ab/full)
            if raw:maxd=max(maxd,dd/len(raw))
        end=tp.state(db,fd);assert end==os.fstat(fd).st_size
        db.rollback();db.close();os.close(fd)
        results[policy]=dict(total_archive_bytes=path.stat().st_size+end,sqlite_bytes=path.stat().st_size,
            sidecar_bytes=end,payload_bytes=end-tp.HEADER,source_reads=n,rank_checks=len(published),
            receipt_replays=len(published),extractive_packets=packet_count,max_score_error=rank_error,
            mean_decode_ratio=decoded/max(1,source_bytes),max_decode_ratio=maxd,max_activation_ratio=maxa,
            activated_bytes=activated,append=h.quant(ingest),receipt=h.quant(rank_times),read=h.quant(source_times))
    return dict(revisions=n,documents=initial,manifest=manifest["source_manifest_sha256"],
        source_sha256=SOURCE_SHA,query_plan_sha256=h.sha(h.canonical([dict(phrases=p,op=o) for p,o in queries])).hex(),
        cuts=cuts,queries_per_cutoff=len(queries),current_only_drift=comparisons,policies=results,
        limitations=["derived text, synthetic round-robin global order, no original publication timeline",
            "query probes selected from initial snapshot token frequencies, no human relevance labels",
            "extractive citation packets only; no generated answers, semantic correctness or hallucination claims",
            "current-only baseline resolves latest version by stable article ID; not a content-addressed archive",
            "same hardware per job, sequential policy builds; timing descriptive, not cold I/O"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:result=run(a.source,a.target,Path(d),a.extension.resolve())
    out=dict(round=138,result=result)
    a.out.write_text(json.dumps(out,indent=2)+"\n");print("RESULT_JSON="+json.dumps(out),flush=True)
