"""R127: compact boundary corrections and selective temporal TF sidecar.

Retain the complete R125 positional index and application mapping.
Use R123's native interval decoder for exact crossing phrase counts and
optionally single-term historical frequencies. No uncharged duplicate index.
"""
import argparse,collections,json,random,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-126"))
from boundary_counts import (FRAG,boundary_data,independent_cross,coalesce,audit_intervals,
    clone,sparse_install,local,counts as sparse_counts,validate_phrase,
    create,partitions,tokens,extract_positions,queries,metadata,maps,active,
    active_oracle,native,score,verify,build,old_counts,extension,quote,order,load,select,SALT,PIN)
from native_compact import Decoder,groups,raw_lookup,page_stats
from compact_temporal import local_records,global_records,pack_postings,unpack_postings,frame,unframe,block,unblock
from temporal_postings import postings
from versioned_evidence import sha

LAYOUTS={"boundary4":(4096,"none"),"boundary16":(16384,"none"),
         "hot4":(4096,"hot"),"all4":(4096,"all"),"all16":(16384,"all")}
METHODS=tuple(LAYOUTS)+("sparse_join","native_history","native_active")

def install(db,path,rows,by,og,cross,tf,mode):
    target,policy=LAYOUTS[mode];final=len(rows)+1
    db.execute("CREATE TABLE blocks(first TEXT PRIMARY KEY,payload BLOB NOT NULL)")
    db.execute("CREATE TABLE hot_terms(term TEXT PRIMARY KEY) WITHOUT ROWID")
    selected={t:rs for t,rs in tf.items() if policy=="all" or (policy=="hot" and len(rs)>=128)}
    if policy=="hot":db.executemany("INSERT INTO hot_terms VALUES(?)",((t,) for t in sorted(selected)))
    if set(selected)&set(cross):raise AssertionError("term/phrase namespace collision")
    combined={**cross,**selected};items=[]
    for t,rs in sorted(combined.items()):
        items.append((t,b"\x00"+pack_postings(local_records(rs,by,og,final)),len(rs)))
    for group in groups(items,target,128):
        db.execute("INSERT INTO blocks VALUES(?,?)",(group[0][0],frame(block(group),True)))
    db.commit();db.execute("VACUUM")
    if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AssertionError("integrity")
    seen=set();n=0
    for first,payload in db.execute("SELECT first,payload FROM blocks ORDER BY first"):
        entries=unblock(unframe(payload))
        if not entries or entries[0][0]!=first:raise AssertionError("directory")
        for t,p in entries:
            if t in seen or not p or p[0]!=0:raise AssertionError("entry")
            seen.add(t);got=global_records(unpack_postings(p[1:]),by,final)
            if got!=sorted(combined[t]):raise AssertionError("persisted interval mismatch")
            n+=len(got)
    if seen!=set(combined):raise AssertionError("missing entries")
    if policy=="hot" and {t for t, in db.execute("SELECT term FROM hot_terms")}!=set(selected):raise AssertionError("dispatch mismatch")
    return dict(sqlite_bytes=path.stat().st_size,blocks=db.execute("SELECT count(*) FROM blocks").fetchone()[0],
       encoded_block_bytes=db.execute("SELECT coalesce(sum(length(payload)),0) FROM blocks").fetchone()[0],
       term_entries=len(selected),crossing_entries=len(cross),persisted_intervals_checked=n,dbstat=page_stats(db))

def compact_lookup(db,p,dec,state):
    raw,encoded=raw_lookup(db,p)
    if raw is None:return {},(0,0,0)
    got,seen=dec.lookup(raw,p,state)
    return got,(encoded,len(raw),seen)

def counts(db,p,c,act,mode,dec,state):
    length=validate_phrase(p);policy=LAYOUTS[mode][1];out=collections.Counter()
    # Hot membership is explicit and physically charged; no query log needed.
    use_tf=length==1 and (policy=="all" or (policy=="hot" and
        db.execute("SELECT 1 FROM hot_terms WHERE term=?",(p,)).fetchone() is not None))
    local_rows=0;work=(0,0,0);cross=0
    if use_tf:
        got,work=compact_lookup(db,p,dec,state)
        out.update(got)
    else:
        for aid,n in local(db,p,c,False):
            if aid not in act or n<=0:raise ValueError("bad fragment count")
            out[act[aid]]+=n;local_rows+=1
        if length>1:
            got,work=compact_lookup(db,p,dec,state);out.update(got);cross=sum(got.values())
    return dict(out),dict(compact_lookups=int(use_tf or length>1),tf_dispatch=int(use_tf),
        encoded_bytes=work[0],decoded_bytes=work[1],intervals_examined=work[2],
        returned_local_rows=local_rows,crossing_occurrences=cross)

def experiment(folder,events,ext,posext,crossext,decoder,repeats):
    dec=Decoder(decoder);pos=extract_positions(events);freqs=[{t:len(v) for t,v in m.items()} for m in pos]
    rows,ids=metadata(events,freqs);by,og=maps(rows);original=tokens(pos)
    words=[""]+sorted({t for m in pos for t in m});wordid={t:i for i,t in enumerate(words) if i}
    seq=[tuple(wordid[t] for t in s) for s in original];crossing=[{}]
    for s in seq[1:]:
        parts=partitions(s,"minima",32);_,ng=boundary_data(s,parts)
        if ng!=independent_cross(s,parts):raise AssertionError("crossing decomposition")
        crossing.append(dict(ng))
    records=coalesce(rows,crossing);expanded=audit_intervals(rows,records,crossing)
    cross=collections.defaultdict(list)
    for key,a,s,e,v in records:cross[" ".join(words[i] for i in key)].append((a,s,e,v))
    tf=postings(rows,freqs,True)
    # Independently expand original positive TF records for all revisions.
    expanded_tf=[{} for _ in freqs]
    for t,rs in tf.items():
        for a,s,e,v in rs:
            for g in by[a]:
                if s<=g<e:
                    if t in expanded_tf[g]:raise AssertionError("TF overlap")
                    expanded_tf[g][t]=v
    if expanded_tf!=freqs:raise AssertionError("TF expansion")
    basepath=folder/"base.sqlite";base,bstat=create(basepath,rows,ids,seq,words,FRAG,ext,posext);base.close()
    dbs={};stats={"base":bstat}
    sp=folder/"sparse.sqlite";dbs["sparse_join"]=clone(basepath,sp,ext,posext,crossext)
    stats["sparse_join"]=sparse_install(dbs["sparse_join"],sp,rows,crossing,words)
    for m in LAYOUTS:
        path=folder/(m+".sqlite");dbs[m]=clone(basepath,path,ext,posext,crossext)
        stats[m]=install(dbs[m],path,rows,by,og,cross,tf,m)
    dbs["native_history"],stats["native_history"]=build(folder/"native_history.sqlite",rows,ids,events,{},"native_history",ext)
    cuts=sorted(set(max(1,len(rows)*i//4) for i in range(1,5)))
    lens=[0]+[r[4] for r in rows];qs,common,selected=queries(pos,freqs,active(rows,cuts[0]))
    boundary_df=collections.Counter()
    for g in active(rows,cuts[0]).values():boundary_df.update(crossing[g].keys())
    for k in (2,3):
        keys=sorted((key for key in boundary_df if len(key)==k),
          key=lambda x:sha(("CDG-R126-cross-v1|"+" ".join(words[i] for i in x)).encode()))[:12]
        for key in keys:
            q=((" ".join(words[i] for i in key),),"AND")
            if q not in qs:qs.append(q)
    rng=random.Random(127);results=[]
    for c in cuts:
        act=active(rows,c);state=dec.prepare(act,og,len(ids)+1)
        total=sum(lens[g] for g in act.values());ref=active_oracle(events,c);extension(ref,ext)
        unique=sorted({p for ps,_ in qs for p in ps});work={m:collections.Counter() for m in LAYOUTS}
        countchecks=0
        for p in unique:
            want=dict(ref.execute("SELECT rowid,cdg_count(fulltext) FROM fulltext WHERE fulltext MATCH ?",(quote(p),)))
            for m in LAYOUTS:
                got,z=counts(dbs[m],p,c,act,m,dec,state)
                if got!=want:raise AssertionError("exact frequency "+repr((m,c,p)))
                key=tuple(wordid[t] for t in p.split(" "))
                if z["crossing_occurrences"]!=sum(crossing[g].get(key,0) for g in act.values()):raise AssertionError("cross attribution")
                work[m].update(z)
            if sparse_counts(dbs["sparse_join"],p,c,act,"sparse_join")[0]!=want:raise AssertionError("sparse")
            countchecks+=len(want)
        def ranked(m,ps,op):
            if m=="native_active":return native(ref,ps,op)
            if m=="native_history":freq=[old_counts(dbs[m],p,c,act,lens,m) for p in ps]
            elif m=="sparse_join":freq=[sparse_counts(dbs[m],p,c,act,m)[0] for p in ps]
            else:freq=[counts(dbs[m],p,c,act,m,dec,state)[0] for p in ps]
            return score(freq,op,len(act),total,lens)[0]
        err={m:0.0 for m in METHODS};hits=0
        for ps,op in qs:
            want=native(ref,ps,op);hits+=len(want)
            for m in METHODS:err[m]=max(err[m],verify(ranked(m,ps,op),want))
        timing={m:[] for m in METHODS};phrase={m:[] for m in METHODS};term={m:[] for m in METHODS};high={m:[] for m in METHODS}
        for _ in range(repeats):
            req=list(qs);rng.shuffle(req)
            for ps,op in req:
                ms=list(METHODS);rng.shuffle(ms)
                for m in ms:
                    st=time.perf_counter_ns();ranked(m,ps,op);us=(time.perf_counter_ns()-st)/1000
                    timing[m].append(us)
                    (phrase if any(" " in p for p in ps) else term)[m].append(us)
                    if len(ps)==1 and ps[0] in common:high[m].append(us)
        results.append(dict(cutoff=c,queries=len(qs),phrase_queries=sum(any(" " in p for p in ps) for ps,op in qs),
            ranked_hits=hits,positive_native_frequency_pairs=countchecks,max_error=err,
            work={m:dict(z) for m,z in work.items()},
            median_us={m:statistics.median(v) for m,v in timing.items()},
            phrase_median_us={m:statistics.median(v) for m,v in phrase.items() if v},
            term_median_us={m:statistics.median(v) for m,v in term.items() if v},
            common_median_us={m:statistics.median(v) for m,v in high.items() if v},
            p95_us={m:sorted(v)[int(.95*(len(v)-1))] for m,v in timing.items()}))
        ref.close()
    for db in dbs.values():db.close()
    return dict(revisions=len(rows),original_tokens=sum(map(len,seq)),crossing_intervals=len(records),
        expanded_crossing_entries=expanded,tf_intervals=sum(map(len,tf.values())),expanded_tf_entries=sum(map(len,freqs)),
        layouts=stats,cutoffs=results,repetitions=repeats)
def run(root,ext,posext,crossext,decoder,repeats):
    a,manifest=load(root);cohort=select(a,len(a),SALT)
    with tempfile.TemporaryDirectory() as tmp:r=experiment(Path(tmp),order(cohort),ext,posext,crossext,decoder,repeats)
    return dict(round=127,upstream_commit=PIN,full_corpus_sha256=manifest,articles=len(cohort),result=r,
      limits=["same processed Versions corpus and R126 query plan, synthetic global order, not independent data",
       "entire positional fragment index retained, all sidecar metadata/bytes charged, source payload excluded",
       "exact 1–3 canonical token phrases and distinct AND/OR, not arbitrary grammar",
       "hot selected by posting interval cardinality >=128, no query log training",
       "R123 native selected-list decoder, offline immutable index; no update/WAL or adversarial-file guarantee",
       "warm rank-only single-runner timings, prepared active maps, logical wire bytes not device I/O",
       "established codecs and boundary correction, no novel algorithm claim"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--position-extension",type=Path,required=True);p.add_argument("--cross-extension",type=Path,required=True)
    p.add_argument("--decoder",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--repetitions",type=int,default=3);a=p.parse_args()
    r=run(a.root,a.extension.resolve(),a.position_extension.resolve(),a.cross_extension.resolve(),a.decoder.resolve(),a.repetitions)
    a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print("RESULT_JSON="+json.dumps(r,separators=(",",":")),flush=True)
