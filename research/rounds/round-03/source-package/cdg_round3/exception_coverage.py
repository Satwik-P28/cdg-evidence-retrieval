#!/usr/bin/env python3
"""Repair shared-base+diff retrieval's lexical coverage holes via provenance-bearing exception lines.
All exception lines are exact bytes from the corresponding historical source version.
Does not yet guarantee arbitrary phrase, positional, or semantic retrieval completeness.
"""
import re,json,statistics,collections
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from git_history_retrieval import create,Z,pack
OUT=Path(__file__).parent

def prep(s):return re.sub(r'([a-z])([A-Z])',r'\1 \2',s).replace('_',' ').replace('.',' ').lower()

def metric(A):
 top=np.argsort(-A,axis=1,kind='stable');ranks=np.where(top==np.arange(A.shape[0])[:,None])[1]+1
 return {'hit1':round(float(np.mean(ranks<=1)),4),'hit5':round(float(np.mean(ranks<=5)),4),'hit10':round(float(np.mean(ranks<=10)),4)}

def run():
 samps=create(250)
 canonical={}
 for s in samps:canonical.setdefault(s['path'],s['after'])
 names=list(canonical);fmap={name:i for i,name in enumerate(names)}
 family=np.array([fmap[s['path']] for s in samps],np.int32)
 canon=[canonical[name] for name in names]
 full=[s['after'] for s in samps];changed=[s['changed'] for s in samps]
 vec=TfidfVectorizer(preprocessor=prep,ngram_range=(1,2),sublinear_tf=True,norm='l2',token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
 analyzer=vec.build_analyzer()
 # Greedy length-conscious cover of absent unigram features with verbatim lines of evidence.
 def words(text):
  return set(re.findall(r'(?u)\b[a-z][a-z0-9]+\b',prep(text)))
 extra=[];lost0=0;d_missing=0;linecounts=[]
 for i,s in enumerate(samps):
  have=words(canonical[s['path']])|words(s['changed'])
  missing=words(s['after'])-have
  lost0+=len(missing);d_missing+=bool(missing)
  lines=s['after'].splitlines(keepends=True)
  line_infos=[]
  for j,ln in enumerate(lines):
   cover=words(ln)&missing
   if cover:line_infos.append((j,ln,cover))
  chosen=[];uncovered=set(missing)
  while uncovered:
   best=max(line_infos,key=lambda x:len(x[2]&uncovered)/max(len(x[1]),1),default=None)
   if not best or len(best[2]&uncovered)==0:raise AssertionError('uncoverable token')
   chosen.append(best);uncovered-=best[2]
  chosen=sorted(chosen,key=lambda x:x[0]);joined=''.join(x[1] for x in chosen)
  assert missing<=words(joined)
  extra.append(joined);linecounts.append(len(chosen))
 vec.fit(full+changed+extra)
 B=vec.transform(canon);D=vec.transform(changed);E=vec.transform(extra);X=vec.transform(full);Q=vec.transform([s['message'] for s in samps])
 f=(Q@X.T).toarray();d=(Q@D.T).toarray();e=(Q@E.T).toarray();b=(Q@B.T).toarray()[:,family]
 scores={'full':f,'base_plus_delta':.3*b+.7*d,
         'base_plus_delta_plus_exceptions_max':.3*b+.7*np.maximum(d,e),
         'base_plus_delta_plus_exceptions_sum':.25*b+.60*d+.15*e}
 results={k:metric(v) for k,v in scores.items()}
 sizes={'full_index':len(Z.compress(pack(X))),
 'base_index':len(Z.compress(pack(B))),
 'diff_index':len(Z.compress(pack(D))),
 'exception_index':len(Z.compress(pack(E))),
 'family_ref':len(Z.compress(family.tobytes())),
 'two_channel':len(Z.compress(pack(B)))+len(Z.compress(pack(D)))+len(Z.compress(family.tobytes())),
 'three_channel':len(Z.compress(pack(B)))+len(Z.compress(pack(D)))+len(Z.compress(pack(E)))+len(Z.compress(family.tobytes())),
 'exception_text_zstd':len(Z.compress('\n'.join(extra).encode('utf8')))}
 # lexical 1-gram coverage contract, not actual retrieval ranking guarantee.
 post_missing=sum(len(words(s['after'])-(words(canonical[s['path']])|words(s['changed'])|words(ex))) for s,ex in zip(samps,extra))
 obj={'dataset':'250 real noVNC changed-file versions; human commit messages; one shared base per path.',
  'before':{'docs_with_unindexed_terms':d_missing,'missing_distinct_term_occurrences':lost0},
  'exception_channel':{'docs_with_exception_lines':sum(bool(x) for x in extra),'total_exception_lines':sum(linecounts),'avg_exception_lines_per_doc':round(statistics.mean(linecounts),3),
       'total_exception_text_bytes':sum(len(x.encode('utf8')) for x in extra),
       'remaining_missing_unigrams':post_missing},
  'metrics':results,'index_bytes':sizes,
  'limits':['Unigram coverage is complete by construction for this sample, not phrase/semantic completeness.','Exception extraction uses exact original lines, not LLM-generated replacements.','Index sizes exclude shared vocabulary and codec model; text snapshots still need lossless source archive.','One source repository, heuristic qrels and lexical retriever, no actual RAG QA accuracy.']}
 (OUT/'real_git_exception_results.json').write_text(json.dumps(obj,indent=2))
 print(json.dumps(obj,indent=2))
if __name__=='__main__':run()
