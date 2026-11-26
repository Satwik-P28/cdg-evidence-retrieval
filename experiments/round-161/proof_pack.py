"""R161: dependency-aware block packing of real proof-source repositories.
Import graph is a syntactic approximation, not a theorem dependency certificate.
"""
import argparse,hashlib,json,random,re,struct,time
from pathlib import Path
import networkx as nx
import zstandard as zstd

C=zstd.ZstdCompressor(level=9);D=zstd.ZstdDecompressor()
MAX=131072
PINS={"grh":"72fead102f663d5c7a407964a13dc0cf9d977207","masullo":"ca6e92b821abdbb36ba7aadb97bd2e2400dff9f7"}
IMPORT=re.compile(r"^\s*(?:(?:public|private|meta)\s+)*import\s+([\w.]+)",re.M)

def sha(x):return hashlib.sha256(x).hexdigest()

def load(root,corpus):
    if corpus.startswith("grh"):
        base=root/("grh-compact" if corpus=="grh-compact" else "grh")/"src"
    else:base=root
    files={str(p.relative_to(base).with_suffix("")).replace("/","."):p.read_bytes()
           for p in sorted(base.rglob("*.lean")) if ".lake" not in p.parts}
    graph=nx.DiGraph();graph.add_nodes_from(files)
    external=0
    # Best-effort header import extraction: remove nested block comments,
    # line comments; recognize import syntax; unresolved imports recorded.
    for name,raw in files.items():
        s=raw.decode("utf8");clean=[];i=depth=0
        while i<len(s):
            if s[i:i+2]=="/-":depth+=1;i+=2
            elif depth and s[i:i+2]=="-/":depth-=1;i+=2
            elif depth:
                if s[i]=="\n":clean.append("\n")
                i+=1
            elif s[i:i+2]=="--":
                n=s.find("\n",i);i=len(s) if n<0 else n
            else:clean.append(s[i]);i+=1
        for dep in IMPORT.findall("".join(clean)):
            if dep in files:graph.add_edge(name,dep)
            else:external+=1
    assert files and graph.number_of_edges()>0
    assert nx.is_directed_acyclic_graph(graph),"approximate import graph cycle"
    return files,graph,external

def block_order(files,g,mode):
    names=sorted(files)
    if mode=="random":random.Random(161).shuffle(names)
    elif mode=="topological":names=list(nx.lexicographical_topological_sort(g.reverse(copy=False)))
    elif mode in ("louvain","closure_affinity"):
        ug=g.to_undirected()
        if mode=="closure_affinity":
            # Add bounded co-use edges from immediate sibling imports only.
            # Structural, not evaluated-query-trained.
            for node in sorted(g):
                deps=sorted(g.successors(node))[:16]
                for i,a in enumerate(deps):
                    for b in deps[i+1:]:
                        if ug.has_edge(a,b):ug[a][b]["weight"]=ug[a][b].get("weight",1)+1
                        else:ug.add_edge(a,b,weight=1)
        communities=nx.community.louvain_communities(ug,seed=161,weight="weight")
        names=[]
        for group in sorted(communities,key=lambda x:(-len(x),min(x))):
            # Stable intra-community dependency order.
            names.extend(nx.lexicographical_topological_sort(g.subgraph(group).reverse(copy=False)))
    assert set(names)==set(files) and len(names)==len(files)
    return names

def build(files,g,mode,cap):
    order=block_order(files,g,mode);blocks=[];cur=[];size=0
    for name in order:
        n=len(files[name])
        if cur and (size+n>cap or mode=="individual"):
            blocks.append(cur);cur=[];size=0
        cur.append(name);size+=n
    if cur:blocks.append(cur)
    # Actual pack bytes plus binary directory (one identical record per
    # file and one offset/length record per block). Name and digest charged.
    payload=bytearray();directory=bytearray();mapping={};meta=[]
    for k,group in enumerate(blocks):
        raw=b"".join(files[name] for name in group);frame=C.compress(raw)
        off=len(payload);payload.extend(frame);meta.append((off,len(frame),len(raw)))
        offset=0
        for name in group:
            v=files[name];nb=name.encode()
            directory.extend(struct.pack(">I",len(nb))+nb+struct.pack(">IQQ",k,offset,len(v))+hashlib.sha256(v).digest())
            mapping[name]=(k,offset,len(v));offset+=len(v)
        assert len(raw)<=cap or len(group)==1
    directory.extend(b"".join(struct.pack(">QQQ",*m) for m in meta))
    # Verify exact source recovery from packed frames after serialization.
    checks=0
    for k,group in enumerate(blocks):
        off,n,rawsize=meta[k];raw=D.decompress(bytes(payload[off:off+n]),max_output_size=rawsize+1)
        for name in group:
            _,start,length=mapping[name];assert raw[start:start+length]==files[name];checks+=1
    return bytes(payload),bytes(directory),mapping,meta,checks

def quant(xs):
    s=sorted(xs);return dict(median=s[len(s)//2],p95=s[int(.95*(len(s)-1))],max=s[-1],total=sum(s))

def run(root,corpus):
    files,g,external=load(root,corpus)
    # Fixed roots sampled across closure-size strata; identical for every arm.
    closures={n:set(nx.descendants(g,n))|{n} for n in sorted(g)}
    ranked=sorted(closures,key=lambda n:(len(closures[n]),n));rng=random.Random(161)
    roots=[]
    for i in range(4):
        pool=ranked[i*len(ranked)//4:(i+1)*len(ranked)//4]
        roots+=rng.sample(pool,min(32,len(pool)))
    results={};baseline=None
    for mode,cap in [("individual",MAX),("random",MAX),("path",MAX),("topological",MAX),
                     ("louvain",MAX),("closure_affinity",MAX),("closure_affinity_32k",32768)]:
        start=time.perf_counter_ns()
        payload,directory,mapping,meta,checks=build(files,g,mode.replace("_32k",""),cap)
        build_us=(time.perf_counter_ns()-start)/1000
        ca=[];cd=[];sa=[];sd=[];counts=[];read_us=[]
        for n in roots:
            want=closures[n];ids={mapping[k][0] for k in want};counts.append(len(ids))
            ca.append(sum(meta[i][1] for i in ids));cd.append(sum(meta[i][2] for i in ids))
            k=mapping[n][0];sa.append(meta[k][1]);sd.append(meta[k][2])
            # Actual batch decode once per distinct block and validate each requested file.
            t=time.perf_counter_ns();decoded={}
            for i in ids:
                off,size,nraw=meta[i];decoded[i]=D.decompress(payload[off:off+size],max_output_size=nraw+1)
            for name in want:
                i,off,nraw=mapping[name];assert decoded[i][off:off+nraw]==files[name]
            read_us.append((time.perf_counter_ns()-t)/1000)
        if baseline is None:baseline=ca
        results[mode]=dict(payload_bytes=len(payload),directory_bytes=len(directory),total_bytes=len(payload)+len(directory),
           blocks=len(meta),max_block_raw=max(m[2] for m in meta),source_checks=checks,
           closure_checks=sum(len(closures[n]) for n in roots),closure_activated=quant(ca),closure_decoded=quant(cd),
           closure_blocks=quant(counts),closure_read_us=quant(read_us),single_activated=quant(sa),single_decoded=quant(sd),
           closure_activation_relative=sum(ca)/sum(baseline),build_us=build_us)
        print("ARM_JSON="+json.dumps(results[mode]),flush=True)
    return dict(round=161,corpus=corpus,modules=len(files),edges=g.number_of_edges(),external_import_occurrences=external,
      raw_bytes=sum(map(len,files.values())),manifest_sha256=sha(json.dumps([(n,sha(files[n])) for n in sorted(files)]).encode()),
      root_count=len(roots),root_sha256=sha(json.dumps(roots).encode()),closure_sizes=quant([len(closures[n]) for n in roots]),
      networkx_version=nx.__version__,policies=results,limitations=[
      "syntactic local imports only, not declaration proof dependencies or Lean kernel verification",
      "readable and compact editions related, not independent proof methods; Masullo is unverified",
      "actual compressed bytes and binary directory, in-memory pack not transactional or indexed RAG archive",
      "hard block cap except oversized single modules; no per-file 2.5x/1.5x bound",
      "closure retrieval is exact for this extracted graph only; external Mathlib imports excluded",
      "single warm timing pass, no physical disk IO; graph methods not claimed novel"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",choices=("grh","grh-compact","masullo"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus);a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
