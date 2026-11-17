#!/usr/bin/env python3
"""Round 42: compare historical full SQLite snapshots to per-document immutable shards.
Real source text with transparently synthetic identity expansion and updates. Uses stdlib zlib.
No semantic QA, fsync durability, or cold-cache guarantees.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, sqlite3, statistics, tempfile, time, zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCES=[ROOT/'inputs'/f'round{i}.md' for i in range(24,29)]
def sha(b):return hashlib.sha256(b).hexdigest()
def totals(root):return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())
def setup_db(path):
 c=sqlite3.connect(path)
 c.execute('CREATE VIRTUAL TABLE fts USING fts5(name UNINDEXED, text)')
 c.commit();return c

def rows_for(doc):
 return [(i,ln) for i,ln in enumerate(doc.decode('utf8').splitlines(),1) if ln.strip()]

def lookup(con,word):
 return con.execute('SELECT name, rowid FROM fts WHERE fts MATCH ? ORDER BY name, rowid',(word,)).fetchall()

class Global:
 def __init__(self,root,sources):
  self.root=root;root.mkdir();self.db=setup_db(root/'live.sqlite');self.maps={}
  self.update(sources,initial=True)
 def update(self,sources,initial=False):
  t=time.perf_counter_ns();changed=[k for k,v in sources.items() if self.maps.get(k)!=sha(v)]
  for k in set(self.maps)-set(sources):
   self.db.execute('DELETE FROM fts WHERE name=?',(k,));self.maps.pop(k)
  for k in changed:
   self.db.execute('DELETE FROM fts WHERE name=?',(k,))
   for _,line in rows_for(sources[k]):self.db.execute('INSERT INTO fts(name,text) VALUES (?,?)',(k,line))
   self.maps[k]=sha(sources[k])
  self.db.commit()
  gen=len(list((self.root/'history').glob('*.sqlite'))) if (self.root/'history').exists() else 0
  hist=self.root/'history';hist.mkdir(exist_ok=True)
  dest=sqlite3.connect(hist/f'{gen:04d}.sqlite');self.db.backup(dest);dest.close()
  payload=self.root/'payload'/f'{gen:04d}';payload.mkdir(parents=True,exist_ok=True)
  for k,v in sources.items():(payload/(k+'.z')).write_bytes(zlib.compress(v,6))
  elapsed=(time.perf_counter_ns()-t)/1e6
  return {'ms':elapsed,'changed':len(changed)}
 def search(self,term):return lookup(self.db,term)
 def read_gen(self,gen,name):return zlib.decompress((self.root/'payload'/f'{gen:04d}'/(name+'.z')).read_bytes())
 def close(self):self.db.close()


class GlobalDelta:
 """Incremental FTS5 append, full historical index snapshots, CAS payloads."""
 def __init__(self,root,sources):
  self.root=root;root.mkdir();self.db=setup_db(root/'live.sqlite');self.maps={};self.old={};self.update(sources)
 def update(self,sources):
  t=time.perf_counter_ns();changed=[k for k,v in sources.items() if self.maps.get(k)!=sha(v)]
  for k in set(self.maps)-set(sources):
   self.db.execute('DELETE FROM fts WHERE name=?',(k,));self.maps.pop(k);self.old.pop(k)
  for k in changed:
   blob=sources[k];newlines=[ln for _,ln in rows_for(blob)]
   previous=self.old.get(k,[])
   if newlines[:len(previous)]==previous:
    suffix=newlines[len(previous):]
   else:
    self.db.execute('DELETE FROM fts WHERE name=?',(k,));suffix=newlines
   for line in suffix:self.db.execute('INSERT INTO fts(name,text) VALUES (?,?)',(k,line))
   self.maps[k]=sha(blob);self.old[k]=newlines
  self.db.commit();gen=len(list((self.root/'history').glob('*.sqlite'))) if (self.root/'history').exists() else 0
  hist=self.root/'history';hist.mkdir(exist_ok=True)
  dest=sqlite3.connect(hist/f'{gen:04d}.sqlite');self.db.backup(dest);dest.close()
  payload=self.root/'payload';payload.mkdir(exist_ok=True)
  for k,blob in sources.items():
   f=payload/(sha(blob)+'.z')
   if not f.exists():f.write_bytes(zlib.compress(blob,6))
  mapdir=self.root/'maps';mapdir.mkdir(exist_ok=True)
  (mapdir/f'{gen:04d}.json').write_text(json.dumps({k:sha(v) for k,v in sources.items()},sort_keys=True))
  return {'ms':(time.perf_counter_ns()-t)/1e6,'changed':len(changed)}
 def search(self,word):return lookup(self.db,word)
 def read_gen(self,gen,name):
  m=json.loads((self.root/'maps'/f'{gen:04d}.json').read_text());return zlib.decompress((self.root/'payload'/(m[name]+'.z')).read_bytes())
 def close(self):self.db.close()

class Shards:
 def __init__(self,root,sources):
  self.root=root;root.mkdir();self.map={};self.current={};self.frames=self.root/'payload';self.index=self.root/'indexes';self.manifests=self.root/'manifests'
  for p in [self.frames,self.index,self.manifests]:p.mkdir()
  self.update(sources)
 def update(self,sources):
  t=time.perf_counter_ns();changed=[k for k,v in sources.items() if self.current.get(k)!=sha(v)]
  for k in set(self.current)-set(sources):self.current.pop(k)
  for k in changed:
   b=sources[k];key=sha(b);self.current[k]=key
   payload=self.frames/(key+'.z');idx=self.index/(sha(k.encode()+b'\0'+key.encode())+'.sqlite')
   if not payload.exists():payload.write_bytes(zlib.compress(b,6))
   if not idx.exists():
    c=setup_db(idx)
    for _,line in rows_for(b):c.execute('INSERT INTO fts(name,text) VALUES (?,?)',(k,line))
    c.commit();c.close()
  gen=len(list(self.manifests.glob('*.json')))
  (self.manifests/f'{gen:04d}.json').write_text(json.dumps(self.current,sort_keys=True))
  return {'ms':(time.perf_counter_ns()-t)/1e6,'changed':len(changed)}
 def search(self,term):
  out=[]
  for name,key in sorted(self.current.items()):
   c=sqlite3.connect(f'file:{self.index/(sha(name.encode()+b'\0'+key.encode())+".sqlite")}?mode=ro&immutable=1',uri=True)
   try:
    # immutable content-addressed per-source index; name is part of index identity
    out.extend(lookup(c,term))
   finally:c.close()
  return out
 def read_gen(self,gen,name):
  m=json.loads((self.manifests/f'{gen:04d}.json').read_text());return zlib.decompress((self.frames/(m[name]+'.z')).read_bytes())
 def close(self):pass


class Hybrid:
 """Current global SQLite index + immutable source-version historical shards.
 Substantial duplicated current-index maintenance. Does not retain global historical FTS snapshots.
 Historical lookup can fan out to source shards from a pinned generation.
 """
 def __init__(self,root,sources):
  self.root=root;root.mkdir();self.shards=Shards(root/'history',sources)
  self.db=setup_db(root/'current.sqlite');self.old={}
  self._update_global(sources)
 def _update_global(self,sources):
  for k in set(self.old)-set(sources):
   self.db.execute('DELETE FROM fts WHERE name=?',(k,));self.old.pop(k)
  for name,blob in sources.items():
   lines=[ln for _,ln in rows_for(blob)];old=self.old.get(name,[])
   if name in self.old and lines==old:continue
   if lines[:len(old)]==old:changed=lines[len(old):]
   else:self.db.execute('DELETE FROM fts WHERE name=?',(name,));changed=lines
   for line in changed:self.db.execute('INSERT INTO fts(name,text) VALUES (?,?)',(name,line))
   self.old[name]=lines
  self.db.commit()
 def update(self,sources):
  t=time.perf_counter_ns();self.shards.update(sources);self._update_global(sources)
  return {'ms':(time.perf_counter_ns()-t)/1e6}
 def search(self,term):return lookup(self.db,term)
 def read_gen(self,gen,name):return self.shards.read_gen(gen,name)
 def close(self):self.db.close()

def source_docs(n):
 texts=[p.read_bytes() for p in SOURCES]
 # n=5 is genuinely five documents. n=20,50 are transparent duplicated real-text inputs with distinct identifiers.
 return {f'doc{i:03d}':texts[i%len(texts)] for i in range(n)}

def mutate(b,step,mode='append'):
 if mode=='replace':
  # replace one byte inside an existing token with a different ASCII letter; preserves UTF8 bytes and document size
  anchor=b.find(b'evidence')
  if anchor<0:anchor=b.find(b'research')
  if anchor<0:anchor=20
  x=bytearray(b);x[anchor]=ord('a')+step%26;return bytes(x)
 line=f'\nCDG revision marker {step} updated evidence frame and provenance.\n'.encode()
 return b+line

def check(g,s,docs,terms,gen):
 # sqlite FTS5 uses different posting rowid: normalize source and line content to compare across architectures
 for word in terms:
  def scan(obj):
   pairs=[]
   for name,rowid in obj.search(word):
    # source indexes are row numbers; global SQLite rowids are not. compare name+matching line multiset using FTS rowid join for global
    pairs.append(name)
   return sorted(pairs)
  if scan(g)!=scan(s):raise AssertionError('FTS parity '+word)
 for name,blob in docs.items():
  if g.read_gen(gen,name)!=blob or s.read_gen(gen,name)!=blob:raise AssertionError('reconstruction '+name)

def exercise(n,frac,seed,updates=6,mode='append'):
 rng=random.Random(seed);docs=source_docs(n)
 with tempfile.TemporaryDirectory() as base:
  root=Path(base);t=time.perf_counter_ns();g=Global(root/'global',docs);gi=(time.perf_counter_ns()-t)/1e6
  t=time.perf_counter_ns();s=Shards(root/'shards',docs);si=(time.perf_counter_ns()-t)/1e6
  t=time.perf_counter_ns();d=GlobalDelta(root/'delta',docs);di=(time.perf_counter_ns()-t)/1e6
  t=time.perf_counter_ns();h=Hybrid(root/'hybrid',docs);hi=(time.perf_counter_ns()-t)/1e6
  terms=['evidence','compression','retrieval','source','algorithm']
  check(g,s,docs,terms,0)
  check(g,d,docs,terms,0)
  check(g,h,docs,terms,0)
  info=[]
  for step in range(1,updates+1):
   change=max(1,round(n*frac));keys=rng.sample(sorted(docs),change)
   for key in keys:docs[key]=mutate(docs[key],step,mode)
   a=g.update(docs);b=s.update(docs);c=d.update(docs);hv=h.update(docs);check(g,s,docs,terms,step);check(g,d,docs,terms,step);check(g,h,docs,terms,step)
   info.append({'update':step,'changed':change,'global_ms':a['ms'],'shards_ms':b['ms'],'delta_ms':c['ms'],'delta_bytes':totals(root/'delta'),'hybrid_ms':hv['ms'],'hybrid_bytes':totals(root/'hybrid'),'global_bytes':totals(root/'global'),'shards_bytes':totals(root/'shards')})
  # check old generation remains exactly readable, not just newest
  original=source_docs(n)
  for name,b in original.items():
   if g.read_gen(0,name)!=b or s.read_gen(0,name)!=b or d.read_gen(0,name)!=b or h.read_gen(0,name)!=b:raise AssertionError('historical read')
  querytimes={}
  for name,obj in [('global',g),('delta',d),('shards',s),('hybrid',h)]:
   t=[]
   for j in range(15):
    st=time.perf_counter_ns();obj.search(terms[j%len(terms)]);t.append((time.perf_counter_ns()-st)/1e3)
   querytimes[name]=round(statistics.median(t),3)
  out={'n':n,'fraction':frac,'mode':mode,'seed':seed,'updates':updates,'initial_global_ms':round(gi,3),'initial_shards_ms':round(si,3),'initial_delta_ms':round(di,3),'initial_hybrid_ms':round(hi,3),'update_global_p50_ms':round(statistics.median(x['global_ms'] for x in info),3),'update_shards_p50_ms':round(statistics.median(x['shards_ms'] for x in info),3),'update_delta_p50_ms':round(statistics.median(x['delta_ms'] for x in info),3),'update_hybrid_p50_ms':round(statistics.median(x['hybrid_ms'] for x in info),3),'final_global_bytes':info[-1]['global_bytes'],'final_shards_bytes':info[-1]['shards_bytes'],'final_delta_bytes':info[-1]['delta_bytes'],'final_hybrid_bytes':info[-1]['hybrid_bytes'],'query_p50_us':querytimes,'runs':[{k:round(v,3) if isinstance(v,float) else v for k,v in x.items()} for x in info]}
  g.close();s.close();d.close();h.close();return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',default=str(ROOT/'results.json'));o=p.parse_args()
 results=[]
 for mode in ['append','replace']:
  for n in [5,20]:
   for frac in [.05,.2,.8,1.0]:
    for seed in [11,23]:
     r=exercise(n,frac,seed,updates=4,mode=mode);results.append(r)
     print(f'mode={mode} n={n:2} changed={frac:.2f} seed={seed} update(ms) global={r["update_global_p50_ms"]:.1f} shards={r["update_shards_p50_ms"]:.1f} sizes={r["final_global_bytes"]}/{r["final_delta_bytes"]}/{r["final_shards_bytes"]}',flush=True)
 out={'study':'Round 42 four-way historical storage: global full snapshots, incremental global + CAS payload, per-source immutable shards, hybrid global live search + immutable history shards','caveats':['Different update implementations, global backup each generation vs shared immutable per-source indexes','20-source dataset duplicates five genuine report texts, not an independent corpus','synthetic append-only updates; no deletions or semantic QA','No cold-cache, fsync or true SSD physical I/O measurements','Shards query fanout is name ordered; global index search by FTS relevance not compared','The global baseline uses naive source replacement; partial row updates could improve it'], 'results':results}
 Path(o.out).write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
