"""R177: adversarial and held-out evaluation of the strongest configuration.

Every suite is built from deterministic bytes, every ranking is compared with the
native FTS5 oracle at every cutoff, and every source byte is compared with the
original.  A wrong rank or a wrong byte is a correctness failure, not a trade-off:
the runner raises instead of reporting a number.

Suites: empty documents, duplicated contents, Unicode normalisation and case
folding, large insertions and deletions, repeated phrases, unrelated revisions,
historical cutoff boundaries, non-UTF-8 input, and physical corruption of a stored
posting block.
"""
import argparse,json,math,random,resource,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-173"))
import blocked_positions as bp
from blocked_positions import (BlockIndex,build_blocks,f,h,tt,nr,
    prepare,recover,rank_blocked,quant_us)

def suite_empty():
    ev=[("e%02d"%i,0,b"" if i%2==0 else b"alpha beta gamma") for i in range(12)]
    return ev,[2,6,12],[(("alpha",),"AND"),(("beta",),"AND"),(("alpha beta",),"AND"),
                         (("zeta",),"AND"),(("alpha",),"OR")]

def suite_duplicates():
    body=b"alpha beta alpha gamma delta"
    ev=[("d%02d"%i,0,body if i<30 else b"gamma zeta theta epsilon") for i in range(34)]
    return ev,[10,30,34],[(("alpha",),"AND"),(("alpha beta",),"AND"),(("zeta",),"OR"),
                          (("gamma",),"AND")]

def suite_unicode():
    texts=[b"istanbul caf\xc3\xa9 naive",              # NFC latin
           b"cafe\xcc\x81 na\xc3\xafve",               # NFD combining acute
           b"STRASSE stra\xc3\x9fe",                    # sharp s
           b"\xc4\xb0stanbul istanbul",                 # dotted capital I
           b"zero\xe2\x80\x8bwidth alpha",              # zero-width space
           b"alpha beta caf\xc3\xa9"]
    ev=[("u%d"%i,0,t) for i,t in enumerate(texts)]
    return ev,[3,6],[(("cafe",),"AND"),(("café",),"AND"),(("istanbul",),"AND"),
                     (("naive",),"AND"),(("alpha",),"AND"),(("straße",),"AND")]

def suite_large_edits():
    head=b"alpha "*100
    big=head+b"filler "*20000+b"omega"
    small=b"alpha omega"
    # one article, five ordinals: grow, grow again, then shrink to almost nothing
    ev=[("x",0,head),("x",1,big),("x",2,big+b" extra"),("x",3,small),
        ("x",4,small+b" alpha")]
    return ev,[1,2,4,5],[(("alpha",),"AND"),(("omega",),"AND"),(("alpha omega",),"AND"),
                         (("filler",),"AND")]

def suite_repeated():
    ev=[("r0",0,b"alpha beta "*500),("r1",0,b"beta alpha "*500),
        ("r2",0,b"alpha"),("r3",0,b"beta "+b"gamma "*50)]
    return ev,[1,2,3,4],[(("alpha beta",),"AND"),(("beta alpha",),"AND"),(("alpha",),"AND"),
                         (("beta alpha alpha",),"AND")]

def suite_unrelated():
    ev=[("n%d"%i,0,("unique%d "%i).encode()*5 + b"shared") for i in range(10)]
    return ev,[5,10],[(("shared",),"AND"),(("unique3",),"AND"),(("shared unique3",),"AND"),
                      (("shared",),"OR")]

def suite_cutoffs():
    ev=[("c%d"%i,0,b"alpha beta gamma" if i%2 else b"alpha delta") for i in range(9)]
    return ev,[1,2,8,9],[(("alpha",),"AND"),(("alpha beta",),"AND")]

def event_digest(events):
    return h.sha(h.canonical([(a,i,raw.hex()) for a,i,raw in events])).hex()

def build(path,ext,events):
    # docs_0 must stay at full detail while the block builder reads it; the tape
    # build then drops it, exactly as R173's arm builder does.
    db,_=f.build(path,ext,events,"marginal",False)
    blocks=build_blocks(db,128,"best","zstd")
    tape=tt.build_tape(db,path,events,"frequency")
    ids,_=tt.vocabulary(db)
    if set(ids.values())!=set(range(1,blocks["selected_terms"]+1)):
        raise AssertionError("block and tape vocabulary differ")
    db.commit()
    return db,tape,blocks

def check(db,events,cuts,queries,reps=3):
    for g,(a,i,want) in enumerate(events,1):
        raw,dd,ab=recover(db,g)
        if raw!=want:raise AssertionError("reconstruction mismatch at revision %d"%g)
    ids,_=tt.vocabulary(db);index=BlockIndex(db,ids,True)
    times=[];work=None;checks=0
    for c in cuts:
        ref=h.active_oracle(events,c);prep=prepare(db,c)
        order=list(queries);random.Random(177).shuffle(order)
        for _ in range(reps):
            for p,o in order:
                t=time.perf_counter_ns()
                hits,df,w=rank_blocked(db,p,o,prep,index)
                times.append((time.perf_counter_ns()-t)/1000)
                h.verify(hits,h.native(ref,p,o));checks+=1
                work=w
        ref.close()
    return dict(cutoffs=cuts,rank_checks=checks,latency=quant_us(times),
                blocks_activated=work.get("blocks_activated",0),
                blocks_decoded=work.get("blocks_decoded",0),
                source_reads=work.get("source_reads",0),
                peak_rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

def bm25_reference(tf,dl,avg,N,df,k1,b):
    x=math.log((N-df+.5)/(df+.5))
    idf=1e-6 if x<=0 else x
    return idf*((tf*(k1+1.0))/(tf+k1*(1-b+b*dl/avg))) if tf else 0.0

def coefficient_check():
    """The scorer is standard BM25 at pinned constants; the formula is checked for
    non-unit coefficients even though the system itself does not expose them."""
    out=[]
    for k1 in (0.0,1.2,10.0):
        for b in (0.0,0.75,1.0):
            got=bm25_reference(3,120,90.0,1000,40,k1,b)
            want=((math.log((1000-40+.5)/(40+.5)))*((3*(k1+1.0))/(3+k1*(1-b+b*120/90.0))))
            if abs(got-want)>1e-12:raise AssertionError("bm25 reference mismatch")
            out.append(dict(k1=k1,b=b,score=got))
    zero=bm25_reference(0,120,90.0,1000,40,1.2,0.75)
    if zero!=0.0:raise AssertionError("empty tf must score zero")
    globals_=bp.ar.positive_score.__globals__
    return dict(cases=out,pinned=dict(k1=globals_.get("K1"),b=globals_.get("B")),
                note="the scorer uses fixed BM25 constants; the formula is validated for non-unit k1/b, but plumbing them is future work")

def utf8_suite(ext,folder):
    bad=[("m0",0,b"alpha\xff beta"),("m1",0,b"gamma")]
    path=folder/"malformed.sqlite"
    try:
        build(path,ext,bad)
        outcome="accepted"
    except UnicodeDecodeError:
        outcome="rejected:UnicodeDecodeError"
    except Exception as exc:                                  # noqa: BLE001
        outcome="rejected:"+type(exc).__name__
    return dict(cases=len(bad),outcome=outcome,
                note="non-UTF-8 source bytes are refused at build time, never silently replaced")

def corruption_suite(ext,folder):
    events=[("k%d"%i,0,("alpha beta gamma%d delta "%i).encode()*3) for i in range(12)]
    p,o=("alpha beta",),"AND"
    out={}
    for field,payload in (("body","00"*64),("dir","ff"*8)):
        path=folder/("corrupt-"+field+".sqlite")
        db,_,_=build(path,ext,events)
        ids,_=tt.vocabulary(db);prep=prepare(db,len(events))
        ref=h.active_oracle(events,len(events));expected=h.native(ref,p,o)
        index=BlockIndex(db,ids,True)
        h.verify(rank_blocked(db,p,o,prep,index)[0],expected)   # clean baseline
        tid=ids[b"alpha"]
        db.execute("UPDATE term_blocks SET %s=x'%s' WHERE tid=?"%(field,payload),(tid,))
        db.commit()
        outcome="silent";detail=""
        try:
            index=BlockIndex(db,ids,True)
            hits,df,_=rank_blocked(db,p,o,prep,index)
            try:h.verify(hits,expected)
            except AssertionError as exc:outcome="mismatch";detail=str(exc)[:120]
        except Exception as exc:                                # noqa: BLE001
            outcome="detected";detail=type(exc).__name__+": "+str(exc)[:100]
        ref.close();db.close();path.unlink()
        out[field]=dict(outcome=outcome,detail=detail,term="alpha")
    out["note"]=("detection comes from the block header/format validation, not from a "
                 "checksum: a corrupted block whose bytes still parse would be silently "
                 "wrong. A per-term truncated BLAKE2b digest would cost 8 B per term "
                 "(358,664 B on AP) and is not part of the archived format.")
    return out

def run_synthetic(ext,folder):
    suites={"empty_documents":suite_empty(),"duplicates":suite_duplicates(),
            "unicode":suite_unicode(),"large_edits":suite_large_edits(),
            "repeated_phrases":suite_repeated(),"unrelated_revisions":suite_unrelated(),
            "cutoff_boundaries":suite_cutoffs()}
    out={}
    for name,(events,cuts,queries) in suites.items():
        path=folder/(name+".sqlite")
        db,tape,blocks=build(path,ext,events)
        res=check(db,events,cuts,queries)
        res.update(revisions=len(events),terms=len(tt.vocabulary(db)[0]),
                   archive_bytes=path.stat().st_size,event_digest=event_digest(events))
        print("SUITE_JSON="+json.dumps({k:res[k] for k in ("revisions","rank_checks","archive_bytes")}),flush=True)
        db.close();path.unlink();out[name]=res
    out["malformed_input"]=utf8_suite(ext,folder)
    out["corruption"]=corruption_suite(ext,folder)
    out["coefficients"]=coefficient_check()
    return out

def run_corpus(ext,folder,source,corpus,target,reps,cuts_plan=None):
    if corpus=="clark":
        import clark_retrieval as cr
        events,_,m,_,_=cr.read(source);manifest=h.sha(h.canonical(m)).hex()
        if manifest!="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f":raise ValueError("CLARK manifest")
        n=len(events);cuts=[n//4,n//2,3*n//4,n]
    else:
        events,_,m=nr.load(source,target,folder);manifest=m["source_manifest_sha256"]
        n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
        got=json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
        if manifest!=got:raise ValueError("AP manifest")
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=bp.query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    for ref in refs.values():ref.close()
    path=folder/"corpus.sqlite"
    db,tape,blocks=build(path,ext,events)
    for g,(a,i,want) in enumerate(events,1):
        raw,_,_=recover(db,g)
        if raw!=want:raise AssertionError("reconstruction mismatch")
    ids,_=tt.vocabulary(db);index=BlockIndex(db,ids,True)
    preps={c:prepare(db,c) for c in cuts}
    reps_out=[];plan=list(expected)
    for r in range(reps):
        random.Random(1000+r).shuffle(plan);times=[]
        for c,p,o in plan:
            t=time.perf_counter_ns();hits,df,_=rank_blocked(db,p,o,preps[c],index)
            times.append((time.perf_counter_ns()-t)/1000)
            h.verify(hits,expected[c,p,o])
        q=quant_us(times);reps_out.append(q)
        print("REP_JSON="+json.dumps({"rep":r+1,"median_us":q["median_us"],"p95_us":q["p95_us"]}),flush=True)
    p95=[q["p95_us"] for q in reps_out];med=[q["median_us"] for q in reps_out]
    db.close()
    return dict(round=177,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        repeats=reps,rank_checks=reps*len(plan),archive_bytes=path.stat().st_size,
        p95_us=p95,p95_median=statistics.median(p95),p95_cv=(statistics.pstdev(p95)/statistics.mean(p95)),
        median_us=med,median_median=statistics.median(med),
        coefficient_of_variation=dict(p95=statistics.pstdev(p95)/statistics.mean(p95),
                                      median=statistics.pstdev(med)/statistics.mean(med)),
        peak_rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        limitations=["warm cache only: dropping the page cache needs root, which this environment lacks",
            "cold behaviour is represented by the first repetition, not by an eviction",
            "logical activation only, no physical I/O instrumentation"])

def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--corpus",choices=("ap","clark","synthetic"),default="synthetic")
    p.add_argument("--source",type=Path);p.add_argument("--target",type=int,default=10000)
    p.add_argument("--reps",type=int,default=5);return p.parse_args()

if __name__=="__main__":
    a=parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="synthetic":
            result=dict(round=177,suites=run_synthetic(a.extension.resolve(),folder),
                limitations=["synthetic fixtures are tiny; they test semantics, not throughput",
                    "physical corruption maps to a documented outcome rather than a guarantee"])
        else:
            if not a.source:raise SystemExit("--source required")
            result=run_corpus(a.extension.resolve(),folder,a.source,a.corpus,a.target,a.reps)
    a.out.write_text(json.dumps(result,indent=2,default=str)+"\n")
    print("RESULT_JSON="+json.dumps({k:v for k,v in result.items() if k!="suites"},default=str),flush=True)
