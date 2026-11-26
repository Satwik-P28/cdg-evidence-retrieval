"""R155 finalized index: compact fragment catalogs and split boundary bridges.
No source reconstruction or append guarantee. Exact phrase TF <=8 native tokens.
"""
import argparse,collections,json,random,struct,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-154"))
import fragment_index as fi
from fragment_index import te,connect,h,nr,ar,tokens,encode,spans,query_plan

def varint(n):
    if n<0:raise ValueError("negative")
    b=bytearray()
    while n>=128:b.append((n&127)|128);n>>=7
    b.append(n);return bytes(b)

def pack(rows):
    prev=0;out=bytearray()
    for cid,m in rows:
        if cid<=prev or m<1:raise ValueError("posting order")
        out+=varint(((cid-prev)<<1)|int(m>1))
        if m>1:out+=varint(m)
        prev=cid
    return bytes(out)

def unpack(blob):
    pos=prev=0
    def get():
        nonlocal pos
        n=shift=0
        while pos<len(blob) and shift<=63:
            b=blob[pos];pos+=1;n|=(b&127)<<shift
            if b<128:return n
            shift+=7
        raise ValueError("bad varint")
    while pos<len(blob):
        v=get();delta=v>>1;m=get() if v&1 else 1
        if delta<1 or m<1:raise ValueError("invalid posting")
        prev+=delta;yield prev,m

def compact(db,path,layout):
    # All arms drop the content insertion catalog in finalized mode.
    db.execute("DROP TABLE content_catalog")
    if layout!="raw":
        db.execute("CREATE TABLE packed_uses(fid INTEGER PRIMARY KEY,body BLOB NOT NULL)")
        for fid, in db.execute("SELECT fid FROM fragments ORDER BY fid").fetchall():
            rows=db.execute("SELECT cid,m FROM uses WHERE fid=? ORDER BY cid",(fid,)).fetchall()
            payload=pack(rows);assert list(unpack(payload))==rows
            db.execute("INSERT INTO packed_uses VALUES(?,?)",(fid,payload))
        if layout=="halo":
            db.execute("CREATE TABLE compact_fragments(fid INTEGER PRIMARY KEY,kind INTEGER NOT NULL,split INTEGER NOT NULL)")
            db.execute("INSERT INTO compact_fragments SELECT fid,1,core FROM fragments")
        else:
            db.execute("CREATE TABLE compact_fragments(fid INTEGER PRIMARY KEY,kind INTEGER NOT NULL,split INTEGER NOT NULL)")
            db.execute("INSERT INTO compact_fragments SELECT fid,kind,split FROM fragments")
        db.execute("DROP TABLE uses");db.execute("DROP TABLE fragments")
    db.commit();db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
    return dict(sqlite_bytes=path.stat().st_size,physical_table_bytes=sizes,
        packed_posting_bytes=db.execute("SELECT coalesce(sum(length(body)),0) FROM packed_uses").fetchone()[0] if layout!="raw" else 0)

def bridge_build(path,ext,events,policy):
    db=connect(path,ext);db.execute("PRAGMA page_size=4096")
    db.executescript("""
      CREATE VIRTUAL TABLE docs USING fts5(body,content='');
      CREATE TABLE revisions(g INTEGER PRIMARY KEY,article TEXT NOT NULL,ord INTEGER NOT NULL,
        cid INTEGER NOT NULL,dl INTEGER NOT NULL,end_g INTEGER);
      CREATE TABLE active_stats(g INTEGER PRIMARY KEY,n INTEGER NOT NULL,tokens INTEGER NOT NULL);
      CREATE TABLE content_catalog(digest BLOB PRIMARY KEY,cid INTEGER NOT NULL,dl INTEGER NOT NULL) WITHOUT ROWID;
      CREATE TABLE fragments(fid INTEGER PRIMARY KEY,digest BLOB NOT NULL UNIQUE,kind INTEGER NOT NULL,split INTEGER NOT NULL);
      CREATE TABLE uses(fid INTEGER NOT NULL,cid INTEGER NOT NULL,m INTEGER NOT NULL,PRIMARY KEY(fid,cid)) WITHOUT ROWID;
    """)
    known={};frags={};heads={};total=0;occ=collections.Counter();unique=collections.Counter();start=time.perf_counter_ns()
    for g,(a,i,raw) in enumerate(events,1):
        digest=h.sha(raw);old=known.get(digest)
        if old:
            cid,dl=old;assert events[cid-1][2]==raw
        else:
            cid=g;ts=tokens(db,raw.decode("utf8"));dl=len(ts);known[digest]=(cid,dl)
            db.execute("INSERT INTO content_catalog VALUES(?,?,?)",(digest,cid,dl))
            counts=collections.Counter();parts=spans(ts,policy);reassembled=[]
            def add(kind,split,part):
                payload=encode(part);key=h.sha(struct.pack(">II",kind,split)+payload)
                if key in frags:
                    fid,k,s,p=frags[key];assert (k,s,p)==(kind,split,payload)
                else:
                    fid=len(frags)+1;frags[key]=(fid,kind,split,payload)
                    body=b" ".join(part).decode("utf8")
                    assert db.execute("SELECT cdg_token_stream(?)",(body,)).fetchone()[0]==payload
                    db.execute("INSERT INTO fragments VALUES(?,?,?,?)",(fid,key,kind,split))
                    db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(fid,body));unique[kind]+=1
                counts[fid]+=1;occ[kind]+=1
            for start_i,end in parts:
                core=ts[start_i:end];reassembled.extend(core);add(0,len(core),core)
                if end<dl:
                    # Nonfinal cores are at least 16 tokens. An <=8-token phrase
                    # cannot cross two internal boundaries.
                    assert len(core)>=8
                    left=core[-7:];right=ts[end:min(dl,end+7)]
                    add(2,len(left),left+right)
            assert reassembled==ts
            db.executemany("INSERT INTO uses VALUES(?,?,?)",((f,cid,m) for f,m in counts.items()))
        if a in heads:
            old_g,old_i,old_dl=heads[a];assert i==old_i+1
            db.execute("UPDATE revisions SET end_g=? WHERE g=?",(g,old_g));total-=old_dl
        else:assert i==0
        db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,NULL)",(g,a,i,cid,dl))
        heads[a]=(g,i,dl);total+=dl
        db.execute("INSERT INTO active_stats VALUES(?,?,?)",(g,len(heads),total))
    db.execute("CREATE INDEX revision_cid ON revisions(cid,g)");db.commit()
    db.execute("INSERT INTO docs(docs) VALUES('optimize')");db.commit();db.execute("VACUUM")
    return db,dict(sqlite_bytes=path.stat().st_size,content_rows=len(known),core_rows=unique[0],bridge_rows=unique[2],
        core_occurrences=occ[0],bridge_occurrences=occ[2],build_us=(time.perf_counter_ns()-start)/1000)

def prepare(db,c):
    active=collections.defaultdict(list);lens={}
    for g,cid,dl in db.execute("SELECT g,cid,dl FROM revisions WHERE g<=? AND (end_g IS NULL OR end_g>?)",(c,c)):
        active[cid].append(g);lens[g]=dl
    n,total=db.execute("SELECT n,tokens FROM active_stats WHERE g=?",(c,)).fetchone()
    assert len(lens)==n and sum(lens.values())==total
    return active,lens,n,total

def rank(db,p,o,prepared,layout):
    ar.expression(p,o);active,lens,n,total=prepared;freq=[]
    for phrase in p:
        if not 1<=len(tokens(db,phrase))<=8:raise ValueError("phrase length")
        content=collections.Counter()
        if layout=="raw":
            for cid,tf in db.execute("SELECT rowid,cdg_count(docs) FROM docs WHERE docs MATCH ?",(ar.quote(phrase),)):
                if cid in active:content[cid]=tf
        else:
            for tf,blob in db.execute("""SELECT CASE f.kind
                WHEN 0 THEN cdg_count(docs)
                WHEN 1 THEN cdg_owned_count(docs,f.split)
                ELSE cdg_crossing_count(docs,f.split) END AS tf,u.body
                FROM docs JOIN compact_fragments f ON f.fid=docs.rowid
                JOIN packed_uses u ON u.fid=docs.rowid WHERE docs MATCH ?""",(ar.quote(phrase),)):
                if not tf:continue
                for cid,m in unpack(blob):
                    if cid in active:content[cid]+=tf*m
        matches={g:tf for cid,tf in content.items() for g in active[cid]}
        assert all(1<=tf<=lens[g] for g,tf in matches.items())
        freq.append(matches)
    return ar.score(freq,o,n,total,lens)

def run(events,manifest,cuts,folder,ext,corpus):
    refs={c:h.active_oracle(events,c) for c in cuts}
    queries=list(dict.fromkeys(query_plan(events,cuts[0],refs[cuts[0]])+fi.boundary_plan(ext,events,cuts[0])))
    check=connect(":memory:",ext);queries=[(p,o) for p,o in queries if all(1<=len(tokens(check,t))<=8 for t in p)];check.close()
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in queries}
    rng=random.Random(155);results={};signatures={}
    for name,layout,policy in [("raw","raw",None),("halo64","halo","cdc64"),("bridge64","bridge","cdc64"),("bridge128","bridge","cdc128")]:
        path=folder/(name+".sqlite")
        if layout=="raw":
            db,size=te.build(path,ext,events,"raw");db.execute("CREATE INDEX revision_cid ON revisions(cid,g)");db.commit();db.execute("VACUUM");size["sqlite_bytes"]=path.stat().st_size
        elif layout=="halo":db,size=fi.build(path,ext,events,policy)
        else:db,size=bridge_build(path,ext,events,policy)
        before=size["sqlite_bytes"];start=time.perf_counter_ns();physical=compact(db,path,layout);compact_us=(time.perf_counter_ns()-start)/1000
        prepared={};prep=[]
        for c in cuts:
            start=time.perf_counter_ns();prepared[c]=prepare(db,c);prep.append((time.perf_counter_ns()-start)/1000)
        times=[];err=0.
        for repeat in range(2):
            plan=list(expected);rng.shuffle(plan)
            for c,p,o in plan:
                start=time.perf_counter_ns();hits,df=rank(db,p,o,prepared[c],layout);times.append((time.perf_counter_ns()-start)/1000)
                err=max(err,h.verify(hits,expected[c,p,o]));sig=(hits,df)
                if (c,p,o) in signatures:assert sig==signatures[c,p,o]
                else:signatures[c,p,o]=sig
        results[name]=dict(before_compaction_bytes=before,build=size,**physical,compact_us=compact_us,
            prepare=h.quant(prep),query=h.quant(times),rank_checks=len(times),max_score_error=err)
        print("ARM_JSON="+json.dumps(results[name]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=155,corpus=corpus,revisions=len(events),manifest_sha256=manifest,cutoffs=cuts,
        query_count=len(queries),query_plan_sha256=h.sha(h.canonical(queries)).hex(),policies=results,
        limitations=["finalized index only; insertion catalogs omitted in ALL arms; not transactional",
          "packed mapping lists decoded in Python; common prepared snapshot mapping cost reported separately",
          "phrase length 1..8, default unicode61, exact AND/OR only; no raw source reconstruction",
          "bridge scheme assumes nonfinal cores >=8 tokens; distinct crossing matches counted once",
          "two warm shuffled repeats; no production latency claim; AP synthetic ordinal schedule"])

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
            first=len(m["retained_paths"]);n=len(events);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            assert manifest==json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
        x=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
