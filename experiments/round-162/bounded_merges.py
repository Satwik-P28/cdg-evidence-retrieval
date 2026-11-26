"""R162: exact pair-merge objective with hard per-object byte budgets.
A maximum-weight matching is exact for disjoint merges on the current
candidate graph, not globally optimal packing.
"""
import argparse,hashlib,json,random,struct,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-161"))
from proof_pack import load,C,D,nx,sha,quant,MAX

def split_roots(graph):
    closures={n:set(nx.descendants(graph,n))|{n} for n in sorted(graph)}
    order=sorted(closures,key=lambda n:(len(closures[n]),n));rng=random.Random(162)
    train=[];test=[]
    for j in range(4):
        pool=order[j*len(order)//4:(j+1)*len(order)//4]
        rng.shuffle(pool);n=min(32,len(pool)//2)
        train.extend(pool[:n]);test.extend(pool[n:2*n])
    assert train and test and not set(train)&set(test)
    return closures,train,test

def masks(names,closures,roots):
    out=dict.fromkeys(names,0)
    for j,r in enumerate(roots):
        for n in closures[r]:out[n]|=1<<j
    return out

def weight(a,b,new,t,lambda_,mu):
    # Score multiplied by 100*t, all exact integers.
    ar,ac,am=a; br,bc,bm=b; nr,nc=new
    sm=(am|bm).bit_count()
    delta_c=nc*sm-ac*am.bit_count()-bc*bm.bit_count()
    delta_r=nr*sm-ar*am.bit_count()-br*bm.bit_count()
    delta_s=nc-ac-bc-24
    return -(100*t*delta_s+lambda_*delta_c+mu*delta_r)

def candidates(groups,graph,rawlen):
    owner={n:k for k,group in groups.items() for n in group}
    pairs=set()
    def add(a,b):
        if a!=b:pairs.add(tuple(sorted((a,b))))
    for a,b in graph.edges:add(owner[a],owner[b])
    for a in sorted(graph):
        deps=sorted(graph.successors(a))[:16]
        for i,u in enumerate(deps):
            for v in deps[i+1:]:add(owner[u],owner[v])
    for order in (sorted(groups,key=lambda k:min(groups[k])),
                  sorted(groups,key=lambda k:(rawlen[k],k))):
        for i,a in enumerate(order):
            for b in order[i+1:i+5]:add(a,b)
    return sorted(pairs)

def make(files,graph,mask,t,method,lam,mu):
    full={k:len(C.compress(v)) for k,v in files.items()}
    groups={i:(n,) for i,n in enumerate(sorted(files))}
    rawlen={i:len(files[n]) for i,(n,) in groups.items()}
    encoded={i:C.compress(files[n]) for i,(n,) in groups.items()}
    access={i:mask[n] for i,(n,) in groups.items()}
    nextid=len(groups);trace=[]
    for round_ in range(4):
        if method=="individual":break
        edges=nx.Graph();edges.add_nodes_from(sorted(groups));frames={}
        considered=feasible=0
        for a,b in candidates(groups,graph,rawlen):
            considered+=1;ns=groups[a]+groups[b];n=rawlen[a]+rawlen[b]
            if n>MAX or any(2*n>5*len(files[x]) for x in ns):continue
            # Test both orderings against the actual codec, keep smaller
            # frame; stable lexicographic tie handling.
            opts=[]
            for seq in (ns,groups[b]+groups[a]):
                frame=C.compress(b"".join(files[x] for x in seq))
                opts.append((len(frame),seq,frame))
            size,seq,frame=min(opts)
            if any(2*size>3*full[x] for x in ns):continue
            feasible+=1
            w=weight((rawlen[a],len(encoded[a]),access[a]),(rawlen[b],len(encoded[b]),access[b]),(n,size),t,lam,mu)
            if w>0:
                edges.add_edge(a,b,weight=w);frames[a,b]=(seq,frame,n,w)
        if method=="greedy":
            chosen=[];used=set()
            for a,b in sorted(frames,key=lambda p:(-frames[p][3],p)):
                if a not in used and b not in used:
                    chosen.append((a,b));used.update((a,b))
        else:chosen=sorted(tuple(sorted(x)) for x in nx.max_weight_matching(edges,weight="weight"))
        if not chosen:
            trace.append(dict(pass_=round_,considered=considered,feasible=feasible,merges=0));break
        gain=sum(frames[p][3] for p in chosen)
        trace.append(dict(pass_=round_,considered=considered,feasible=feasible,merges=len(chosen),objective_gain_scaled=gain))
        for a,b in chosen:
            seq,frame,n,w=frames[a,b];k=nextid;nextid+=1
            groups[k]=seq;rawlen[k]=n;encoded[k]=frame;access[k]=access[a]|access[b]
            for old in (a,b):
                del groups[old],rawlen[old],encoded[old],access[old]
    return groups,encoded,trace,full

def serialize(files,groups,encoded):
    # Same per-file and per-block directory record costs as R161,
    # plus a fixed 8-byte header charged equally in every arm.
    payload=bytearray();directory=bytearray(struct.pack(">II",len(files),len(groups)));records=[]
    for b,k in enumerate(sorted(groups)):
        off=len(payload);frame=encoded[k];payload.extend(frame);pos=0
        for name in groups[k]:
            raw=files[name];nb=name.encode()
            directory.extend(struct.pack(">I",len(nb))+nb+struct.pack(">IQQ",b,pos,len(raw))+hashlib.sha256(raw).digest())
            pos+=len(raw)
        records.append((off,len(frame),pos))
    directory.extend(b"".join(struct.pack(">QQQ",*m) for m in records))
    return bytes(payload),bytes(directory)

def parse(directory,payload):
    n,b=struct.unpack_from(">II",directory);pos=8;mapping={}
    for _ in range(n):
        length,=struct.unpack_from(">I",directory,pos);pos+=4
        name=directory[pos:pos+length].decode();pos+=length
        block,start,size=struct.unpack_from(">IQQ",directory,pos);pos+=20
        digest=directory[pos:pos+32];pos+=32
        assert name not in mapping and block<b and len(digest)==32
        mapping[name]=(block,start,size,digest)
    meta=[];end=0
    for _ in range(b):
        off,size,raw=struct.unpack_from(">QQQ",directory,pos);pos+=24
        assert off==end and size>0;end=off+size;meta.append((off,size,raw))
    assert pos==len(directory) and end==len(payload)
    for block,start,size,_ in mapping.values():assert start+size<=meta[block][2]
    return mapping,meta

def measure(files,payload,mapping,meta,closures,roots):
    ca=[];cd=[];checks=0
    for root in roots:
        want=closures[root];ids={mapping[x][0] for x in want};cache={}
        for i in ids:
            off,n,raw=meta[i];cache[i]=D.decompress(payload[off:off+n],max_output_size=raw+1)
        for x in want:
            i,off,n,digest=mapping[x];v=cache[i][off:off+n]
            assert hashlib.sha256(v).digest()==digest and v==files[x];checks+=1
        ca.append(sum(meta[i][1] for i in ids));cd.append(sum(meta[i][2] for i in ids))
    return dict(activated=quant(ca),decoded=quant(cd),checks=checks)

def run(root,corpus):
    files,g,external=load(root,corpus);closures,train,test=split_roots(g)
    mask=masks(files,closures,train);t=len(train);results={}
    for name,method,lam,mu in [("individual","individual",0,0),("greedy_storage","greedy",0,0),
           ("matching_storage","matching",0,0),("matching_balanced","matching",100,25),
           ("matching_readheavy","matching",500,100)]:
        start=time.perf_counter_ns();groups,encoded,trace,full=make(files,g,mask,t,method,lam,mu)
        payload,directory=serialize(files,groups,encoded);mapping,meta=parse(directory,payload)
        maxd=maxa=0.;checks=0
        for name_,(i,off,n,digest) in mapping.items():
            p,z,d=meta[i];raw=D.decompress(payload[p:p+z],max_output_size=d+1)[off:off+n]
            assert raw==files[name_] and hashlib.sha256(raw).digest()==digest
            assert 2*d<=5*n and 2*z<=3*full[name_]
            maxd=max(maxd,d/max(1,n));maxa=max(maxa,z/full[name_]);checks+=1
        build=(time.perf_counter_ns()-start)/1000
        tr=measure(files,payload,mapping,meta,closures,train);te=measure(files,payload,mapping,meta,closures,test)
        objective=100*t*(len(payload)+len(directory))+lam*tr["activated"]["total"]+mu*tr["decoded"]["total"]
        results[name]=dict(total_bytes=len(payload)+len(directory),payload_bytes=len(payload),directory_bytes=len(directory),
             blocks=len(meta),source_checks=checks,max_decode_ratio=maxd,max_activation_ratio=maxa,
             train=tr,test=te,lambda_scaled=lam,mu_scaled=mu,objective_scaled=objective,merge_trace=trace,build_us=build)
        print("ARM_JSON="+json.dumps(results[name]),flush=True)
    return dict(round=162,corpus=corpus,modules=len(files),edges=g.number_of_edges(),external_import_occurrences=external,
      manifest_sha256=sha(json.dumps([(n,sha(files[n])) for n in sorted(files)]).encode()),
      train_roots=len(train),test_roots=len(test),train_sha256=sha(json.dumps(train).encode()),test_sha256=sha(json.dumps(test).encode()),
      policies=results,limitations=["syntactic local imports only; held-out roots in same graph, not independent workload or repository",
      "candidate generation sees structural graph, but objective uses training root access masks only",
      "maximum-weight matching optimizes disjoint merges per pass over restricted candidate graph, not global partitioning",
      "exact logical compressed/decoded bounds, not physical IO or transaction contract",
      "actual in-memory serialized pack and directory, no historical retrieval or index",
      "weights fixed before results; no claim novelty for matching or graph packing"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=("grh","grh-compact","masullo"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
