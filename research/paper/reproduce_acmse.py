"""Independent reproduction entrypoint for ACMSE core experiments.
Run from a clean checkout on Linux after installing pinned dependencies.
Keep raw logs and report; no matching timing requirement.
"""
import argparse,hashlib,json,platform,sqlite3,subprocess,sys,time
from pathlib import Path
import zstandard
ROOT=Path(__file__).resolve().parents[2]
EXPS=ROOT/"experiments"
SCRIPTS={148:"matched_final.py",151:"joint_archive.py",153:"fair_receipt.py",159:"physical_io.py"}
FIELDS={148:("total_archive_bytes","source_payload_bytes","unique_frames","source_reads","rank_checks","batch_receipts","mean_decode_ratio","max_decode_ratio","max_activation_ratio","receipt_commitments_sha256","max_score_error"),
151:("total_archive_bytes","payload_bytes","unique_frames","index_rows","source_reads","rank_checks","batch_receipts","mean_decode_ratio","max_decode_ratio","max_activation_ratio","max_score_error"),
153:("rank_checks","max_score_error"),
159:("total_archive_bytes","source_payload_bytes","source_checks","rank_checks","receipt_checks")}
SOURCE_SHA="005cf42b35f6b42700e16bf69d9a9e7cbd541d74faa0cd3b4c5b666e5c319e1e"

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def compare(reference,actual,round_):
    mismatches=[]
    def check(label,a,b):
        if a!=b:mismatches.append(dict(field=label,reference=a,actual=b))
    for key in ("round","revisions","manifest_sha256"):
        check(key,reference[key],actual[key])
    check("policies",sorted(reference["policies"]),sorted(actual["policies"]))
    for name in set(reference["policies"])&set(actual["policies"]):
        for key in FIELDS[round_]:
            check(name+"."+key,reference["policies"][name][key],actual["policies"][name][key])
    return mismatches

def command(argv,log):
    print("RUN",argv,flush=True)
    with log.open("w") as f:
        result=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=False)
    return result.returncode

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--target",type=int,choices=(10000,100000),default=10000)
    p.add_argument("--rounds",type=int,nargs="+",choices=tuple(SCRIPTS),default=list(SCRIPTS))
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    source=a.source.resolve();source_sha=digest(source)
    if source_sha!=SOURCE_SHA:raise SystemExit("source digest mismatch: "+source_sha)
    n=10009 if a.target==10000 else 74364
    extension=out/"cdgfts.so"
    git_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    report=dict(git_head=git_head,source_sha256=source_sha,target=a.target,
        environment=dict(python=sys.version,sqlite=sqlite3.sqlite_version,zstandard=zstandard.__version__,
            platform=platform.platform(),machine=platform.machine(),compiler=subprocess.check_output(["cc","--version"],text=True).splitlines()[0]),
        results={},limitations=["not independent until executed by a person outside the original experiment",
        "deterministic fields exact; file sizes may differ with SQLite/codec versions and are reported as discrepancies, not silently ignored",
        "timing, allocated bytes, kernel IO counters and cache behavior deliberately not equality gates"])
    def save(): (out/"reproduction-report.json").write_text(json.dumps(report,indent=2)+"\n")
    rc=command(["cc","-O3","-Wall","-Wextra","-Werror","-shared","-fPIC",str(EXPS/"round-118/cdgfts.c"),"-o",str(extension)],out/"compile.log")
    if rc:report["compile_exit"]=rc;save();return 1
    for r in a.rounds:
        ref=EXPS/("round-"+str(r))/("results-"+str(n)+".json")
        if not ref.exists():
            report["results"][str(r)]=dict(status="reference_not_archived",path=str(ref));save();continue
        output=out/("round-"+str(r)+".json")
        start=time.perf_counter()
        argv=[sys.executable,str(EXPS/("round-"+str(r))/SCRIPTS[r]),"--source",str(source),"--target",str(a.target),"--extension",str(extension),"--out",str(output)]
        rc=command(argv,out/("round-"+str(r)+".log"))
        result=dict(exit_code=rc,elapsed_s=time.perf_counter()-start,reference_sha256=digest(ref),command=argv)
        if rc==0 and output.exists():
            differences=compare(json.loads(ref.read_text()),json.loads(output.read_text()),r)
            result.update(status="match" if not differences else "mismatch",differences=differences,result_sha256=digest(output))
        else:result["status"]="execution_failed"
        report["results"][str(r)]=result;save()
    return 0 if all(x["status"]=="match" for x in report["results"].values()) and report["results"] else 1

if __name__=="__main__":raise SystemExit(main())
