"""R175: joint representation optimization over regions, terms and postings.

The archive is not forced into one strategy.  Each layout chooses, independently:

* source representation - always the R149 bounded marginal recipe, shared as the
  base archive and never replaced by a losing alternative;
* term representation - frequency postings only, frequency postings plus
  block-addressable positions, or block positions *replacing* the postings for that
  term (term-level unified selection, which drops the duplicate document list);
* region representation - a "hot" region of high-service-cost contents served by a
  native positional FTS5 index, with cold candidates falling back to bounded source
  recovery.

Every layout reports complete archive bytes, median/p95/p99 latency, source
reconstruction checks, dependency depth, decoded/activated amplification and peak
RSS.
"""
import argparse,collections,json,random,resource,shutil,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-173"))
sys.path.insert(0,str(HERE.parent/"round-174"))
from blocked_positions import (BlockIndex,shifted_count,quant_us,
    f,h,tt,connect,nr,tokens,query_plan,prepare,recover)
import cost_selection as cs
import active_rank as ar
from forward_index import phrase_count

EXTENSION=None

def hot_contents(db,k):
    """Contents ranked by service cost: revisions served x source activated bytes."""
    service={}
    for cid,n in db.execute("SELECT cid,count(*) FROM revisions GROUP BY cid"):
        g=db.execute("SELECT min(g) FROM revisions WHERE cid=?",(cid,)).fetchone()[0]
        _,dd,ab=recover(db,g)
        service[cid]=(n,n*ab)
    ranked=sorted(service.items(),key=lambda kv:(-kv[1][1],kv[0]))
    return [cid for cid,_ in ranked[:k]]

def build_hot(db,k):
    cids=hot_contents(db,k)
    db.execute("CREATE VIRTUAL TABLE hot_docs USING fts5(body,content='')")
    for cid in cids:
        g=db.execute("SELECT min(g) FROM revisions WHERE cid=?",(cid,)).fetchone()[0]
        raw,_,_=recover(db,g)
        db.execute("INSERT INTO hot_docs(rowid,body) VALUES(?,?)",(cid,raw.decode("utf8")))
    db.commit()
    return set(cids)

def materialize(base,path,terms,ids,chosen,unify):
    shutil.copyfile(base,path)
    db=connect(path,EXTENSION)
    db.execute("CREATE TABLE selected_terms(tid INTEGER PRIMARY KEY)")
    db.executemany("INSERT INTO selected_terms VALUES(?)",((t,) for t in chosen))
    db.execute("CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,"
               "nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)")
    inverse={ids[t]:(s,e) for t,(s,e) in terms.items()}
    for tid in chosen:
        stats,enc=inverse[tid]
        db.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",
                   (tid,stats["df"],enc["blocks"],enc["dir"],enc["body"]))
        if unify:db.execute("DELETE FROM token_postings WHERE tid=?",(tid,))
    db.commit()
    return db

def rank_joint(db,p,o,prep,index,hot):
    ar.expression(p,o);active,lens,n,total=prep;freq=[]
    index.reset()
    for phrase in p:
        qs=tokens(db,phrase)
        qids=[index.ids.get(t) for t in qs]
        if None in qids:freq.append({});continue
        if len(qids)==1:
            matches={cid:tf for cid,tf in index.all_counts(qids[0]).items() if cid in active}
        else:
            distinct=list(dict.fromkeys(qids))
            maps={t:index.all_counts(t) for t in distinct}
            candidates={cid for cid in set.intersection(*(set(maps[t]) for t in distinct)) if cid in active}
            index.work["candidate_checks"]+=len(candidates)
            hot_tf={}
            if hot is not None and candidates:
                hot_tf={cid:tf for cid,tf in db.execute(
                    "SELECT rowid,cdg_count(hot_docs) FROM hot_docs WHERE hot_docs MATCH ?",
                    (ar.quote(phrase),))}
                index.work["hot_phrase_queries"]+=1
                index.work["hot_matches"]+=len(hot_tf)
            matches={};cache={}
            covered=[(i,t) for i,t in enumerate(qids) if index.directory(t) is not None]
            complete=len(covered)==len(qids)
            for cid in candidates:
                if hot is not None and cid in hot:
                    tf=hot_tf.get(cid,0);index.work["hot_exact"]+=1
                    if tf:matches[cid]=tf
                    continue
                lists=None;upper=None
                if len(covered)>=2:
                    lists=[]
                    for i,t in covered:
                        k=index.block_of(t,cid)
                        if k is None:lists=None;break
                        ps=index.block(t,k,True)["positions"].get(cid)
                        if ps is None:lists=None;break
                        lists.append((i,ps))
                    if lists is not None:
                        upper=shifted_count(lists,lens[active[cid][0]],len(qids))
                        if not upper:index.work["position_rejections"]+=1;continue
                        if complete:
                            matches[cid]=upper;index.work["position_exact"]+=1;continue
                if cid not in cache:
                    raw,dd,ab=recover(db,cid)
                    cache[cid]=b" ".join(tokens(db,raw.decode("utf8")))
                    index.work["source_reads"]+=1
                    index.work["source_decoded_bytes"]+=dd
                    index.work["source_activated_bytes"]+=ab
                tf=phrase_count(cache[cid],qs)
                if upper is not None and tf>upper:raise AssertionError("position bound violated")
                if tf:matches[cid]=tf
                index.work["source_resolved"]+=1
        expanded={g:tf for cid,tf in matches.items() for g in active[cid]}
        if any(not 1<=tf<=lens[g] for g,tf in expanded.items()):raise ValueError("frequency bound")
        freq.append(expanded)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,index.work

def run(events,manifest,cuts,folder,ext,corpus):
    global EXTENSION
    EXTENSION=ext
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    for ref in refs.values():ref.close()
    base=folder/"base.sqlite"
    db,base_size=f.build(base,ext,events,"marginal",False)
    terms=cs.extract(db)                       # needs docs_0, before the tape build drops it
    base_size.update(tt.build_tape(db,base,events,"frequency"))
    ids,_=tt.vocabulary(db)
    if set(terms)!=set(ids):raise AssertionError("statistics and vocabulary differ")
    split=cs.split_plan(qs)
    plan=[(c,p,o) for c in cuts for p,o in split["train"]]
    value=cs.workload_value(db,plan,ids,cs.make_freq_lookup(db))
    rows=cs.score_terms(terms,ids,"train_candidates",value)
    db.close()
    base_bytes=base.stat().st_size
    chosen,selection_bytes=cs.greedy(rows,0.10*base_bytes)
    inverse={ids[t]:(s,e) for t,(s,e) in terms.items()}
    payload=sum(len(inverse[t][1]["body"])+len(inverse[t][1]["dir"]) for t in chosen)
    layouts=[("freq",0,False),("sel",0,False),("sel_unified",0,True),
             ("hot256",256,False),("hot1024",1024,False),("hot4096",4096,False),
             ("sel_unified_hot1024",1024,True)]
    out={}
    for i,(name,hot_k,unify) in enumerate(layouts):
        path=folder/("layout-%d.sqlite"%i)
        db=materialize(base,path,terms,ids,[] if name=="freq" else chosen,unify)
        hot=build_hot(db,hot_k) if hot_k else None
        db.commit();db.execute("VACUUM")
        sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
        db.close()
        db=connect(path,ext);index=BlockIndex(db,ids,True)
        preps={c:prepare(db,c) for c in cuts}
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g)
            if raw!=want:raise AssertionError("source mismatch")
        plan_q=list(expected);rng=random.Random(175);times=[];classes=collections.defaultdict(list)
        work=collections.Counter();err=0.0
        for _ in range(2):
            rng.shuffle(plan_q)
            for c,p,o in plan_q:
                group="unigram_only" if all(len(tokens(db,q))==1 for q in p) else "has_phrase"
                t=time.perf_counter_ns()
                hits,df,w=rank_joint(db,p,o,preps[c],index,hot)
                times.append((time.perf_counter_ns()-t)/1000);classes[group].append(times[-1])
                work.update(w)
                err=max(err,h.verify(hits,expected[c,p,o]))
        hot_pages=sum(v for k2,v in sizes.items() if k2.startswith("hot_docs"))
        out[name]=dict(sqlite_bytes=path.stat().st_size,table_bytes=sizes,
            base_archive_bytes=base_bytes,selected_terms=(0 if name=="freq" else len(chosen)),
            selected_payload_bytes=(0 if name=="freq" else payload),
            unified_terms=(len(chosen) if unify else 0),
            hot_contents=(0 if not hot_k else len(hot)),hot_index_bytes=hot_pages,
            index_dependency_depth=(0 if not hot_k else 1),
            source_dependency_depth_max=1,
            query=quant_us(times),query_by_class={k:quant_us(v) for k,v in classes.items()},
            rank_checks=len(times),score_error=err,work=dict(work),
            decoded_bytes_per_query=(work.get("decoded_bytes",0)+work.get("source_decoded_bytes",0))/max(1,len(times)),
            activated_bytes_per_query=(work.get("storage_bytes_activated",0)+work.get("source_activated_bytes",0))/max(1,len(times)),
            peak_rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        print("LAYOUT_JSON="+json.dumps({k:out[name][k] for k in
            ("sqlite_bytes","selected_terms","hot_contents","query","score_error")}),flush=True)
        db.close();path.unlink()
    base.unlink()
    return dict(round=175,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),
        selection=dict(terms=len(chosen),payload_bytes=payload,bytes=selection_bytes,
                       split_sizes={k:len(v) for k,v in split.items()}),
        layouts=out,limitations=[
          "source layer fixed to the R149 marginal recipe in every layout",
          "the hot region is a native positional FTS5 table over the k highest service-cost contents",
          "legacy R167 signed corrections were not re-measured in this run; R173's adaptive arm is the reference",
          "logical activation only, no physical I/O; peak RSS is process-wide",
          "one machine, two shuffled warm passes, 640 rank checks per layout"])

def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True)
    p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    return p.parse_args()

if __name__=="__main__":
    a=parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="clark":
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex()
            if manifest!="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f":raise ValueError("CLARK manifest")
            n=len(events);cuts=[n//4,n//2,3*n//4,n]
        else:
            events,_,m=nr.load(a.source,a.target,folder);manifest=m["source_manifest_sha256"]
            n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            got=json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
            if manifest!=got:raise ValueError("AP manifest")
        result=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
