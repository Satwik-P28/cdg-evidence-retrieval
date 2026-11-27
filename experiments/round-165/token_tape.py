"""R170: integer token tape + frequency postings + optional bounded source residual.
Finalized archive experiment. All persistent lexicon/tape/posting pages charged.
"""
import argparse,collections,itertools,json,random,struct,tempfile,time
from pathlib import Path
import signed_phrase as sp
from frequency_index import f,h,si,connect,nr,ar,tokens,query_plan,prepare,recover
from compact_fragments import pack,unpack
from forward_index import D,delta_decode,phrase_count

HERE=Path(__file__).resolve().parent

def encode_ids(ids):
    return struct.pack("<"+"I"*len(ids),*ids)

def decode_ids(raw):
    if len(raw)%4:raise ValueError("unaligned token tape")
    return [v for v, in struct.iter_unpack("<I",raw)]

def count_ids(raw,needle):
    if not needle or len(raw)%4 or len(needle)%4:raise ValueError("invalid tape or phrase")
    n=pos=0
    while True:
        i=raw.find(needle,pos)
        if i<0:return n
        if i%4==0:n+=1
        pos=i+1

def payload(raw):
    z=h.C.compress(raw)
    return (1,z) if len(z)<len(raw) else (0,raw)

def unpayload(n,z,body):
    raw=D.decompress(body,max_output_size=n+1) if z else body
    if len(raw)!=n:raise ValueError("payload length")
    return raw

def build_tape(db,path,events,mode):
    start=time.perf_counter_ns()
    integer=mode.startswith("ids")
    tape=mode!="frequency"
    joint=mode.endswith("_joint")
    delta="_delta" in mode
    db.executescript("""
      CREATE TABLE lexicon(tid INTEGER PRIMARY KEY,term TEXT NOT NULL);
      CREATE TABLE token_postings(tid INTEGER PRIMARY KEY,n INTEGER NOT NULL,z INTEGER NOT NULL,body BLOB NOT NULL);
      CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,docs_0,'instance');
    """)
    if tape:db.execute("CREATE TABLE token_tape(cid INTEGER PRIMARY KEY,n INTEGER NOT NULL,z INTEGER NOT NULL,base INTEGER NOT NULL,body BLOB NOT NULL)")
    ids={};stats=collections.Counter()
    for term,rows in itertools.groupby(db.execute("SELECT term,doc,count(*) FROM temp.vocab GROUP BY term,doc ORDER BY term,doc"),key=lambda r:r[0]):
        tid=len(ids)+1;ids[term.encode("utf8")]=tid
        vals=[(cid,tf) for _,cid,tf in rows]
        raw=pack(vals);assert list(unpack(raw))==vals
        z,body=payload(raw)
        db.execute("INSERT INTO lexicon VALUES(?,?)",(tid,term))
        db.execute("INSERT INTO token_postings VALUES(?,?,?,?)",(tid,len(raw),z,body))
        stats["lexicon_payload_bytes"]+=len(term.encode("utf8"))
        stats["posting_payload_bytes"]+=len(body);stats["posting_pairs"]+=len(vals)
    db.execute("DROP TABLE temp.vocab")
    stats["lexicon_terms"]=len(ids)
    if tape:
        hist=collections.defaultdict(list)
        gids=dict(db.execute("SELECT g,cid FROM revisions"))
        full_cids=set()
        for g,(article,_,source) in enumerate(events,1):
            cid=gids[g]
            if cid!=g:
                if cid in full_cids and cid not in hist[article]:hist[article].append(cid)
                continue
            ts=tokens(db,source.decode("utf8"))
            raw=encode_ids([ids[t] for t in ts]) if integer else b" ".join(ts)
            z,body=payload(raw)
            full_size=len(body)
            best=(full_size,0,z,body)
            if delta and raw:
                for parent in hist[article][-4:]:
                    pn,pz,pbase,pbody=db.execute("SELECT n,z,base,body FROM token_tape WHERE cid=?",(parent,)).fetchone()
                    assert pbase==0 and pz in (0,1) and parent<cid
                    if not pn or 2*(len(raw)+pn)>5*len(raw):continue
                    pr=unpayload(pn,pz,pbody)
                    diff=h.delta_encode(raw,pr)
                    if diff is None:continue
                    stats["tape_delta_candidates"]+=1
                    if 5*len(diff)>4*full_size or 2*(len(pbody)+len(diff))>3*full_size:continue
                    if len(diff)+8<best[0]:
                        assert delta_decode(diff,pr,len(raw))==raw
                        best=(len(diff)+8,parent,2,diff)
            _,base,z,body=best
            if not base:
                full_cids.add(cid);hist[article].append(cid)
            else:stats["tape_delta_selected"]+=1
            stats["tape_full_control_bytes"]+=full_size
            db.execute("INSERT INTO token_tape VALUES(?,?,?,?,?)",(cid,len(raw),z,base,body))
            stats["tape_payload_bytes"]+=len(body);stats["tape_decoded_bytes"]+=len(raw)
    if joint:
        sources=list(db.execute("SELECT g,kind,parent,fid,n FROM source ORDER BY g"))
        refs=collections.Counter(r[3] for r in sources)
        parents={r[2] for r in sources if r[1]==1}
        frames={fid:body for fid,body in db.execute("SELECT fid,body FROM frames")}
        keys={h.sha(body):fid for fid,body in frames.items()}
        next_fid=max(frames,default=0)+1
        gids=dict(db.execute("SELECT g,cid FROM revisions"))
        for g,kind,_,fid,n in sources:
            # Never replace a full frame needed by an existing child.
            if g in parents:continue
            raw=events[g-1][2]
            ts=tokens(db,raw.decode("utf8"));canonical=b" ".join(ts)
            if not canonical:continue
            unpacked,ta,td=get_tape(db,gids[g])
            tn=len(unpacked)
            assert unpacked==(encode_ids([ids[t] for t in ts]) if integer else canonical)
            # Conservative cold lexical payload charge for ID tapes, even when
            # the vocabulary is loaded once for query execution.
            lex=sum(map(len,set(ts))) if integer else 0
            dd=n+len(canonical)+(td+lex if integer else td-tn)
            if 2*dd>5*n:
                stats["joint_decode_bound_reject"]+=1;continue
            diff=h.delta_encode(raw,canonical)
            if diff is None:continue
            full=h.C.compress(raw)
            stats["joint_candidates"]+=1
            stats["joint_candidate_residual_bytes"]+=len(diff)
            if 5*len(diff)>4*len(full) or 2*(len(diff)+ta+lex)>3*len(full):
                stats["joint_activation_bound_reject"]+=1;continue
            stats["joint_bound_feasible"]+=1
            key=h.sha(diff);existing=keys.get(key)
            if existing is not None:assert frames[existing]==diff
            marginal=(0 if existing is not None else len(diff)+48)-(len(frames[fid])+48 if refs[fid]==1 else 0)
            if existing==fid or marginal>=0:continue
            if existing is None:
                new=next_fid;next_fid+=1;frames[new]=diff;keys[key]=new
                db.execute("INSERT INTO frames VALUES(?,?)",(new,diff))
            else:new=existing
            refs[fid]-=1;refs[new]+=1
            db.execute("UPDATE source SET kind=4,parent=0,fid=? WHERE g=?",(new,g))
            stats["joint_selected"]+=1;stats["joint_proxy_savings"]-=marginal
        db.execute("DELETE FROM frames WHERE fid NOT IN (SELECT fid FROM source)")
    db.execute("DROP TABLE docs_0")
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return dict(sqlite_bytes=path.stat().st_size,fts_bytes=0,table_bytes=sizes,
        index_bytes=sum(sizes.get(k,0) for k in ("lexicon","token_postings","token_tape")),
        tape_build_us=(time.perf_counter_ns()-start)/1000,**stats)

def vocabulary(db):
    ids={};terms={}
    for tid,term in db.execute("SELECT tid,term FROM lexicon ORDER BY tid"):
        t=term.encode("utf8")
        assert t not in ids and tid not in terms
        ids[t]=tid;terms[tid]=t
    return ids,terms

def get_tape(db,cid):
    n,z,base,body=db.execute("SELECT n,z,base,body FROM token_tape WHERE cid=?",(cid,)).fetchone()
    if not base:
        assert z in (0,1)
        return unpayload(n,z,body),len(body),n
    assert 0<base<cid and z==2
    pn,pz,pbase,pbody=db.execute("SELECT n,z,base,body FROM token_tape WHERE cid=?",(base,)).fetchone()
    assert pbase==0 and pz in (0,1)
    parent=unpayload(pn,pz,pbody)
    raw=delta_decode(body,parent,n)
    assert len(raw)==n
    return raw,len(body)+len(pbody),n+pn

def recover_tape(db,g,mode,terms):
    kind,=db.execute("SELECT kind FROM source WHERE g=?",(g,)).fetchone()
    if kind!=4:return recover(db,g)
    digest,n,cid,frame=db.execute("SELECT s.digest,s.n,r.cid,f.body FROM source s JOIN revisions r ON s.g=r.g JOIN frames f ON f.fid=s.fid WHERE s.g=?",(g,)).fetchone()
    tape,ab,td=get_tape(db,cid)
    if mode.startswith("ids"):
        seq=decode_ids(tape);lex=sum(len(terms[i]) for i in set(seq))
        canonical=b" ".join(terms[i] for i in seq);dd=n+len(canonical)+td+lex
    else:
        canonical=tape;lex=0;dd=n+td
    raw=delta_decode(frame,canonical,n)
    assert len(raw)==n and h.sha(raw)==digest
    return raw,dd,ab+len(frame)+lex

def rank_tape(db,p,o,prep,mode,ids):
    ar.expression(p,o);active,lens,n,total=prep;freq=[];work=collections.Counter()
    cache={};posting_cache={}
    for phrase in p:
        qs=tokens(db,phrase)
        if not qs:raise ValueError("empty phrase")
        qids=[ids.get(t) for t in qs]
        if None in qids:freq.append({});continue
        for tid in set(qids):
            if tid not in posting_cache:
                row=db.execute("SELECT n,z,body FROM token_postings WHERE tid=?",(tid,)).fetchone()
                posting_cache[tid]=dict(unpack(unpayload(*row)))
                work["posting_bytes"]+=len(row[2])
        if len(qids)==1:
            matches={cid:tf for cid,tf in posting_cache[qids[0]].items() if cid in active}
        else:
            candidates=set.intersection(*(set(posting_cache[tid]) for tid in set(qids)))
            matches={}
            for cid in candidates:
                if cid not in active:continue
                work["candidate_checks"]+=1
                if cid not in cache:
                    if mode=="frequency":
                        raw,dd,ab=recover(db,cid)
                        cache[cid]=b" ".join(tokens(db,raw.decode("utf8")))
                        work["source_reads"]+=1;work["source_activated_bytes"]+=ab;work["source_decoded_bytes"]+=dd
                    else:
                        cache[cid],ab,td=get_tape(db,cid)
                        work["tape_reads"]+=1;work["tape_activated_bytes"]+=ab;work["tape_decoded_bytes"]+=td
                tf=count_ids(cache[cid],encode_ids(qids)) if mode.startswith("ids") else phrase_count(cache[cid],qs)
                if tf:matches[cid]=tf
        expanded={g:tf for cid,tf in matches.items() for g in active[cid]}
        assert all(1<=tf<=lens[g] for g,tf in expanded.items());freq.append(expanded)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,work

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    results={};sigs={}
    for mode in ("positional","adaptive","frequency","text","text_joint","text_delta","text_delta_joint","ids","ids_delta"):
        path=folder/(mode+".sqlite");db,size=f.build(path,ext,events,"marginal",False)
        if mode=="adaptive":size.update(sp.build_delta(db,path,events,"independent_adaptive_weighted_adjusted_multi"))
        elif mode!="positional":size.update(build_tape(db,path,events,mode))
        db.close();db=connect(path,ext);ids={};terms={};mapping=None
        t=time.perf_counter_ns()
        if mode=="adaptive":mapping=sp.load_patch_map(db)
        elif mode!="positional":ids,terms=vocabulary(db)
        setup=(time.perf_counter_ns()-t)/1000
        tape_checks=0
        if mode not in ("positional","adaptive","frequency"):
            for cid, in db.execute("SELECT cid FROM contents ORDER BY cid"):
                ts=tokens(db,events[cid-1][2].decode("utf8"))
                want=encode_ids([ids[x] for x in ts]) if mode.startswith("ids") else b" ".join(ts)
                raw,ab,dd=get_tape(db,cid)
                assert raw==want and 2*dd<=5*len(want) and 2*ab<=3*len(payload(want)[1])
                tape_checks+=1
        source_times=[];ddtotal=abtotal=0;maxd=maxa=0.
        for g,(_,_,want) in enumerate(events,1):
            t=time.perf_counter_ns()
            raw,dd,ab=recover_tape(db,g,mode,terms) if mode.endswith("_joint") else recover(db,g)
            source_times.append((time.perf_counter_ns()-t)/1000)
            assert raw==want
            full=len(h.C.compress(want))
            assert 2*dd<=5*len(raw) and 2*ab<=3*full
            ddtotal+=dd;abtotal+=ab
            if raw:maxd=max(maxd,dd/len(raw))
            maxa=max(maxa,ab/full)
        size["final_frame_payload_bytes"]=db.execute("SELECT coalesce(sum(length(body)),0) FROM frames").fetchone()[0]
        size["final_unique_frames"]=db.execute("SELECT count(*) FROM frames").fetchone()[0]
        preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns()
            preps[c]=sp.prepare_delta(db,c,mapping) if mode=="adaptive" else prepare(db,c)
            pt.append((time.perf_counter_ns()-t)/1000)
        times=[];classes=collections.defaultdict(list);work=collections.Counter();err=0.
        rng=random.Random(170);plan=list(expected)
        for _ in range(2):
            rng.shuffle(plan)
            for c,p,o in plan:
                group="unigram_only" if all(len(tokens(db,q))==1 for q in p) else "has_phrase"
                t=time.perf_counter_ns()
                if mode=="positional":hits,df=si.rank(db,1,p,o,preps[c])
                elif mode=="adaptive":hits,df,w=sp.rank_delta(db,p,o,preps[c]);work.update(w)
                else:hits,df,w=rank_tape(db,p,o,preps[c],mode,ids);work.update(w)
                dt=(time.perf_counter_ns()-t)/1000;times.append(dt);classes[group].append(dt)
                err=max(err,h.verify(hits,expected[c,p,o]))
                if (c,p,o) in sigs:assert sigs[c,p,o]==(hits,df)
                else:sigs[c,p,o]=(hits,df)
        results[mode]=dict(**size,setup_us=setup,prepare=h.quant(pt),source_checks=len(events),tape_checks=tape_checks,
            source_recovery=h.quant(source_times),source_decoded_bytes=ddtotal,source_activated_bytes=abtotal,
            max_decode_ratio=maxd,max_activation_ratio=maxa,query=h.quant(times),
            query_by_class={k:h.quant(v) for k,v in classes.items()},rank_checks=len(times),max_score_error=err,work=dict(work))
        print("ARM_JSON="+json.dumps(results[mode]),flush=True);db.close()
    assert results["text"]["index_bytes"]==results["text_joint"]["index_bytes"]
    assert results["text_delta"]["index_bytes"]==results["text_delta_joint"]["index_bytes"]
    for ref in refs.values():ref.close()
    return dict(round=171,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),policies=results,
        limitations=["finalized subset, no transactional provenance","global vocabulary loaded at open; physical pages charged, cold lexical term bytes charged for source admission",
        "fixed32 token IDs; integer joint omitted after R170 rejected all tested candidates",
        "tape delta uses up to four prior full same-article tapes; includes both frames in activated and decoded bytes; no chained tape deltas",
        "tape candidate bound <=2.5x full raw tape bytes and <=1.5x independent tape payload; not physical page IO",
        "frequency lists fully decoded; phrase candidate scans; no physical IO claim",
        "source kind 4 replaces only non-parent revisions under existing raw/activated byte bounds",
        "R156 self-index historical results not same run; R157 text predictor reconstructed via matched frequency controls",
        "two shuffled warm query passes and sequential full source audit, not isolated random source latency"])

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
