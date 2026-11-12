#!/usr/bin/env python3
"""CDG Round 8b: query-conditioned multi-passage read with per-query chunk dedup.

All methods read the same five-line passages from BM25-retrieved versions. Measures
compressed payload bytes touched, unique frames decoded, warm CPU latency.
Queries are human commit subjects, relevance is NOT labeled QA.
"""
import io,contextlib,sys,json,time,random,statistics,hashlib,bisect,collections
from pathlib import Path
HERE=Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    import run_round8 as r

class Frames:
 def __init__(self,dedup,cdc):
    self.name=('dedup_cdc' if dedup else 'indep_fixed') if (dedup or not cdc) else 'indep_cdc'
    self.frames=[];self.refs=[];self.ends=[];self.look={};self.source_bytes=0;self.meta=0
    for doc in r.DOCS:
        lines=doc.splitlines(keepends=True);ends=r.boundaries(lines,32) if cdc else [min(i+32,len(lines)) for i in range(0,len(lines),32)]
        start=0;ids=[]
        for end in ends:
            raw=b''.join(lines[start:end]);start=end
            h=hashlib.blake2b(raw,digest_size=16).digest()
            if dedup and h in self.look:
                fid=self.look[h]
                assert self.frames[fid][3]==raw
            else:
                encoded=r.Z.compress(raw,3);israw=len(raw)<=len(encoded)
                payload=raw if israw else encoded
                fid=len(self.frames);self.frames.append((israw,payload,len(raw),raw))
                self.source_bytes+=len(payload)+9
                if dedup:self.look[h]=fid
            ids.append(fid)
        self.refs.append(ids);self.ends.append(ends)
        self.meta+=len(ids)*8+8
    self.disk_bytes=self.source_bytes+self.meta
    # Avoid accidentally reading original uncompressed source during query evaluation
    self.frames=[f[:3] for f in self.frames]
 def read(self,reqs,cache=False):
    out=[];used_ids=set();bytes_fetch=0;bytes_raw=0;decs=0;refs=0;cache_map={}
    for docid,a,b in reqs:
        ids=self.refs[docid];ends=self.ends[docid];k=bisect.bisect_right(ends,a);parts=[]
        while k<len(ids):
            start=ends[k-1] if k else 0
            if start>=b:break
            fid=ids[k];israw,payload,n=self.frames[fid];refs+=1
            if cache and fid in cache_map:
                txt=cache_map[fid]
            else:
                txt=payload if israw else r.Z.decompress(payload,n)
                if cache:cache_map[fid]=txt
                used_ids.add(fid);bytes_fetch+=len(payload);bytes_raw+=len(txt);decs+=1
            lines=txt.splitlines(keepends=True)
            parts.extend(lines[max(0,a-start):min(len(lines),b-start)])
            k+=1
        out.append(b''.join(parts))
    return out, {'payload_bytes':bytes_fetch,'decoded_bytes':bytes_raw,'frames_decoded':decs,'chunk_references':refs,'unique_ids_used':len(used_ids)}

ind=Frames(False,False)
cdc=Frames(True,True)
# Verify all original source bytes. Queries will only ask passages.
for store in [ind,cdc]:
 for i,doc in enumerate(r.DOCS):
    recovered,_=store.read([(i,0,len(doc.splitlines(keepends=True)))],True)
    assert recovered[0]==doc,(store.name,i)

line_tokens=[[set(r.toks_bytes(line)) for line in doc.splitlines(keepends=True)] for doc in r.DOCS]

def choose_window(qid,docid):
    qt=set(r.toks_query(r.QUERIES[qid]));lines=line_tokens[docid]
    if not lines:return (docid,0,0)
    # Query-matched passage. Inference only uses query and candidate document content.
    match=[len(qt.intersection(lt)) for lt in lines]
    best=max(range(len(lines)),key=lambda j:(match[j],-j))
    a=max(0,min(max(0,len(lines)-5),best-2))
    return (docid,a,min(a+5,len(lines)))

rng=random.Random(587)
ids=list(r.test)
traces={}
for topk in [1,5,10]:
    traces[f'BM25_top{topk}']=[ [choose_window(i,int(x)) for x in r.full_orders[i][:topk]] for i in ids ]
    traces[f'random_top{topk}']=[ [choose_window(i,int(x)) for x in rng.sample(range(len(r.DOCS)),topk)] for i in ids ]

modes={'independent_fixed32':(ind,False),'dedup_cdc32_no_batch':(cdc,False),'dedup_cdc32_batch':(cdc,True)}
results={'source_versions':len(r.DOCS),'raw_bytes':sum(map(len,r.DOCS)),'source_disk_bytes':{'independent_fixed32':ind.disk_bytes,'dedup_cdc32':cdc.disk_bytes},'traces':{},'notes':['BM25 top-k retrieval uses the exact document scoring and tokenizer from Round 8a.','All passages verified against original file bytes for both stores; no relevance/QA labels.','Warm CPU in-memory compressed payloads with per-query cache only, no SSD and no cross-query retention.','Random k candidates used to estimate how much duplication is caused by retrieving similar versions.','Metadata costs: 9B per unique compressed frame and 8B per document chunk ref plus 8B per file.','Timing includes Python decompression, chunk navigation, splitting lines, assembly; excludes BM25 query scoring.']}
for label,trace in traces.items():
   stats={k:{'latencies_us':[],'payload_bytes':[],'decoded_bytes':[],'frames_decoded':[],'chunk_references':[]} for k in modes}
   total_groups=len(trace)
   for repeat in range(5):
     methods=list(modes);random.Random(93000+repeat).shuffle(methods)
     shuffled=list(range(total_groups));random.Random(12000+repeat).shuffle(shuffled)
     for name in methods:
        st,cache=modes[name]
        for j in shuffled:
            req=trace[j]
            t0=time.perf_counter_ns();reads,counts=st.read(req,cache=cache);dt=(time.perf_counter_ns()-t0)/1e3
            if repeat==0:
                expected=[b''.join(r.DOCS[di].splitlines(keepends=True)[a:b]) for di,a,b in req]
                assert reads==expected,(label,name,j)
            x=stats[name];x['latencies_us'].append(dt)
            for col in ['payload_bytes','decoded_bytes','frames_decoded','chunk_references']:x[col].append(counts[col])
   results['traces'][label]={}
   for name,z in stats.items():
     srt=sorted(z['latencies_us'])
     results['traces'][label][name]={
       'median_us':round(statistics.median(srt),2),'p95_us':round(srt[int(.95*(len(srt)-1))],2),
       **{f'mean_{col}':round(statistics.mean(z[col]),1) for col in ('payload_bytes','decoded_bytes','frames_decoded','chunk_references')}
     }
    
(HERE/'round8_batch_results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
