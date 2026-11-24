"""R139: restricted leaf materialization under a frozen extra payload budget.

Offline compacted counterfactual for existing delta leaves; no physical archive
or online rewrite/transaction claim. Train only on past probes, hold out terms.
"""
import argparse,collections,json,random,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
import news_retrieval as nr
import heldout_archive as h
from anchor_bench import D,delta_decode
SALT="CDG-R139-fold-v1|"
BPS=(1,5,10,50)
POLICIES=("uniform_density","recent","random","lfu","query_density","article_density")

def choose_under_budget(items,score,budget):
    # items: g -> (extra payload bytes, avoided parent raw bytes)
    selected=[];remaining=budget
    for g in sorted(items,key=lambda g:(-score(g),g)):
        if score(g)<=0:continue
        cost,_=items[g]
        if cost<=remaining:selected.append(g);remaining-=cost
    return selected,budget-remaining

def fractional_bound(items,counts,budget):
    value=0.;remaining=budget
    for g in sorted(items,key=lambda g:(-counts[g]*items[g][1]/items[g][0],g)):
        cost,saving=items[g];benefit=counts[g]*saving
        if not benefit or remaining<=0:break
        spend=min(remaining,cost);value+=benefit*spend/cost;remaining-=spend
    return value

def encode(events,train_cut):
    histories=collections.defaultdict(list);by_article=collections.defaultdict(list)
    costs={};base_bytes=0;prefix_bytes=0;frames={}
    for g,(a,i,raw) in enumerate(events,1):
        hist=histories[a];assert len(hist)==i
        parent,depth,payload=h.choose_config(raw,i,hist,"bounded_anchor")
        full=h.C.compress(raw);base_bytes+=len(payload)
        if g<=train_cut:prefix_bytes+=len(payload)
        if depth:
            old,encoded,dep=hist[parent]
            assert dep==0 and len(full)>len(payload)
            assert delta_decode(payload,old,len(raw))==raw
            assert 2*(len(old)+len(raw))<=5*len(raw) and 2*(encoded+len(payload))<=3*len(full)
            costs[g]=(len(full)-len(payload),len(old),encoded+len(payload),len(full),len(raw))
            if g<=train_cut:frames[g]=full
        else:
            assert D.decompress(payload,max_output_size=len(raw)+1)==raw
        hist.append((raw,len(payload),depth));by_article[a].append(g)
    return costs,frames,base_bytes,prefix_bytes

def metrics(events,costs,counts,chosen):
    chosen=set(chosen);requests=sum(counts.values());raw=decoded=activated=0;maxd=maxa=1.
    saved=0;hits=0
    for g,n in counts.items():
        body=events[g-1][2];size=len(body);full=len(h.C.compress(body))
        raw+=n*size
        if g in costs and g not in chosen:
            _,parent,ab,_,_=costs[g];decoded+=n*(size+parent);activated+=n*ab
            if size:maxd=max(maxd,(size+parent)/size)
            maxa=max(maxa,ab/full)
        else:
            decoded+=n*size;activated+=n*full
            if g in chosen:saved+=n*costs[g][1];hits+=n
    assert maxd<=2.5 and maxa<=1.5
    return dict(requests=requests,requested_bytes=raw,decoded_bytes=decoded,activated_bytes=activated,
        avoided_decode_bytes=saved,materialized_hits=hits,mean_decode_ratio=decoded/max(1,raw),
        max_decode_ratio=maxd,max_activation_ratio=maxa)

def trial(source,target,folder):
    events,origins,manifest=nr.load(source,target,folder);n=len(events);initial=len(manifest["retained_paths"])
    cuts=sorted(set([initial,initial+(n-initial)//3,initial+2*(n-initial)//3,n]))
    assert len(cuts)==4;train_cut=cuts[1]
    ref=h.active_oracle(events,cuts[0]);qs=nr.plan(ref);ref.close()
    # Only single-term probes: disjoint lexical terms, not overlapping mixtures.
    single=[(p,o) for p,o in qs if len(p)==1]
    single.sort(key=lambda x:h.sha((SALT+x[0][0]).encode()))
    train=single[::2];test=single[1::2]
    assert train and test and not set(train)&set(test)
    counts=collections.Counter();article_counts=collections.Counter();held={}
    for c in cuts:
        ref=h.active_oracle(events,c)
        if c<=train_cut:
            for p,o in train:
                for g,_ in h.native(ref,p,o):counts[g]+=1;article_counts[events[g-1][0]]+=1
        if c>=train_cut:
            ct=collections.Counter()
            for p,o in test:
                for g,_ in h.native(ref,p,o):ct[g]+=1
            held[str(c)]=ct
        ref.close()
    costs,frames,payload,prefix=encode(events,train_cut)
    frozen=json.loads((HERE.parent/"round-138"/("results-"+str(n)+".json")).read_text())["result"]
    assert manifest["source_manifest_sha256"]==frozen["manifest"]
    assert payload==frozen["policies"]["bounded_anchor"]["payload_bytes"]
    items={g:(v[0],v[1]) for g,v in costs.items() if g<=train_cut}
    all_held=sum(held.values(),collections.Counter())
    rnd=random.Random(139);random_order={g:rnd.random() for g in sorted(items)}
    scores={
        "uniform_density":lambda g:items[g][1]/items[g][0],
        "recent":lambda g:g,
        "random":lambda g:random_order[g],
        "lfu":lambda g:counts[g],
        "query_density":lambda g:counts[g]*items[g][1]/items[g][0],
        "article_density":lambda g:article_counts[events[g-1][0]]*items[g][1]/items[g][0],
    }
    results={}
    for bp in BPS:
        budget=prefix*bp//10000
        arms={}
        for p in POLICIES:
            selected,extra=choose_under_budget(items,scores[p],budget)
            assert extra==sum(costs[g][0] for g in selected)<=budget
            for g in selected:
                raw=events[g-1][2]
                assert D.decompress(frames[g],max_output_size=len(raw)+1)==raw
            arms[p]=dict(materialized=len(selected),extra_payload_bytes=extra,
                train=metrics(events,costs,counts,selected),
                heldout={c:metrics(events,costs,ct,selected) for c,ct in held.items()},
                aggregate_heldout=metrics(events,costs,all_held,selected))
        bound=fractional_bound(items,all_held,budget)
        assert all(a["aggregate_heldout"]["avoided_decode_bytes"]<=bound+1e-6 for a in arms.values())
        results[str(bp)]=dict(budget=budget,heldout_fractional_oracle_upper_bound=bound,policies=arms)
    return dict(revisions=n,documents=initial,source_manifest=manifest["source_manifest_sha256"],
        training_cutoffs=cuts[:2],heldout_cutoffs=cuts[1:],train_terms=len(train),heldout_terms=len(test),
        query_split_sha256=h.sha(h.canonical(dict(train=train,test=test))).hex(),
        prefix_payload=prefix,final_payload=payload,candidate_delta_leaves=len(items),
        train_requests=sum(counts.values()),heldout_requests=sum(all_held.values()),
        baseline_heldout=metrics(events,costs,all_held,[]),budgets=results,
        limitations=["restricted preexisting one-hop leaf substitution, compacted source payload counterfactual",
            "no physical archive size, rewrite cost, update atomicity or latency claim",
            "lexically disjoint artificial probes, not human workload; same cutoff and future-cutoff tests",
            "future revisions ineligible, oracle uses heldout counts only for upper bound",
            "training frequency materialization is established prior art"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:result=trial(a.source,a.target,Path(d))
    x=dict(round=139,result=result);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
