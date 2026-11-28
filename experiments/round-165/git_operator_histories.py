"""R193: fixed R160 technical-document histories, signed operator paths."""
import argparse,json,sys,tempfile
from pathlib import Path
import operator_paths as op
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-131"))
sys.path.insert(0,str(HERE.parent/"round-132"))
import budget_archive
import heldout_archive

def run(root,corpus,folder,ext):
    if corpus in ("cpython","bips"):
        events,m=budget_archive.collect(root,corpus)
        frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    else:
        events,m=heldout_archive.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    manifest=op.h.sha(op.h.canonical(m)).hex()
    assert manifest==json.loads(frozen.read_text())["manifest_sha256"]
    assert m["cutoffs"][-1]==len(events)
    result=op.run(events,manifest,m["cutoffs"],folder,ext,corpus)
    result["pin"]=m["pin"];result["retained_paths"]=len(m["retained_paths"])
    result["changed_paths"]=m["changed_paths"]
    result["limitations"].append("same previously studied R160 first-parent path-touch cohorts; excluded deleted paths; not new independent corpora or transactional commit ingestion")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--corpus",choices=("cpython","bips","gitdocs","k8sdocs"),required=True)
    p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        x=run(a.root,a.corpus,Path(tmp),a.extension.resolve())
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
