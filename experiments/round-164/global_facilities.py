"""R164: exact reassignment moves, global bounds, restricted MILP.
All gains are relative to literal frames, with exact integer cost accounting.
"""
import argparse,collections,json,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_array
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-163"))
from dictionary_facilities import (DICT_META,load,C,nx,sha,split_roots,masks,candidates,choose,
    cut_clients,serialize,parse,recover,measure)

def model(full,cands,access,t,lam,mu):
    scale=100*t
    weights=[{n:(len(full[n])-len(f))*(scale+lam*access[n].bit_count())
              for n,f in d["frames"].items()} for d in cands]
    opening=[scale*(len(d["stored"])+DICT_META) for d in cands]
    activation=[lam*len(d["stored"])+mu*len(d["raw"]) for d in cands]
    return weights,opening,activation

def bits(mask):
    while mask:
        v=mask&-mask;mask-=v;yield v.bit_length()-1

def value(assignment,w,opening,activation,access):
    unions={};gain=0
    for n,j in assignment.items():
        gain+=w[j][n];unions[j]=unions.get(j,0)|access[n]
    return gain-sum(opening[j]+activation[j]*u.bit_count() for j,u in unions.items())

def closure(weights,implications):
    source=("source",);sink=("sink",);g=nx.DiGraph();g.add_nodes_from((source,sink))
    positive=sum(max(0,v) for v in weights.values());inf=positive+1
    for node,c in weights.items():
        g.add_node(node)
        if c>0:g.add_edge(source,node,capacity=c)
        elif c<0:g.add_edge(node,sink,capacity=-c)
    for a,b in implications:g.add_edge(a,b,capacity=inf)
    v,(left,_)=nx.minimum_cut(g,source,sink,capacity="capacity")
    return left,positive-v

def expansion(assignment,target,w,opening,activation,access):
    # Move any subset of eligible clients to target (-1 = literal).
    possible=sorted(n for n in (access if target==-1 else w[target]) if assignment.get(n,-1)!=target)
    if not possible:return assignment,0
    nodes={("m",n):(0 if target==-1 else w[target][n])-
           (0 if n not in assignment else w[assignment[n]][n]) for n in possible}
    implications=[];can=set(possible);groups=collections.defaultdict(list);byq=collections.defaultdict(list)
    for n,j in assignment.items():
        groups[j].append(n)
        for q in bits(access[n]):byq[j,q].append(n)
    # Cost of opening new facility / newly activated query.
    if target!=-1:
        if target not in groups:
            k=("new",target);nodes[k]=-opening[target]
            implications.extend((("m",n),k) for n in possible)
        for n in possible:
            for q in bits(access[n]):
                if (target,q) not in byq:
                    k=("newq",target,q);nodes[k]=-activation[target];implications.append((("m",n),k))
    # Refund only if every remaining old client is moved.
    for j,ns in groups.items():
        if j!=target and set(ns)<=can:
            k=("close",j);nodes[k]=opening[j];implications.extend((k,("m",n)) for n in ns)
    for (j,q),ns in byq.items():
        if j!=target and set(ns)<=can and activation[j]:
            k=("refund",j,q);nodes[k]=activation[j];implications.extend((k,("m",n)) for n in ns)
    chosen,gain=closure(nodes,implications)
    out=dict(assignment)
    for n in possible:
        if ("m",n) in chosen:
            if target==-1:out.pop(n,None)
            else:out[n]=target
    assert value(out,w,opening,activation,access)-value(assignment,w,opening,activation,access)==gain
    return out,gain

def improve(initial,w,opening,activation,access):
    x=dict(initial);trace=[]
    for sweep in range(3):
        gains=[]
        for j in [-1]+list(range(len(w))):
            new,g=expansion(x,j,w,opening,activation,access)
            if g>0:x=new;gains.append(g)
        trace.append(dict(sweep=sweep,moves=len(gains),gain=sum(gains)))
        if not gains:break
    return x,trace

def bound(w,opening,activation,access):
    # Relax client exclusivity, pricing every client with nonnegative p.
    # Each facility independently optimizes via exact R163 min-cut.
    maxw={n:0 for n in access}
    for ws in w:
        for n,v in ws.items():maxw[n]=max(maxw[n],v)
    price={n:v//2 for n,v in maxw.items()}
    best=sum(maxw.values());trace=[]
    for step in range(5):
        counts=collections.Counter();total=sum(price.values())
        for j,ws in enumerate(w):
            adjusted={n:v-price[n] for n,v in ws.items() if v>price[n]}
            ns,g=cut_clients(adjusted,access,activation[j])
            if g>opening[j]:total+=g-opening[j];counts.update(ns)
        best=min(best,total);trace.append(dict(step=step,upper_bound=total,best=best))
        for n in price:
            direction=1 if counts[n]>1 else -1 if counts[n]==0 else 0
            price[n]=min(maxw[n],max(0,price[n]+direction*(maxw[n]//(4+2*step))))
    return best,trace

def restricted(w,assignments,k=3):
    available=collections.defaultdict(list)
    for j,ws in enumerate(w):
        for n,v in ws.items():available[n].append((v,j))
    keep={n:{j for _,j in sorted(v,key=lambda p:(-p[0],p[1]))[:k]} for n,v in available.items()}
    for x in assignments:
        for n,j in x.items():keep[n].add(j)
    return [{n:v for n,v in ws.items() if j in keep[n]} for j,ws in enumerate(w)]

def exact_mip(w,opening,activation,access,scale,seconds=60):
    """Binary assignment, facility and query activation. All constraints
    charge costs once; sparse matrix. Restricted candidate graph only."""
    cost=[];integrality=[];ri=[];ci=[];val=[];ub=[];assign={};fac={};qs={}
    def variable(c,binary=True):
        idx=len(cost);cost.append(c/scale);integrality.append(int(binary));return idx
    def row(items,b):
        i=len(ub);ub.append(b)
        for j,v in items:ri.append(i);ci.append(j);val.append(v)
    byclient=collections.defaultdict(list)
    for j,ws in enumerate(w):
        if not ws:continue
        fac[j]=variable(opening[j])
        for n,v in sorted(ws.items()):
            a=variable(-v);assign[n,j]=a;byclient[n].append(a)
            row([(a,1),(fac[j],-1)],0)
            for q in bits(access[n]):
                if not activation[j]:continue
                if (j,q) not in qs:qs[j,q]=variable(activation[j],False)
                row([(a,1),(qs[j,q],-1)],0)
    for xs in byclient.values():row([(a,1) for a in xs],1)
    if not cost:return {},dict(status=0,upper_bound=0,variables=0,constraints=0)
    a=coo_array((np.asarray(val,dtype=np.float64),(np.asarray(ri,dtype=np.int32),np.asarray(ci,dtype=np.int32))),
                shape=(len(ub),len(cost))).tocsc()
    res=milp(np.array(cost),integrality=np.asarray(integrality),
          bounds=Bounds(0,1),constraints=LinearConstraint(a,-np.inf,np.asarray(ub)),
          options={"time_limit":float(seconds),"mip_rel_gap":0.0})
    out=None
    if res.x is not None:
        out={n:j for (n,j),i in assign.items() if res.x[i]>.5}
        assert sum(res.x[i]>.5 for i in assign.values())==len(out)
        gain=value(out,w,opening,activation,access)
        assert abs(gain+res.fun*scale)<=max(1,abs(gain)*1e-7)
    dual=getattr(res,"mip_dual_bound",None)
    return out,dict(status=int(res.status),message=str(res.message),variables=len(cost),constraints=len(ub),
        upper_bound=None if dual is None or not np.isfinite(dual) else -float(dual)*scale,
        mip_gap=None if getattr(res,"mip_gap",None) is None else float(res.mip_gap))

def run(root,corpus):
    files,g,external=load(root,corpus);closures,train,test=split_roots(g);access=masks(files,closures,train);t=len(train)
    full={n:C.compress(v) for n,v in files.items()}
    cands,failures=candidates(files,g,full)
    lam,mu=100,25;scale=100*t
    w,o,a=model(full,cands,access,t,lam,mu)
    results={};start=time.perf_counter_ns()
    _,initial,trace=choose(cands,full,access,t,"cut",lam,mu)
    times={"greedy":(time.perf_counter_ns()-start)/1000}
    start=time.perf_counter_ns();expanded,moves=improve(initial,w,o,a,access);times["expansion"]=(time.perf_counter_ns()-start)/1000
    start=time.perf_counter_ns();ub,dual_trace=bound(w,o,a,access);bound_us=(time.perf_counter_ns()-start)/1000
    assert ub>=value(expanded,w,o,a,access)>=value(initial,w,o,a,access)
    wr=restricted(w,[initial,expanded])
    start=time.perf_counter_ns();mip,solver=exact_mip(wr,o,a,access,scale);times["restricted_mip"]=(time.perf_counter_ns()-start)/1000
    # Retain best known feasible incumbent; time-limited solver may not
    # find an improvement or even an incumbent.
    selected=expanded if mip is None or value(mip,w,o,a,access)<value(expanded,w,o,a,access) else mip
    solver["solver_incumbent_gain"]=None if mip is None else value(mip,w,o,a,access)
    solver["selected_gain"]=value(selected,w,o,a,access)
    if solver["status"]==0:assert mip is not None and value(mip,w,o,a,access)>=value(expanded,w,o,a,access)
    assert ub>=solver["selected_gain"]
    for name,x in [("individual",{}),("greedy",initial),("expansion",expanded),("restricted_mip",selected)]:
        opened=sorted(set(x.values()));payload,dir_=serialize(files,full,cands,opened,x);records,dicts=parse(payload,dir_)
        maxd=maxa=0.
        for n,row in records.items():
            raw,i,_,size,_=row;extra,_,z,_=dicts[i] if i else (0,0,0,b"")
            assert recover(payload,row,dicts,{})==files[n]
            assert 2*(raw+extra)<=5*raw and 2*(size+z)<=3*len(full[n])
            maxd=max(maxd,(raw+extra)/max(1,raw));maxa=max(maxa,(size+z)/len(full[n]))
        tr=measure(payload,records,dicts,files,closures,train);te=measure(payload,records,dicts,files,closures,test)
        total=len(payload)+len(dir_);objective=scale*total+lam*tr["activated"]["total"]+mu*tr["decoded"]["total"]
        if name=="individual":base=objective
        gain=value(x,w,o,a,access);assert base-objective==gain
        results[name]=dict(total_bytes=total,clients=len(x),dictionaries=len(opened),gain_scaled=gain,
           objective_scaled=objective,source_checks=len(records),max_decode_ratio=maxd,max_activation_ratio=maxa,
           train=tr,test=te,optimization_us=times.get(name,0))
        print("ARM_JSON="+json.dumps(results[name]),flush=True)
    return dict(round=164,corpus=corpus,modules=len(files),edges=g.number_of_edges(),external_import_occurrences=external,
       manifest_sha256=sha(json.dumps([(n,sha(files[n])) for n in sorted(files)]).encode()),
       train_sha256=sha(json.dumps(train).encode()),test_sha256=sha(json.dumps(test).encode()),
       candidate_count=len(cands),training_failures=failures,greedy_trace=trace,expansion_trace=moves,
       unrestricted_gain_upper_bound=ub,bound_trace=dual_trace,bound_us=bound_us,restricted_solver=solver,
       full_assignment_edges=sum(map(len,w)),restricted_assignment_edges=sum(map(len,wr)),policies=results,
       limitations=["same R163 offline candidate dictionaries, not an optimum over all dictionaries/codecs",
        "alpha expansion label-cost optimization and Lagrangian relaxation are established; no generic novelty claim",
        "exact each expansion move; 3 sweeps only, not globally optimal",
        "unrestricted upper bound exact integer for fixed candidate set; may be loose",
        "MILP restricted to top3 assignment edges plus greedy and expansion incumbents; HiGHS numerical solver bound not full graph proof",
        "same graph heldout roots, synthetic dependency access, no transactional historical index or device IO"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=("grh","grh-compact","masullo"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
