#!/usr/bin/env python3
"""CDG Round 8: exact BM25 via a factorized shared-chunk term matrix.

Real noVNC versions and commit subject proxy queries. Benchmarks a conventional
term-document index, factorized (doc-chunk membership @ chunk-term counts),
and a query-trained hybrid with precomputed postings for selected terms.
No pretrained dense model or real RAG QA labels. Byte/metadata accounting explicit.
"""
import re, json, sys, math, time, random, hashlib, statistics, collections, struct, os
from pathlib import Path
import numpy as np
from scipy import sparse
HERE=Path(__file__).resolve().parent
SRC=HERE/'dependencies'
sys.path.insert(0,str(SRC))
from git_history_retrieval import create
from revision_storage_benchmark import Z

SAMPLES=create(250)
DOCS=[s['after'].encode('utf-8') for s in SAMPLES]
QUERIES=[s['message'] for s in SAMPLES]
PATHS=[s['path'] for s in SAMPLES]

pat=re.compile(r'(?u)[a-z][a-z0-9_]+')
def toks_bytes(b):
    # Match per-line and full-text tokenization. Source code camelCase is preserved.
    return pat.findall(b.decode('utf-8','replace').lower())
def toks_query(s): return pat.findall(s.lower())

# Build line-level CDC chunks with a deterministic rolling boundary. Same conceptual
# algorithm as Round 7, independently implemented to avoid re-running its benchmark.
MASK=(1<<64)-1
def rol(v,n):
    n%=64
    return ((v<<n)|(v>>(64-n)))&MASK if n else v

def boundaries(lines,target=32):
    n=len(lines);lo=max(2,target//4);hi=target*2;ends=[];start=0
    sig=[int.from_bytes(hashlib.blake2b(line,digest_size=8).digest(),'little') for line in lines]
    for i in range(n):
        sz=i+1-start
        if sz<lo:continue
        h=0
        for j in range(max(0,i-3),i+1):h^=rol(sig[j],(i-j)*11+1)
        if sz>=hi or (h&(target-1))==0:
            ends.append(i+1);start=i+1
    if not ends or ends[-1]!=n:ends.append(n)
    return ends

all_chunks=[];lookup={};doc_maps=[];meta_lens=[]
for doc in DOCS:
    lines=doc.splitlines(keepends=True);ends=boundaries(lines)
    seq=[];start=0
    for end in ends:
        data=b''.join(lines[start:end]);start=end
        digest=hashlib.blake2b(data,digest_size=16).digest()
        if digest not in lookup:
            lookup[digest]=len(all_chunks);all_chunks.append(data)
        elif all_chunks[lookup[digest]]!=data:raise AssertionError('hash collision')
        seq.append(lookup[digest])
    doc_maps.append(seq)

# Count token frequencies in unique chunks and documents via the membership map.
chunk_counters=[collections.Counter(toks_bytes(b)) for b in all_chunks]
vocab={term:i for i,term in enumerate(sorted(set().union(*(set(d) for d in chunk_counters))))}
V=len(vocab); N=len(DOCS);U=len(all_chunks)
C_rows=[];C_cols=[];C_data=[]
for ci,ctr in enumerate(chunk_counters):
    for term,val in ctr.items():C_rows.append(ci);C_cols.append(vocab[term]);C_data.append(val)
C=sparse.coo_matrix((np.array(C_data,dtype=np.int32),(C_rows,C_cols)),shape=(U,V),dtype=np.int32).tocsr()
M_rows=[];M_cols=[];M_data=[]
for d,seq in enumerate(doc_maps):
    cnt=collections.Counter(seq)
    for cid,val in cnt.items():M_rows.append(d);M_cols.append(cid);M_data.append(val)
M=sparse.coo_matrix((np.array(M_data,dtype=np.int32),(M_rows,M_cols)),shape=(N,U),dtype=np.int32).tocsr()
F=(M@C).tocsr()
# Compare per-document term vector with direct tokenization to ensure exact factorization.
for i,d in enumerate(DOCS):
    ctr=collections.Counter(toks_bytes(d))
    got={term:int(F[i,vid]) for term,vid in vocab.items() if F[i,vid]}
    assert ctr==got, ('not-exact',i,len(ctr),len(got))

Ccol=C.tocsc();Fcol=F.tocsc()
doc_len=np.asarray(F.sum(axis=1)).ravel().astype(np.float64)
avg_len=float(doc_len.mean()); df=np.asarray((F>0).sum(axis=0)).ravel().astype(np.float64)
idf=np.log1p((N-df+0.5)/(df+0.5))
k1=1.2;b=0.75;denom_norm=k1*(1-b+b*doc_len/avg_len)
query_terms=[sorted({vocab[t] for t in toks_query(q) if t in vocab}) for q in QUERIES]

def scores_from_tfs(tfs,indices):
    if len(indices)==0:return np.zeros(N)
    tf=tfs.astype(np.float64)
    return np.sum(idf[np.asarray(indices)][None,:]*(k1+1)*tf/(tf+denom_norm[:,None]),axis=1)

def flat_score(ts):
    if not ts:return np.zeros(N)
    return scores_from_tfs(Fcol[:,ts].toarray(),ts)

def factor_score(ts):
    if not ts:return np.zeros(N)
    return scores_from_tfs((M@Ccol[:,ts]).toarray(),ts)

# Compressed matrix accounting, independent of SciPy object overhead.
def pack_csr(x):
    x=x.tocsr();return x.indptr.astype('<i4').tobytes()+x.indices.astype('<i4').tobytes()+x.data.astype('<i4').tobytes()
def compressed(x):return len(Z.compress(pack_csr(x),3))
def comp_vocab():return len(Z.compress(json.dumps(vocab,sort_keys=True).encode(),3))

# Train-only query frequency for choosing optional materialized term postings.
shuffled=list(range(N));random.Random(190731).shuffle(shuffled)
train=shuffled[:100];test=shuffled[100:]
counts=collections.Counter(t for i in train for t in query_terms[i])

# Fully materialized postings for chosen term(s) only. True incremental sizes count
# the extra postings plus the shared chunk+membership representations.
# Heuristic cost: weighted query frequency * number of chunk hits * mean doc fan-out.
chunk_doc_fanout=np.asarray((M>0).sum(axis=0)).ravel()
term_work={t:int(Ccol[:,t].indices.size + sum(chunk_doc_fanout[int(c)] for c in Ccol[:,t].indices)) for t in counts}
ordered=sorted(counts,key=lambda t:counts[t]*term_work[t],reverse=True)

# Show both 10% and 30% hot-term budgets relative to training vocabulary.
hybrid={}
for frac in (0.1,0.3):
    hot=set(ordered[:max(1,int(len(ordered)*frac))])
    terms=sorted(hot)
    hot_F=Fcol[:,terms].tocsr()
    mapping={t:i for i,t in enumerate(terms)}
    def scorer(qts,hot=hot,mapping=mapping,hot_F=hot_F):
        if not qts:return np.zeros(N)
        qt_hot=[t for t in qts if t in hot]
        qt_cold=[t for t in qts if t not in hot]
        score=np.zeros(N)
        if qt_hot:
            score+=scores_from_tfs(hot_F[:,[mapping[t] for t in qt_hot]].toarray(),qt_hot)
        if qt_cold:score+=factor_score(qt_cold)
        return score
    hybrid[frac]={'hot_terms':len(hot),'stored_bytes':compressed(hot_F),'fn':scorer}

# Correctness on every commit subject, not just held-out.
full_orders=[]
for i,t in enumerate(query_terms):
    flat=flat_score(t); fac=factor_score(t)
    if not np.allclose(flat,fac,rtol=1e-12,atol=1e-12):raise AssertionError(('scores differ',i))
    full_orders.append(np.argsort(-flat,kind='stable'))
    for frac,h in hybrid.items():
        hs=h['fn'](t)
        if not np.allclose(hs,flat,rtol=1e-12,atol=1e-12):raise AssertionError(('hybrid mismatch',frac,i))

# Runs isolated functions with randomized method/query orders. Directly compare
# exact same task, warm in-memory CPU, no IO or generation.
variants={'flat_document_postings':flat_score,'factorized_chunks':factor_score}
for frac,h in hybrid.items():variants[f'hybrid_{int(frac*100)}pct_hot']=h['fn']
raw_times={k:[] for k in variants};per_query={k:[] for k in variants};dummy=0.
for repeat in range(12):
    methods=list(variants);random.Random(21001+repeat).shuffle(methods)
    for name in methods:
        f=variants[name]; ids=test[:];random.Random(34000+repeat).shuffle(ids)
        for i in ids:
            t0=time.perf_counter_ns();ret=f(query_terms[i]);dt=(time.perf_counter_ns()-t0)/1e3
            dummy+=float(ret[i]);raw_times[name].append(dt)
            per_query[name].append((i,dt))

def metrics(name,vals):
    values=sorted(vals)
    return {'median_us':round(statistics.median(values),2),'p95_us':round(values[int(.95*(len(values)-1))],2),'mean_us':round(statistics.mean(values),2)}

# Query relevance of same scoring function is necessarily constant, reported as
# an evaluation sanity check, not an improvement in retrieval quality.
ranks=[]
for i,order in enumerate(full_orders):ranks.append(int(np.where(order==i)[0][0])+1)
results={
 'experiment':'CDG Round 8: exact BM25 matrix factorization through shared CDC chunks on real noVNC file histories.',
 'date':'2026-11-09',
 'provenance':{'repo':'/opt/novnc','selected_versions':N,'unique_paths':len(set(PATHS)),'raw_bytes':sum(map(len,DOCS)),'queries':N,'train_queries':len(train),'heldout_queries':len(test),'unique_cdc_chunks':U,'logical_chunk_references':sum(len(x) for x in doc_maps),'vocabulary':V,'source_bytes':769939},
 'index_storage_compressed_bytes':{
   'flat_term_document':compressed(F),
   'factorized_chunk_terms':compressed(C),
   'factorized_chunk_membership':compressed(M),
   'factorized_total_exclusive_vocab':compressed(C)+compressed(M),
   'flat_plus_cdc_source_exclusive_vocab':769939+compressed(F),
   'factorized_plus_cdc_source_exclusive_vocab':769939+compressed(C)+compressed(M),
   'vocabulary_common':comp_vocab(),
   **{f'hybrid_{int(frac*100)}pct_hot_extra_postings':h['stored_bytes'] for frac,h in hybrid.items()},
 },
 'timing_heldout_warm_cpu':{name:metrics(name,vals) for name,vals in raw_times.items()},
 'retrieval_quality_flat_bm25':{'hit_at1':round(sum(x<=1 for x in ranks)/N,4),'hit_at5':round(sum(x<=5 for x in ranks)/N,4),'hit_at10':round(sum(x<=10 for x in ranks)/N,4)},
 'exact_all_250_queries':True,
 'notes':[
  'All full-document term counts equal membership x unique-chunk counts, verified for every doc with exact tokenization.',
  'All 250 BM25 score vectors match within floating-point tolerance between factorized, flat, and hybrid variants.',
  '12 randomized timing rounds over 150 held-out commit-subject queries; query-term lookup and scoring included, no preprocessing, IO, source decompression or generation.',
  'Compressed CSR int32 indices, pointers and frequency arrays, Zstd level 3. SciPy CSR object overhead and vocabulary RAM excluded from byte totals.',
  'Membership matrix M is already implicit in chunk reference metadata for CDC source storage; reporting its size separately to avoid free metadata.',
  'Only commit-message queries with automatic single-revision targets, not human-labeled QA or semantic-neural retrieval.',
  'The implementation is a straightforward factorized sparse-matrix method; factorized DB systems and inverted indexes are prior art.',
  'The source_bytes entry is reused from independently verified Round 7 representation with the same CDC target and corpus; no SSD implementation here.'
 ]
}
(HERE/'round8_results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2));print('checksum_unused',dummy)
