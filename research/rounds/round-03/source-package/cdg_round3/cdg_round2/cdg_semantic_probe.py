#!/usr/bin/env python3
"""CDG round 2: shared-basis linear feature retrieval with exact residual bounds.

Real software documentation as background, controlled synthetic version edits and query labels.
This is NOT a pretrained neural embedding or real RAG experiment. All scores use linear
TF-IDF vectors; the exactness claim applies ONLY to that scoring model.
"""
from __future__ import annotations
import json, math, random, statistics, time, zlib
from pathlib import Path
from collections import Counter
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from cdg_experiment_suite import collect_base_docs, Z

SEED=53143
rng=np.random.default_rng(SEED)


def corpus(versions=10):
    orig=collect_base_docs()
    bases=[]; docs=[]; families=[]; qs=[]; targets=[]
    states=['approved','rejected','pending','suspended','revised']
    for f,(_,raw) in enumerate(orig):
        background=raw.decode('utf8')
        prefix=f'\n\nCDG CONTROLLED RECORD project_{f:04d} report series alpha.'
        def line(v):
            status=states[(v*3+f)%5]
            value=100+17*v+f%11
            return f'\nAudit for project_{f:04d}: revision_{v:02d} status_{status} metric_{value} regulatory_waiver_{(v+f)%4}.'
        base=background+prefix+line(0)
        bases.append(base)
        for v in range(versions):
            docs.append(background+prefix+line(v))
            families.append(f)
            if v>=1 and (v%2==1 or v==versions-1):
                q=f'project_{f:04d} revision_{v:02d} status_{states[(v*3+f)%5]} metric_{100+17*v+f%11}'
                qs.append(q);targets.append(f*versions+v)
    selection=rng.choice(len(qs),size=min(300,len(qs)),replace=False)
    queries=[qs[i] for i in selection]
    targets=[targets[i] for i in selection]
    return bases,docs,np.asarray(families,np.int32),queries,np.asarray(targets,np.int32)


def pack_csr(M):
    M=M.tocsr()
    # Store feature weights and index metadata as 32-bit, corresponding to an ordinary CSR index.
    return b''.join([np.asarray(M.data,np.float32).tobytes(),
                     np.asarray(M.indices,np.int32).tobytes(),
                     np.asarray(M.indptr,np.int32).tobytes()])


def zipped_count(M):
    payload=pack_csr(M)
    return {'raw_bytes':len(payload),'zstd3_bytes':len(Z.compress(payload,3)), 'nnz':int(M.nnz)}


def get_topk(scores,k):
    # Exact stable order under ties. Score differences >1e-6 are expected for reference labels.
    return np.argsort(-scores,kind='stable')[:k]


def score_row(M,q):
    # Sparse dot between one document and one normalized query.
    return float(M @ q.T.toarray()[:,0])


def exact_bound_search(q,B,D,family,doc_norm,delta_norm,k=5,top_residual_terms=0):
    """Exact top-k by upper bounds. Account for all overhead in timing separately.

    For unnormalized document vector x=b+delta and normalized query q:
       cosine(q,x) = (q.b + q.delta) / ||x||
       q.delta <= ||q|| ||delta|| (q is unit norm)
    For improved bound, use top residual coordinates exactly, bound unseen tail by its norm.
    """
    base_scores=(B @ q.T).toarray().ravel()
    q_dense=np.asarray(q.toarray()).ravel()
    # This experiment tests two variants: simple residual norm bound and top-coordinate refinement.
    n=D.shape[0]
    bounds=np.empty(n,dtype=np.float64)
    if top_residual_terms==0:
        bounds=(base_scores[family]+delta_norm)/doc_norm
    else:
        for j in range(n):
            dr=D.getrow(j)
            vv=dr.data.astype(np.float64)
            ii=dr.indices
            if len(vv)<=top_residual_terms:
                partial=float(np.dot(vv,q_dense[ii]));rem_norm=0.
            else:
                ix=np.argpartition(np.abs(vv),-top_residual_terms)[-top_residual_terms:]
                partial=float(np.dot(vv[ix],q_dense[ii[ix]]))
                rem_norm=float(np.linalg.norm(np.delete(vv,ix)))
            bounds[j]=(base_scores[family[j]]+partial+rem_norm)/doc_norm[j]
    # We use a sorted bound pass; a production structure would avoid scanning every bound.
    order=np.argsort(-bounds,kind='stable')
    scores={};evals=0; threshold=-float('inf')
    for j in order:
        if len(scores)>=k and bounds[j]<threshold-1e-9:
            break
        s=(base_scores[family[j]]+float(D.getrow(int(j)).multiply(q).sum()))/doc_norm[j]
        scores[int(j)]=s; evals+=1
        if len(scores)>=k:
            threshold=sorted(scores.values(),reverse=True)[k-1]
    result=sorted(scores.items(),key=lambda pair:(-pair[1],pair[0]))[:k]
    return [j for j,_ in result],evals


def timed(fn,reps=5):
    vals=[]
    for _ in range(reps):
        t=time.perf_counter();fn();vals.append(time.perf_counter()-t)
    return {'median_s':float(statistics.median(vals)),'min_s':float(min(vals))}


def run():
    bases,docs,family,queries,targets=corpus()
    t0=time.perf_counter()
    vec=TfidfVectorizer(ngram_range=(1,2),dtype=np.float32,lowercase=True,
                        token_pattern=r'(?u)\b\w\w+\b',max_features=24000,norm=None)
    X=vec.fit_transform(docs).tocsr()
    B=vec.transform(bases).tocsr()
    Q=vec.transform(queries).tocsr()
    Q=normalize(Q,norm='l2',copy=False)
    rows_B=B[family].tocsr()
    D=(X-rows_B).tocsr()
    X.sort_indices();B.sort_indices();D.sort_indices()
    norm=np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel()).astype(np.float64)
    delta_norm=np.sqrt(np.asarray(D.multiply(D).sum(axis=1)).ravel()).astype(np.float64)
    assert (norm>0).all()
    # Check additive reconstruction: floating-point cancellation yields limited tolerances.
    recon_err=(X-(rows_B+D)).tocsr()
    max_recon_err=float(max(abs(recon_err.data),default=0))
    assert max_recon_err < 1e-3,max_recon_err
    print('corpus',len(docs),'feature_count',X.shape[1],'nnz',X.nnz,D.nnz,'prep_s',round(time.perf_counter()-t0,2),flush=True)

    # Exhaustive full TF-IDF topk in a single optimized sparse matrix multiply.
    def full_scores():
        raw=(Q @ X.T).toarray()
        return raw / norm[None,:]
    def decomposed_scores():
        bs=(Q@B.T).toarray()[:,family]
        ds=(Q@D.T).toarray()
        return (bs+ds)/norm[None,:]
    S=full_scores();Sd=decomposed_scores()
    score_error=float(np.max(np.abs(S-Sd)))
    assert score_error < 1e-4
    t_full=timed(full_scores)
    t_delta=timed(decomposed_scores)
    k=5
    baseline_top=[get_topk(row,k).tolist() for row in S]
    retrieved_top=[get_topk(row,k).tolist() for row in Sd]
    matched=sum(set(a)==set(b) for a,b in zip(baseline_top,retrieved_top))
    # Base-only retrieval cannot distinguish variants from the same family.
    base_only=(Q@B.T).toarray()[:,family]/np.sqrt(np.asarray(B.multiply(B).sum(axis=1)).ravel())[family][None,:]
    full_mrr=np.mean([1/(list(top).index(int(target))+1) if int(target) in top else 0
                     for top,target in zip(baseline_top,targets)])
    base_mrr=np.mean([1/(list(get_topk(row,k)).index(int(target))+1) if int(target) in get_topk(row,k) else 0
                     for row,target in zip(base_only,targets)])
    # Exact theorem-backed bound evaluation; don't count this as speedup without timing.
    qsel=np.arange(min(100,len(queries)))
    counts=[];ok=0
    t=time.perf_counter()
    for i in qsel:
        candidates,n=exact_bound_search(Q.getrow(int(i)),B,D,family,norm,delta_norm,k)
        counts.append(n)
        if set(candidates)==set(baseline_top[i]):ok+=1
    bound_t=time.perf_counter()-t
    # A linear score model is not a neural embedding. Test dense proxy separately via SVD.
    svd=TruncatedSVD(n_components=64,n_iter=3,random_state=SEED)
    tsvd=time.perf_counter();svd.fit(X)
    XB=svd.transform(B).astype(np.float32)
    XX=svd.transform(X).astype(np.float32)
    QQ=svd.transform(Q).astype(np.float32)
    QQ=normalize(QQ)
    d_dense=XX-XB[family]
    # Cosine with a low rank learned linear feature projection.
    dense_ref=normalize(XX)@QQ.T
    dense_ref_top=np.argsort(-dense_ref,axis=0,kind='stable')[:k].T
    dense_base=normalize(XB)[family]@QQ.T
    dense_base_top=np.argsort(-dense_base,axis=0,kind='stable')[:k].T
    # vector quantization baselines, global rowwise scales, int8 and int4 (packed approximated storage)
    def quant(A,bits):
        rngv=(2**(bits-1)-1)
        scale=np.maximum(np.max(np.abs(A),axis=1,keepdims=True)/rngv,1e-9)
        qarr=np.clip(np.rint(A/scale),-rngv,rngv).astype(np.int8)
        return qarr,scale.astype(np.float32),(qarr*scale).astype(np.float32)
    dense_results={}
    for bits in (8,4):
        full_q,full_sc,full_approx=quant(XX,bits)
        res_q,res_sc,res_approx=quant(d_dense,bits)
        comp_approx=XB[family]+res_approx
        full_hits=(set(dense_ref_top[i])==set(np.argsort(-(normalize(full_approx)@QQ.T)[:,i],kind='stable')[:k]) for i in range(len(queries)))
        comp_scores=normalize(comp_approx)@QQ.T
        comp_top=np.argsort(-comp_scores,axis=0,kind='stable')[:k].T
        full_reconscores=normalize(full_approx)@QQ.T
        full_top=np.argsort(-full_reconscores,axis=0,kind='stable')[:k].T
        dense_results[f'{bits}bit']={
            'full_q_exact_top5_set_rate':float(np.mean([set(x)==set(y) for x,y in zip(dense_ref_top,full_top)])),
            'base_residual_q_exact_top5_set_rate':float(np.mean([set(x)==set(y) for x,y in zip(dense_ref_top,comp_top)])),
            'full_q_target_hit_at5':float(np.mean([int(t) in ids for t,ids in zip(targets,full_top)])),
            'base_residual_q_target_hit_at5':float(np.mean([int(t) in ids for t,ids in zip(targets,comp_top)])),
            # includes 4-byte scalar per vector; base vectors float32 and family map counted for base+residual
            'full_index_estimated_bytes':int((XX.shape[0]*XX.shape[1]*bits+7)//8+4*XX.shape[0]),
            'base_residual_estimated_bytes':int(XB.nbytes+(d_dense.shape[0]*d_dense.shape[1]*bits+7)//8+4*d_dense.shape[0]+4*len(family)),
        }
    dense_results['reference_target_hit_at5']=float(np.mean([int(t) in ids for t,ids in zip(targets,dense_ref_top)]))
    dense_results['base_only_target_hit_at5']=float(np.mean([int(t) in ids for t,ids in zip(targets,dense_base_top)]))
    dense_results['svd_fit_and_project_seconds']=time.perf_counter()-tsvd

    storage_full=zipped_count(X)
    storage_base=zipped_count(B)
    storage_delta=zipped_count(D)
    base_total=storage_base['zstd3_bytes']+storage_delta['zstd3_bytes']+len(Z.compress(family.astype(np.int32).tobytes()))+len(Z.compress(norm.astype(np.float32).tobytes()))
    # independent full index also stores document norms
    full_total=storage_full['zstd3_bytes']+len(Z.compress(norm.astype(np.float32).tobytes()))
    result={
      'description':'150 real local technical-document bases with 10 controlled synthetic revisions; lexical TF-IDF scoring and linear SVD proxy, NOT neural embedding RAG',
      'data':{'base_docs':len(bases),'versions_per_base':10,'logical_docs':len(docs),'raw_bytes':sum(len(x.encode()) for x in docs),'queries':len(queries),'features':X.shape[1]},
      'tfidf':{'full_index_csr':storage_full,'shared_base_csr':storage_base,'delta_csr':storage_delta,
          'full_index_zstd_total_bytes':full_total,'base_delta_zstd_total_bytes':base_total,
          'max_element_reconstruction_error':max_recon_err,'max_score_abs_error':score_error,
          'exact_top5_set_matches':matched,'query_count':len(queries),
          'full_scores_batch_time':t_full,'base_delta_scores_batch_time':t_delta,
          'labeled_target_mrr_at5_full':float(full_mrr),'labeled_target_mrr_at5_base_only':float(base_mrr)},
      'safe_pruning':{'query_count':len(qsel),'correct_top5_sets':ok,
          'avg_docs_exactly_scored':float(np.mean(counts)),
          'median_docs_exactly_scored':float(np.median(counts)),
          'p95_docs_exactly_scored':float(np.quantile(counts,.95)),
          'total_document_count':len(docs),'total_python_query_seconds':bound_t,
          'note':'Scans all document-level bounds in Python; counts are avoided exact residual dot evaluations, not a measured latency speedup.'},
      'dense_svd_proxy':dense_results,
      'limitations':['Models are TF-IDF and linear SVD, not contextual neural embeddings.',
                     'Synthetic version-specific queries and synthetic edits over real background text.',
                     'Counts include CSR arrays, family map, norms; exclude shared vectorizer vocabulary and model, equal across alternatives.',
                     'Dense quantization storage estimates omit some alignment and indexing overhead; treat as lower bounds.',
                     'Timing uses warm-cache CPU microbenchmarks with no isolation; not production latency.',
                     'Correct topk means score identity under TF-IDF, not correctness of an LLM answer.']}
    out=Path('/mnt/data/cdg_round2/cdg_semantic_results.json');out.write_text(json.dumps(result,indent=2))
    print(json.dumps({
        'tfidf_full_bytes':full_total,'tfidf_shared_bytes':base_total,'top5_matches':matched,
        'bound_mean_refinements':float(np.mean(counts)),
        'svd':dense_results
    },indent=2),flush=True)
    return result

if __name__=='__main__':run()
