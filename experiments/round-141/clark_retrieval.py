"""CLARK-News: dated, labeled historical retrieval and evidence replay.

Use upstream known-answer intervals and question schedule, source read times.
No answer choices in retrieval; exact answer token coverage is a proxy, not QA accuracy.
"""
import argparse,bisect,collections,csv,datetime,hashlib,json,os,re,subprocess,sys,tempfile,unicodedata
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-137"))
import transactional_pack as tp
import heldout_archive as h

PIN="b93f898780b3cf40fedd4e9a00c51af9a27688bc"
SALT="CDG-R141-CLARK-v1|"
STOP=set("a an the in on of to for from is are was were be been being do does did what which who whom whose when where why how has have had it its by at as and or with hold member".split())

def ts(s):
    if s is None or not str(s).strip():return None
    t=datetime.datetime.fromisoformat(str(s).strip().replace("Z","+00:00"))
    if t.tzinfo is None:t=t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc)

def tokens(x):
    return re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",x).casefold(),flags=re.UNICODE)

def terms(q):
    return tuple(dict.fromkeys(t for t in tokens(q) if t not in STOP and len(t)>1))[:16]

def contains(text,answer):
    a=tokens(answer);s=tokens(text)
    if not a:return False
    return any(s[i:i+len(a)]==a for i in range(len(s)-len(a)+1))

def gold(rows,date):
    labels={r["Answer"].strip() for r in rows
        if (ts(r["Known start timestamp"]) is None or ts(r["Known start timestamp"])<=date)
        and (ts(r["Known end timestamp"]) is None or date<ts(r["Known end timestamp"]))}
    if len(labels)!=1:return None
    label=next(iter(labels))
    return label if label and label.casefold() not in ("yes","no","none","nan") else None

def read(root):
    assert subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()==PIN
    root=root/"CLARK_news"/"full"
    names=("questions.csv","timestamp_to_questions.json","external_sources.json")
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
    sources=json.loads((root/names[2]).read_text())
    rows=[]
    dropped=collections.Counter()
    for url,versions in sources.items():
        for t,item in versions.items():
            if not isinstance(item.get("source_text"),str) or not item["source_text"].strip():
                dropped["empty_or_missing_source_text"]+=1;continue
            date=ts(t)
            if date is None:raise ValueError("missing source read timestamp")
            rows.append((date,url,item["source_text"].encode("utf8"),item.get("archive_url"),item.get("source_timestamp")))
    rows.sort(key=lambda x:(x[0],x[1]))
    # Same URL is a document identity. Keep every nonempty released timestamped source text.
    histories=collections.Counter();events=[];origins=[];times=[];source_refs=[]
    for g,(date,url,raw,archive_url,source_timestamp) in enumerate(rows,1):
        i=histories[url];histories[url]+=1
        events.append((url,i,raw));times.append(date)
        identity=hashlib.sha1(h.canonical([url,date.isoformat(),archive_url])).hexdigest()
        blob=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
        origins.append((identity,int(date.timestamp()),blob))
        source_refs.append([g,url,i,date.isoformat(),archive_url,source_timestamp,h.sha(raw).hex()])
    by_q=collections.defaultdict(list)
    with (root/names[0]).open(newline="",encoding="utf8") as f:
        for row in csv.DictReader(f):by_q[row["Question"]].append(row)
    schedule=json.loads((root/names[1]).read_text())
    cases=[];seen=set()
    for t,qs in sorted(schedule.items(),key=lambda x:ts(x[0])):
        date=ts(t);cut=bisect.bisect_right(times,date)
        for q in qs:
            key=(date,q)
            if key in seen:dropped["duplicate_schedule_case"]+=1;continue
            seen.add(key)
            if cut<1:dropped["before_first_source"]+=1;continue
            if not terms(q):dropped["empty_query"]+=1;continue
            answer=gold(by_q[q],date)
            if answer is None:dropped["ambiguous_or_nonextractive_gold"]+=1;continue
            cases.append(dict(date=date.isoformat(),cut=cut,question=q,answer=answer,terms=terms(q)))
    if not cases:raise ValueError("empty benchmark")
    # Prespecified hash selection; no selection by retrieval or answer coverage.
    cases.sort(key=lambda c:(h.sha((SALT+c["date"]+"|"+c["question"]).encode()),c["date"],c["question"]))
    manifest=dict(source="CLARK-News published extracted source text",upstream_pin=PIN,input_sha256=hashes,
        source_refs=source_refs,provenance="synthetic identity SHA1 of URL/read timestamp/archive URL, actual released read timestamps",
        schedule="upstream read timestamp; ties by URL, queries after all sources with read time <= query time")
    return events,origins,manifest,cases,dict(dropped)

def cover(events,hits,answer):
    flags=[contains(events[g-1][2].decode("utf8"),answer) for g,_ in hits]
    return dict(top1=bool(flags and flags[0]),top5=any(flags[:5]),top10=any(flags[:10]),hits=len(flags))

def run(root,folder,ext,target):
    events,origins,m,cases,dropped=read(root);eligible=len(cases);cases=cases[:target]
    n=len(events);cuts=sorted({c["cut"] for c in cases}|{n})
    expected={};latest={};native={}
    for cut in cuts:
        ref=h.active_oracle(events,cut)
        for c in cases:
            q=c["terms"]
            if c["cut"]==cut or cut==n:
                key=cut,q
                if key not in native:native[key]=h.native(ref,q,"OR")
        ref.close()
    for i,c in enumerate(cases):
        expected[i]=native[c["cut"],c["terms"]];latest[i]=native[n,c["terms"]]
    results={};published={}
    for policy in ("snapshot","bounded_anchor"):
        path=folder/(policy+".sqlite");db=tp.setup(path,ext,m)
        db.execute("PRAGMA wal_autocheckpoint=1000")
        fd=os.open(tp.side(path),os.O_RDWR);issued={}
        at=collections.defaultdict(list)
        for i,c in enumerate(cases):at[c["cut"]].append(i)
        for g,((a,i,raw),origin) in enumerate(zip(events,origins),1):
            assert tp.append(db,fd,a,raw,origin,policy)==(g,i)
            if g in at:
                db.execute("BEGIN")
                for j in at[g]:
                    body,d=tp.issue(db,fd,cases[j]["terms"],"OR",g)
                    h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["hits"]],expected[j])
                    issued[j]=(body,d)
                db.rollback()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)");db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
        db.close();db=h.connect(path,ext);db.execute("BEGIN")
        assert tp.audit(db,fd)==n
        maxerr=0.;hits=0
        for j,c in enumerate(cases):
            body,d=tp.issue(db,fd,c["terms"],"OR",c["cut"])
            assert (body,d)==issued[j]
            if j in published:assert published[j]==(body,d)
            else:published[j]=(body,d)
            maxerr=max(maxerr,h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["hits"]],expected[j]))
            for v in body["hits"]:
                a,i,want=events[v["g"]-1]
                raw,*_=tp.recover(db,fd,a,i);assert raw==want;hits+=1
        rawbytes=decoded=0;maxa=maxd=1.
        for a,i,want in events:
            got,ab,dd,depth=tp.recover(db,fd,a,i);assert got==want
            full=len(h.C.compress(got));rawbytes+=len(got);decoded+=dd
            if got:maxd=max(maxd,dd/len(got))
            maxa=max(maxa,ab/full)
            if policy=="bounded_anchor":assert depth<=1 and 2*ab<=3*full and 2*dd<=5*len(got)
        end=tp.state(db,fd);assert end==os.fstat(fd).st_size
        db.rollback();db.close();os.close(fd)
        results[policy]=dict(total_archive_bytes=path.stat().st_size+end,payload_bytes=end-tp.HEADER,
            source_reads=n,rank_checks=len(cases),receipt_replays=len(cases),evidence_hits=hits,max_score_error=maxerr,
            mean_decode_ratio=decoded/max(1,rawbytes),max_decode_ratio=maxd,max_activation_ratio=maxa)
    totals=collections.Counter();detail=[]
    by_url={}
    for g,(a,i,raw) in enumerate(events,1):by_url[a]=g
    for i,c in enumerate(cases):
        old=expected[i];new=latest[i]
        # Keep original ranked document identities but resolve to latest URL version.
        resolved=[(by_url[events[g-1][0]],s) for g,s in old]
        old_cov=cover(events,old,c["answer"]);new_cov=cover(events,new,c["answer"]);resolved_cov=cover(events,resolved,c["answer"])
        d=dict(case_sha256=h.sha(h.canonical([c["date"],c["question"],c["answer"]])).hex(),cutoff=c["cut"],
            old=old_cov,current=new_cov,latest_url_resolved=resolved_cov)
        totals.update(cases=1,historical_top10=old_cov["top10"],current_top10=new_cov["top10"],
            latest_url_top10=resolved_cov["top10"],historical_only_top10=old_cov["top10"] and not new_cov["top10"],
            current_only_top10=new_cov["top10"] and not old_cov["top10"],
            historical_top1=old_cov["top1"],current_top1=new_cov["top1"],
            historical_top5=old_cov["top5"],current_top5=new_cov["top5"],
            revision_rank_changed=[g for g,_ in old]!=[g for g,_ in new],
            document_rank_changed=[events[g-1][0] for g,_ in old]!=[events[g-1][0] for g,_ in new])
        detail.append(d)
    return dict(round=141,upstream_pin=PIN,input_sha256=m["input_sha256"],source_manifest_sha256=h.sha(h.canonical(m)).hex(),
        documents=len(by_url),revisions=n,changed_urls=sum(x>1 for x in collections.Counter(a for a,_,_ in events).values()),
        eligible_cases=eligible,evaluated_cases=len(cases),excluded=dropped,unique_cutoffs=len(cuts),
        counts=dict(totals),policies=results,details=detail,
        limitations=["published extracted source text, not original HTML bytes",
          "upstream relation-derived questions with human-validated source annotations, not independently human-authored questions",
          "gold token-sequence presence is retrieval coverage proxy, not semantic answer correctness",
          "known-answer intervals and upstream query schedule; ambiguous and yes/no labels excluded",
          "latest-only active URL archive is not the original ERASE system; no LLM generation",
          "read-time chronology is upstream availability time, not inferred real event time"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--upstream",type=Path,required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--target",type=int,default=256);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=run(a.upstream,Path(d),a.extension.resolve(),a.target)
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
