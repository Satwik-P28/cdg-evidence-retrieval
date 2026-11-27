"""R174: cost-based selective positional materialization.

R172 selected terms by document frequency and R173 showed that block-addressable
positions make *partial* coverage useful: a phrase with two covered offsets can
reject a candidate without reading its source.  This round asks which terms deserve
positions under an explicit byte budget.

Policies are corpus-statistics-only (document frequency, collection frequency,
source reconstruction expense, historical revision redundancy, and a
value-per-byte ratio) or trained on a disjoint split of the frozen query plan
(candidate-rejection opportunities per byte).  Optimizers are greedy ratio, a
reduced 0/1 knapsack over the highest-ratio candidates, and one-swap local search.

Every persistent structure is charged: the position blocks, their per-term
directories and the selected-term table.  The held-out split is never used for
selection, budget choice or hyper-parameter tuning.
"""
import argparse,collections,hashlib,itertools,json,random,shutil,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-173"))
from blocked_positions import (encode_term,BlockIndex,rank_blocked,quant_us,
    f,h,tt,connect,nr,tokens,query_plan,prepare,recover)
from compact_fragments import unpack

BLOCK=32
CODEC="best"
COMPRESS=True
BUDGETS=(1,2,5,10,20,40)
POLICIES=("df","cf","srccost","redundancy","train_candidates")

def split_plan(queries,salt="r174"):
    """Deterministic 60/20/20 split of the frozen query plan."""
    parts=collections.defaultdict(list)
    for q in queries:
        bucket=hashlib.sha256((salt+repr(q)).encode()).digest()[0]%10
        parts["train" if bucket<6 else "validation" if bucket<8 else "heldout"].append(q)
    return dict(parts)

def extract(db):
    """One pass: encoded blocks per term plus term statistics, keyed by term bytes."""
    src={};redundancy={};dl={}
    for cid,g in db.execute("SELECT cid,min(g) FROM revisions GROUP BY cid"):
        _,dd,ab=recover(db,g)
        src[cid]=ab
    for cid,n in db.execute("SELECT cid,count(*) FROM revisions GROUP BY cid"):redundancy[cid]=n
    for cid,n in db.execute("SELECT cid,max(dl) FROM revisions GROUP BY cid"):dl[cid]=n
    db.execute("CREATE VIRTUAL TABLE temp.terms USING fts5vocab(main,docs_0,'instance')")
    terms={}
    for term,group in itertools.groupby(db.execute("SELECT term,doc,offset FROM temp.terms ORDER BY term,doc,offset"),
                                        key=lambda r:r[0]):
        postings=[(cid,[p for _,_,p in rs]) for cid,rs in itertools.groupby(group,key=lambda r:r[1])]
        enc=encode_term(postings,BLOCK,CODEC,COMPRESS)
        stats=dict(df=len(postings),cf=sum(len(p) for _,p in postings),
                   posbytes=len(enc["body"])+len(enc["dir"]),blocks=enc["blocks"],
                   srccost=sum(src.get(cid,0)*redundancy.get(cid,1) for cid,_ in postings),
                   redundancy=sum(redundancy.get(cid,1) for cid,_ in postings),
                   avgdl=sum(dl.get(cid,1) for cid,_ in postings)/max(1,len(postings)))
        terms[term.encode("utf8")]=(stats,enc)
    db.execute("DROP TABLE temp.terms")
    return terms

def make_freq_lookup(db):
    cache={}
    def lookup(tid):
        if tid not in cache:
            row=db.execute("SELECT n,z,body FROM token_postings WHERE tid=?",(tid,)).fetchone()
            cache[tid]=set(dict(unpack(tt.unpayload(*row)))) if row else set()
        return cache[tid]
    return lookup

def workload_value(db,plan,ids,lookup):
    """Candidate-rejection opportunities per term: candidates sharing the phrase."""
    value=collections.Counter()
    for _,p,_ in plan:
        for phrase in p:
            qids=[ids.get(t) for t in tokens(db,phrase)]
            if len(qids)<2 or None in qids:continue
            distinct=list(dict.fromkeys(qids))
            sets=[lookup(t) for t in distinct]
            if not all(sets):continue
            candidates=set.intersection(*sets)
            share=len(candidates)/max(1,len(distinct)-1)
            for t in distinct:value[t]+=share
    return value

def score_terms(terms,ids,policy,workload_value_map):
    """Rank terms by value per stored byte.

    The marginal physical cost is always the measured block payload plus
    directory bytes for that term; only the value model changes with policy.
    """
    rows=[]
    for term,(stats,enc) in terms.items():
        tid=ids.get(term)
        if tid is None:raise ValueError("term not in vocabulary")
        if policy in ("df","ratio_df"):value=stats["df"]
        elif policy=="cf":value=stats["cf"]
        elif policy=="srccost":value=stats["srccost"]
        elif policy=="redundancy":value=stats["redundancy"]
        elif policy in ("train_candidates","train_value"):
            value=workload_value_map.get(tid,0.0)
            if not value:continue
        else:raise ValueError("policy")
        cost=float(stats["posbytes"])
        rows.append((value/max(cost,1.0),float(value),cost,tid))
    rows.sort(key=lambda r:(-r[0],-r[1],r[3]))
    return rows

def topk(terms,ids,k):
    """R172's policy: the k highest-document-frequency terms, cost ignored."""
    inverse={ids[t]:(s,e) for t,(s,e) in terms.items() if t in ids}
    ranked=sorted(((inverse[tid][0]["df"],tid) for tid in inverse),key=lambda r:(-r[0],r[1]))[:k]
    rows=[]
    for df,tid in ranked:
        cost=float(inverse[tid][0]["posbytes"])
        rows.append((df/max(cost,1.0),float(df),cost,tid))
    return rows

def greedy(rows,budget):
    chosen=[];spent=0.0
    for ratio,value,cost,tid in rows:
        if cost>budget-spent:continue
        chosen.append(tid);spent+=cost
    return chosen,spent

def knapsack(rows,budget,limit=250,slots=4000):
    """Reduced 0/1 knapsack over the highest-ratio candidates.

    Budget is discretized into ``slots`` capacity units so the DP stays
    tractable; the returned set is then trimmed to respect the hard byte budget,
    so the discretisation can only under-fill, never overspend.
    """
    head=rows[:limit]
    if budget<=0 or not head:return [],0.0
    unit=budget/slots;cap=slots
    weights=[max(1,int(round(r[2]/unit))) for r in head]
    best=[0.0]*(cap+1);take=[bytearray(cap+1) for _ in head]
    for i,(ratio,value,cost,tid) in enumerate(head):
        w=weights[i]
        if w>cap:continue
        row=take[i]
        for c in range(cap,w-1,-1):
            cand=best[c-w]+value
            if cand>best[c]:best[c]=cand;row[c]=1
    chosen=[];c=cap
    for i in range(len(head)-1,-1,-1):
        if take[i][c]:chosen.append(head[i][3]);c-=weights[i]
    chosen.reverse()
    cost_of={r[3]:r[2] for r in head};ratio_of={r[3]:r[0] for r in head}
    spent=sum(cost_of[t] for t in chosen)
    while chosen and spent>budget:
        worst=min(chosen,key=lambda t:(ratio_of[t],t))
        chosen.remove(worst);spent-=cost_of[worst]
    return chosen,spent

def local_search(rows,budget,chosen,rounds=6,limit=250):
    """One-swap improvement toward higher value per byte (bounded search)."""
    by_tid={r[3]:r for r in rows}
    selected=set(chosen);spent=sum(by_tid[t][2] for t in selected)
    for _ in range(rounds):
        order=sorted(selected,key=lambda t:by_tid[t][0])[:8]
        improved=False
        for candidate in rows[:limit]:
            if candidate[3] in selected:continue
            victim=next((t for t in order if spent-by_tid[t][2]+candidate[2]<=budget
                         and by_tid[t][0]<candidate[0] and by_tid[t][1]<candidate[1]),None)
            if victim is None:continue
            selected.discard(victim);selected.add(candidate[3])
            spent+=candidate[2]-by_tid[victim][2];improved=True
            break
        if not improved:break
    return sorted(selected),spent

def materialize(base,path,terms,ids,chosen):
    shutil.copyfile(base,path)
    db=connect(path,EXTENSION)
    db.execute("CREATE TABLE selected_terms(tid INTEGER PRIMARY KEY)")
    db.executemany("INSERT INTO selected_terms VALUES(?)",((t,) for t in chosen))
    db.execute("CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,"
               "nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)")
    by_tid={ids[t]:(s,e) for t,(s,e) in terms.items()}
    payload=directory=0
    for tid in chosen:
        stats,enc=by_tid[tid]
        db.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",(tid,stats["df"],enc["blocks"],enc["dir"],enc["body"]))
        payload+=len(enc["body"]);directory+=len(enc["dir"])
    db.commit();db.execute("VACUUM")
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    db.close()
    return dict(sqlite_bytes=path.stat().st_size,table_bytes=sizes,
                selected_terms=len(chosen),selected_payload_bytes=payload,
                selected_directory_bytes=directory,
                selected_table_bytes=sizes.get("term_blocks",0)+sizes.get("selected_terms",0))

EXTENSION=None

def evaluate(db,ids,cuts,expected,splits,archive_bytes):
    index=BlockIndex(db,ids,True)
    preps={c:prepare(db,c) for c in cuts}
    out={}
    for name,plan in dict(splits,all=[q for part in splits.values() for q in part]).items():
        entries=[(c,p,o) for c in cuts for p,o in plan]
        order=list(entries);random.Random(174).shuffle(order)
        times=[];work=collections.Counter();err=0.0
        for _ in range(2):
            for c,p,o in order:
                t=time.perf_counter_ns()
                hits,_,w=rank_blocked(db,p,o,preps[c],index)
                times.append((time.perf_counter_ns()-t)/1000);work.update(w)
                err=max(err,h.verify(hits,expected[c,p,o]))
        q=quant_us(times)
        out[name]=dict(query=q,work=dict(work),rank_checks=len(times),score_error=err,
                       bytes_per_query_median=q["median_us"],archive_bytes=archive_bytes)
    return out

def run(events,manifest,cuts,folder,ext,corpus,only=None,max_arms=None):
    global EXTENSION
    EXTENSION=ext
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    splits=split_plan(qs)
    for ref in refs.values():ref.close()
    base=folder/"base.sqlite"
    build_start=time.perf_counter()
    db,base_size=f.build(base,ext,events,"marginal",False)
    terms=extract(db)
    base_size.update(tt.build_tape(db,base,events,"frequency"))
    build_seconds=time.perf_counter()-build_start
    ids,_=tt.vocabulary(db)
    if set(terms)!=set(ids):raise AssertionError("statistics and vocabulary differ")
    lookup=make_freq_lookup(db)
    train_plan=[(c,p,o) for c in cuts for p,o in splits["train"]]
    value_map=workload_value(db,train_plan,ids,lookup)
    db.close()
    base_bytes=base.stat().st_size
    rows_cache={p:score_terms(terms,ids,p,value_map) for p in POLICIES}
    configs=[]
    for policy in POLICIES:
        for pct in BUDGETS:
            configs.append(dict(policy=policy,budget_pct=pct,optimizer="greedy"))
    for k in (32,128,512):
        configs.append(dict(policy="df_topk",k=k,optimizer="fixed"))
    for policy in ("df","train_candidates"):
        for pct in (5,10):
            configs.append(dict(policy=policy,budget_pct=pct,optimizer="knapsack"))
            configs.append(dict(policy=policy,budget_pct=pct,optimizer="local_search"))
    out={}
    for i,cfg in enumerate(configs):
        name=("%s-k%d-fixed"%(cfg["policy"],cfg["k"]) if cfg["optimizer"]=="fixed"
              else "%s-%d%%-%s"%(cfg["policy"],cfg["budget_pct"],cfg["optimizer"]))
        if only and name not in only:continue
        if max_arms is not None and len(out)>=max_arms:break
        if cfg["optimizer"]=="fixed":
            rows=topk(terms,ids,cfg["k"]);budget=float("inf");chosen=[r[3] for r in rows]
            spent=sum(r[2] for r in rows)
        else:
            budget=cfg["budget_pct"]/100.0*base_bytes
            rows=rows_cache[cfg["policy"]]
            if cfg["optimizer"]=="greedy":chosen,spent=greedy(rows,budget)
            elif cfg["optimizer"]=="knapsack":chosen,spent=knapsack(rows,budget)
            else:
                seed,_=greedy(rows,budget);chosen,spent=local_search(rows,budget,seed)
        path=folder/("arm-%d.sqlite"%i)
        materialize_start=time.perf_counter()
        size=materialize(base,path,terms,ids,chosen)
        materialize_seconds=time.perf_counter()-materialize_start
        db=connect(path,ext)
        stats=evaluate(db,ids,cuts,expected,splits,size["sqlite_bytes"])
        db.close();path.unlink()
        out[name]=dict(**cfg,**{k:v for k,v in size.items() if k!="table_bytes"},
            table_bytes=size["table_bytes"],selection_bytes=spent,
            budget_bytes=(None if budget==float("inf") else budget),
            budget_fraction=size["sqlite_bytes"]/base_bytes,
            build_seconds=round(build_seconds,3),materialize_seconds=round(materialize_seconds,3),
            splits=stats)
        print("ARM_JSON="+json.dumps(dict(name=name,sqlite=size["sqlite_bytes"],selected=len(chosen),
            heldout_p95=stats["heldout"]["query"]["p95_us"],heldout_median=stats["heldout"]["query"]["median_us"],
            heldout_src=stats["heldout"]["work"].get("source_reads",0),
            all_p95=stats["all"]["query"]["p95_us"])),flush=True)
    sweep=dict(base_archive_bytes=base_bytes,block=BLOCK,codec=CODEC,compression="zstd" if COMPRESS else "raw",
        budgets=BUDGETS,policies=list(POLICIES),split_sizes={k:len(v) for k,v in splits.items()},
        frequency_archive_bytes=base_bytes,terms=len(terms),build_seconds=round(build_seconds,3),
        position_bytes_all_terms=sum(s["posbytes"] for s,_ in terms.values()))
    base.unlink()
    return dict(round=174,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),
        split_manifest={k:h.sha(h.canonical(v)).hex() for k,v in splits.items()},
        sweep=sweep,policies=out,limitations=[
          "selective materialization on top of an exact frequency archive; sources unchanged",
          "selection uses the train split only; budgets and optimizers were not tuned on the held-out split",
          "value models are analytic proxies (candidate opportunities, source bytes), not measured per-query benefit",
          "logical activation only; two shuffled warm passes per split; no cold cache claim",
          "the held-out split has 16 queries x 4 cutoffs = 64 rank checks per arm"])


def parse_args():
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True)
    p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);    p.add_argument("--only",default="")
    p.add_argument("--max-arms",type=int,default=0)
    return p.parse_args()

if __name__=="__main__":
    a=parse_args();only={x for x in a.only.split(",") if x} or None
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
        result=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus,only,
                   a.max_arms or None)
        if a.out.exists():
            old=json.loads(a.out.read_text())
            if old.get("manifest_sha256")==manifest:
                old["policies"].update(result["policies"]);result=old
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
