"""R126: exact local fragment phrase counts plus first-boundary correction.

Keep R125's full positional fragment index and placement mapping. Add either
sparse crossing-phrase intervals or an indexed, reusable boundary-context
corpus. Never sum fragment BM25 scores: reconstruct active version TF/DF.
"""
import argparse,collections,json,random,shutil,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-125"))
from fragment_index import (create,partitions,tokens,term_positions,phrase_freq,extract_positions,
    queries,metadata,maps,active,active_oracle,native,score,verify,build,old_counts,
    extension,quote,order,load,select,SALT,PIN)
from native_compact import page_stats

FRAG="min64_coalesced"
METHODS=("positions","sparse_join","sparse_cte","window_cte","native_history","native_active")

def boundary_data(seq,parts):
    """Return context multiplicities and exact crossing ngram counts.

    Each start belongs to exactly one fragment. Its first crossed boundary
    is the end of that fragment. A right window may span tiny fragments.
    The left window never reaches into a previous fragment.
    """
    contexts=collections.Counter();counts=collections.Counter()
    for start,part in parts[:-1]:
        end=start+len(part)
        left=part[-2:];right=seq[end:end+2]
        context=(len(left),left+right)
        contexts[context]+=1
        for k in (2,3):
            for p in range(len(left)):
                if p+k>len(left) and p+k<=len(context[1]):
                    counts[context[1][p:p+k]]+=1
    return contexts,counts

def independent_cross(seq,parts):
    owner=[]
    for i,(off,part) in enumerate(parts):
        if off!=len(owner):raise ValueError("noncontiguous partition")
        owner.extend([i]*len(part))
    if len(owner)!=len(seq):raise ValueError("partition length")
    return collections.Counter(seq[p:p+k] for k in (2,3) for p in range(len(seq)-k+1)
                               if owner[p]!=owner[p+k-1])

def coalesce(rows,values):
    prior={};opened={};out=[];final=len(rows)+1
    for g,a,i,e,dl,d in rows:
        cur=values[g];old=prior.get(a,{})
        for key in old.keys()|cur.keys():
            before,after=old.get(key,0),cur.get(key,0)
            if before==after:continue
            if before:
                start,v=opened.pop((a,key));out.append((key,a,start,g,v))
            if after:opened[(a,key)]=(g,after)
        prior[a]=cur
    for (a,key),(start,v) in opened.items():out.append((key,a,start,final,v))
    return sorted(out)

def audit_intervals(rows,records,values):
    by,_=maps(rows);expanded=[{} for _ in values];checks=0
    for key,a,s,e,tf in records:
        if not tf>0 or not s<e:raise AssertionError("bad interval")
        for g in by[a]:
            if s<=g<e:
                if key in expanded[g]:raise AssertionError("overlap")
                expanded[g][key]=tf;checks+=1
    if expanded!=values:raise AssertionError("interval expansion mismatch")
    return checks

def clone(base,path,ext,posext,crossext):
    shutil.copyfile(base,path);db=sqlite3.connect(path)
    for p in (ext,posext,crossext):extension(db,p)
    return db

def sparse_install(db,path,rows,values,words):
    # Phrase strings consist of canonical native tokens separated by one space.
    records=coalesce(rows,values)
    db.execute("""CREATE TABLE crossing(phrase TEXT NOT NULL,aid INTEGER NOT NULL,
       start_g INTEGER NOT NULL,end_g INTEGER NOT NULL,tf INTEGER NOT NULL,
       PRIMARY KEY(phrase,start_g,aid)) WITHOUT ROWID""")
    db.executemany("INSERT INTO crossing VALUES(?,?,?,?,?)",
        ((" ".join(words[i] for i in key),a,s,e,tf) for key,a,s,e,tf in records))
    db.commit();db.execute("VACUUM")
    wordid={t:i for i,t in enumerate(words) if i}
    persisted=sorted((tuple(wordid[t] for t in phrase.split(" ")),a,s,e,tf)
        for phrase,a,s,e,tf in db.execute("SELECT * FROM crossing"))
    if persisted!=records:raise AssertionError("sparse persisted mismatch")
    expanded=audit_intervals(rows,persisted,values)
    return dict(sqlite_bytes=path.stat().st_size,intervals=len(records),
                expanded_entries=expanded,dbstat=page_stats(db))

def window_install(db,path,rows,values,words):
    keys=sorted({key for v in values for key in v});ids={k:i for i,k in enumerate(keys,1)}
    records=coalesce(rows,values)
    db.executescript("""
    CREATE VIRTUAL TABLE edge USING fts5(body,content='');
    CREATE TABLE edge_meta(eid INTEGER PRIMARY KEY,left_n INTEGER NOT NULL);
    CREATE TABLE edge_apps(eid INTEGER NOT NULL,aid INTEGER NOT NULL,start_g INTEGER NOT NULL,
      end_g INTEGER NOT NULL,mult INTEGER NOT NULL,PRIMARY KEY(eid,start_g,aid)) WITHOUT ROWID;
    """)
    db.executemany("INSERT INTO edge(rowid,body) VALUES(?,?)",
        ((i," ".join(words[t] for t in k[1])) for k,i in ids.items()))
    db.executemany("INSERT INTO edge_meta VALUES(?,?)",((i,k[0]) for k,i in ids.items()))
    db.executemany("INSERT INTO edge_apps VALUES(?,?,?,?,?)",
        ((ids[k],a,s,e,tf) for k,a,s,e,tf in records))
    db.execute("INSERT INTO edge(edge) VALUES('optimize')")
    db.commit();db.execute("VACUUM")
    db.execute("CREATE VIRTUAL TABLE temp.edge_vocab USING fts5vocab(main,edge,'instance')")
    wordid={t:i for i,t in enumerate(words) if i}
    restored=collections.defaultdict(list)
    for t,eid,off in db.execute("SELECT term,doc,offset FROM temp.edge_vocab ORDER BY doc,offset"):
        if off!=len(restored[eid]):raise AssertionError("edge offsets")
        restored[eid].append(wordid[t])
    got={eid:(l,tuple(restored[eid])) for eid,l in db.execute("SELECT * FROM edge_meta")}
    if got!={i:k for k,i in ids.items()}:raise AssertionError("edge dictionary mismatch")
    persisted=sorted((got[eid],a,s,e,tf) for eid,a,s,e,tf in db.execute("SELECT * FROM edge_apps"))
    if persisted!=records:raise AssertionError("edge intervals mismatch")
    expanded=audit_intervals(rows,persisted,values)
    return dict(sqlite_bytes=path.stat().st_size,unique_contexts=len(keys),
        indexed_context_tokens=sum(len(k[1]) for k in keys),intervals=len(records),
        expanded_entries=expanded,dbstat=page_stats(db))

def validate_phrase(p):
    parts=p.split(" ")
    if not 1<=len(parts)<=3 or not all(parts):raise ValueError("only one to three canonical tokens")
    return len(parts)

def local(db,p,c,cte):
    if cte:
        return db.execute("""WITH matches AS MATERIALIZED (
             SELECT rowid AS fid,cdg_count(docs) AS tf FROM docs WHERE docs MATCH ?
          ) SELECT a.aid,sum(m.tf) FROM matches m JOIN applications a ON a.fid=m.fid
          WHERE a.start_g<=? AND a.end_g>? GROUP BY a.aid""",(quote(p),c,c))
    return db.execute("""SELECT a.aid,cdg_count(docs) FROM docs
          JOIN applications a ON a.fid=docs.rowid
          WHERE docs MATCH ? AND a.start_g<=? AND a.end_g>?""",(quote(p),c,c))

def sparse_cross(db,p,c):
    return db.execute("SELECT aid,tf FROM crossing WHERE phrase=? AND start_g<=? AND end_g>?",(p,c,c))

def window_cross(db,p,c):
    return db.execute("""WITH hits AS MATERIALIZED (
       SELECT edge.rowid AS eid,cdg_cross(edge,em.left_n) AS tf FROM edge
       JOIN edge_meta em ON em.eid=edge.rowid WHERE edge MATCH ?
       ) SELECT a.aid,sum(h.tf*a.mult) FROM hits h JOIN edge_apps a ON a.eid=h.eid
       WHERE h.tf>0 AND a.start_g<=? AND a.end_g>? GROUP BY a.aid""",(quote(p),c,c))

def counts(db,p,c,act,mode):
    k=validate_phrase(p);out=collections.Counter()
    internal=cross=0;local_rows=edge_rows=0
    for a,tf in local(db,p,c,mode!="sparse_join"):
        if a not in act or tf<1:raise ValueError("invalid local count")
        out[act[a]]+=tf;internal+=tf;local_rows+=1
    if k>1:
        it=window_cross(db,p,c) if mode=="window_cte" else sparse_cross(db,p,c)
        for a,tf in it:
            if a not in act or tf<1:raise ValueError("invalid crossing count")
            out[act[a]]+=tf;cross+=tf;edge_rows+=1
    return dict(out),(internal,cross,local_rows,edge_rows)

def experiment(folder,events,ext,posext,crossext,repeats):
    pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);original=tokens(pos)
    words=[""]+sorted({t for m in pos for t in m});wordid={t:i for i,t in enumerate(words) if i}
    seq=[tuple(wordid[t] for t in s) for s in original]
    contexts=[{}];crossing=[{}];all_cross=0
    for s in seq[1:]:
        parts=partitions(s,"minima",32);ctx,ng=boundary_data(s,parts)
        if ng!=independent_cross(s,parts):raise AssertionError("first boundary decomposition")
        # Independent check of complete 2/3-gram multiplicities.
        whole=collections.Counter(s[p:p+k] for k in (2,3) for p in range(len(s)-k+1))
        inside=collections.Counter(part[p:p+k] for _,part in parts for k in (2,3) for p in range(len(part)-k+1))
        if inside+ng!=whole:raise AssertionError("complete phrase decomposition")
        contexts.append(dict(ctx));crossing.append(dict(ng));all_cross+=sum(ng.values())
    basepath=folder/"positions.sqlite";base,bstat=create(basepath,rows,ids,seq,words,FRAG,ext,posext)
    base.close()
    sparsepath=folder/"sparse.sqlite";winpath=folder/"window.sqlite"
    sparse=clone(basepath,sparsepath,ext,posext,crossext);win=clone(basepath,winpath,ext,posext,crossext)
    stats={"positions":bstat,"sparse":sparse_install(sparse,sparsepath,rows,crossing,words),
           "window":window_install(win,winpath,rows,contexts,words)}
    base=sqlite3.connect(basepath);extension(base,ext);extension(base,posext)
    control,stats["native_history"]=build(folder/"native_history.sqlite",rows,ids,events,{},"native_history",ext)
    dbs={"positions":base,"sparse_join":sparse,"sparse_cte":sparse,"window_cte":win}
    for db in (sparse,win):
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AssertionError("integrity")
    lens=[0]+[r[4] for r in rows];cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    qs,common,selected=queries(pos,freqs,active(rows,cuts[0]))
    # Add queries selected exclusively from first-prefix crossing phrases.
    # They are not necessarily frequent in the complete active documents.
    boundary_df=collections.Counter()
    for g in active(rows,cuts[0]).values():boundary_df.update(crossing[g].keys())
    from versioned_evidence import sha
    for k in (2,3):
        keys=[key for key in boundary_df if len(key)==k]
        keys=sorted(keys,key=lambda x:sha(("CDG-R126-cross-v1|"+" ".join(words[i] for i in x)).encode()))[:12]
        for key in keys:
            q=((" ".join(words[i] for i in key),),"AND")
            if q not in qs:qs.append(q)
    rng=random.Random(126);results=[]
    for c in cuts:
        act=active(rows,c);total=sum(lens[g] for g in act.values());ref=active_oracle(events,c);extension(ref,ext)
        unique=sorted({p for ps,_ in qs for p in ps});work={m:[0,0,0,0] for m in METHODS[1:4]}
        positive=0;cross_queries=0;cross_hits=0
        for p in unique:
            want=dict(ref.execute("SELECT rowid,cdg_count(fulltext) FROM fulltext WHERE fulltext MATCH ?",(quote(p),)))
            ids_=tuple(wordid[t] for t in p.split(" "))
            cross_expected=sum(crossing[g].get(ids_,0) for g in act.values())
            cross_queries+=int(cross_expected>0);cross_hits+=cross_expected
            for m in METHODS[1:4]:
                got,z=counts(dbs[m],p,c,act,m)
                if got!=want or z[1]!=cross_expected or z[0]+z[1]!=sum(want.values()):
                    raise AssertionError("phrase count or crossing attribution "+repr((m,c,p)))
                for i,n in enumerate(z):work[m][i]+=n
            if phrase_freq(p,lambda t:term_positions(base,t,c,act))!=want:raise AssertionError("position control")
            positive+=len(want)
        def ranked(m,ps,op):
            if m=="native_active":return native(ref,ps,op)
            if m=="native_history":freq=[old_counts(control,p,c,act,lens,m) for p in ps]
            elif m=="positions":
                cache={}
                def lookup(t):
                    if t not in cache:cache[t]=term_positions(base,t,c,act)
                    return cache[t]
                freq=[phrase_freq(p,lookup) for p in ps]
            else:freq=[counts(dbs[m],p,c,act,m)[0] for p in ps]
            return score(freq,op,len(act),total,lens)[0]
        err={m:0.0 for m in METHODS};hits=0
        for ps,op in qs:
            want=native(ref,ps,op);hits+=len(want)
            for m in METHODS:err[m]=max(err[m],verify(ranked(m,ps,op),want))
        timing={m:[] for m in METHODS};phrase={m:[] for m in METHODS};term={m:[] for m in METHODS}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for ps,op in req:
                ms=list(METHODS);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns();ranked(m,ps,op);us=(time.perf_counter_ns()-st)/1000
                    timing[m].append(us)
                    (phrase if any(" " in p for p in ps) else term)[m].append(us)
        results.append(dict(cutoff=c,queries=len(qs),phrase_queries=sum(any(" " in p for p in ps) for ps,op in qs),
            ranked_hits=hits,unique_phrases_terms=len(unique),positive_native_frequency_pairs=positive,
            unique_queries_with_crossing_hits=cross_queries,crossing_occurrences=cross_hits,max_error=err,
            logical_rows={m:dict(zip(("internal_occurrences","crossing_occurrences","returned_local_rows","returned_crossing_rows"),z)) for m,z in work.items()},
            median_us={m:statistics.median(v) for m,v in timing.items()},
            phrase_median_us={m:statistics.median(v) for m,v in phrase.items() if v},
            term_median_us={m:statistics.median(v) for m,v in term.items() if v},
            p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timing.items()}))
        ref.close()
    for db in (base,sparse,win,control):db.close()
    return dict(revisions=len(rows),original_tokens=sum(map(len,seq)),crossing_ngram_occurrences=all_cross,
                layouts=stats,cutoffs=results,repetitions=repeats)
def run(root,ext,posext,crossext,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,posext,crossext,repeats)
    return dict(round=126,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
       limits=["same processed Versions corpus, synthetic order, not independent",
       "normalized token exact phrases of length 1 to 3 and distinct AND/OR; longer phrases rejected; not arbitrary FTS grammar",
       "boundary counts and windows are added to the complete R125 positional index, all physical bytes charged",
       "offline bulk builds, source payload and online maintenance/WAL excluded",
       "logical returned SQL rows not native internal posting work or physical I/O",
       "warm rank-only one-runner timings, prepared active maps, no real user access trace",
       "fragment-local phrase matching and boundary correction are established ideas, no novelty claim"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--position-extension",type=Path,required=True);p.add_argument("--cross-extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.position_extension.resolve(),a.cross_extension.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
