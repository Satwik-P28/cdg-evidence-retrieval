"""Restricted latest-literal offline optimum, source payload only."""
import argparse,collections,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"round-132"))
from heldout_archive import C,delta_encode,collect,canonical,sha

def solve(full,edge):
    if not full:return 0
    states={0:full[0]}
    for t in range(1,len(full)):
        next_states={t:min(states.values())+full[t]}
        for j,v in states.items():
            d=edge(j,t)
            if d is not None:next_states[j]=v+d
        states=next_states
    return min(states.values())

def greedy(full,edge):
    if not full:return 0
    anchor=0;cost=full[0]
    for t in range(1,len(full)):
        d=edge(anchor,t)
        if d is None:anchor=t;cost+=full[t]
        else:cost+=d
    return cost

def evaluate(events):
    histories=collections.defaultdict(list)
    for a,i,raw in events:
        assert len(histories[a])==i
        histories[a].append(raw)
    result=[];calls=0
    for a,vs in histories.items():
        fs=[len(C.compress(v)) for v in vs]
        cache={}
        def edge(j,t):
            nonlocal calls
            if (j,t) not in cache:
                calls+=1
                old,raw=vs[j],vs[t];d=None
                if 2*(len(old)+len(raw))<=5*len(raw):
                    p=delta_encode(raw,old)
                    if p is not None and 5*len(p)<=4*fs[t] and 2*(fs[j]+len(p))<=3*fs[t]:d=len(p)
                cache[j,t]=d
            return cache[j,t]
        g=greedy(fs,edge);o=solve(fs,edge)
        assert o<=g<=sum(fs)
        result.append(dict(path=a,revisions=len(vs),snapshot=sum(fs),greedy=g,offline=o))
    sums={k:sum(x[k] for x in result) for k in ("revisions","snapshot","greedy","offline")}
    return dict(**sums,documents=len(result),improved_documents=sum(x["offline"]<x["greedy"] for x in result),candidate_checks=calls,per_document=result)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    events,manifest=collect(a.root,a.corpus,window=800,cohort=160)
    frozen=json.loads((Path(__file__).resolve().parent.parent/"round-132"/("results-"+a.corpus+"-800-132.json")).read_text())
    assert sha(canonical(manifest)).hex()==frozen["manifest_sha256"]
    result=evaluate(events)
    assert result["greedy"]==frozen["result"]["policies"]["k1"]["payload_bytes"]
    out=dict(corpus=a.corpus,manifest_sha256=frozen["manifest_sha256"],scope="source payload only; offline latest-literal optimum",result=result)
    a.out.write_text(json.dumps(out,indent=2)+"\n")
    print("ORACLE_JSON="+json.dumps(out),flush=True)
