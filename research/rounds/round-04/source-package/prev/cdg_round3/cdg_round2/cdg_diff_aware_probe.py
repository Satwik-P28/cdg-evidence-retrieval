#!/usr/bin/env python3
"""Ablation: automatically protect version-difference terms in compressed retrieval vocabulary.

Train-side signal: only document base/version differences, never queries or relevance labels.
Target synthetic generated version-specific fields make this an engineered stress test,
not a real-world semantic or RAG benchmark.
"""
import json,collections,time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from cdg_semantic_probe import corpus,Z,pack_csr

MAXF=24000
KW=dict(ngram_range=(1,2),dtype=np.float32,token_pattern=r'(?u)\b\w\w+\b',norm='l2')

def change_context(old,new):
    a=old.splitlines(); b=new.splitlines()
    prefix=0
    while prefix<min(len(a),len(b)) and a[prefix]==b[prefix]: prefix+=1
    suffix=0
    while suffix<min(len(a)-prefix,len(b)-prefix) and a[len(a)-1-suffix]==b[len(b)-1-suffix]:suffix+=1
    # One line of context around a changed region. Empty documents get empty windows.
    alo=max(0,prefix-1); ahi=min(len(a),len(a)-suffix+1)
    blo=max(0,prefix-1); bhi=min(len(b),len(b)-suffix+1)
    a_win='\n'.join(a[alo:ahi]);b_win='\n'.join(b[blo:bhi])
    if not b_win:b_win='\n'.join(b[max(0,len(b)-2):])
    return b_win,a_win

def recall(S,targets,k=5):
    top=np.argsort(-S,axis=1,kind='stable')[:,:k]
    return {f'hit_at{k}':float(np.mean([t in x for t,x in zip(targets,top)])),
            'hit_at1':float(np.mean(top[:,0]==targets))}

def run():
    bases,docs,family,queries,targets=corpus()
    freq=TfidfVectorizer(max_features=MAXF,**KW).fit(docs)
    default=set(freq.vocabulary_)
    analyzer=freq.build_analyzer()
    counter=collections.Counter()
    changed=[]
    for d,f in zip(docs,family):
        after,before=change_context(bases[int(f)],d)
        changed.append(after)
        # Both additions and deletions matter for version-sensitive indexing.
        counter.update(set(analyzer(after)) | set(analyzer(before)))
    # Keep all tokens involved in a changed region, then fill rest by frequency.
    reserve=set(counter)
    # Frequency approximation uses the published base frequency ranking from sklearn selected vocab,
    # followed by full corpus frequency for any additional slots.
    if len(reserve)>MAXF:
        reserve={x for x,_ in counter.most_common(MAXF)}
    count_all=collections.Counter()
    for d in docs:count_all.update(analyzer(d))
    keep=set(reserve)
    for x,_ in count_all.most_common():
        if len(keep)==MAXF:break
        keep.add(x)
    assert len(keep)==MAXF
    protected=TfidfVectorizer(vocabulary=sorted(keep),**KW).fit(docs)
    out={'data':{'documents':len(docs),'queries':len(queries),'vocabulary_budget':MAXF},
         'detected_changed_vocabulary_features':len(counter),
         'original_frequency_vocab_missing_change_features':sum(1 for t in counter if t not in default),
         'results':{},'limitations':[
            'Changes are synthetic and usually occupy a single known line in each technical document.',
            'Diff detection uses common unchanged line prefix and suffix, not a general-purpose minimal diff.',
            'Both methods have the same feature count but different vocabularies; known revised queries favor change preservation.',
            'Does not measure neural embedding retrieval or RAG generation.',
            'A standard chunk index can solve the same synthetic query task; this experiment does not prove novelty.']}
    for name,enc in [('frequency_24k',freq),('automatic_diff_protected_24k',protected)]:
        XX=enc.transform(docs); QQ=enc.transform(queries); CC=enc.transform(changed)
        full=(QQ@XX.T).toarray()
        diff=(QQ@CC.T).toarray()
        out['results'][name]={
          'full_document':recall(full,targets),
          'changed_region':recall(diff,targets),
          'full_index_zstd_bytes':len(Z.compress(pack_csr(XX))),
          'changed_region_index_zstd_bytes':len(Z.compress(pack_csr(CC))),
          'retained_changed_features':sum(1 for t in counter if t in enc.vocabulary_),
        }
    path='/mnt/data/cdg_round2/cdg_diff_aware_results.json'
    with open(path,'w') as f:json.dump(out,f,indent=2)
    print(json.dumps(out,indent=2))
if __name__=='__main__':run()
