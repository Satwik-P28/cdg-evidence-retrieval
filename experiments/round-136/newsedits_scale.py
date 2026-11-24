"""R136: actual NewsEdits derived revision text, source-only storage scale.

Source sentence rows are canonicalized into UTF-8 joined by newline. This is
not reconstruction of original news HTML/bytes or chronological global replay.
"""
import argparse,collections,gzip,hashlib,json,sqlite3,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-132"))
from heldout_archive import C,sha,canonical,choose,choose_config
from anchor_bench import setup,recover
POLICIES=("snapshot","prev8","anchor8","k1","bounded_anchor","tight_activation")
SALT="CDG-R136-NewsEdits-v1|"

def file_sha(p):
    digest=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):digest.update(block)
    return digest.hexdigest()

def sample(db,target):
    # Document selection depends only on IDs and revision counts, never codec results.
    cols={x[1] for x in db.execute("PRAGMA table_info(split_sentences)")}
    if not {"entry_id","version","sent_idx","sentence"}<=cols:raise ValueError("unexpected upstream schema")
    rows=db.execute("""SELECT entry_id,COUNT(DISTINCT version) FROM split_sentences
       GROUP BY entry_id HAVING COUNT(DISTINCT version)>=2""").fetchall()
    if any(a is None for a,_ in rows):raise ValueError("missing entry id")
    rows.sort(key=lambda x:(sha((SALT+str(x[0])).encode()),str(x[0])))
    selected=[];n=0
    for a,count in rows:
        selected.append((a,count));n+=count
        if n>=target:break
    return selected,n,len(rows)

def read_article(db,a,count):
    rows=db.execute("""SELECT version,sent_idx,sentence FROM split_sentences WHERE entry_id=?
       ORDER BY version,sent_idx""",(a,))
    versions=collections.OrderedDict()
    for v,i,s in rows:
        if v is None or i is None or not isinstance(s,str):raise ValueError("invalid sentence row")
        try:
            v_int,i_int=int(v),int(i)
            if float(v)!=v_int or float(i)!=i_int:raise ValueError("noninteger version or sentence index")
        except (TypeError,ValueError,OverflowError):raise ValueError("invalid version/index")
        sentence_map=versions.setdefault(v_int,{})
        if i_int in sentence_map:raise ValueError("duplicate sentence index")
        sentence_map[i_int]=s
    if len(versions)!=count:raise ValueError("revision count mismatch")
    return [(v,"\n".join(m[i] for i in sorted(m)).encode("utf8")) for v,m in sorted(versions.items())]

def encode_article(db,a,versions,policy):
    history=[]
    with db:
        for i,(v,raw) in enumerate(versions):
            if policy in ("k1","bounded_anchor","tight_activation"):
                parent,depth,payload=choose_config(raw,i,history,policy)
            else:parent,depth,payload=choose(raw,i,history,policy)
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?)",(str(a),i,len(raw),sha(raw),depth,parent,payload))
            db.execute("INSERT INTO upstream_versions VALUES(?,?,?)",(str(a),i,v))
            history.append((raw,len(payload),depth))

def run(source,target,folder):
    db=sqlite3.connect("file:"+str(source.resolve())+"?mode=ro",uri=True)
    chosen,n,eligible=sample(db,target)
    if not chosen:raise ValueError("empty cohort")
    # Avoid thousands of full-table scans when the upstream DB lacks an entry index.
    # Copy only selected sentence rows to a scratch indexed DB, never count it as an archive.
    scratch=sqlite3.connect(folder/"scratch.sqlite")
    scratch.execute("CREATE TABLE split_sentences(entry_id,version,sent_idx,sentence)")
    db.execute("CREATE TEMP TABLE selected(entry_id PRIMARY KEY)")
    db.executemany("INSERT INTO selected VALUES(?)",((a,) for a,_ in chosen))
    cur=db.execute("SELECT s.entry_id,s.version,s.sent_idx,s.sentence FROM split_sentences s JOIN selected q ON q.entry_id=s.entry_id")
    while True:
        block=cur.fetchmany(20000)
        if not block:break
        scratch.executemany("INSERT INTO split_sentences VALUES(?,?,?,?)",block)
    scratch.execute("CREATE INDEX by_entry ON split_sentences(entry_id,version,sent_idx)");scratch.commit()
    db.close()
    results={};archives={}
    for p in POLICIES:
        path=folder/(p+".sqlite");out=setup(path)
        out.execute("CREATE TABLE upstream_versions(article TEXT,ord INTEGER,upstream_version INTEGER,PRIMARY KEY(article,ord),FOREIGN KEY(article,ord) REFERENCES versions(article,ord)) WITHOUT ROWID")
        out.commit();out.execute("PRAGMA wal_autocheckpoint=1000")
        archives[p]=out;results[p]=collections.Counter()
    manifest=hashlib.sha256();count=raw_bytes=0;start=time.perf_counter()
    for k,(a,vcount) in enumerate(chosen):
        versions=read_article(scratch,a,vcount)
        for i,(v,raw) in enumerate(versions):
            manifest.update(canonical([str(a),i,v,sha(raw).hex(),len(raw)]));manifest.update(b"\n")
            raw_bytes+=len(raw);count+=1
        for p,out in archives.items():encode_article(out,a,versions,p)
        for i,(v,want) in enumerate(versions):
            full=len(C.compress(want))
            for p,out in archives.items():
                got,ab,dd,d=recover(out,str(a),i)
                if got!=want:raise AssertionError("source mismatch")
                if p in ("k1","bounded_anchor","tight_activation"):
                    budget=110 if p=="tight_activation" else 150
                    assert d<=1 and 100*ab<=budget*full and 100*dd<=250*len(want)
                x=results[p];x.update(reads=1,activated=ab,decoded=dd)
                x["max_depth"]=max(x["max_depth"],d)
                x["max_activation"]=max(x["max_activation"],ab/full)
                if want:x["max_decode"]=max(x["max_decode"],dd/len(want))
        if k%1000==0:print("PROGRESS",k,count,flush=True)
    assert count==n
    for p,out in archives.items():
        out.commit();out.execute("PRAGMA wal_checkpoint(TRUNCATE)");out.execute("PRAGMA journal_mode=DELETE");out.execute("VACUUM")
        assert out.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert not out.execute("PRAGMA foreign_key_check").fetchall()
        x=results[p];x["source_sqlite_bytes"]=(folder/(p+".sqlite")).stat().st_size
        x["payload_bytes"]=out.execute("SELECT SUM(length(payload)) FROM versions").fetchone()[0]
        x["decode_amplification"]=x["decoded"]/max(1,raw_bytes)
        out.close()
    scratch.close()
    return dict(requested_revisions=target,target_reached=count>=target,retained_revisions=count,documents=len(chosen),
        eligible_documents=eligible,raw_derived_bytes=raw_bytes,manifest_sha256=manifest.hexdigest(),
        selected_id_sha256=sha(canonical([[str(a),v] for a,v in chosen])).hex(),
        policies={p:dict(x) for p,x in results.items()},elapsed_s=time.perf_counter()-start)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,default=100000);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    if a.target<1:raise ValueError("invalid target")
    with tempfile.TemporaryDirectory() as d:result=run(a.source,a.target,Path(d))
    out=dict(round=136,source_sha256=file_sha(a.source),source_file=a.source.name,
        scope="source-only SQLite storage and reconstruction of derived NewsEdits sentence text; no retrieval index",result=result)
    a.out.write_text(json.dumps(out,indent=2)+"\n");print("RESULT_JSON="+json.dumps(out),flush=True)
