#!/usr/bin/env python3
"""Ablation: whether contextualized residual retrieval beats full-document scoring AND passage indexing.
Seed documents are real local docs, changes and qrels are synthetic. No neural retriever involved.
"""
import json, time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from cdg_semantic_probe import corpus


def hit_mrr(scores,targets,k=5):
    order=np.argsort(-scores,axis=1,kind='stable')[:,:k]
    hits=np.array([int(t) in row for t,row in zip(targets,order)])
    mrr=[]
    for t,row in zip(targets,order):
        matches=np.where(row==t)[0]
        mrr.append(1./(matches[0]+1) if len(matches) else 0.)
    return {'hit_at5':float(np.mean(hits)),'mrr_at5':float(np.mean(mrr)),'hit_at1':float(np.mean(order[:,0]==targets))}

def run():
    bases,docs,family,queries,targets=corpus()
    # True revised span is known here, not inferred. In realistic data use version diff + a short context window.
    audit_spans=[d.split('Audit for project_')[-1] for d in docs]
    audit_spans=['Audit for project_'+x for x in audit_spans]
    tf=TfidfVectorizer(ngram_range=(1,2),dtype=np.float32,max_features=24000,norm='l2',token_pattern=r'(?u)\b\w\w+\b')
    X=tf.fit_transform(docs)
    B=tf.transform(bases)
    A=tf.transform(audit_spans)
    Q=tf.transform(queries)
    # Compare the exact same TF-IDF encoder with the only change being what is indexed.
    full=(Q@X.T).toarray()
    audit=(Q@A.T).toarray()
    family_score=(Q@B.T).toarray()
    fam_best=np.argsort(-family_score,axis=1,kind='stable')[:,:5]
    # Route to top 5 base document families; then search audit spans only in those families.
    routed=audit.copy()
    family_mask=np.zeros_like(routed,dtype=bool)
    for i,ids in enumerate(fam_best):family_mask[i]=np.isin(family,ids)
    routed[~family_mask]=-1e6
    # A weak hybrid score; base relevance helps identify the family but conflates semantically similar versions.
    # Normalized score in [0,1] for nonnegative TFIDF features.
    hybrid=.2*family_score[:,family]+.8*audit
    results={
       'description':'Controlled queries identifying explicitly changed synthetic facts inside 150 real technical-document bases (1500 versions).',
       'methods':{
         'full_document_tfidf':hit_mrr(full,targets),
         'revision_span_tfidf':hit_mrr(audit,targets),
         'family_route_top5_then_span':hit_mrr(routed,targets),
         'family_plus_span_hybrid':hit_mrr(hybrid,targets),
       },
       'family_router_top5_contains_true_family':float(np.mean([int(family[t]) in row for t,row in zip(targets,fam_best)])),
       'limitations':[
           'The revised sentence is isolated with a known delimiter. Inferring evidence spans remains unsolved.',
           'A chunked RAG baseline can isolate the same span; this is not a CDG-specific gain.',
           'Queries explicitly identify the controlled project and revision.',
           'No real relevance judgments, pretrained embedding model, LLM generation, or measured SSD latency.'
       ]
    }
    path='/mnt/data/cdg_round2/cdg_fact_retrieval_results.json'
    with open(path,'w') as f:json.dump(results,f,indent=2)
    print(json.dumps(results,indent=2))
if __name__=='__main__':run()
