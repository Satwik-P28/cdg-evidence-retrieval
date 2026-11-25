"""R149: source-only causal frame-cost / exact-recipe / resemblance ablation.

No transactional or complete archive claim: new cross-article references
require a different physical schema. All policies store and decode actual
Zstandard frames and preserve the R148 byte constraints.
"""
import argparse,collections,dataclasses,heapq,json,re,sys,tempfile,time,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-138"))
import news_retrieval as nr
import heldout_archive as h
from anchor_bench import D,delta_decode

POLICIES=("snapshot","baseline","marginal","recipe","recipe_sketch")
CATALOG_PROXY=48
@dataclasses.dataclass(frozen=True)
class Recipe:
    parent:int
    frame:bytes
    decoded:int
    activated:int

def features(raw):
    # Deterministic bounded sketch; evenly sample up to 128 token trigrams.
    words=re.findall(rb"\w+",raw.lower())
    n=len(words)-2
    if n<=0:return ()
    stride=max(1,(n+127)//128)
    return tuple(heapq.nsmallest(4,{zlib.crc32(b" ".join(words[i:i+3])) for i in range(0,n,stride)}))

def encode(events,policy,proxy=CATALOG_PROXY):
    histories=collections.defaultdict(list)
    recipes=[None];frames={};best={};buckets=collections.defaultdict(lambda:collections.deque(maxlen=8))
    stats=collections.Counter();maxd=maxa=0.;fingerprint=__import__("hashlib").sha256()
    t0=time.perf_counter()
    for g,(article,i,raw) in enumerate(events,1):
        local=histories[article];assert len(local)==i
        full=h.C.compress(raw);literal=Recipe(0,full,len(raw),len(full));choice=literal
        key=h.sha(raw);sketch=features(raw) if policy=="recipe_sketch" else ()
        def raw_at(j):return events[j-1][2]
        def candidate(j):
            old=raw_at(j);base=recipes[j]
            assert j<g and base.parent==0
            if 2*(len(old)+len(raw))>5*len(raw):return None
            diff=h.delta_encode(raw,old);stats["delta_attempts"]+=1
            if diff is None or 5*len(diff)>4*len(full) or 2*(len(base.frame)+len(diff))>3*len(full):return None
            return Recipe(j,diff,len(old)+len(raw),len(base.frame)+len(diff))
        def frame_cost(c):
            stored=frames.get(h.sha(c.frame))
            if stored is not None:
                assert stored==c.frame
                return 0
            return len(c.frame)+proxy
        def score(c):
            return (frame_cost(c),c.decoded,c.activated,len(c.frame),-c.parent)
        if policy=="baseline":
            hist=[(raw_at(j),len(recipes[j].frame),int(recipes[j].parent!=0)) for j in local]
            parent,depth,frame=h.choose_config(raw,i,hist,"bounded_anchor")
            if depth:
                j=local[parent];choice=Recipe(j,frame,len(raw)+len(raw_at(j)),len(frame)+len(recipes[j].frame))
        elif policy!="snapshot":
            local_candidates=[j for j in reversed(local) if recipes[j].parent==0][:4]
            choices=[literal]
            candidates=list(local_candidates)
            if policy=="recipe_sketch":
                hits=collections.Counter(j for f in sketch for j in buckets[f] if events[j-1][0]!=article)
                candidates+=sorted(hits,key=lambda j:(-hits[j],-j))[:4]
            for j in dict.fromkeys(candidates):
                c=candidate(j)
                if c is not None:choices.append(c)
            if policy in ("recipe","recipe_sketch") and key in best:
                oldg=best[key];assert raw_at(oldg)==raw
                previous=recipes[oldg]
                assert previous.parent<g
                choices.append(previous);stats["exact_recipe_opportunities"]+=1
            choice=min(choices,key=score)
            if choice.parent and events[choice.parent-1][0]!=article:stats["cross_article_deltas"]+=1
            if frame_cost(choice)==0:stats["zero_incremental_choices"]+=1
        digest=h.sha(choice.frame)
        if digest in frames:
            assert frames[digest]==choice.frame;stats["reused_frames"]+=1
        else:frames[digest]=choice.frame
        if choice.parent:
            j=choice.parent;assert 0<j<g and recipes[j].parent==0
            anchor=D.decompress(recipes[j].frame,max_output_size=len(raw_at(j))+1)
            assert anchor==raw_at(j)
            reconstructed=delta_decode(choice.frame,anchor,len(raw))
            assert 2*choice.decoded<=5*len(raw) and 2*choice.activated<=3*len(full)
            assert 5*len(choice.frame)<=4*len(full)
            stats["deltas"]+=1
        else:
            reconstructed=D.decompress(choice.frame,max_output_size=len(raw)+1)
            stats["literals"]+=1
            if policy=="recipe_sketch":
                for f in sketch:buckets[f].append(g)
        assert reconstructed==raw
        recipes.append(choice);local.append(g)
        if key in best:assert raw_at(best[key])==raw
        if key not in best or (choice.decoded,choice.activated,len(choice.frame))<(recipes[best[key]].decoded,recipes[best[key]].activated,len(recipes[best[key]].frame)):
            best[key]=g
        stats["raw_bytes"]+=len(raw);stats["decoded_bytes"]+=choice.decoded;stats["activated_bytes"]+=choice.activated
        if raw:maxd=max(maxd,choice.decoded/len(raw))
        maxa=max(maxa,choice.activated/len(full))
        fingerprint.update(h.canonical([g,choice.parent,digest.hex()]));fingerprint.update(b"\n")
    payload=sum(map(len,frames.values()))
    return dict(policy=policy,revisions=len(events),unique_frames=len(frames),unique_source_objects=len(best),
        payload_bytes=payload,catalog_proxy_bytes=proxy*len(frames),payload_plus_catalog_proxy=payload+proxy*len(frames),
        mean_decode_ratio=stats["decoded_bytes"]/max(1,stats["raw_bytes"]),max_decode_ratio=maxd,max_activation_ratio=maxa,
        elapsed_s=time.perf_counter()-t0,recipe_sha256=fingerprint.hexdigest(),**stats)

def run(source,target,order,folder):
    events,_,manifest=nr.load(source,target,folder);n=len(events)
    old=json.loads((HERE.parent/"round-142"/("results-"+str(n)+".json")).read_text())
    assert old["manifest_sha256"]==manifest["source_manifest_sha256"]
    if order=="reordered":
        # Alternative causal interleaving, preserving every article's ordinals.
        events=sorted(events,key=lambda x:(x[1],h.sha(("R149-order|"+x[0]).encode())))
    results={}
    for policy in POLICIES:
        x=encode(events,policy);results[policy]=x
        print("POLICY_JSON="+json.dumps(x),flush=True)
    if order=="original":
        for p,q in [("snapshot","snapshot_coalesced"),("baseline","bounded_anchor_coalesced")]:
            assert results[p]["payload_bytes"]==old["policies"][q]["payload_bytes"]
            assert results[p]["unique_frames"]==old["policies"][q]["unique_frames"]
            assert results[p]["mean_decode_ratio"]==old["policies"][q]["mean_decode_ratio"]
    return dict(round=149,revisions=n,order=order,manifest_sha256=manifest["source_manifest_sha256"],
        event_order_sha256=h.sha(h.canonical([(a,i) for a,i,_ in events])).hex(),policies=results,
        limitations=["source-only, actual encoded frames but catalog cost is proxy (48 B per distinct frame)",
          "no new physical archive, ranking, transactional or latency guarantee",
          "global exact recipe and sketch arms use global generation anchor IDs, not original local ordinals",
          "causal ordering synthetic, nested AP cohorts not independent",
          "sketch is a simple bounded resemblance heuristic, not a reproduced MeGA/LoopDelta implementation",
          "current greedy incremental-cost choice does not prove global optimality"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--target",type=int,required=True);p.add_argument("--order",choices=("original","reordered"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:x=run(a.source,a.target,a.order,Path(tmp))
    a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
