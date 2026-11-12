#!/usr/bin/env python3
"""Access-skew/caching experiment with real local text and controlled interior edits.
Does not measure SSD I/O or full RAG; latency is warm CPU decoding only.
"""
import json,random,time,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from revision_storage_benchmark import edit_doc,patch,Z,collect_base_docs
OUT=Path(__file__).parent
R=random.Random(203018)

def setup():
 bases=[d[1] for d in collect_base_docs() if len(d[1].splitlines())>=30][:48]
 rec=[]
 for f,b in enumerate(bases):
  v=[b]+[edit_doc(b,.05,638492+f*131+i,'mixed') for i in range(1,7)]
  bz=Z.compress(b,3)
  pat=[];stand=[]
  for x in v:
   buf=patch(b,x)
   pat.append((Z.compress(buf,3),len(buf)))
   stand.append(Z.compress(x,3))
  rec.append({'base':b,'bz':bz,'docs':v,'patch':pat,'ind':stand})
 return rec

def lookup(rec,f,v,mode):
 item=rec[f]
 if mode=='independent' or ('hot-copy' in mode and v==1):
  return Z.decompress(item['ind'][v],len(item['docs'][v]))
 if 'base-cache' in mode:
  b=item['base']
 else:
  b=Z.decompress(item['bz'],len(item['base']))
 buf,n=item['patch'][v]
 return __import__('revision_storage_benchmark').apply_patch(b,Z.decompress(buf,n))

def bench(rec,pattern):
 access=[]
 for _ in range(900):
  f=R.randrange(len(rec)); v=1 if (pattern=='hot' and R.random()<0.75) else R.randrange(7)
  access.append((f,v))
 results={}
 for mode in ['independent','patch','hot-copy','base-cache','base-cache+hot-copy']:
  times=[]
  for f,v in access:
   t=time.perf_counter_ns();out=lookup(rec,f,v,mode);dt=time.perf_counter_ns()-t
   assert out==rec[f]['docs'][v]
   times.append(dt/1e6)
  results[mode]={'mean_ms':round(statistics.mean(times),4),'median_ms':round(statistics.median(times),4),'p95_ms':round(sorted(times)[int(.95*len(times))],4)}
 return results

def run():
 rec=setup()
 sizes={'independent_archive_bytes':sum(sum(map(len,x['ind'])) for x in rec),
   'patch_archive_bytes':sum(len(x['bz'])+sum(len(p[0])+4 for p in x['patch']) for x in rec),
   'patch_plus_hotcopy_archive_bytes':sum(len(x['bz'])+sum(len(p[0])+4 for p in x['patch'])+len(x['ind'][1]) for x in rec),
   'uncompressed_base_cache_ram_bytes':sum(len(x['base']) for x in rec)}
 obj={'corpus':'48 families × 7 versions, 5% synthetic interior edits on real technical-document bodies',
  'sizes':sizes,'query_distribution':{'hot':'75% hot version 1, 25% uniform over 7 versions','uniform':'uniform version selection'},
  'results':{'hot':bench(rec,'hot'),'uniform':bench(rec,'uniform')},
  'limitations':['Warm CPU decode only. No retrieval index, actual disk I/O, neural model or generated answers.','Source code text from installed local documentation, artificial interior edits and artificial access skew.','Patch reconstruction uses relatively slow Python/JSON operations; Rust/C implementation could change trade-offs.','Base-cache variant reports its extra uncompressed RAM; no cache eviction or update handling.','Storage excludes cross-family metadata beyond simple compressed patch length fields.']}
 (OUT/'access_cache_results.json').write_text(json.dumps(obj,indent=2))
 print(json.dumps(obj,indent=2))
if __name__=='__main__':run()
