#!/usr/bin/env python3
"""Mixed-workload test of shared-base + changed-region retrieval vs chunk dedup.
Not a neural RAG benchmark; all question labels constructed from known source features.
"""
import json,collections,time,re,hashlib,random
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from cdg_semantic_probe import corpus,Z,pack_csr
from cdg_experiment_suite import chunk_lines
from cdg_diff_aware_probe import KW,MAXF,change_context


def run():
    bases,docs,family,version_questions,version_targets=corpus()
    freq=TfidfVectorizer(max_features=MAXF,**KW).fit(docs)
    analyzer=freq.build_analyzer(); changed=[];changedpairs=[];changes=set()
    for doc,f in zip(docs,family):
        a,b=change_context(bases[int(f)],doc)
        changed.append(a)
        changes.update(analyzer(a)); changes.update(analyzer(b))
    count_all=collections.Counter()
    for doc in docs:count_all.update(analyzer(doc))
    keep=set(changes)
    for t,_ in count_all.most_common():
        if len(keep)>=MAXF:break
        keep.add(t)
    vec=TfidfVectorizer(vocabulary=sorted(keep),**KW).fit(docs)
    B=vec.transform(bases);X=vec.transform(docs);C=vec.transform(changed)
    # Construct previously unchanged 'general' queries by selecting relatively discriminative 
    # source terms per family. This is a diagnostic source lookup test, not human query relevance.
    names=np.array(vec.get_feature_names_out())
    general=[];general_families=[]
    for f in range(len(bases)):
        row=B.getrow(f)
        top=np.argsort(-row.data)[:min(20,row.nnz)]
        terms=[]
        for j in top:
            x=names[row.indices[j]]
            if (len(x)>5 and not any(y in x for y in ['project_','audit','revision_','status_','metric_'])
                and not x.startswith('cdg')):
                terms.append(x)
            if len(terms)>=5:break
        if len(terms)<3:continue
        general.append(' '.join(terms[:5])); general_families.append(f)
    queries=version_questions+general
    Q=vec.transform(queries)
    family_vec=(Q@B.T).toarray()
    changed_vec=(Q@C.T).toarray()
    doc_full=(Q@X.T).toarray()
    mixed=np.maximum(family_vec[:,family],changed_vec)
    # Chunk dedup baseline. Same protected vocabulary and synthetic query set.
    unique=[];hmap={};occ_owners=[];occ_chunk_ids=[];full_chunks=[]
    for did,d in enumerate(docs):
        for chunk in chunk_lines(d.encode('utf8'),target=1100):
            st=chunk.decode('utf8','replace')
            full_chunks.append(st)
            h=hashlib.sha256(chunk).digest()
            if h not in hmap:hmap[h]=len(unique); unique.append(st)
            occ_chunk_ids.append(hmap[h]);occ_owners.append(did)
    occ_chunk_ids=np.asarray(occ_chunk_ids,np.int32);occ_owners=np.asarray(occ_owners,np.int32)
    U=vec.transform(unique)
    t0=time.perf_counter()
    sim=(Q@U.T).toarray()
    chunk_doc=np.full((len(queries),len(docs)),-1,np.float32)
    for i in range(len(queries)):
        np.maximum.at(chunk_doc[i],occ_owners,sim[i,occ_chunk_ids])
    chunk_s=time.perf_counter()-t0
    nversion=len(version_questions)
    def ver_stats(scores):
        top=np.argsort(-scores[:nversion],axis=1,kind='stable')[:,:5]
        return {'hit_at5':float(np.mean([int(t) in row for t,row in zip(version_targets,top)])),
                'hit_at1':float(np.mean(top[:,0]==version_targets))}
    def gen_stats(scores):
        # We only ask the family to be found; all 10 versions contain the same general source text.
        s=np.stack([scores[nversion:,family==f].max(axis=1) for f in range(len(bases))],axis=1)
        top=np.argsort(-s,axis=1,kind='stable')[:,:5]
        target=np.array(general_families)
        return {'family_hit_at5':float(np.mean([int(t) in row for t,row in zip(target,top)])),
                'family_hit_at1':float(np.mean(top[:,0]==target))}
    metrics={name:{'version_queries':ver_stats(score),'general_queries':gen_stats(score)}
             for name,score in [('full_document',doc_full),('base_plus_changed_region',mixed),('deduplicated_chunk',chunk_doc)]}
    # Compressed index sizes count the actual CSR binary arrays and the explicit reference tables.
    familymap=len(Z.compress(family.astype(np.int32).tobytes()))
    dedupmap=len(Z.compress(occ_chunk_ids.tobytes()+occ_owners.tobytes()))
    data={'data':{'families':len(bases),'documents':len(docs),'version_queries':nversion,
                    'general_source_lookup_queries':len(general),'unique_chunks':len(unique),'chunk_occurrences':len(full_chunks)},
          'metrics':metrics,
          'search_index_zstd_bytes':{
              'full_document':len(Z.compress(pack_csr(X))),
              'base_plus_changed_region':len(Z.compress(pack_csr(B)))+len(Z.compress(pack_csr(C)))+familymap,
              'deduplicated_chunk':len(Z.compress(pack_csr(U)))+dedupmap,
          },
          'dedup_chunk_search_batch_seconds':chunk_s,
          'limitations':[
            'General queries are generated from distinctive TF-IDF words of each document family, not written by humans.',
            'Version queries concern synthetic record changes, not naturally occurring revisions.',
            'Only the revision-derived changed region is indexed in second channel; real changes may span many passages.',
            'Lexical vector spaces only; no contextual semantic embeddings or generative answer testing.',
            'Source content compression excluded from index-only numbers; codec/decoder/vocabulary excluded equally.',
            'Query and data layout are favorable to version-aware methods; gains may disappear in heterogeneous corpora.'
          ]}
    path='/mnt/data/cdg_round2/cdg_two_channel_results.json'
    with open(path,'w') as f:json.dump(data,f,indent=2)
    print(json.dumps(data,indent=2))
if __name__=='__main__':run()
