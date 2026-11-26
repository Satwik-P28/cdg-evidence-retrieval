"""R163: exact activation-aware dictionary client selection by min cut.
Offline finalized source archive; independently compressed dictionary facilities.
"""
import argparse,collections,hashlib,json,random,struct,sys,time
from pathlib import Path
import zstandard as zstd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-162"))
from bounded_merges import split_roots,masks,load,C,D,nx,sha,quant

# Common source record: name length/name, raw len, dictionary id,
# frame offset/length, source SHA256; dict record: raw len, frame
# offset/length, SHA256. Charge all metadata.
DICT_META=56
SIZES=(256,1024,4096)

def samples(files,names,seed):
    rng=random.Random(seed);out=[]
    for name in sorted(names):
        v=files[name]
        if len(v)<32:continue
        starts=list(range(0,len(v),512))
        for j in rng.sample(starts,min(8,len(starts))):
            x=v[j:j+512]
            if len(x)>=32:out.append(x)
    rng.shuffle(out)
    return out[:2048]

def candidates(files,g,full):
    groups=[("global",set(files))]
    bypath=collections.defaultdict(set)
    for n in files:bypath[".".join(n.split(".")[:2])].add(n)
    groups.extend(("path:"+k,v) for k,v in sorted(bypath.items(),key=lambda x:(-len(x[1]),x[0]))[:12] if len(v)>=8)
    communities=nx.community.louvain_communities(g.to_undirected(),seed=163)
    groups.extend(("graph:"+min(v),v) for v in sorted(communities,key=lambda v:(-len(v),min(v)))[:12] if len(v)>=8)
    out=[];seen=set();failures=0
    for group,names in groups:
        data=samples(files,names,163)
        for size in SIZES:
            if sum(map(len,data))<size*8:continue
            try:dictionary=zstd.train_dictionary(size,data,threads=1)
            except zstd.ZstdError:failures+=1;continue
            raw=dictionary.as_bytes();key=sha(raw)
            if key in seen:continue
            seen.add(key);stored=C.compress(raw)
            comp=zstd.ZstdCompressor(level=9,dict_data=dictionary)
            decomp=zstd.ZstdDecompressor(dict_data=dictionary)
            eligible={}
            for n in sorted(names):
                src=files[n];f=full[n]
                if 2*(len(src)+len(raw))>5*len(src):continue
                frame=comp.compress(src)
                if len(frame)>=len(f) or 2*(len(stored)+len(frame))>3*len(f):continue
                assert decomp.decompress(frame,max_output_size=len(src)+1)==src
                eligible[n]=frame
            if eligible:out.append(dict(group=group,raw=raw,stored=stored,frames=eligible))
    return out,failures

def cut_clients(weights,access,penalty):
    """Exact best subset for one fixed opening, ignoring its constant cost.
    Positive client weight; activating a query node costs penalty once.
    Source-side closure under infinite client->query edges.
    """
    if not weights:return [],0
    if penalty==0:return sorted(weights),sum(weights.values())
    net=nx.DiGraph();source=("s",);sink=("t",)
    net.add_nodes_from((source,sink));infinity=sum(weights.values())+1
    for n,w in sorted(weights.items()):
        node=("c",n);net.add_edge(source,node,capacity=w);bits=access[n]
        while bits:
            bit=bits&-bits;bits-=bit;q=("q",bit.bit_length()-1)
            net.add_edge(node,q,capacity=infinity)
            if not net.has_edge(q,sink):net.add_edge(q,sink,capacity=penalty)
    value,(left,_)=nx.minimum_cut(net,source,sink,capacity="capacity")
    chosen=sorted(n for n in weights if ("c",n) in left)
    union=0
    for n in chosen:union|=access[n]
    gain=sum(weights[n] for n in chosen)-penalty*union.bit_count()
    assert gain==sum(weights.values())-value
    return chosen,gain

def choose(cands,full,access,t,method,lam,mu):
    available=set(full);opened=[];assignment={};trace=[]
    scale=100*t
    for _ in range(32):
        best=None
        for i,d in enumerate(cands):
            if method=="global" and d["group"]!="global":continue
            if i in opened:continue
            weights={n:(len(full[n])-len(f))*(scale+lam*access[n].bit_count())
                     for n,f in d["frames"].items() if n in available}
            penalty=lam*len(d["stored"])+mu*len(d["raw"])
            if method=="all_clients":
                clients=sorted(weights);union=0
                for n in clients:union|=access[n]
                benefit=sum(weights.values())-penalty*union.bit_count()
            else:clients,benefit=cut_clients(weights,access,penalty)
            gain=benefit-scale*(len(d["stored"])+DICT_META)
            if gain>0 and (best is None or (gain,-i)>(best[0],-best[1])):
                best=(gain,i,clients)
        if best is None:break
        gain,i,clients=best;opened.append(i)
        for n in clients:assignment[n]=i;available.remove(n)
        trace.append(dict(candidate=i,group=cands[i]["group"],dictionary_raw_bytes=len(cands[i]["raw"]),clients=len(clients),gain_scaled=gain))
    return opened,assignment,trace

def serialize(files,full,cands,opened,assignment):
    payload=bytearray();directory=bytearray(struct.pack(">II",len(files),len(opened)))
    ids={x:i+1 for i,x in enumerate(opened)};dict_records=[]
    for i in opened:
        d=cands[i];p=len(payload);payload.extend(d["stored"])
        dict_records.append(struct.pack(">QQQ",len(d["raw"]),p,len(d["stored"]))+hashlib.sha256(d["raw"]).digest())
    for name in sorted(files):
        raw=files[name];nb=name.encode();i=assignment.get(name)
        frame=full[name] if i is None else cands[i]["frames"][name]
        p=len(payload);payload.extend(frame)
        directory.extend(struct.pack(">I",len(nb))+nb+struct.pack(">QIQQ",len(raw),0 if i is None else ids[i],p,len(frame))+hashlib.sha256(raw).digest())
    directory.extend(b"".join(dict_records))
    return bytes(payload),bytes(directory)

def parse(payload,dir_):
    n,k=struct.unpack_from(">II",dir_);p=8;files={};dicts={}
    for _ in range(n):
        z,=struct.unpack_from(">I",dir_,p);p+=4
        name=dir_[p:p+z].decode();p+=z
        raw,i,off,size=struct.unpack_from(">QIQQ",dir_,p);p+=28
        digest=dir_[p:p+32];p+=32
        assert name not in files and i<=k and off+size<=len(payload)
        files[name]=(raw,i,off,size,digest)
    for i in range(1,k+1):
        raw,off,size=struct.unpack_from(">QQQ",dir_,p);p+=24
        digest=dir_[p:p+32];p+=32
        assert off+size<=len(payload)
        dicts[i]=(raw,off,size,digest)
    assert p==len(dir_)
    ranges=sorted((off,off+size) for raw,i,off,size,digest in files.values())+[]
    ranges=sorted(ranges+[(off,off+size) for raw,off,size,digest in dicts.values()])
    end=0
    for a,b in ranges:assert a==end and b>a;end=b
    assert end==len(payload)
    return files,dicts

def recover(payload,record,dicts,cache):
    n,i,off,size,digest=record
    if i:
        if i not in cache:
            raw,p,z,d=dicts[i]
            dictionary=D.decompress(payload[p:p+z],max_output_size=raw+1)
            assert len(dictionary)==raw and hashlib.sha256(dictionary).digest()==d
            cache[i]=zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(dictionary))
        codec=cache[i]
    else:codec=D
    data=codec.decompress(payload[off:off+size],max_output_size=n+1)
    assert len(data)==n and hashlib.sha256(data).digest()==digest
    return data

def measure(payload,records,dicts,files,closures,roots):
    activated=[];decoded=[];checks=0;times=[]
    for root in roots:
        want=closures[root];used=set();a=d=0;cache={};start=time.perf_counter_ns()
        for name in sorted(want):
            row=records[name];n,i,_,size,_=row
            assert recover(payload,row,dicts,cache)==files[name];checks+=1
            a+=size;d+=n
            if i and i not in used:
                raw,_,z,_=dicts[i];a+=z;d+=raw;used.add(i)
        times.append((time.perf_counter_ns()-start)/1000);activated.append(a);decoded.append(d)
    return dict(activated=quant(activated),decoded=quant(decoded),checks=checks,read_us=quant(times))

def run(root,corpus):
    files,g,external=load(root,corpus);closures,train,test=split_roots(g)
    access=masks(files,closures,train);t=len(train)
    full={n:C.compress(v) for n,v in files.items()}
    start=time.perf_counter_ns();cands,failures=candidates(files,g,full);candidate_us=(time.perf_counter_ns()-start)/1000
    results={}
    for name,method,lam,mu in [("individual","none",0,0),("global_storage","global",0,0),
        ("facility_storage","cut",0,0),("all_clients_balanced","all_clients",100,25),
        ("cut_balanced","cut",100,25),("cut_readheavy","cut",500,100)]:
        start=time.perf_counter_ns()
        opened,assignment,trace=([],{},[]) if method=="none" else choose(cands,full,access,t,method,lam,mu)
        payload,dir_=serialize(files,full,cands,opened,assignment);records,dicts=parse(payload,dir_)
        maxd=maxa=0.
        for n,row in records.items():
            raw,i,_,size,_=row;extra,p,z,digest=dicts[i] if i else (0,0,0,b"")
            assert recover(payload,row,dicts,{})==files[n]
            assert 2*(raw+extra)<=5*raw and 2*(size+z)<=3*len(full[n])
            maxd=max(maxd,(raw+extra)/max(1,raw));maxa=max(maxa,(size+z)/len(full[n]))
        tr=measure(payload,records,dicts,files,closures,train);te=measure(payload,records,dicts,files,closures,test)
        total=len(payload)+len(dir_);objective=100*t*total+lam*tr["activated"]["total"]+mu*tr["decoded"]["total"]
        base_a=sum(len(full[n])*access[n].bit_count() for n in files)
        base_d=sum(len(files[n])*access[n].bit_count() for n in files)
        # Opening gains must telescope to exact serialized objective.
        base_size=sum(len(v) for v in full.values())+len(dir_)-DICT_META*len(dicts)
        assert 100*t*base_size+lam*base_a+mu*base_d-objective==sum(x["gain_scaled"] for x in trace)
        results[name]=dict(total_bytes=total,payload_bytes=len(payload),directory_bytes=len(dir_),dictionaries=len(dicts),
            clients=len(assignment),dictionary_stored_bytes=sum(x[2] for x in dicts.values()),max_decode_ratio=maxd,max_activation_ratio=maxa,
            source_checks=len(records),train=tr,test=te,objective_scaled=objective,trace=trace,
            elapsed_us=(time.perf_counter_ns()-start)/1000)
        print("ARM_JSON="+json.dumps(results[name]),flush=True)
    return dict(round=163,corpus=corpus,modules=len(files),edges=g.number_of_edges(),external_import_occurrences=external,
      manifest_sha256=sha(json.dumps([(n,sha(files[n])) for n in sorted(files)]).encode()),
      train_sha256=sha(json.dumps(train).encode()),test_sha256=sha(json.dumps(test).encode()),candidate_count=len(cands),
      training_failures=failures,candidate_us=candidate_us,policies=results,limitations=[
      "offline finalized archive, dictionary training sees source collection, held-out query roots only",
      "cold per-object dictionary bytes charged, per-query dictionary reuse exactly once, no OS cache assumption",
      "candidate dictionaries from global/path/graph groups, fixed sample/size, no global optimization",
      "min-cut is exact for one candidate and remaining unassigned clients; greedy openings irreversible",
      "syntactic local imports, not kernel-certified theorem dependency graph; no historical retrieval or transaction guarantee",
      "no new dictionary codec claim; logical byte work not physical IO"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=("grh","grh-compact","masullo"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
