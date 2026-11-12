#!/usr/bin/env python3
"""Controlled stress test: standard feature-budget truncation vs schema-protected terms.

Note artificial labels, known schema and synthetic queries. The point is failure detection,
not a novel retrieval algorithm. Same 24,000 feature budget in primary comparison.
"""
import json, collections, re, time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from cdg_semantic_probe import corpus, Z, pack_csr

MAX_FEATURES=24000

def hit_scores(scores,targets,k=5):
    top=np.argsort(-scores,axis=1,kind='stable')[:,:k]
    return {'hit_at1':float(np.mean(top[:,0]==targets)),
            'hit_at5':float(np.mean([t in row for t,row in zip(targets,top)])),
            'mrr_at5':float(np.mean([1./(int(np.where(row==t)[0][0])+1) if t in row else 0 for t,row in zip(targets,top)]))}

def run():
    bases,docs,families,queries,targets=corpus()
    kw={'ngram_range':(1,2),'dtype':np.float32,'token_pattern':r'(?u)\b\w\w+\b','norm':'l2'}
    default=TfidfVectorizer(max_features=MAX_FEATURES,**kw)
    t0=time.perf_counter()
    default.fit(docs)
    orig_vocab=set(default.vocabulary_)
    # Protected features selected solely from known entity/attribute token schema in documents.
    # No query label, query score, or held-out query text is used.
    analyzer=default.build_analyzer()
    protected=collections.Counter()
    frequencies=collections.Counter()
    for doc in docs:
        terms=analyzer(doc)
        frequencies.update(terms)
        # Metadata recognition is deliberately given the schema used to generate the synthetic revisions.
        for token in terms:
            atoms=token.split(' ')
            if any(atom.startswith(('project_','metric_','revision_','status_','regulatory_waiver_')) for atom in atoms):
                protected[token]+=1
    # Reserve all controlled fact terms and bigrams; remaining budget is allocated by corpus frequency.
    keep=set(protected)
    ordered=[term for term,_ in frequencies.most_common() if term not in keep]
    assert len(keep)<MAX_FEATURES,len(keep)
    keep.update(ordered[:MAX_FEATURES-len(keep)])
    assert len(keep)==MAX_FEATURES
    schema=TfidfVectorizer(vocabulary=sorted(keep),**kw)
    full=TfidfVectorizer(**kw)
    results={}
    for name,encoder in [('frequency_top24k',default),('schema_protected_24k',schema),('unlimited_features',full)]:
        if name!='frequency_top24k': encoder.fit(docs)
        X=encoder.transform(docs); Q=encoder.transform(queries)
        # Build revision span for passage-indexing control.
        spans=['Audit for project_'+d.split('Audit for project_')[-1] for d in docs]
        A=encoder.transform(spans)
        full_scores=(Q@X.T).toarray()
        span_scores=(Q@A.T).toarray()
        Xc=len(Z.compress(pack_csr(X)))
        Ac=len(Z.compress(pack_csr(A)))
        results[name]={'features':X.shape[1],'index_zstd_bytes_full_docs':Xc,
                       'index_zstd_bytes_revision_spans':Ac,
                       'full_doc':hit_scores(full_scores,targets),
                       'revision_span':hit_scores(span_scores,targets)}
    out={'data':{'docs':len(docs),'queries':len(queries),'fixed_vocabulary_budget':MAX_FEATURES},
         'protected_feature_count':len(protected),
         'rare_schema_terms_originally_missing':sum(1 for x in protected if x not in orig_vocab),
         'examples_missing':sorted([t for t in protected if t not in orig_vocab])[:15],
         'results':results,
         'limitations':['All edited facts are synthetic with a known metadata token schema.',
                        'Schema-protected feature selection is established practice; this is a diagnostic baseline.',
                        'Revision spans are extracted using a known delimiter, not learned or inferred.',
                        'No generative model, actual semantic embedding, or end-to-end RAG evaluation.',
                        'These comparisons use compressed float32 CSR structures rather than optimized inverted indexes.']}
    path='/mnt/data/cdg_round2/cdg_rare_fact_results.json'
    with open(path,'w') as f:json.dump(out,f,indent=2)
    print(json.dumps(out,indent=2))
if __name__=='__main__':run()
