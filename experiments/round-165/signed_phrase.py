"""R165: one-hop signed phrase corrections over native token edit windows.
Identical marginal source archive in all arms; no source decode at query time.
"""
import argparse,bisect,collections,json,random,sys,time,tempfile
from pathlib import Path
from rapidfuzz.distance import Levenshtein
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-158"))
from frequency_index import f,h,si,connect,nr,ar,tokens,query_plan,prepare,recover
L=8
HALO=L-1

def windows(a,b,multi,limit=L):
    if not 1<=limit<=L:raise ValueError('unsupported phrase length')
    halo=limit-1
    if a==b:return []
    if multi:
        # Exact token interning avoids treating a hash collision as equality.
        ids={t:i for i,t in enumerate(dict.fromkeys(a+b))}
        edits=[];pa=pb=0
        for op,i,j,k,l in Levenshtein.opcodes([ids[t] for t in a],[ids[t] for t in b]):
            assert i==pa and k==pb;pa,pb=j,l
            if op=="equal":assert a[i:j]==b[k:l]
            else:edits.append((i,j,k,l))
        assert pa==len(a) and pb==len(b)
    else:
        p=0
        while p<min(len(a),len(b)) and a[p]==b[p]:p+=1
        s=0
        while s<min(len(a),len(b))-p and a[len(a)-s-1]==b[len(b)-s-1]:s+=1
        edits=[(p,len(a)-s,p,len(b)-s)]
    groups=[]
    for i,j,k,l in edits:
        if groups and i-groups[-1][1]<2*halo:
            x,y,z,w=groups[-1]
            assert i-y==k-w
            groups[-1]=(x,j,z,l)
        else:groups.append((i,j,k,l))
    out=[];pa=pb=0
    for i,j,k,l in groups:
        assert i-pa==k-pb and a[pa:i]==b[pb:k]
        x,y=max(0,i-halo),min(len(a),j+halo)
        z,w=max(0,k-halo),min(len(b),l+halo)
        out.append((a[x:y],b[z:w]));pa,pb=j,l
    assert a[pa:]==b[pb:]
    return out

def count(ts,p):
    return sum(ts[i:i+len(p)]==p for i in range(len(ts)-len(p)+1))

def signed_terms(patches):
    """Exact sparse signed multiset; never rely on hash equality alone."""
    out=collections.Counter()
    for old,new in patches:
        if old:out[tuple(old)]-=1
        if new:out[tuple(new)]+=1
    return {w:c for w,c in out.items() if c}

def share_window(w,uses,adjusted=False):
    # Fixed, untuned token-equivalent proxy, not a byte-optimal estimator.
    multiplicity=len(uses) if adjusted else sum(abs(c) for _,c in uses)
    return len(uses)>1 and (multiplicity-1)*len(w)>6*len(uses)

def write_runs(db,terms,insert,stats,adaptive,weighted=False,adjusted=False):
    """Direct signed rows grouped by cid; shared rows occupy a separate range."""
    uses=collections.defaultdict(list)
    for cid,corrections in terms:
        for w,coeff in corrections.items():uses[w].append((cid,coeff))
    shared={w for w,v in uses.items() if adaptive and share_window(w,v,adjusted)}
    ordinal=0
    for cid,corrections in terms:
        before=ordinal
        for w,coeff in corrections.items():
            if w in shared:continue
            for _ in range(1 if weighted else abs(coeff)):
                ordinal+=1
                rid=2*ordinal+int(coeff>0)
                insert("patch_fts",rid,list(w))
                if weighted and abs(coeff)>1:
                    if not stats["coefficient_exceptions"]:
                        db.execute("CREATE TABLE patch_coeff(rid INTEGER PRIMARY KEY,magnitude INTEGER NOT NULL CHECK(magnitude>1))")
                    db.execute("INSERT INTO patch_coeff VALUES(?,?)",(rid,abs(coeff)))
                    stats["coefficient_exceptions"]+=1
                    stats["avoided_rows"]+=abs(coeff)-1
                    stats["avoided_tokens"]+=(abs(coeff)-1)*len(w)
                stats["direct_rows"]+=1
                stats["direct_tokens"]+=len(w)
        if ordinal>before:
            db.execute("INSERT INTO patch_run VALUES(?,?)",(ordinal,cid))
            stats["direct_runs"]+=1
    rid=2*ordinal+1
    for w,v in uses.items():
        if w not in shared:continue
        rid+=1;insert("patch_fts",rid,list(w))
        stats["shared_rows"]+=1;stats["shared_tokens"]+=len(w)
        for cid,coeff in v:
            db.execute("INSERT INTO patch_use VALUES(?,?,?)",(rid,cid,coeff))
            stats["window_uses"]+=1
    stats["correction_coeff_l1"]=sum(abs(c) for v in uses.values() for _,c in v)

class PatchRuns:
    def __init__(self,rows,shared,coefficients=None):
        self.ends=[end for end,_ in rows]
        self.cids=[cid for _,cid in rows]
        self.shared=shared
        self.coefficients=coefficients if coefficients is not None else {}

    def get(self,rid,default=()):
        if self.ends and 2<=rid<=2*self.ends[-1]+1:
            i=bisect.bisect_left(self.ends,rid//2)
            magnitude=self.coefficients.get(rid,1)
            return ((self.cids[i],magnitude if rid&1 else -magnitude),)
        return self.shared.get(rid,default)

def load_patch_map(db):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "patch_use" not in tables:return None
    mapping=collections.defaultdict(list)
    for wid,cid,coeff in db.execute("SELECT wid,cid,coeff FROM patch_use"):
        mapping[wid].append((cid,coeff))
    if "patch_run" in tables:
        coefficients=dict(db.execute("SELECT rid,magnitude FROM patch_coeff")) if "patch_coeff" in tables else {}
        return PatchRuns(list(db.execute("SELECT last_ordinal,cid FROM patch_run ORDER BY last_ordinal")),mapping,coefficients)
    return mapping

def build_delta(db,path,events,mode,residual_builder=None):
    start=time.perf_counter_ns()
    db.executescript("""
      CREATE VIRTUAL TABLE base_fts USING fts5(body,content='');
      CREATE VIRTUAL TABLE patch_fts USING fts5(body,content='');
      CREATE TABLE idx_delta(cid INTEGER PRIMARY KEY,base INTEGER NOT NULL CHECK(base<cid));
    """)
    quotient="_quotient_" in mode
    dense="_dense_" in mode
    runs="_runs_" in mode or "_adaptive_" in mode
    mapped=quotient or dense or runs
    window_ids={};pending=[]
    if runs:
        db.execute("CREATE TABLE patch_run(last_ordinal INTEGER PRIMARY KEY,cid INTEGER NOT NULL)")
    if mapped:
        db.execute("CREATE TABLE patch_use(wid INTEGER NOT NULL,cid INTEGER NOT NULL,coeff INTEGER NOT NULL CHECK(coeff<>0),PRIMARY KEY(wid,cid)) WITHOUT ROWID")
    gids=dict(db.execute("SELECT g,cid FROM revisions"));parents=dict(db.execute("SELECT g,parent FROM source"))
    bases=set();hist=collections.defaultdict(list);token_cache={};stats=collections.Counter()
    def ts(cid):
        if cid not in token_cache:
            token_cache[cid]=tokens(db,events[cid-1][2].decode("utf8"))
        return token_cache[cid]
    def insert(table,rid,t):
        text=b" ".join(t).decode("utf8")
        assert tokens(db,text)==t
        db.execute(f"INSERT INTO {table}(rowid,body) VALUES(?,?)",(rid,text))
    for g,(article,_,_) in enumerate(events,1):
        cid=gids[g]
        if cid!=g:
            hist[article].append(cid);continue
        target=ts(cid);parent=parents[g];aligned=gids[parent] if parent else 0
        if mode.startswith("aligned"):
            candidates=[aligned] if aligned in bases else []
        else:
            candidates=list(dict.fromkeys(x for x in reversed(hist[article]) if x in bases))[:4]
        if aligned in bases:stats["aligned_available"]+=1
        choices=[]
        # Proxy only: total tokens indexed plus 12 token-equivalents
        # per patch pair and a mapping row. Actual physical bytes measured.
        for base in candidates:
            old=ts(base)
            if len(old)+len(target)>100000:continue
            patches=windows(old,target,mode.endswith("multi"))
            cost=sum(len(x)+len(y)+12 for x,y in patches)+8
            if 4*cost<=3*len(target):
                choices.append((cost,-base,patches))
        if choices:
            _,neg,patches=min(choices,key=lambda x:(x[0],x[1]));base=-neg
            db.execute("INSERT INTO idx_delta VALUES(?,?)",(cid,base))
            assert len(patches)<32768
            for i,(old,new) in enumerate(patches):
                if not mapped:
                    if old:insert("patch_fts",(cid<<16)|(i<<1),old)
                    if new:insert("patch_fts",(cid<<16)|(i<<1)|1,new)
                stats["patch_pairs"]+=1;stats["patch_tokens"]+=len(old)+len(new)
                stats["raw_nonempty_windows"]+=int(bool(old))+int(bool(new))
            if runs:
                pending.append((cid,signed_terms(patches)))
            elif mapped:
                terms=(signed_terms(patches).items() if quotient else
                    [(tuple(w),sign) for old,new in patches for w,sign in ((old,-1),(new,1)) if w])
                for w,coeff in terms:
                    if dense:
                        stats["dense_rows"]+=1;wid=stats["dense_rows"]
                        insert("patch_fts",wid,list(w))
                    else:
                        wid=window_ids.get(w)
                        if wid is None:
                            wid=len(window_ids)+1;window_ids[w]=wid
                            insert("patch_fts",wid,list(w))
                            stats["distinct_windows"]+=1
                            stats["distinct_window_tokens"]+=len(w)
                    db.execute("INSERT INTO patch_use VALUES(?,?,?)",(wid,cid,coeff))
                    stats["window_uses"]+=1
                    stats["coefficient_l1"]+=abs(coeff)
            stats["delta_contents"]+=1
            stats["aligned_selected"]+=int(base==aligned)
        else:
            insert("base_fts",cid,target);bases.add(cid);stats["base_contents"]+=1;stats["base_tokens"]+=len(target)
        hist[article].append(cid)
    if residual_builder is not None:
        if not runs:raise ValueError("residual builder requires signed pending rows")
        pending=residual_builder(db,pending,stats)
    if runs:write_runs(db,pending,insert,stats,"_adaptive_" in mode,"_weighted_" in mode,"_adjusted_" in mode)
    db.execute("DROP TABLE docs_0")
    for table in ("base_fts","patch_fts"):
        db.execute(f"INSERT INTO {table}({table}) VALUES('optimize')")
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return dict(sqlite_bytes=path.stat().st_size,fts_bytes=sum(v for k,v in sizes.items() if k.startswith(("base_fts_","patch_fts_"))),
        table_bytes=sizes,delta_build_us=(time.perf_counter_ns()-start)/1000,**stats)

def prepare_delta(db,c,global_map=None):
    state=prepare(db,c);active=state[0];parents=dict(db.execute("SELECT cid,base FROM idx_delta"))
    children=collections.defaultdict(list)
    for cid in active:children[parents.get(cid,cid)].append(cid)
    patch_children=global_map
    if global_map is None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='patch_run'").fetchone():
        patch_children=load_patch_map(db)
    elif global_map is None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='patch_use'").fetchone():
        patch_children=collections.defaultdict(list)
        for wid,cid,coeff in db.execute("SELECT wid,cid,coeff FROM patch_use"):
            if cid in active:patch_children[wid].append((cid,coeff))
    return state,children,patch_children

def rank_delta(db,p,o,prep,residual_reader=None,frequency_sink=None,patch_cache=None):
    ar.expression(p,o);(active,lens,n,total),children,patch_children=prep;freq=[];work=collections.Counter()
    for phrase in p:
        q=tokens(db,phrase)
        if not 1<=len(q)<=L:raise ValueError("unsupported phrase length")
        counts=collections.Counter()
        for base,tf in db.execute("SELECT rowid,cdg_count(base_fts) FROM base_fts WHERE base_fts MATCH ?",(ar.quote(phrase),)):
            work["base_hits"]+=1
            for cid in children.get(base,()):counts[cid]+=tf;work["expansions"]+=1
        if patch_cache is None or not patch_cache(db,q,active,counts,work):
            for rid,tf in db.execute("SELECT rowid,cdg_count(patch_fts) FROM patch_fts WHERE patch_fts MATCH ?",(ar.quote(phrase),)):
                work["patch_hits"]+=1
                if patch_children is None:
                    cid=rid>>16
                    if cid in active:counts[cid]+=tf if rid&1 else -tf
                else:
                    for cid,coeff in patch_children.get(rid,()):
                        work["patch_mapping_visits"]+=1
                        if cid in active:
                            counts[cid]+=coeff*tf
                            work["patch_expansions"]+=1
        if residual_reader is not None:residual_reader(db,q,active,counts,work)
        assert all(v>=0 for v in counts.values())
        matches={g:tf for cid,tf in counts.items() if tf for g in active[cid]}
        assert all(1<=tf<=lens[g] for g,tf in matches.items())
        freq.append(matches)
    if frequency_sink is not None:frequency_sink.extend(freq)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,work

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=list(query_plan(events,cuts[0],refs[cuts[0]]))
    # Additional probes from actual edits across revisions (not tuned to
    # chosen anchors), including deletion and insertion boundaries.
    check=connect(":memory:",ext);prior={};pool=set()
    for a,i,raw in events[:min(len(events),20000)]:
        if i and a in prior:
            old=tokens(check,prior[a].decode("utf8"));new=tokens(check,raw.decode("utf8"))
            for x,y in windows(old,new,False):
                for w in (x,y):
                    for n in (2,4,8):
                        if len(w)>=n:
                            k=(len(w)-n)//2;pool.add(b" ".join(w[k:k+n]).decode("utf8"))
        prior[a]=raw
        if len(pool)>=2048:break
    qs=list(dict.fromkeys(qs+[((p,),"AND") for p in sorted(pool,key=lambda p:h.sha(("R165|"+p).encode()))[:24]]))
    qs=[(p,o) for p,o in qs if all(1<=len(tokens(check,t))<=L for t in p)];check.close()
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    results={};sigs={}
    for mode in ("positional","independent_multi","independent_quotient_global_multi","independent_runs_multi","independent_adaptive_multi","independent_runs_weighted_multi","independent_adaptive_weighted_multi","independent_adaptive_weighted_adjusted_multi"):
        path=folder/(mode+".sqlite");db,size=f.build(path,ext,events,"marginal",False)
        if mode!="positional":size.update(build_delta(db,path,events,mode))
        db.close();db=connect(path,ext)
        for g,(_,_,raw) in enumerate(events,1):
            got,dd,ab=recover(db,g);assert got==raw
            assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
        prep={};prep_us=[]
        global_map=None;map_load_us=0
        if any(tag in mode for tag in ("_global_","_runs_","_adaptive_")):
            t=time.perf_counter_ns();global_map=load_patch_map(db);map_load_us=(time.perf_counter_ns()-t)/1000
        for c in cuts:
            t=time.perf_counter_ns();prep[c]=prepare(db,c) if mode=="positional" else prepare_delta(db,c,global_map)
            prep_us.append((time.perf_counter_ns()-t)/1000)
        plan=list(expected);rng=random.Random(165);times=[];classes=collections.defaultdict(list);work=collections.Counter();err=0.
        for repeat in range(2):
            rng.shuffle(plan)
            for c,p,o in plan:
                group="unigram_only" if all(len(tokens(db,t))==1 for t in p) else "has_phrase"
                t=time.perf_counter_ns()
                if mode=="positional":hits,df=si.rank(db,1,p,o,prep[c])
                else:hits,df,w=rank_delta(db,p,o,prep[c]);work.update(w)
                elapsed=(time.perf_counter_ns()-t)/1000;times.append(elapsed);classes[group].append(elapsed)
                err=max(err,h.verify(hits,expected[c,p,o]))
                if (c,p,o) in sigs:assert sigs[c,p,o]==(hits,df)
                else:sigs[c,p,o]=(hits,df)
        results[mode]=dict(**size,source_checks=len(events),rank_checks=len(times),max_score_error=err,
            map_load_us=map_load_us,query=h.quant(times),query_by_class={k:h.quant(v) for k,v in classes.items()},prepare=h.quant(prep_us),work=dict(work))
        print("ARM_JSON="+json.dumps(results[mode]),flush=True);db.close()
    for new in results:
        if new=="positional":continue
        old="independent_multi"
        for key in ("base_contents","base_tokens","patch_pairs","patch_tokens","delta_contents","aligned_selected"):
            assert results[old].get(key,0)==results[new].get(key,0),(old,new,key)
    for old,new in (("independent_runs_multi","independent_runs_weighted_multi"),
                    ("independent_adaptive_multi","independent_adaptive_weighted_multi")):
        assert results[old].get("direct_rows",0)==results[new].get("direct_rows",0)+results[new].get("avoided_rows",0)
        assert results[old].get("direct_tokens",0)==results[new].get("direct_tokens",0)+results[new].get("avoided_tokens",0)
        for key in ("shared_rows","shared_tokens","window_uses","correction_coeff_l1"):
            assert results[old].get(key,0)==results[new].get(key,0),(old,new,key)
    for ref in refs.values():ref.close()
    return dict(round=168,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),policies=results,
        limitations=["finalized source/index subset, identical source encoding, no transactional origin ledger",
          "exact default unicode61 phrase counts up to eight tokens, AND/OR, no highlighting or arbitrary positional query semantics",
          "one-hop base with signed edit-context windows, no source reconstruction during ranking",
          "quotient arms intern exact token windows with signed multiplicity; full active-use map prepared at every cutoff",
          "dense arm assigns consecutive row IDs with identical mapping layout but no window sharing or cancellation",
          "run arms build offline signed terms; global maps loaded once per opened archive and measured separately; active membership checked at query time",
          "adaptive sharing proxy fixed at six token-equivalents per use, not actual byte-optimal; no peak-memory measure",
          "weighted private rows store one indexed row per nonzero term with sparse magnitude exceptions; adjusted admission uses child count instead of replicated multiplicity",
          "base/patch anchor selection proxy not physical byte optimum; aligned only when source parent is an index base",
          "two warm prepared passes, preparation reported separately, no physical IO claim",
          "versioned delta indexing and compressed pattern matching established; no first-of-kind claim"])

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
