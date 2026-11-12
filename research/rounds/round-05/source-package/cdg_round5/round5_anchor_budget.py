#!/usr/bin/env python3
"""CDG Round 5: real revision retrieval with constrained lexical representation.
Human-written commit subjects, auto-derived single target qrels (no RAG/semantic model).
Uses no test queries to build the feature selector.
"""
import sys,re,json,zlib,time,collections
from pathlib import Path
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'cdg_round4'/'prev'/'cdg_round3'))
from git_history_retrieval import create


def prep(s):
    s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s)
    return s.replace('_',' ').replace('.',' ').lower()

def bm25(C):
    C=C.tocsr().astype(np.float32)
    N,V=C.shape
    lens=np.asarray(C.sum(axis=1)).reshape(-1)
    mean=max(float(np.mean(lens)),1)
    df=np.bincount(C.indices,minlength=V)
    idf=np.log(1+(N-df+0.5)/(df+0.5))
    x=C.copy()
    ln=np.repeat(lens,np.diff(C.indptr))
    x.data=(x.data*2.2/(x.data+1.2*(.25+.75*ln/mean)))*idf[x.indices]
    return x

def prep_data():
    samples=create(250)
    full=[s['after'] for s in samples]
    diffs=[s['changed'] for s in samples]
    q=[s['message'] for s in samples]
    vec=CountVectorizer(preprocessor=prep,token_pattern=r'(?u)\b[a-z][a-z0-9]+\b',ngram_range=(1,1))
    counts=vec.fit_transform(full+diffs)
    N=len(samples)
    return samples,vec,counts[:N].tocsr(),counts[N:].tocsr(),vec.transform(q).tocsr()

def index_size(M):
    M=M.tocsr()
    payload=M.data.astype('float32').tobytes()+M.indices.astype('int32').tobytes()+M.indptr.astype('int32').tobytes()
    return len(zlib.compress(payload,6))

def eval_rank(S,ix):
    # qrelevance = target revision id == its query index
    ix=np.asarray(ix)
    order=np.argsort(-S[ix,:],axis=1,kind='stable')
    matched=order==ix[:,None]
    ranks=matched.argmax(axis=1)+1
    return {'hit1':round(float(np.mean(ranks<=1)),4), 'hit5':round(float(np.mean(ranks<=5)),4),
      'hit10':round(float(np.mean(ranks<=10)),4), 'mrr10':round(float(np.mean(np.where(ranks<=10,1/ranks,0))),4)}

def score(W,Q):
    return np.asarray((Q@W.T).toarray(),dtype=np.float32)

def evaluate():
    t0=time.perf_counter();samples,vec,F,D,Q=prep_data();N=len(samples);V=F.shape[1]
    # query sets are split by a fixed hash of sha, not by document text or label
    train=np.array([i for i,s in enumerate(samples) if int(s['sha'][-4:],16)%5<2]); test=np.array([i for i in range(N) if i not in set(train)])
    dfF=np.bincount(F.indices,minlength=V);dfD=np.bincount(D.indices,minlength=V)
    tfF=np.asarray(F.sum(axis=0)).ravel();tfD=np.asarray(D.sum(axis=0)).ravel()
    # Actual cost of index: count separate full and diff postings after BM25 transformations.
    fullbm=bm25(F);diffbm=bm25(D)
    Sf=score(fullbm,Q);Sd=score(diffbm,Q)
    # Fixed normalizations, no query labels; also experiment with a common merged index
    maxF=np.maximum(Sf.max(axis=1,keepdims=True),1e-6);maxD=np.maximum(Sd.max(axis=1,keepdims=True),1e-6)
    Sn=(Sf/maxF+Sd/maxD)/2
    rrF=np.argsort(-Sf,axis=1,kind='stable')
    rrD=np.argsort(-Sd,axis=1,kind='stable')
    ranksF=np.argsort(rrF,axis=1,kind='stable'); ranksD=np.argsort(rrD,axis=1,kind='stable')
    rrf=1/(60+ranksF)+1/(60+ranksD)
    methods={'full_bm25':Sf, 'diff_bm25':Sd,'normalized_fusion':Sn, 'rrf':rrf}
    out={'dataset':{'n':N,'unique_files':len(set(s['path'] for s in samples)),'vocab':V,'split_train':len(train),'split_test':len(test),'query_type':'human-written Git commit subjects; automatic same-commit target'}, 'full_vocab':{}}
    for name,S in methods.items():out['full_vocab'][name]={'train':eval_rank(S,train),'test':eval_rank(S,test),'all':eval_rank(S,np.arange(N))}
    out['storage']={'full_matrix_compressed':index_size(fullbm),'diff_matrix_compressed':index_size(diffbm),'both_matrices_compressed':index_size(fullbm)+index_size(diffbm),'vocab_zlib_bytes':len(zlib.compress(json.dumps(vec.vocabulary_,separators=(',',':')).encode(),6))}
    out['budgets']={}
    # Unsupervised term ranking. Select top unique normalized word features.
    idf=np.log((N+1)/(dfF+1))+1
    global_freq=tfF+tfD
    # 'delta_salience': term frequent in changes compared to full source, with preference for rare terms, selecting automatically
    novelty=np.log1p(tfD)/(np.sqrt(dfF+1))*np.log1p(N/(dfD+1))
    # enforce hybrid of shared and residual terms, allocate 30% to changed salience
    feature_order={
     'frequency':np.argsort(-global_freq,kind='stable'),
     'document_frequency':np.argsort(-dfF,kind='stable'),
     'delta_salience':np.argsort(-novelty,kind='stable')}
    # New shape: materialize full-document scores via a single merged posting matrix for all features,
    # avoiding separate query-time searches, but not preserving independent field normalization.
    for K in [512,1024,2048,4096,8192]:
      if K>=V:continue
      selections={
       'frequency':feature_order['frequency'][:K],
       'diff_only':feature_order['delta_salience'][:K]}
      selected=[];seen=set()
      for x in feature_order['frequency'][:int(K*.7)]:
       x=int(x);seen.add(x);selected.append(x)
      for x in feature_order['delta_salience']:
       x=int(x)
       if x not in seen:
        seen.add(x);selected.append(x)
       if len(selected)>=K:break
      selections['balanced_70_30']=np.array(selected,dtype=np.int64)
      out['budgets'][str(K)]={}
      for strategy,cols in selections.items():
        cols=np.asarray(cols,dtype=int)
        Fi=bm25(F[:,cols]); Di=bm25(D[:,cols]); Qi=Q[:,cols]
        Sfi=score(Fi,Qi); Sdi=score(Di,Qi)
        normfi=Sfi/np.maximum(Sfi.max(axis=1,keepdims=True),1e-6)
        normdi=Sdi/np.maximum(Sdi.max(axis=1,keepdims=True),1e-6)
        blend=(normfi+normdi)/2
        # critical: pooled BM25 weights allow a single physical inverted index
        # fixed 1.0 coefficient in BM25 score space (independent normalized scores can't be premerged)
        merged=Fi+Di
        Smer=score(merged,Qi)
        tok=[vec.get_feature_names_out()[k] for k in cols]
        res={'matrix_bytes':index_size(Fi)+index_size(Di),
            'merged_matrix_bytes':index_size(merged),
            'vocabulary_bytes':len(zlib.compress(json.dumps(tok,separators=(',',':')).encode(),6)),
            'coverage_commits':round(float(np.mean([(Q[i,cols].nnz>0) for i in range(N)])),3),
            'full':eval_rank(Sfi,test),'diff':eval_rank(Sdi,test),'fusion':eval_rank(blend,test), 'merged':eval_rank(Smer,test),
            'train_merged':eval_rank(Smer,train)}
        out['budgets'][str(K)][strategy]=res
    # Robust tests for source-vs-change: delete markers can be historical, not current evidence.
    out['limits']=['No neural encoder available in runtime; lexical BM25, not pretrained semantic retrieval.',
        'Commit message labels are weak automatically derived qrels; version collisions are penalized.',
        'Original source files / indexes and exact source reconstruction stored separately from matrix-byte accounting.',
        'No online dataset or downloadable pretrained models in this container.',
        'Experiment uses only one repository and token unigram BM25; independent domains required.']
    out['duration_seconds']=round(time.perf_counter()-t0,3)
    (ROOT/'round5_results.json').write_text(json.dumps(out,indent=2))
    print('N',N,'V',V,'duration',out['duration_seconds'])
    print('FULL',out['full_vocab'])
    for k,d in out['budgets'].items():
      print('K',k, ' | '.join(f'{a}:fused={v["fusion"]["hit5"]} single={v["merged"]["hit5"]} size={v["merged_matrix_bytes"]}' for a,v in d.items()),flush=True)

if __name__=='__main__':evaluate()
