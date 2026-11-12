#!/usr/bin/env python3
"""Real revision retrieval experiment from noVNC git history.
Query: human-written commit subject. Target: actual single changed source revision.
This is a proxy task with noisy auto-derived qrels, NOT end-user RAG relevance.
"""
import subprocess,re,json,time,collections,hashlib,statistics,zlib,sys
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy import sparse
sys.path.insert(0,str(Path(__file__).parent/'cdg_round2'))
from cdg_experiment_suite import Z
REPO='/opt/novnc'
OUT=Path(__file__).parent

def git(*args):
 return subprocess.run(['git','-C',REPO,*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout

def commits():
 b=git('log','-n','1500','--no-merges','--format=@@@%H\t%s','--name-only')
 results=[];curr=None
 for line in b.decode('utf8','replace').splitlines():
  if line.startswith('@@@'):
   if curr:results.append(curr)
   h,msg=line[3:].split('\t',1);curr=[h,msg,[]]
  elif line.strip() and curr:curr[2].append(line.strip())
 if curr:results.append(curr)
 candidates=[]
 for h,msg,paths in results:
  if len(paths)!=1 or not paths[0].endswith(('.js','.md','.mjs','.html','.css')):continue
  if len(msg.split())<3 or msg.lower().startswith(('merge','bump','release','update translation','fix typo')):continue
  candidates.append((h,msg,paths[0]))
 return candidates

def context_diff(before,after):
 import difflib
 a=before.splitlines(keepends=True);b=after.splitlines(keepends=True)
 m=difflib.SequenceMatcher(None,a,b,autojunk=False)
 windows=[]
 for typ,i0,i1,j0,j1 in m.get_opcodes():
  if typ=='equal':continue
  start=max(0,j0-2);stop=min(len(b),j1+2)
  new=''.join(b[start:stop])
  if typ=='delete':new+='\nREMOVED_FROM_PREVIOUS_VERSION '+''.join(a[i0:i1])
  windows.append(new)
 return '\n'.join(windows),len(windows)

def create(limit=250):
 samples=[];paths=set()
 for h,msg,path in commits():
  if len(samples)>=limit:break
  raw=git('show',f'{h}:{path}');prev=git('show',f'{h}^:{path}')
  if not (200<=len(raw)<=150000 and 100<=len(prev)<=150000):continue
  try:after=raw.decode('utf8');before=prev.decode('utf8')
  except UnicodeDecodeError:continue
  if after==before:continue
  changed,n=context_diff(before,after)
  if not (30<=len(changed)<=15000 and n<=30):continue
  samples.append({'sha':h,'message':msg,'path':path,'after':after,'before':before,'changed':changed})
  paths.add(path)
 print('collected',len(samples),'edits',len(paths),'paths',flush=True)
 return samples

def pack(M):
 M=M.tocsr();return M.data.astype('float32').tobytes()+M.indices.astype('int32').tobytes()+M.indptr.astype('int32').tobytes()

def evaluate(samples):
 texts=[s['after'] for s in samples];changes=[s['changed'] for s in samples];qs=[s['message'] for s in samples]
 # Simple code-aware normalization. No query text or relevance labels supplied to index.
 def prep(s):
  s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s)
  s=s.replace('_',' ').replace('.',' ')
  return s.lower()
 vec=TfidfVectorizer(preprocessor=prep,ngram_range=(1,2),min_df=1,sublinear_tf=True,norm='l2',max_features=None,token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
 vec.fit(texts+changes)
 x=vec.transform(texts);d=vec.transform(changes);q=vec.transform(qs)
 full=(q@x.T).toarray(); delta=(q@d.T).toarray()
 hybrid=.7*delta+.3*full
 # Unfair against plain full docs? Report all, index budget counted.
 metrics={}
 for name,scores in [('full_file',full),('change_region_only',delta),('hybrid_70_30',hybrid)]:
  order=np.argsort(-scores,axis=1,kind='stable'); labels=np.arange(len(samples))
  ranks=np.array([int(np.where(order[i]==i)[0][0])+1 for i in labels])
  metrics[name]={'hit_at1':round(float(np.mean(ranks<=1)),4),'hit_at5':round(float(np.mean(ranks<=5)),4),
                 'hit_at10':round(float(np.mean(ranks<=10)),4),'mrr_at10':round(float(np.mean((ranks<=10)/ranks)),4),
                 'zero_score_target':int(np.sum(scores[labels,labels]==0))}
 # Simple index accounting: matrix only, plus shared vocabulary one time.
 sizes={'full_index_zstd_bytes':len(Z.compress(pack(x))), 'diff_index_zstd_bytes':len(Z.compress(pack(d))),
        'both_indexes_zstd_bytes':len(Z.compress(pack(x)))+len(Z.compress(pack(d))),'vocabulary_items':len(vec.vocabulary_),
        'vocab_json_zstd_bytes':len(Z.compress(json.dumps(vec.vocabulary_).encode()))}
 return metrics,sizes

def run():
 samps=create()
 assert len(samps)>100
 m,s=evaluate(samps)
 # Check byte exact reconstruction using source and diff for every real edit.
 import difflib
 recon=0; sizes=[]
 for item in samps:
  old=item['before'].encode();new=item['after'].encode()
  # Reversible with opcode spans at byte line granularity.
  a=old.splitlines(keepends=True);b=new.splitlines(keepends=True)
  ops=[];p=0
  for tag,i0,i1,j0,j1 in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
   if tag!='equal':ops.append([i0,i1,b''.join(b[j0:j1]).decode('utf8')])
  encoded=json.dumps(ops,ensure_ascii=False,separators=(',',':')).encode();comp=Z.compress(encoded,3)
  pp=json.loads(Z.decompress(comp,len(encoded)))
  rebuilt=[];pos=0
  for i0,i1,t in pp:rebuilt.extend(a[pos:i0]);rebuilt.append(t.encode());pos=i1
  rebuilt.extend(a[pos:]);assert b''.join(rebuilt)==new
  recon+=1
  sizes.append({'independent':len(Z.compress(new,3)),'parent_plus_patch':len(Z.compress(old,3))+len(comp),'patch_only':len(comp)})
 obj={'dataset':{'repository':'/opt/novnc (public source git history)','samples':len(samps),'unique_paths':len(set(s['path'] for s in samps)),'human_written_queries':len(samps), 'task':'single-file commit message -> matching changed file-version', 'automated_labels':'same commit SHA and changed source file. No human relevance annotation.'},
 'metrics':m, 'index_storage':s, 'source_pairs':{'independent_after_zstd_bytes':sum(x['independent'] for x in sizes),
            'parent_plus_patch_zstd_bytes':sum(x['parent_plus_patch'] for x in sizes), 'patch_bytes_total':sum(x['patch_only'] for x in sizes),
            'byte_exact_pairs':recon},
 'limitations':['Commits and qrels extracted from one repository, not general RAG questions.','Index sizes exclude source storage and shared normalization model; vocabulary is reported separately.','A full baseline using changed regions with BM25, hybrid neural reranker, and real end-to-end RAG not available here.','Target revision is a single changed file, and commit messages may not mention changed terms.','Deleted content can appear in the special diff channel, which is useful for historical change search but may mislead current-state QA.']}
 (OUT/'real_git_retrieval_results.json').write_text(json.dumps(obj,indent=2))
 (OUT/'real_git_queries.json').write_text(json.dumps([{'sha':s['sha'],'query':s['message'],'path':s['path']} for s in samps],indent=2))
 print(json.dumps(obj,indent=2))
if __name__=='__main__':run()
