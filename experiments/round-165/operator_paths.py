"""R191: bounded shared correction operator paths with fixed R168 index roots."""
import argparse,collections,json,random,shutil,tempfile,time
from pathlib import Path
import signed_phrase as sp
from signed_phrase import f,h,si,nr,connect,prepare,recover
from real_residuals import plans,quant,MODE
HERE=Path(__file__).resolve().parent

def cost(m):
    return sum((len(w)+6)*abs(v) for w,v in m.items())

def diff(a,b):
    c=collections.Counter(a);c.subtract(b)
    return {w:v for w,v in c.items() if v}

def path_builder(events,limit,objective='local',lookback=1):
    def build(db,pending,stats):
        roots=dict(db.execute("SELECT cid,base FROM idx_delta"))
        direct=dict(pending);assert set(direct)==set(roots)
        refs=collections.Counter(w for m in direct.values() for w in m)
        parent={};depth={};cum={};recent=collections.defaultdict(lambda:collections.deque(maxlen=lookback));out=[]
        for cid,m in pending:
            root=roots[cid];d=cost(m);best=(d if objective=="local" else 0,0,root,m,"direct")
            def shared_cost(w,n):
                if n<=0:return 0
                if objective=="quotient":return len(w)+6+4*n
                # Approximate R168 adaptive writer, not measured page costs.
                return min(n*(len(w)+6),len(w)+6+6*n)
            def marginal(z):
                removed=set(m)-set(z);added=set(z)-set(m)
                return 4+sum(shared_cost(w,refs[w]-1)-shared_cost(w,refs[w]) for w in removed)+sum(shared_cost(w,refs[w]+1)-shared_cost(w,refs[w]) for w in added)
            for prev in reversed(recent[root]):
                if depth[prev]>=limit:continue
                alternatives=[("difference",diff(m,direct[prev]))]
                a=sp.tokens(db,events[prev-1][2].decode("utf8"))
                b=sp.tokens(db,events[cid-1][2].decode("utf8"))
                if len(a)+len(b)<=100000:
                    alternatives.append(("adjacent",sp.signed_terms(sp.windows(a,b,True))))
                for label,z in alternatives:
                    c=cost(z)
                    # Bound cumulative token-equivalent path cost, not physical reads.
                    if cum[prev]+c>2*d+24:continue
                    x=(c+4 if objective=='local' else marginal(z),depth[prev],prev,z,label)
                    if x[:3]<best[:3]:best=x
            _,_,p,m2,kind=best
            refs.subtract(m.keys());refs.update(m2.keys())
            if any(refs[w]<0 for w in m):raise ValueError('window refcount underflow')
            parent[cid]=p;depth[cid]=1 if p==root else depth[p]+1
            cum[cid]=cost(m2)+(0 if p==root else cum[p])
            assert depth[cid]<=limit and p<cid
            recent[root].append(cid);out.append((cid,m2))
            stats["operator_"+kind]+=1;stats["operator_direct_proxy"]+=d
            stats["operator_stored_proxy"]+=cost(m2)
            stats["operator_path_steps"]+=depth[cid]
            stats["operator_max_depth"]=max(stats["operator_max_depth"],depth[cid])
        rows=[(c,p) for c,p in parent.items() if p!=roots[c]]
        if rows:
            db.execute("CREATE TABLE operator_parent(cid INTEGER PRIMARY KEY,p INTEGER NOT NULL CHECK(p<cid))")
            db.executemany("INSERT INTO operator_parent VALUES(?,?)",rows)
        stats["operator_parent_rows"]=len(rows)
        return out
    return build

class PathMap:
    def __init__(self,mapping,desc):
        self.mapping=mapping;self.desc=desc;self.visits=0
    def get(self,rid,default=()):
        for c,k in self.mapping.get(rid,default):
            self.visits+=1
            for target in self.desc.get(c,()):yield target,k

def load_paths(db,limit):
    roots=dict(db.execute("SELECT cid,base FROM idx_delta"))
    links=dict(db.execute("SELECT cid,p FROM operator_parent")) if db.execute("SELECT 1 FROM sqlite_master WHERE name='operator_parent'").fetchone() else {}
    paths={}
    for c,r in sorted(roots.items()):
        p=links.get(c,r)
        if p>=c or (p!=r and (p not in paths or roots[p]!=r)):raise ValueError("bad operator parent")
        path=(c,) if p==r else (c,)+paths[p]
        if len(path)>limit:raise ValueError("operator depth")
        paths[c]=path
    if not set(links)<=set(roots):raise ValueError("orphan operator")
    return paths

def path_prepare(db,c,mapping,paths):
    state,children,_=sp.prepare_delta(db,c,mapping);desc=collections.defaultdict(list)
    for cid in state[0]:
        for op in paths.get(cid,()):desc[op].append(cid)
    return state,children,PathMap(mapping,desc)

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts};groups=plans(events,cuts,refs,ext)
    expected={(c,p,o):h.native(refs[c],p,o) for c in cuts for qs in groups.values() for p,o in qs}
    for ref in refs.values():ref.close()
    root=folder/"source.sqlite";db,size0=f.build(root,ext,events,"marginal",False);db.close()
    sigs={};freq_sigs={};results={};anchor_sig=None
    for mode,limit,objective,lookback in (("positional",0,"local",1),("signed",1,"local",1),("path4",4,"local",1),("quotient4",4,"quotient",1),("quotient4_k4",4,"quotient",4),("quotient4_k8",4,"quotient",8),("adaptive4_k4",4,"adaptive",4)):
        path=folder/(mode+".sqlite");shutil.copyfile(root,path);db=connect(path,ext);size=dict(size0)
        if limit:
            size.update(sp.build_delta(db,path,events,MODE,path_builder(events,limit,objective,lookback) if limit>1 else None))
            signature=h.sha(h.canonical(list(db.execute("SELECT cid,base FROM idx_delta ORDER BY cid")))).hex()
            if anchor_sig is None:anchor_sig=signature
            else:assert anchor_sig==signature
        db.close();db=connect(path,ext)
        for g,(_,_,raw) in enumerate(events,1):
            got,dd,ab=recover(db,g);assert got==raw and 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        t=time.perf_counter_ns()
        mapping=sp.load_patch_map(db) if limit else None
        paths=load_paths(db,limit) if limit>1 else None
        setup=(time.perf_counter_ns()-t)/1000
        preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns()
            preps[c]=prepare(db,c) if not limit else path_prepare(db,c,mapping,paths) if paths is not None else sp.prepare_delta(db,c,mapping)
            pt.append((time.perf_counter_ns()-t)/1000)
        splits={}
        for group,qs in groups.items():
            if not qs:continue
            plan=[(c,p,o) for c in cuts for p,o in qs];rng=random.Random(191);times=[];work=collections.Counter();err=0.
            if paths is not None:
                for prep in preps.values():prep[2].visits=0
            for _ in range(2):
                rng.shuffle(plan)
                for c,p,o in plan:
                    sink=[];t=time.perf_counter_ns()
                    if not limit:hits,df=si.rank(db,1,p,o,preps[c])
                    else:hits,df,w=sp.rank_delta(db,p,o,preps[c],frequency_sink=sink)
                    times.append((time.perf_counter_ns()-t)/1000)
                    if limit:work.update(w)
                    err=max(err,h.verify(hits,expected[c,p,o]))
                    k=(c,p,o)
                    if not limit:sigs[k]=(hits,df)
                    else:
                        assert sigs[k]==(hits,df)
                        digest=h.sha(h.canonical([sorted(m.items()) for m in sink])).hex()
                        if limit==1:freq_sigs[k]=digest
                        else:assert freq_sigs[k]==digest
            if paths is not None:work["operator_mapping_visits"]=sum(prep[2].visits for prep in preps.values())
            splits[group]=dict(query=quant(times),rank_checks=len(times),max_score_error=err,work=dict(work))
        results[mode]=dict(**size,source_checks=len(events),setup_us=setup,prepare=quant(pt),splits=splits)
        print("ARM_JSON="+json.dumps(dict(mode=mode,**results[mode])),flush=True);db.close();path.unlink()
    return dict(round=193,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_counts={k:len(v) for k,v in groups.items()},query_hashes={k:h.sha(h.canonical(v)).hex() for k,v in groups.items()},
        anchors_sha256=anchor_sig,policies=results,limitations=["fixed native source/index roots, finalized archive only",
        "operator path depth distinct from unchanged one-hop source recovery bound",
        "admission uses token-equivalent proxy, not physical byte optimum; paths limited to same root",
        "signed window telescoping exact for supported phrases; no arbitrary positions or RH theorem transfer",
        "precomputed active descendants charged setup; no peak RSS or physical IO claim; warm sequential timings"])

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
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
