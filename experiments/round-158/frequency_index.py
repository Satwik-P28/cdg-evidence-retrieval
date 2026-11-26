"""R158 frequency postings with bounded-source fallback for exact phrases.
Finalized matched source/index subset, no new transactional guarantee.
"""
import argparse,collections,itertools,json,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-157"))
sys.path.insert(0,str(HERE.parent/"round-155"))
import forward_index as f
from forward_index import h,si,connect,nr,ar,tokens,query_plan,prepare,recover,D,phrase_count
from compact_fragments import pack,unpack

def frequency_index(db,path):
    db.execute("CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main,docs_0,'instance')")
    db.execute("CREATE TABLE term_freq(term TEXT PRIMARY KEY,n INTEGER NOT NULL,compressed INTEGER NOT NULL,body BLOB NOT NULL) WITHOUT ROWID")
    start=time.perf_counter_ns();terms=pairs=packed=encoded=0
    for term,rows in itertools.groupby(db.execute("SELECT term,doc,count(*) FROM temp.vocab GROUP BY term,doc ORDER BY term,doc"),key=lambda row:row[0]):
        values=[(cid,tf) for _,cid,tf in rows];raw=pack(values)
        assert list(unpack(raw))==values
        z=h.C.compress(raw);compressed=int(len(z)<len(raw));body=z if compressed else raw
        db.execute("INSERT INTO term_freq VALUES(?,?,?,?)",(term,len(raw),compressed,body))
        terms+=1;pairs+=len(values);packed+=len(raw);encoded+=len(body)
    db.execute("DROP TABLE temp.vocab")
    db.execute("DROP TABLE docs_0");db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    return dict(term_count=terms,posting_pairs=pairs,packed_posting_bytes=packed,encoded_posting_bytes=encoded,
        transposition_us=(time.perf_counter_ns()-start)/1000,sqlite_bytes=path.stat().st_size)

def get(db,t):
    row=db.execute("SELECT n,compressed,body FROM term_freq WHERE term=?",(t.decode("utf8"),)).fetchone()
    if row is None:return {},0
    n,compressed,body=row;raw=D.decompress(body,max_output_size=n+1) if compressed else body
    assert len(raw)==n
    return dict(unpack(raw)),len(body)

def rank_frequency(db,p,o,prepared):
    ar.expression(p,o);active,lens,n,total=prepared;freq=[];cache={};term_cache={};work=collections.Counter()
    for phrase in p:
        qs=tokens(db,phrase);assert qs
        for t in set(qs):
            if t not in term_cache:
                rows,size=get(db,t);term_cache[t]=rows;work["posting_bytes"]+=size
        if len(qs)==1:
            content={cid:tf for cid,tf in term_cache[qs[0]].items() if cid in active}
        else:
            candidates=set.intersection(*(set(term_cache[t]) for t in set(qs)))
            content={}
            for cid in candidates:
                if cid not in active:continue
                work["candidate_checks"]+=1
                if cid not in cache:
                    raw,dd,ab=recover(db,cid);cache[cid]=b" ".join(tokens(db,raw.decode("utf8")))
                    work["source_activated_bytes"]+=ab;work["source_decoded_bytes"]+=dd;work["source_reads"]+=1
                tf=phrase_count(cache[cid],qs)
                if tf:content[cid]=tf
        matches={g:tf for cid,tf in content.items() for g in active[cid]}
        assert all(1<=tf<=lens[g] for g,tf in matches.items());freq.append(matches)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,work

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(158);results={};sigs={}
    for mode in ("positional","presence","frequency"):
        path=folder/(mode+".sqlite");db,size=f.build(path,ext,events,"marginal",mode=="presence")
        if mode=="frequency":size.update(frequency_index(db,path))
        db.close();db=connect(path,ext)
        source_checks=0
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g);assert raw==want
            assert 2*dd<=5*len(raw) and 2*ab<=3*len(h.C.compress(raw))
            source_checks+=1
        prep={};prep_times=[]
        for c in cuts:
            t=time.perf_counter_ns();prep[c]=prepare(db,c);prep_times.append((time.perf_counter_ns()-t)/1000)
        times=[];classes=collections.defaultdict(list);work=collections.Counter();err=0.
        for repeat in range(2):
            order=list(expected);rng.shuffle(order)
            for c,p,o in order:
                group="unigram_only" if all(len(tokens(db,t))==1 for t in p) else "has_phrase"
                t=time.perf_counter_ns()
                if mode=="frequency":
                    hits,df,w=rank_frequency(db,p,o,prep[c]);work.update(w)
                elif mode=="presence":
                    hits,df,k,ab=f.rank_presence(db,p,o,prep[c]);work.update(candidate_checks=k,source_activated_bytes=ab)
                else:hits,df=si.rank(db,1,p,o,prep[c])
                elapsed=(time.perf_counter_ns()-t)/1000;times.append(elapsed);classes[group].append(elapsed)
                err=max(err,h.verify(hits,expected[c,p,o]));sig=hits,df
                if (c,p,o) in sigs:assert sig==sigs[c,p,o]
                else:sigs[c,p,o]=sig
        results[mode]=dict(**size,source_checks=source_checks,query=h.quant(times),
            query_by_class={k:h.quant(v) for k,v in classes.items()},prepare=h.quant(prep_times),
            rank_checks=len(times),max_score_error=err,work=dict(work))
        print("ARM_JSON="+json.dumps(results[mode]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=158,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(queries),query_plan_sha256=h.sha(h.canonical(queries)).hex(),policies=results,
        limitations=["finalized index/source subset only; no provenance or append contract",
          "all source codecs identical; exact native term-frequency lists with per-term raw or Zstd delta-varint encoding",
          "multitoken phrases decode candidate sources; candidate and frame bytes not physical IO",
          "same active snapshot preparation, two shuffled warm passes; query classes reported separately",
          "full term list decoding, no skip pointers or block compression; no general novelty claim"])

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
