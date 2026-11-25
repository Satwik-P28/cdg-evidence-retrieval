"""Pinned upstream TimIR DAO SQL executed on actual MonetDB, independently
rebuilt native Lucene 8.4.1 oracles. Component reproduction only."""
import argparse,base64,collections,datetime,hashlib,json,os,re,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path
import pymonetdb
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-132"))
import heldout_archive as h
PIN="90df24ba022f18280c30ffcf68fcbd0f4b7685a6"
DAO="backend/src/main/java/at/ac/tuwien/lucombonet/Persistence/impl/DocumentDaoMonetDB.java"
def sql_from_source(root):
    code=(root/DAO).read_text()
    section=code[code.index("findByTermsBM25Version("):]
    body=re.search(r"String sql = String.format\((.*?),\s*inSql\s*\);",section,re.S)
    if body is None:raise ValueError("upstream SQL not found")
    sql="".join(json.loads(x) for x in re.findall(r'"(?:\\.|[^"\\])*"',body[1]))
    assert sql.count("?")==8 and sql.count("%s")==1
    return sql
def decode(x):return base64.b64decode(x).decode("utf8")
def encode(x):return base64.b64encode(x).decode("ascii")
def ts(g):return datetime.datetime(2000,1,1)+datetime.timedelta(seconds=g)
def connect():
    for _ in range(60):
        try:return pymonetdb.connect(hostname="127.0.0.1",port=50000,database="demo",username="monetdb",password="monetdb")
        except Exception:time.sleep(2)
    raise RuntimeError("MonetDB startup failed")
def bulk(cur,sql,rows):
    for i in range(0,len(rows),2000):cur.executemany(sql,rows[i:i+2000])
def load_data(cur,folder):
    cur.execute("CREATE TABLE doc(id BIGINT PRIMARY KEY,name VARCHAR(4096),length BIGINT,approximated_length BIGINT,added TIMESTAMP,removed TIMESTAMP)")
    cur.execute("CREATE TABLE dictionary(id BIGINT PRIMARY KEY,term VARCHAR(4096))")
    cur.execute("CREATE TABLE doc_terms(document_id BIGINT,dictionary_id BIGINT,term_frequency BIGINT)")
    docs=[]
    for row in (folder/"docs.tsv").read_text().splitlines():
        g,name,l,approx,end=row.split("\t");docs.append((int(g),decode(name),int(l),int(approx),ts(int(g)),ts(int(end)) if int(end) else None))
    terms={};postings=[]
    for row in (folder/"terms.tsv").read_text().splitlines():
        g,t,f=row.split("\t");t=decode(t)
        if t not in terms:terms[t]=len(terms)+1
        postings.append((int(g),terms[t],int(f)))
    bulk(cur,"INSERT INTO doc VALUES (%s,%s,%s,%s,%s,%s)",docs)
    bulk(cur,"INSERT INTO dictionary VALUES (%s,%s)",[(i,t) for t,i in terms.items()])
    bulk(cur,"INSERT INTO doc_terms VALUES (%s,%s,%s)",postings)
    return docs,terms,postings
def run(root,corpus,upstream,classpath,folder):
    assert subprocess.check_output(["git","-C",str(upstream),"rev-parse","HEAD"],text=True).strip()==PIN
    sql=sql_from_source(upstream)
    if corpus in ("gitdocs","k8sdocs"):
        events,m=h.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    else:
        sys.path.insert(0,str(HERE.parent/"round-131"));import budget_archive as old
        events,m=old.collect(root,corpus);frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    expected=json.loads(frozen.read_text());assert h.sha(h.canonical(m)).hex()==expected["manifest_sha256"]
    cut=m["cutoffs"];path=folder/"events.tsv"
    path.write_text("".join(f"{g}\t{encode(a.encode())}\t{encode(raw)}\n" for g,(a,i,raw) in enumerate(events,1)),encoding="utf8")
    java=folder/"java";java.mkdir()
    subprocess.run(["javac","-cp",classpath,"-d",str(java),str(HERE/"NativeReference.java")],check=True)
    subprocess.run(["java","-cp",str(java)+os.pathsep+classpath,"NativeReference",str(path),str(folder),",".join(map(str,cut))],check=True)
    queries=(folder/"queries.txt").read_text().splitlines()
    assert all(re.fullmatch("[a-z]{3,30}",q) for q in queries)
    native=collections.defaultdict(list)
    for line in (folder/"native.tsv").read_text().splitlines():
        c,q,n,s=line.split("\t");native[int(c),q].append((decode(n),float(s)))
    db=connect();cur=db.cursor()
    docs,terms,postings=load_data(cur,folder);db.commit()
    cur.execute("SELECT value FROM sys.env() WHERE name='monet_version'")
    version=cur.fetchall()
    comparisons=[];old_hashes={}
    for c in cut:
        active=sum(d[4]<=ts(c) and (d[5] is None or d[5]>ts(c)) for d in docs)
        for q in queries:
            # Replace only placeholders and the safe, single alphabetic term list.
            statement=sql.replace("%s","'"+q+"'").replace("?","%s")
            args=(active,ts(c),ts(c),ts(c),ts(c),ts(c),ts(c),10)
            start=time.perf_counter_ns();cur.execute(statement,args);got=[(str(n),float(s)) for n,s in cur.fetchall()]
            elapsed=(time.perf_counter_ns()-start)/1000
            want=native[c,q];a=[n for n,_ in got];b=[n for n,_ in want]
            intersection=set(a)&set(b);scores=dict(got);ref=dict(want)
            # Reproduce the upstream title concatenation commitment; NOT a source hash.
            digest=hashlib.md5("".join(a).encode()).hexdigest()
            old_hashes[c,q]=(got,digest)
            comparisons.append(dict(cutoff=c,query=q,rank_exact=a==b,overlap=len(intersection),
                native_hits=len(b),monet_hits=len(a),max_common_score_error=max((abs(scores[n]-ref[n]) for n in intersection),default=0.),
                query_us=elapsed,result_name_md5=digest))
    # Verify final-state database reproduces the same historical queries on repeat.
    for (c,q),(old,digest) in old_hashes.items():
        active=sum(d[4]<=ts(c) and (d[5] is None or d[5]>ts(c)) for d in docs)
        cur.execute(sql.replace("%s","'"+q+"'").replace("?","%s"),(active,*([ts(c)]*6),10))
        got=[(str(n),float(s)) for n,s in cur.fetchall()]
        assert got==old and hashlib.md5("".join(n for n,_ in got).encode()).hexdigest()==digest
    db.close()
    return dict(round=140,corpus=corpus,upstream_pin=PIN,upstream_sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
        manifest_sha256=expected["manifest_sha256"],lucene_version="8.4.1",monet_version=version,
        revisions=len(events),documents=len(m["retained_paths"]),dictionary=len(terms),postings=len(postings),
        queries_per_cutoff=len(queries),comparisons=len(comparisons),rank_exact=sum(x["rank_exact"] for x in comparisons),
        repeat_checks=len(old_hashes),query_us=h.quant([x["query_us"] for x in comparisons]),details=comparisons,
        limitations=["component-level upstream DAO SQL, not full TimIR service",
        "single alphabetic terms only; stable paths replace titles; actual Lucene StandardAnalyzer, not FTS5 unicode61",
        "synthetic generation timestamps; no direct cross-engine score equality required",
        "native Lucene rebuilt active index vs final-state MonetDB historical queries",
        "no full service storage/latency parity, exact source archive, or crash comparison"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--upstream",type=Path,required=True);p.add_argument("--classpath",required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as d:x=run(a.root,a.corpus,a.upstream,a.classpath,Path(d))
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
