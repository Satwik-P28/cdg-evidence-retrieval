"""Source-only VCDIFF control. No SQLite/index or latency claims."""
import argparse,json,random,subprocess,tempfile
from pathlib import Path
from budget_archive import collect,C,sha,canonical

def vcdiff(base,body,decode=False):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d);(p/"base").write_bytes(base);(p/"input").write_bytes(body)
        cmd=["xdelta3","-f","-d" if decode else "-e","-s",str(p/"base"),str(p/"input"),str(p/"out")]
        subprocess.run(cmd,check=True,capture_output=True)
        return (p/"out").read_bytes()

def screen(events,depth_cap):
    histories={};total=decoded=activated=raw_bytes=0;max_depth=0;max_decode=1.;max_activation=1.
    for a,i,raw in events:
        h=histories.setdefault(a,[])
        assert len(h)==i
        full=C.compress(raw);parent=None;depth=0;payload=full
        if h and h[-1][2]<depth_cap and h[-1][0] and raw:
            diff=vcdiff(h[-1][0],raw)
            if len(diff)<len(full):
                parent=i-1;depth=h[-1][2]+1;payload=diff
        h.append((raw,payload,depth,parent))
        def recover(j):
            want,data,dep,par=h[j]
            if par is None:
                import zstandard
                got=zstandard.ZstdDecompressor().decompress(data);ab=len(data);db=len(got)
            else:
                old,ab,db=recover(par)
                got=vcdiff(old,data,True);ab+=len(data);db+=len(got)
            assert got==want
            return got,ab,db
        got,ab,db=recover(i)
        assert got==raw
        total+=len(payload);decoded+=db;activated+=ab;raw_bytes+=len(raw);max_depth=max(max_depth,depth)
        max_decode=max(max_decode,db/max(1,len(raw)));max_activation=max(max_activation,ab/len(full))
    return dict(payload_bytes=total,decode_amplification=decoded/max(1,raw_bytes),activated_payload_bytes=activated,
                max_depth=max_depth,max_decode_ratio=max_decode,max_activation_ratio=max_activation,source_reads=len(events))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    events,manifest=collect(a.root,a.corpus)
    frozen=json.loads((Path(__file__).resolve().parent.parent/"round-129"/("results-"+a.corpus+".json")).read_text())
    assert sha(canonical(manifest)).hex()==frozen["manifest_sha256"]
    result=dict(corpus=a.corpus,manifest_sha256=frozen["manifest_sha256"],scope="source payload only; Zstd snapshots, xdelta3 VCDIFF deltas; no latency or full archive claim",
                xdelta_version=subprocess.run(["xdelta3","-V"],capture_output=True,text=True).stderr,
                policies={str(k):screen(events,k) for k in (0,1,4,8)})
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print("VCDIFF_JSON="+json.dumps(result),flush=True)
