#!/usr/bin/env python3
"""Compare stable chunk boundaries on edited data: baseline line-chunks vs Gear CDC.
No version-aware patching in these controls. Every decoded document is verified byte-exact.
"""
from cdg_experiment_suite import collect_base_docs, Z, chunk_lines
import hashlib,random,struct,json,time
from pathlib import Path

SEED=35198
GEAR=[random.Random(4421+i).getrandbits(32) for i in range(256)]

def gear_chunks(data,min_size=256,avg=1024,max_size=2048):
    mask=avg-1; h=0;start=0;res=[]
    for i,b in enumerate(data):
        h=((h<<1)+GEAR[b]) & 0xffffffff
        length=i+1-start
        if length>=min_size and (h&mask)==0 or length>=max_size:
            res.append(data[start:i+1]);start=i+1;h=0
    if start<len(data):res.append(data[start:])
    assert b''.join(res)==data
    return res

def versions(rate, count=7):
    original=collect_base_docs()
    docs=[]
    for f,(_,b) in enumerate(original):
        lines=b.decode('utf8').splitlines(keepends=True)
        for v in range(count):
            rr=random.Random(SEED+f*987+v*701)
            chosen=set(rr.sample(range(len(lines)),k=min(len(lines),round(rate*len(lines))))) if v else set()
            out=lines[:]
            for li in sorted(chosen):
                old=lines[li];ending='\n' if old.endswith('\n') else ''
                out[li]=old.rstrip('\n')+f' [experiment edit family={f} revision={v} field={li} value={rr.randrange(10000000)}]'+ending
            docs.append(''.join(out).encode())
    return docs

def chunk_store(docs,mode):
    ids={};unique=[];encoded=[];manifests=[]
    for doc in docs:
        if mode=='line_1024': chunks=chunk_lines(doc,target=1024)
        elif mode=='line_256':chunks=chunk_lines(doc,target=256)
        elif mode=='gear_1024':chunks=gear_chunks(doc)
        elif mode=='line_individual':chunks=doc.splitlines(keepends=True)
        else:raise KeyError(mode)
        mid=[]
        for ch in chunks:
            h=hashlib.sha256(ch).digest()
            if h not in ids:
                ids[h]=len(unique);unique.append(ch);encoded.append(Z.compress(ch))
            mid.append(ids[h])
        manifests.append(mid)
    meta=Z.compress(json.dumps(manifests,separators=(',',':')).encode()+b''.join(hashlib.sha256(b).digest()+struct.pack('<II',len(b),len(e)) for b,e in zip(unique,encoded)))
    # verify selected or all docs decode from independently compressed chunks
    for i in range(len(docs)):
        decoded=b''.join(Z.decompress(encoded[j],len(unique[j])) for j in manifests[i])
        assert decoded==docs[i]
    return {'bytes':sum(map(len,encoded))+len(meta),'unique_chunks':len(unique),'occurrences':sum(len(x) for x in manifests)}

def main():
    res=[]
    for rate in [0.,0.01,0.05,0.20]:
        docs=versions(rate);out={'edit_fraction':rate,'documents':len(docs)}
        for mode in (['line_1024','line_256','gear_1024','line_individual'] if rate<=0.01 else ['line_1024','gear_1024']):
            t=time.perf_counter();o=chunk_store(docs,mode);o['seconds']=round(time.perf_counter()-t,2);out[mode]=o
        print(json.dumps(out),flush=True);res.append(out)
    data={'data':res,'limitations':['Version changes are synthetic line annotations.',
         'Gear hash code is a simple reference CDC implementation, not optimized FastCDC.',
         'Each distinct chunk is individually compressed for independent access, unlike solid archives.',
         'Indexing and query processing are not measured, only source compressed bytes and reconstruction.',
         'Results compare a particular chunker configuration, not an optimized CDC parameter sweep.']}
    Path('/mnt/data/cdg_round2/cdg_cdc_results.json').write_text(json.dumps(data,indent=2))
if __name__=='__main__':main()
