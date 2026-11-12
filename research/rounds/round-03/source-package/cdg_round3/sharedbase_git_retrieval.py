#!/usr/bin/env python3
"""Real-change query retrieval with 1 shared index per source path + changed-region index.
EVALUATION is commit-message exact-revision retrieval, not general RAG.
"""
import json,re,time,statistics,collections
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from git_history_retrieval import create, pack,Z
OUT=Path(__file__).parent

def prep(s):return re.sub(r'([a-z])([A-Z])',r'\1 \2',s).replace('_',' ').replace('.',' ').lower()

def metrics(scores):
 top=np.argsort(-scores,axis=1,kind='stable')
 ranks=np.where(top==np.arange(len(scores))[:,None])[1]+1
 return {'Hit@1':round(float(np.mean(ranks<=1)),4),'Hit@5':round(float(np.mean(ranks<=5)),4),'Hit@10':round(float(np.mean(ranks<=10)),4)}

def run():
 samples=create(250)
 full=[s['after'] for s in samples];changes=[s['changed'] for s in samples];qs=[s['message'] for s in samples]
 ids={};canonical=[];family=[]
 for s in samples:
  if s['path'] not in ids:
   ids[s['path']]=len(ids)
   canonical.append(s['after']) # most recent sampled revision per path
  family.append(ids[s['path']])
 family=np.asarray(family,dtype=np.int32)
 v=TfidfVectorizer(preprocessor=prep,ngram_range=(1,2),sublinear_tf=True,norm='l2',token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
 v.fit(full+changes)
 X=v.transform(full);D=v.transform(changes);B=v.transform(canonical);Q=v.transform(qs)
 def compute():
  f=(Q@X.T).toarray();c=(Q@D.T).toarray();b=(Q@B.T).toarray()[:,family]
  return f,c,b
 # Warm and timed batches.
 for i in range(3): f,c,b=compute()
 times=[]
 for i in range(12):
  t=time.perf_counter();f,c,b=compute();times.append(time.perf_counter()-t)
 blend=.7*c+.3*b
 prev=.7*c+.3*f
 # Strong comparator: changed-region only; makes clear whether base helps.
 variants={'full_file':metrics(f),'changed_region':metrics(c),'full_plus_change':metrics(prev), 'shared_path_base_plus_change':metrics(blend),
           'shared_base_only':metrics(b)}
 sizes={'full_file_zstd':len(Z.compress(pack(X))), 'changed_region_zstd':len(Z.compress(pack(D))),
  'shared_path_base_zstd':len(Z.compress(pack(B))), 'family_ref_zstd':len(Z.compress(family.tobytes())),
  'full_plus_change_total_zstd':len(Z.compress(pack(X)))+len(Z.compress(pack(D))),
  'base_plus_change_total_zstd':len(Z.compress(pack(B)))+len(Z.compress(pack(D)))+len(Z.compress(family.tobytes()))}
 obj={'dataset':'250 real noVNC single-file commits from 56 paths, human commit subjects as queries and exact commit revision as target',
  'representations':variants, 'index_bytes':sizes,'scoring_batch_median_seconds':round(statistics.median(times),5),
  'limitations':['Base per path is most recent sampled after-file. It is not a verified common-content intersection across versions.',
   'This tests version-specific human commit messages. Unchanged-fact or arbitrary old-version lookup may fail without a fuller overlay.',
   'No learned neural embeddings, only sparse TF-IDF. No model loading or generation time.',
   'Index sizes exclude shared vocabulary and source archive; include compressed per-document family references.',
   'Strong full+change baseline has similar code-aware tokenization; qrels auto-created from Git not expert annotations.']}
 (OUT/'real_git_sharedbase_results.json').write_text(json.dumps(obj,indent=2))
 print(json.dumps(obj,indent=2))
if __name__=='__main__':run()
