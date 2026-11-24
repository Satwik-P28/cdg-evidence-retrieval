"""R128: proposal-prioritized exact historical ranking after frequency recovery.
Uno-inspired execution order, not diffusion, entropy coding, or a new WAND algorithm.
All block construction and candidate proposal overhead is charged to rank-stage time.
"""
import argparse,collections,heapq,json,random,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-124"))
from positional_temporal import extract_positions,queries,metadata,active,active_oracle,native,score,verify,extension,quote,order,load,select,SALT,PIN
from rank_replay import idf,positive_score

def exact_rank(freq,op,n,total,lengths,aid_by_g,mode,draft=(),audit=False):
    if mode not in ("heap","bound16","bound64","draft16","draft64","bad_draft16"):
        raise ValueError("unknown method")
    sets=[set(m) for m in freq]
    candidates=set.intersection(*sets) if op=="AND" else set.union(*sets)
    work=dict(candidates=len(candidates),scored=0,pruned=0,blocks=0,pruned_blocks=0,draft_scored=0,bound_terms=0)
    if not candidates:return [],work
    avg=total/n;weights=[idf(n,len(m)) for m in freq]
    heap=[];done=set()
    def val(g):
        return sum(positive_score(m.get(g,0),lengths[g],avg,w) for m,w in zip(freq,weights))
    def visit(g,seed=False):
        if g in done:return
        done.add(g);work["scored"]+=1;work["draft_scored"]+=int(seed)
        s=val(g);key=(s,-g)
        if len(heap)<10:heapq.heappush(heap,key)
        elif key>heap[0]:heapq.heapreplace(heap,key)
    if mode=="heap":
        for g in candidates:visit(g)
    else:
        size=64 if mode.endswith("64") else 16
        blocks=collections.defaultdict(list)
        for g in candidates:blocks[(aid_by_g[g]-1)//size].append(g)
        work["blocks"]=len(blocks)
        # For each phrase and each distinct positive TF in this block, choose
        # the shortest actual matching document. At fixed TF the native score
        # is monotone nonincreasing in document length (positive IEEE ops).
        # Maximum of those actual scores bounds each phrase; sum bounds total.
        # Bounds are recomputed from exact current-snapshot statistics, not
        # inherited from the speculative previous snapshot.
        plan=[]
        for bid,gs in blocks.items():
            caps=[]
            for m,w in zip(freq,weights):
                minlen={}
                for g in gs:
                    tf=m.get(g,0)
                    if tf and (tf not in minlen or lengths[g]<minlen[tf]):minlen[tf]=lengths[g]
                work["bound_terms"]+=len(minlen)
                caps.append(max((positive_score(tf,dl,avg,w) for tf,dl in minlen.items()),default=0.0))
            upper=sum(caps)
            if audit and any(val(g)>upper for g in gs):raise AssertionError("unsafe upper bound")
            plan.append((upper,bid,gs))
        if mode.startswith("draft") or mode.startswith("bad_draft"):
            # Draft is an article ID proposal only. Never use its scores or
            # assume all prior hits remain candidates.
            by_a={aid_by_g[g]:g for g in candidates}
            for a in draft:
                if a in by_a:visit(by_a[a],True)
        for upper,bid,gs in sorted(plan,key=lambda x:(-x[0],x[1])):
            rest=[g for g in gs if g not in done]
            if not rest:continue
            # Strict inequality preserves exact row-ID tie breaking.
            if len(heap)==10 and upper<heap[0][0]:
                work["pruned"]+=len(rest);work["pruned_blocks"]+=1
                continue
            for g in rest:visit(g)
    if work["scored"]+work["pruned"]!=len(candidates):raise AssertionError("coverage")
    return sorted(((-ng,-s) for s,ng in heap),key=lambda x:(x[1],x[0])),work

MODES=("heap","bound16","bound64","draft16","draft64","bad_draft16")
def experiment(events,ext,repeats):
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);lens=[0]+[r[4] for r in rows];aid={r[0]:r[1] for r in rows}
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,_,_=queries(pos,freqs,active(rows,cuts[0]))
    previous={};rng=random.Random(128);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values());ref=active_oracle(events,c);extension(ref,ext)
        uniq=sorted({p for ps,_ in qs for p in ps})
        counts={p:dict(ref.execute("SELECT rowid,cdg_count(fulltext) FROM fulltext WHERE fulltext MATCH ?",(quote(p),))) for p in uniq}
        prepared=[];next_previous={};stats={m:collections.Counter() for m in MODES};err={m:0.0 for m in MODES};hits=0
        for ps,op in qs:
            freq=[counts[p] for p in ps];want=native(ref,ps,op);hits+=len(want)
            exhaustive=score(freq,op,len(act),total,lens)[0];verify(exhaustive,want)
            draft=previous.get((ps,op),())
            # Deliberately unrelated proposal: ten deterministic article IDs.
            bad=tuple(sorted(act,reverse=True)[:10])
            for m in MODES:
                got,z=exact_rank(freq,op,len(act),total,lens,aid,m,bad if m=="bad_draft16" else draft,audit=True)
                if got!=exhaustive:raise AssertionError("exact ranking differs")
                err[m]=max(err[m],verify(got,want));stats[m].update(z)
            next_previous[(ps,op)]=tuple(aid[g] for g,_ in want)
            prepared.append((freq,op,draft,bad))
        timings={m:[] for m in ("sort",)+MODES}
        for _ in range(repeats):
            req=list(prepared);rng.shuffle(req)
            for freq,op,draft,bad in req:
                ms=list(timings);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns()
                    if m=="sort":score(freq,op,len(act),total,lens)
                    else:exact_rank(freq,op,len(act),total,lens,aid,m,bad if m=="bad_draft16" else draft)
                    timings[m].append((time.perf_counter_ns()-st)/1000)
        results.append(dict(cutoff=c,queries=len(qs),ranked_hits=hits,previous_proposals=len(previous),
          max_error=err,work={m:dict(z) for m,z in stats.items()},
          median_us={m:statistics.median(v) for m,v in timings.items()},
          p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timings.items()}))
        previous=next_previous;ref.close()
    return dict(revisions=len(rows),vocabulary=len({t for m in pos for t in m}),cutoffs=results,repetitions=repeats)

def run(root,ext,repeats):
    articles,manifest=load(root);cohort=select(articles,len(articles),SALT)
    return dict(round=128,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),
      result=experiment(order(cohort),ext,repeats),limits=[
      "same previously tuned Versions corpus, synthetic chronology, R124 prefix-selected query plan",
      "rank-stage only: native exact phrase counts prepared outside timing for every method",
      "block bounds and candidate sets constructed inside timing; no saved compressed block reads or I/O measured",
      "previous snapshot top-k article proposals, no real query trace, no diffusion model",
      "established safe dynamic pruning (WAND/Block-Max family), not a novelty claim",
      "strict upper-bound comparison, score and row-ID tie parity checked against native"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=5);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
