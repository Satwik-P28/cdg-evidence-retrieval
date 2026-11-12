#!/usr/bin/env python3
"""BM25 control on real noVNC git revision history, strict query-target mapping.
No neural model, no human relevance judgments. Source corpus from local git.
"""
import json,random,re,time
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from scipy import sparse
from git_history_retrieval import create, Z, pack
OUT=Path(__file__).parent

def prep(s):
 s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s)
 return s.replace('_',' ').replace('.',' ').lower()

def bm25_weights(X):
 X=X.tocsr();N,T=X.shape
 lengths=np.asarray(X.sum(axis=1)).reshape(-1)
 average=float(np.mean(lengths))
 df=np.bincount(X.indices,minlength=T)
 idf=np.log(1+(N-df+0.5)/(df+0.5))
 W=X.copy().astype(np.float32)
 lens=np.repeat(lengths,np.diff(X.indptr))
 norm=1.2*(1-0.75+0.75*lens/max(average,1))
 W.data=(X.data*2.2/(X.data+norm))*idf[X.indices]
 return W

def metric(S):
 order=np.argsort(-S,axis=1,kind='stable')
 ranks=(order==np.arange(len(S))[:,None]).argmax(axis=1)+1
 return {'hit1':round(float(np.mean(ranks<=1)),4),'hit5':round(float(np.mean(ranks<=5)),4),
  'hit10':round(float(np.mean(ranks<=10)),4),'mrr10':round(float(np.mean((ranks<=10)/ranks)),4),
  'zero_positive':int(np.sum(S.diagonal()<=0))}

def run():
 samples=create(250)
 full=[s['after'] for s in samples]; diff=[s['changed'] for s in samples];queries=[s['message'] for s in samples]
 # Same vocabulary; no frequency cap, standard BM25 k1=1.2, b=.75.
 vec=CountVectorizer(preprocessor=prep,ngram_range=(1,1),token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
 V=vec.fit_transform(full+diff)
 X=V[:len(samples)];D=V[len(samples):];Q=vec.transform(queries)
 WX=bm25_weights(X);WD=bm25_weights(D)
 S=(Q@WX.T).toarray();T=(Q@WD.T).toarray()
 # Score rank normalization allows fusion of two independently-scaled BM25 vectors.
 def norm(A):return A/np.maximum(A.max(axis=1,keepdims=True),1e-8)
 Fs=norm(S);Fd=norm(T)
 vals={}
 vals['full_bm25']=metric(S)
 vals['diff_bm25']=metric(T)
 for w in [.25,.50,.75]:vals[f'fusion_diff_weight_{w}']=metric((1-w)*Fs+w*Fd)
 # Explicit temporal test: earliest commits in the selected subset are the tail,
 # newest commits at front. No trained weights; compare all three pre-fixed fusion ratios.
 temporal={}
 half=len(samples)//2
 for label,ind in [('newer_half',np.arange(0,half)),('older_half',np.arange(half,len(samples)))]:
  # Full database stays unchanged, but queries are subset. Target index is original sample id.
  vv={}
  for name,mat in [('full',S),('diff',T),('fusion_.25',.75*Fs+.25*Fd),('fusion_.50',.5*Fs+.5*Fd),('fusion_.75',.25*Fs+.75*Fd)]:
   rows=np.argsort(-mat[ind],axis=1,kind='stable')[:,:5]
   vv[name]=round(float(np.mean([i in row for i,row in zip(ind,rows)])),4)
  temporal[label]=vv
 blob={
  'data':{'repo':'/opt/novnc','real_commits':len(samples),'unique_files':len(set(s['path'] for s in samples)),
  'query_type':'human-written single-file commit messages, labels from git history, not human relevance judgments'},
  'bm25':vals,'temporal_split_hit5':temporal,
  'indexes_zstd':{'full':len(Z.compress(pack(WX))),'diff':len(Z.compress(pack(WD))),
                 'both':len(Z.compress(pack(WX)))+len(Z.compress(pack(WD))),
                 'vocab':len(Z.compress(json.dumps(vec.vocabulary_).encode()))},
  'characters':{'full':sum(map(len,full)),'changed':sum(map(len,diff))},
  'limitations':['No pretrained semantic model.','Exact revision matching may penalize semantically related file versions.',
  'The same dataset contains duplicate file paths across revisions, yielding hard near-duplicate retrieval.','Diff includes removed text for pure deletions: correct for edit-history search but not current-state factual QA.',
  'No dataset-level cross-validation or external repository held-out test.']}
 (OUT/'real_git_bm25_results.json').write_text(json.dumps(blob,indent=2))
 print(json.dumps(blob,indent=2))
if __name__=='__main__':run()
