#!/usr/bin/env python3
"""Strong lexical passage baseline, with optional exact deduplication of passages.
Synthetic version queries on real tech documentation. This tests if proposed diff indexes
have an advantage over ordinary chunking, and counts chunk-to-doc mappings.
"""
import json,hashlib,collections,time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from cdg_semantic_probe import corpus,Z,pack_csr
from cdg_experiment_suite import chunk_lines
from cdg_diff_aware_probe import change_context,MAXF,KW,recall

def chunk_list(document):
    return [x.decode('utf8','replace') for x in chunk_lines(document.encode('utf8'),target=1100)]

def run():
    bases,docs,family,queries,targets=corpus()
    original_vocab=TfidfVectorizer(max_features=MAXF,**KW).fit(docs)
    analyzer=original_vocab.build_analyzer()
    changed=[];changed_both=[]
    for i,d in enumerate(docs):
        new,old=change_context(bases[int(family[i])],d)
        changed.append(new);changed_both.append(new+'\n'+old)
    # Same automatic diff-aware vocabulary as preceding experiment.
    change_terms=set()
    for d in changed_both:change_terms.update(analyzer(d))
    import collections
    freq=collections.Counter()
    for d in docs:freq.update(analyzer(d))
    keep=set(change_terms)
    for term,_ in freq.most_common():
        if len(keep)>=MAXF:break
        keep.add(term)
    protected=TfidfVectorizer(vocabulary=sorted(keep),**KW).fit(docs)
    tests={'frequency_24k':original_vocab,'diff_protected_24k':protected}
    chunks=[];owners=[];unique=[];chunk_ids=[];hash_to_id={}
    for docid,d in enumerate(docs):
        for s in chunk_list(d):
            chunks.append(s);owners.append(docid)
            h=hashlib.sha256(s.encode()).digest()
            if h not in hash_to_id:
                hash_to_id[h]=len(unique);unique.append(s)
            chunk_ids.append(hash_to_id[h])
    owners=np.array(owners,dtype=np.int32);chunk_ids=np.array(chunk_ids,dtype=np.int32)
    # Compressed mapping for inverted common-chunk -> all original docs, encoded as occurrence list.
    mapping_payload=owners.tobytes()+chunk_ids.tobytes()
    mapping_size=len(Z.compress(mapping_payload))
    result={'documents':len(docs),'chunks':len(chunks),'unique_chunks':len(unique),
            'chunk_membership_mapping_zstd_bytes':mapping_size,'comparisons':{},
            'cautions':['Chunking by 1.1KB line-aligned groups is one arbitrary baseline; tuned chunking may improve it.',
                'Python reduction loops and BLAS timings are not calibrated latency measurements.',
                'Queries intentionally describe version-specific synthetic audit records.']}
    for name,vec in tests.items():
        Q=vec.transform(queries)
        C=vec.transform(chunks); U=vec.transform(unique)
        t0=time.perf_counter()
        S=(Q@C.T).toarray()
        match_full=np.full((len(queries),len(docs)),-1.,np.float32)
        for qi in range(len(queries)):
            np.maximum.at(match_full[qi],owners,S[qi])
        t_full=time.perf_counter()-t0
        t0=time.perf_counter()
        US=(Q@U.T).toarray()
        match_unique=np.full((len(queries),len(docs)),-1.,np.float32)
        for qi in range(len(queries)):
            np.maximum.at(match_unique[qi],owners,US[qi,chunk_ids])
        t_uniq=time.perf_counter()-t0
        assert np.max(np.abs(match_full-match_unique))<1e-5
        result['comparisons'][name]={
            'ordinary_chunk_index_bytes':len(Z.compress(pack_csr(C)))+len(Z.compress(owners.tobytes())),
            'unique_chunk_index_plus_mapping_bytes':len(Z.compress(pack_csr(U)))+mapping_size,
            'ordinary_chunk_top5':recall(match_full,targets),
            'unique_chunk_top5':recall(match_unique,targets),
            'full_chunk_query_batch_seconds':t_full,
            'dedup_chunk_query_batch_seconds':t_uniq,
        }
    with open('/mnt/data/cdg_round2/cdg_chunk_baseline_results.json','w') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
if __name__=='__main__':run()
