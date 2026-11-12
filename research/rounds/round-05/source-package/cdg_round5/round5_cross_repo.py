"""Cross-repo validation on nvm actual Git revisions and commit subjects.
Reproduces fixed merged-BM25 family correction, no tuning with test labels."""
import sys,subprocess,re,json,zlib
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from scipy import sparse
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from round5_anchor_budget import bm25,prep,eval_rank,index_size
REPO='/opt/nvm'
def git(*args):
 return subprocess.run(['git','-C',REPO,*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
b=git('log','-n','3000','--no-merges','--format=@@@%H\t%s','--name-only')
commits=[];curr=None
for line in b.decode('utf8','replace').splitlines():
 if line.startswith('@@@'):
  if curr:commits.append(curr)
  h,msg=line[3:].split('\t',1);curr=[h,msg,[]]
 elif line.strip() and curr:curr[2].append(line.strip())
if curr:commits.append(curr)
print('commits',len(commits),flush=True)
samples=[]
for h,msg,paths in commits:
 if len(samples)>=250:break
 if len(paths)!=1 or not paths[0].endswith(('.sh','.md','.js','.html')):continue
 if len(msg.split())<3 or msg.lower().startswith(('merge','bump','release','fix typo')):continue
 path=paths[0]; raw=git('show',f'{h}:{path}'); old=git('show',f'{h}^:{path}')
 if not (100<len(raw)<350000 and 100<len(old)<350000):continue
 try:after=raw.decode('utf8');before=old.decode('utf8')
 except:continue
 if after==before:continue
 import difflib
 a=before.splitlines(keepends=True);c=after.splitlines(keepends=True)
 changed=[]
 for op,i0,i1,j0,j1 in difflib.SequenceMatcher(None,a,c,autojunk=False).get_opcodes():
  if op=='equal':continue
  new=''.join(c[max(0,j0-2):min(len(c),j1+2)])
  if op=='delete':new+='\nREMOVED_FROM_PREVIOUS_VERSION '+' '.join(a[i0:i1])
  changed.append(new)
 if not changed:continue
 diff='\n'.join(changed)
 if not 20<len(diff)<18000:continue
 samples.append({'sha':h,'message':msg,'path':path,'after':after,'changed':diff})
print('samples',len(samples),'paths',len(set(s['path'] for s in samples)),flush=True)
if len(samples)<60:raise SystemExit('insufficient new repository samples')
N=len(samples)
vec=CountVectorizer(preprocessor=prep,token_pattern=r'(?u)\b[a-z][a-z0-9]+\b')
X=vec.fit_transform([s['after'] for s in samples]+[s['changed'] for s in samples]);F=X[:N];D=X[N:];Q=vec.transform([s['message'] for s in samples]);V=F.shape[1]
FW=bm25(F);DW=bm25(D)
Sf=(Q@FW.T).toarray();Sd=(Q@DW.T).toarray();Sm=(Q@(FW+DW).T).toarray()
train=np.array([i for i,s in enumerate(samples) if int(s['sha'][-4:],16)%5<2]);test=np.array([i for i in range(N) if i not in set(train)])
out={'repo':'nvm','n':N,'files':len(set(s['path'] for s in samples)),'vocab':V,'train_n':len(train),'test_n':len(test),
 'scores':{name:{'test':eval_rank(M,test),'all':eval_rank(M,np.arange(N))} for name,M in [('full',Sf),('diff',Sd),('merged',Sm)]},
 'index_compressed_bytes':{'full':index_size(FW),'diff':index_size(DW),'merged':index_size(FW+DW), 'separate':index_size(FW)+index_size(DW)},
 'limitations':['human-written commit subject with automatically constructed same-commit target, not human annotated RAG QA','shell code and documentation only','no neural encoder']}
(ROOT/'round5_cross_repo_results.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
