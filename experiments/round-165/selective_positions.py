"""R172: selective exact positional postings over a frequency index.

Finalized archive; no training-query selection, no physical I/O guarantee.
"""
import argparse,collections,itertools,json,random,tempfile,time
from pathlib import Path
import signed_phrase as sp
import token_tape as tt
from frequency_index import f,h,si,connect,nr,ar,tokens,query_plan,prepare,recover
from compact_fragments import varint,unpack
from forward_index import phrase_count

HERE=Path(__file__).resolve().parent

def pack_positions(rows):
    out=bytearray();prev=0
    for cid,positions in rows:
        if cid<=prev or not positions:raise ValueError("position posting order")
        out.extend(varint(cid-prev));out.extend(varint(len(positions)));prev=cid
        last=-1
        for pos in positions:
            if pos<=last:raise ValueError("position order")
            out.extend(varint(pos-last));last=pos
    return bytes(out)

def unpack_positions(raw):
    i=0;cid=0
    def get():
        nonlocal i
        n=shift=0
        while i<len(raw) and shift<=63:
            b=raw[i];i+=1;n|=(b&127)<<shift
            if b<128:return n
            shift+=7
        raise ValueError("truncated position varint")
    while i<len(raw):
        step=get();n=get()
        if not step or not n or n>len(raw)-i:raise ValueError("invalid position posting")
        cid+=step;last=-1;positions=[]
        for _ in range(n):
            step=get()
            if not step:raise ValueError("nonincreasing position")
            last+=step;positions.append(last)
        yield cid,positions

def shifted_count(covered,dl,length):
    """Upper bound on phrase TF for partial coverage, exact if full coverage."""
    if not covered:raise ValueError("empty coverage")
    i,positions=min(covered,key=lambda x:len(x[1]))
    starts={p-i for p in positions if 0<=p-i<=dl-length}
    for j,ps in covered:
        if j!=i:starts.intersection_update(p-j for p in ps)
        if not starts:break
    return len(starts)

def build_positions(db,limit):
    start=time.perf_counter_ns()
    db.execute("CREATE VIRTUAL TABLE temp.select_vocab USING fts5vocab(main,docs_0,'row')")
    vocab=list(db.execute("SELECT term,doc FROM temp.select_vocab ORDER BY term"))
    tids={t:i for i,(t,_) in enumerate(vocab,1)}
    chosen={t for t,_ in sorted(vocab,key=lambda r:(-r[1],r[0]))[:limit]} if limit is not None else set(tids)
    db.execute("DROP TABLE temp.select_vocab")
    db.execute("CREATE TABLE term_positions(tid INTEGER PRIMARY KEY,n INTEGER NOT NULL,z INTEGER NOT NULL,body BLOB NOT NULL)")
    db.execute("CREATE VIRTUAL TABLE temp.pos_vocab USING fts5vocab(main,docs_0,'instance')")
    if limit is None:
        groups=itertools.groupby(db.execute("SELECT term,doc,offset FROM temp.pos_vocab ORDER BY term,doc,offset"),key=lambda r:r[0])
    else:
        groups=((t,db.execute("SELECT term,doc,offset FROM temp.pos_vocab WHERE term=? ORDER BY doc,offset",(t,))) for t in sorted(chosen))
    stats=collections.Counter()
    for term,rows in groups:
        postings=[(cid,[p for _,_,p in rs]) for cid,rs in itertools.groupby(rows,key=lambda r:r[1])]
        raw=pack_positions(postings)
        assert list(unpack_positions(raw))==postings
        z,body=tt.payload(raw)
        db.execute("INSERT INTO term_positions VALUES(?,?,?,?)",(tids[term],len(raw),z,body))
        stats["position_payload_bytes"]+=len(body)
        stats["position_raw_bytes"]+=len(raw)
        stats["position_occurrences"]+=sum(len(p) for _,p in postings)
        stats["position_doc_pairs"]+=len(postings)
    db.execute("DROP TABLE temp.pos_vocab")
    assert db.execute("SELECT count(*) FROM term_positions").fetchone()[0]==len(chosen)
    return dict(selected_terms=len(chosen),position_build_us=(time.perf_counter_ns()-start)/1000,**stats)

def rank_selective(db,p,o,prep,ids,selected):
    ar.expression(p,o);active,lens,n,total=prep;freq=[];work=collections.Counter()
    cache={};post={};positions={}
    for phrase in p:
        qs=tokens(db,phrase)
        if not 1<=len(qs)<=sp.L:raise ValueError("unsupported phrase length")
        qids=[ids.get(t) for t in qs]
        if None in qids:freq.append({});continue
        for tid in set(qids):
            if tid not in post:
                row=db.execute("SELECT n,z,body FROM token_postings WHERE tid=?",(tid,)).fetchone()
                post[tid]=dict(unpack(tt.unpayload(*row)))
                work["posting_bytes"]+=len(row[2])
        if len(qids)==1:
            matches={cid:tf for cid,tf in post[qids[0]].items() if cid in active}
        else:
            candidates=set.intersection(*(set(post[t]) for t in set(qids)))
            candidates.intersection_update(active)
            work["candidate_checks"]+=len(candidates)
            covered=[(i,t) for i,t in enumerate(qids) if t in selected]
            complete=len(covered)==len(qids)
            # One stored position list for one occurrence cannot check adjacency.
            # If coverage is partial, only load lists when >=2 offsets can constrain it.
            use_positions=len(covered)>=2
            if use_positions and candidates:
                for _,tid in covered:
                    if tid not in positions:
                        row=db.execute("SELECT n,z,body FROM term_positions WHERE tid=?",(tid,)).fetchone()
                        positions[tid]=dict(unpack_positions(tt.unpayload(*row)))
                        work["position_bytes"]+=len(row[2])
                        work["position_decoded_bytes"]+=row[0]
            matches={}
            for cid in candidates:
                if use_positions:
                    lists=[(i,positions[t][cid]) for i,t in covered]
                    upper=shifted_count(lists,lens[active[cid][0]],len(qids))
                    if not upper:
                        work["position_rejections"]+=1;continue
                    if complete:
                        matches[cid]=upper;work["position_exact"]+=1;continue
                if cid not in cache:
                    raw,dd,ab=recover(db,cid)
                    cache[cid]=b" ".join(tokens(db,raw.decode("utf8")))
                    work["source_reads"]+=1
                    work["source_decoded_bytes"]+=dd;work["source_activated_bytes"]+=ab
                tf=phrase_count(cache[cid],qs)
                if use_positions:assert tf<=upper
                if tf:matches[cid]=tf
        expanded={g:tf for cid,tf in matches.items() for g in active[cid]}
        assert all(1<=tf<=lens[g] for g,tf in expanded.items())
        freq.append(expanded)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,work

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    checker=connect(":memory:",ext)
    qs=[(p,o) for p,o in qs if all(1<=len(tokens(checker,x))<=sp.L for x in p)]
    checker.close()
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    results={};sigs={}
    for mode,limit in (("positional",0),("adaptive",0),("frequency",0),("top32",32),("top128",128),("top512",512),("all_positions",None)):
        path=folder/(mode+".sqlite");db,size=f.build(path,ext,events,"marginal",False)
        if mode=="adaptive":
            size.update(sp.build_delta(db,path,events,"independent_adaptive_weighted_adjusted_multi"))
        elif mode!="positional":
            if limit!=0:size.update(build_positions(db,limit))
            size.update(tt.build_tape(db,path,events,"frequency"))
            size["index_bytes"]+=size["table_bytes"].get("term_positions",0)
        db.close();db=connect(path,ext)
        ids={};selected=set();mapping=None;t=time.perf_counter_ns()
        if mode=="adaptive":mapping=sp.load_patch_map(db)
        elif mode!="positional":
            ids,_=tt.vocabulary(db)
            if limit!=0:selected={tid for tid, in db.execute("SELECT tid FROM term_positions")}
        setup=(time.perf_counter_ns()-t)/1000
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g);assert raw==want
            assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns()
            preps[c]=sp.prepare_delta(db,c,mapping) if mode=="adaptive" else prepare(db,c)
            pt.append((time.perf_counter_ns()-t)/1000)
        plan=list(expected);rng=random.Random(170);times=[];classes=collections.defaultdict(list);work=collections.Counter();err=0.
        covered_queries=partial_queries=0
        for _ in range(2):
            rng.shuffle(plan)
            for c,p,o in plan:
                group="unigram_only" if all(len(tokens(db,q))==1 for q in p) else "has_phrase"
                t=time.perf_counter_ns()
                if mode=="positional":hits,df=si.rank(db,1,p,o,preps[c])
                elif mode=="adaptive":hits,df,w=sp.rank_delta(db,p,o,preps[c]);work.update(w)
                else:hits,df,w=rank_selective(db,p,o,preps[c],ids,selected);work.update(w)
                dt=(time.perf_counter_ns()-t)/1000;times.append(dt);classes[group].append(dt)
                err=max(err,h.verify(hits,expected[c,p,o]))
                if (c,p,o) in sigs:assert sigs[c,p,o]==(hits,df)
                else:sigs[c,p,o]=(hits,df)
                if mode not in ("positional","adaptive"):
                    for q in p:
                        ts=tokens(db,q)
                        if len(ts)>1:
                            count=sum(ids.get(x) in selected for x in ts)
                            covered_queries+=int(count==len(ts))
                            partial_queries+=int(2<=count<len(ts))
        results[mode]=dict(**size,setup_us=setup,prepare=h.quant(pt),source_checks=len(events),
            query=h.quant(times),query_by_class={k:h.quant(v) for k,v in classes.items()},
            rank_checks=len(times),max_score_error=err,work=dict(work),
            fully_covered_phrase_executions=covered_queries,partially_covered_phrase_executions=partial_queries)
        print("ARM_JSON="+json.dumps(results[mode]),flush=True);db.close()
    assert results["all_positions"]["work"].get("source_reads",0)==0
    for ref in refs.values():ref.close()
    return dict(round=172,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),policies=results,
        limitations=["finalized matched archive, no transaction guarantee","positions selected by full-archive content document frequency, not query labels; not online selection",
        "top32/128/512 fixed in advance, full positions control duplicates frequency lists and positions",
        "full term position lists decoded in Python, no skip blocks, no physical IO claim",
        "partial coverage rejects impossible starts, remaining candidates read source; exact BM25 and DF",
        "two shuffled warm passes; no independent held-out query workload or novelty claim"])

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
            n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            assert manifest==json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
        result=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
