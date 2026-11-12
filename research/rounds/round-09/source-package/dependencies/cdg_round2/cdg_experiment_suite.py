#!/usr/bin/env python3
"""Small, fully reproducible CDG research probes.

Uses local Markdown/RST/TXT documents as seed text and creates *synthetic* edited
versions. It does not benchmark LLM accuracy, ANN recall, SSD latency, or
end-to-end RAG. Requires libzstd, which can be replaced with another codec.
"""
from __future__ import annotations
import ctypes, ctypes.util, collections, glob, hashlib, json, os, random, re, statistics, struct, time
from pathlib import Path

SEED=72026
R=random.Random(SEED)
TOKEN=re.compile(rb'[a-z0-9_]{2,}')

class Zstd:
    def __init__(self):
        name=ctypes.util.find_library('zstd')
        if not name: raise RuntimeError('libzstd not found')
        self.l=ctypes.CDLL(name)
        self.l.ZSTD_compressBound.argtypes=[ctypes.c_size_t]
        self.l.ZSTD_compressBound.restype=ctypes.c_size_t
        self.l.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
        self.l.ZSTD_compress.restype=ctypes.c_size_t
        self.l.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
        self.l.ZSTD_decompress.restype=ctypes.c_size_t
        self.l.ZSTD_isError.argtypes=[ctypes.c_size_t]
        self.l.ZSTD_isError.restype=ctypes.c_uint
    def compress(self,data:bytes,level=3):
        src=ctypes.create_string_buffer(data,len(data))
        buf=ctypes.create_string_buffer(self.l.ZSTD_compressBound(len(data)))
        n=self.l.ZSTD_compress(buf,len(buf),src,len(data),level)
        if self.l.ZSTD_isError(n):raise RuntimeError('zstd compress error')
        return buf.raw[:n]
    def decompress(self,data:bytes,outsize:int):
        src=ctypes.create_string_buffer(data,len(data))
        buf=ctypes.create_string_buffer(outsize)
        n=self.l.ZSTD_decompress(buf,outsize,src,len(data))
        if self.l.ZSTD_isError(n) or n!=outsize:raise RuntimeError('zstd decompress error')
        return buf.raw[:n]
Z=Zstd()

def collect_base_docs():
    paths=[]
    roots=[Path('/home/oai/skills'),Path('/opt/pyvenv/lib/python3.13/site-packages')]
    for root in roots:
        if root.exists():
            for ext in ('*.md','*.rst','*.txt'):
                paths+=list(root.rglob(ext))
    docs=[]
    for p in sorted(set(paths)):
        try:
            size=p.stat().st_size
            if not 3000<=size<=50000: continue
            b=p.read_bytes()
            if b'\x00' in b or b.count(b'\n')<15:continue
            b.decode('utf8')
            docs.append((p.name,b))
        except (UnicodeError,OSError):continue
        if len(docs)>=150:break
    if len(docs)<60:raise RuntimeError('Insufficient local text files for this environmental test')
    return docs

def variants(seed_docs,versions=5):
    out=[]
    for i,(_,b) in enumerate(seed_docs):
        # Add deterministic *synthetic* revision records; the main body is real local text.
        for v in range(versions):
            tag=f'\n\nCDG_EXPERIMENT_FACT tag_family_{i:04d} tag_revision_{v} status_{(v+i)%3} amount_{i*13+v*7} provenance_test_only.\n'.encode()
            out.append((i,v,b+tag))
    return out

def chunk_lines(b,target=1024):
    # Line-aligned chunks: insertion at the end does not shift earlier boundaries.
    lines=b.splitlines(keepends=True)
    cur=bytearray();out=[]
    for ln in lines:
        if cur and len(cur)+len(ln)>target:
            out.append(bytes(cur));cur.clear()
        if len(ln)>target*4:
            if cur:out.append(bytes(cur));cur.clear()
            for pos in range(0,len(ln),target*4):out.append(ln[pos:pos+target*4])
        else:cur+=ln
    if cur:out.append(bytes(cur))
    assert b''.join(out)==b
    return out

def build_store(documents):
    unique=[];ids={};manifests=[];lengths=[]
    for _,_,b in documents:
        chunks=[]
        for c in chunk_lines(b):
            key=hashlib.sha256(c).digest()
            if key not in ids:
                ids[key]=len(unique);unique.append(c)
            chunks.append(ids[key])
        manifests.append(chunks);lengths.append(len(b))
    enc=[Z.compress(c) for c in unique]
    manifest_bytes=json.dumps({'docs':manifests,'sizes':lengths},separators=(',',':'),sort_keys=True).encode()
    table=b''.join(hashlib.sha256(c).digest()+struct.pack('<II',len(c),len(e)) for c,e in zip(unique,enc))
    meta=Z.compress(manifest_bytes+table)
    return dict(unique=unique,ids=ids,manifests=manifests,enc=enc,metadata=meta,storage=sum(map(len,enc))+len(meta))

def recover(store,i):
    return b''.join(Z.decompress(store['enc'][j],len(store['unique'][j])) for j in store['manifests'][i])

def tokenize(b):return set(TOKEN.findall(b.lower()))

def index_queries(docs):
    terms=[tokenize(b) for _,_,b in docs]
    postings=collections.defaultdict(set)
    for i,tt in enumerate(terms):
        for t in tt:postings[t].add(i)
    # 3 variations: family only; family+version; family+status
    families=sorted(set(i for i,_,_ in docs))
    q=[]
    for f in families:
        q.append((f'tag_family_{f:04d}'.encode(),))
        q.append((f'tag_family_{f:04d}'.encode(),b'tag_revision_3'))
        q.append((f'tag_family_{f:04d}'.encode(),f'status_{f%3}'.encode()))
    R.shuffle(q)
    q=q[:min(180,len(q))]
    exact=[]
    for tokens in q:
        docs_ids=set.intersection(*(postings.get(t,set()) for t in tokens))
        exact.append(docs_ids)
    return terms,postings,q,exact

def get_blocks(ids,group_size=20):return [ids[i:i+group_size] for i in range(0,len(ids),group_size)]

def run_filter(docs,terms,postings,queries,truth,order):
    blocks=get_blocks(order)
    summaries=[set().union(*(terms[j] for j in ids)) for ids in blocks]
    cbytes=[Z.compress(b) for _,_,b in docs]
    n_cand=[];bytes_read=[];matched=[];pages=[]
    tic=time.perf_counter()
    for qt in queries:
        cand=[j for bid,ids in enumerate(blocks) if all(t in summaries[bid] for t in qt) for j in ids]
        actual={j for j in cand if all(t in tokenize(Z.decompress(cbytes[j],len(docs[j][2]))) for t in qt)}
        matched.append(actual);n_cand.append(len(cand));bytes_read.append(sum(len(cbytes[j]) for j in cand))
        pages.append(sum(all(t in ss for t in qt) for ss in summaries))
    elapsed=time.perf_counter()-tic
    return dict(avg_decompressed_docs=statistics.mean(n_cand),avg_compressed_bytes_read=statistics.mean(bytes_read),avg_candidate_blocks=statistics.mean(pages),elapsed_s=elapsed,correct=all(a==b for a,b in zip(matched,truth)),block_count=len(blocks),sum_block_summary_entries=sum(len(s) for s in summaries))

def packed_pages(store,order,page_size=16384):
    chunk_to_page={};page=-1;remaining=0
    for cid in order:
        size=len(store['enc'][cid])
        if page<0 or size>remaining: page+=1;remaining=page_size
        chunk_to_page[cid]=page;remaining-=size
    return chunk_to_page,page+1

def pages_touched(store,doc_ids,chunk_to_page):
    return len({chunk_to_page[x] for i in doc_ids for x in store['manifests'][i]})

def bench():
    base=collect_base_docs()
    docs=variants(base)
    raw=sum(len(x[2]) for x in docs)
    t0=time.perf_counter();store=build_store(docs);build_time=time.perf_counter()-t0
    independent=[Z.compress(b) for _,_,b in docs]
    z9=[Z.compress(b,9) for _,_,b in docs]
    solid=Z.compress(b''.join(struct.pack('<I',len(b))+b for _,_,b in docs),9)
    assert all(recover(store,j)==b for j,(_,_,b) in enumerate(docs))
    doc_index,postings,queries,truth=index_queries(docs)
    randomorder=list(range(len(docs)));R.shuffle(randomorder)
    familyorder=sorted(range(len(docs)),key=lambda j:docs[j][:2])
    rf=run_filter(docs,doc_index,postings,queries,truth,randomorder)
    ff=run_filter(docs,doc_index,postings,queries,truth,familyorder)
    # Exact postings baseline: no document decompression to find candidate documents.
    tic=time.perf_counter()
    for qt,goal in zip(queries,truth):
        actual=set.intersection(*(postings[t] for t in qt))
        assert actual==goal
    post_time=time.perf_counter()-tic
    # Index serialization: dictionary term -> sorted doc ids, included in index cost.
    idx_bytes=Z.compress(json.dumps({t.decode():sorted(v) for t,v in postings.items()},separators=(',',':'),sort_keys=True).encode())
    # Sort compressed chunks either by first family ownership or randomly.
    owner={}
    for i,(fam,ver,_) in enumerate(docs):
        for cid in store['manifests'][i]:owner.setdefault(cid,fam)
    cids=list(range(len(store['enc'])))
    ownerorder=sorted(cids,key=lambda cid:(owner[cid],cid))
    scramble=cids[:];R.shuffle(scramble)
    page_coherent,num_coherent=packed_pages(store,ownerorder)
    page_random,num_random=packed_pages(store,scramble)
    touched_c=[pages_touched(store,m,page_coherent) for m in truth]
    touched_r=[pages_touched(store,m,page_random) for m in truth]
    # Block summary serialized size: one term list per block, compressed with zstd.
    def summary_bytes(order):
        bl=get_blocks(order)
        values=[sorted(t.decode() for t in set().union(*(doc_index[i] for i in ids))) for ids in bl]
        return len(Z.compress(json.dumps(values,separators=(',',':'),sort_keys=True).encode()))
    result={
        'description':'Real local documentation with deterministic synthetic near-duplicate versions; not a production RAG benchmark',
        'environment':{'python':'3.13','codec':'libzstd','seed':SEED},
        'data':{'original_seed_docs':len(base),'synthetic_versions_per_doc':5,'logical_documents':len(docs),'raw_bytes':raw,'unique_chunks':len(store['unique']),'total_chunk_occurrences':sum(len(x) for x in store['manifests']),'queries':len(queries)},
        'storage':{'independent_zstd_3_bytes':sum(map(len,independent)),'independent_zstd_9_bytes':sum(map(len,z9)),'solid_archive_zstd_9_bytes':len(solid),'shared_zstd_chunks_plus_metadata_bytes':store['storage'],'lexical_inverted_index_compressed_bytes':len(idx_bytes),'shared_plus_full_lexical_index_bytes':store['storage']+len(idx_bytes),'build_seconds':build_time},
        'retrieval':{'random_block_filter':rf,'family_block_filter':ff,'compressed_summary_random_bytes':summary_bytes(randomorder),'compressed_summary_family_bytes':summary_bytes(familyorder),'postings_query_time_s':post_time,'all_results_exact':rf['correct'] and ff['correct']},
        'physical_layout':{'page_bytes':16384,'random_pages':num_random,'family_pages':num_coherent,'avg_pages_to_fetch_exact_matches_random':statistics.mean(touched_r),'avg_pages_to_fetch_exact_matches_family':statistics.mean(touched_c)},
        'cautions':['Input edits are synthetic and deliberately create extremely high redundancy.','Queries are controlled lexical conjunctions, not semantic questions.','Compressed bytes read count is logical I/O, not measured disk read time.','Block-filter latency includes Python decompression and tokenization; postings index is a strong exact baseline.','Metadata and index sizes are accounted for explicitly; OS page cache and SSD behavior are not measured.']}
    output=Path('/mnt/data/cdg_results_2026-11-08.json'); output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':bench()
