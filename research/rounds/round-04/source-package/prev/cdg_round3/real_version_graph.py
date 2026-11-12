#!/usr/bin/env python3
"""Real Git version history source compression and access-depth experiment.
Proves byte-exact reconstructions; compares stars, chains, checkpointing, and
workload-aware checkpoint choices. Never modifies the Git repository.
"""
import subprocess,collections,math,random,json,statistics,struct,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from revision_storage_benchmark import patch,apply_patch,Z
OUT=Path(__file__).parent
REPO='/opt/novnc'

def git(*args):return subprocess.run(['git','-C',REPO,*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout

def histories(target=18,versions=10):
 lines=git('log','-n','2000','--no-merges','--format=@@@%H','--name-only').decode('utf8','replace').splitlines()
 counts=collections.Counter(x for x in lines if x and not x.startswith('@@@') and x.endswith(('.js','.md','.css','.html')))
 histories=[]
 for fname,_ in counts.most_common():
  if len(histories)>=target:break
  shas=git('log','--no-merges','--format=%H','--',fname).decode().splitlines()[:versions+20]
  arr=[]
  for h in shas:
   b=git('show',f'{h}:{fname}')
   if not (300<=len(b)<=80000):continue
   try:b.decode('utf8')
   except UnicodeError:continue
   if arr and arr[-1]==b:continue
   arr.append(b)
   if len(arr)>=versions:break
  if len(arr)>=versions:histories.append((fname,arr))
 return histories

def dp_checkpoints(full,delta,prob,lam):
 """Minimize compressed bytes + lambda * expected number of patch applications.
 First version always a checkpoint, segment chosen using exact O(m^3) DP (m<=10).
 """
 n=len(full); D=[float('inf')]*(n+1);checkpoint=[None]*(n+1)
 D[n]=0.;checkpoint[n]=[]
 for a in range(n-1,-1,-1):
  if a!=0: pass
  for b in range(a,n):
   segment=full[a]+sum(delta[i]+4 for i in range(a+1,b+1))
   decode_penalty=lam*sum(prob[i]*(i-a) for i in range(a,b+1))
   total=segment+decode_penalty+D[b+1]
   if total<D[a]:D[a]=total;checkpoint[a]=[a]+checkpoint[b+1]
 return checkpoint[0],D[0]

def construct(file,arr):
 n=len(arr); compressed=[Z.compress(x,3) for x in arr];sizes=[len(z) for z in compressed]
 zipped_star=[]; zipped_chain=[]; patch_raw_star=[];patch_raw_chain=[]
 for i in range(n):
  if i==0:
   zipped_star.append((b'',0));zipped_chain.append((b'',0));continue
  sr=patch(arr[0],arr[i]);cr=patch(arr[i-1],arr[i]);
  zipped_star.append((Z.compress(sr,3),len(sr)));zipped_chain.append((Z.compress(cr,3),len(cr)))
  assert apply_patch(arr[0],sr)==arr[i]
  assert apply_patch(arr[i-1],cr)==arr[i]
 star=sizes[0]+sum(len(p[0])+4 for p in zipped_star[1:])
 chain=sizes[0]+sum(len(p[0])+4 for p in zipped_chain[1:])
 def layout(cps):
  points=set(cps); tot=sum(sizes[i] if i in points else len(zipped_chain[i][0])+4 for i in range(n))
  hops=[i-max(c for c in cps if c<=i) for i in range(n)]
  return tot,hops
 cp3=list(range(0,n,3)); fixed3,hops3=layout(cp3)
 cp5=list(range(0,n,5));fixed5,hops5=layout(cp5)
 prob=[1/((i+1)**1.2) for i in range(n)];norm=sum(prob);prob=[p/norm for p in prob]
 best_cps,_=dp_checkpoints(sizes,[len(x[0]) for x in zipped_chain],prob,lam=20000)
 best_size,best_hops=layout(best_cps)
 # Trace on-disk reconstruction for each sample using chain parent delta (not zstd benchmarks).
 def reconstruct(i,cps):
  start=max(x for x in cps if x<=i)
  data=Z.decompress(compressed[start],len(arr[start]))
  for j in range(start+1,i+1):
   buf,sz=zipped_chain[j];data=apply_patch(data,Z.decompress(buf,sz))
  return data
 for j in range(n):assert reconstruct(j,best_cps)==arr[j]
 def mean_hops(hops):return sum(p*h for p,h in zip(prob,hops))
 return {'name':file,'versions':n,'original_bytes':sum(map(len,arr)),'independent_bytes':sum(sizes),
  'star_bytes':star,'chain_bytes':chain,'checkpoint3_bytes':fixed3,'checkpoint5_bytes':fixed5,
  'workload_opt_bytes':best_size,'optimal_checkpoints':best_cps,
  'expected_hops_chain':round(mean_hops(list(range(n))),3),
  'expected_hops_checkpoint3':round(mean_hops(hops3),3),
  'expected_hops_workload_opt':round(mean_hops(best_hops),3)}

def run():
 hs=histories()
 print('histories',len(hs),[(f,len(a)) for f,a in hs],flush=True)
 res=[construct(f,a) for f,a in hs]
 keys=['original_bytes','independent_bytes','star_bytes','chain_bytes','checkpoint3_bytes','checkpoint5_bytes','workload_opt_bytes']
 agg={k:sum(x[k] for x in res) for k in keys}
 agg.update({'mean_chain_hops':round(statistics.mean(x['expected_hops_chain'] for x in res),3),
             'mean_fixed3_hops':round(statistics.mean(x['expected_hops_checkpoint3'] for x in res),3),
             'mean_opt_hops':round(statistics.mean(x['expected_hops_workload_opt'] for x in res),3)})
 out={'dataset':'18 real version histories ×10 versions from public local noVNC repository, JavaScript/CSS/HTML/Markdown',
  'all_reconstructions_exact':True,'algorithm':'Real Git commit snapshots; zstd3; line-sequence diff compressed via zstd3; checkpoints every 3/5 or small exact DP choosing checkpoints under storage + 20000 bytes*weighted chain hops objective.',
  'probability_assumption':'Zipf-like version accesses, latest revisions more likely; not measured workload.',
  'aggregate':agg,'files':res,'limitations':['Real Git changes, but only one project and 18 file histories.',
 'No real observed access traces, no SSD latency. Workload cost uses number of patch applications as proxy.',
 'DP objective lambda=20000 bytes/expected-hop is a design parameter, not tuned against a held-out workload.',
 'No per-version index costs or cross-document grammar compression, all sizes are exact patch/full encodings plus simple length metadata.']}
 (OUT/'real_git_version_graph_results.json').write_text(json.dumps(out,indent=2))
 print(json.dumps({'dataset':out['dataset'],'aggregate':agg,'sample_opt_checkpoints':res[:5]},indent=2))
if __name__=='__main__':run()
