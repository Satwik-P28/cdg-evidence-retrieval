#!/usr/bin/env python3
"""Count duplicate base-frame decode requests within exact passage reads."""
from pathlib import Path
from collections import Counter
import contextlib,io,sys,bisect,struct,json
ROOT=Path(__file__).parent
source=(ROOT/'round7_span_coalescing.py').read_text().split('layouts={v:')[0]
ns={'__name__':'cdg_frame_analysis','__file__':str(ROOT/'round7_span_coalescing.py')}
with contextlib.redirect_stdout(io.StringIO()):exec(compile(source,str(ROOT/'round7_span_coalescing.py'),'exec'),ns)
a=ns['a']; L=ns['Layout'](8)
result={}
for length in [1,5,20,40]:
 total_reads=0;total_unique=0;total_pieces=0;max_dup=0
 for i,s,t in a.test_same[:500]+a.test_shift[:500]:
  num=len(a.r.files[i].splitlines(keepends=True))
  cen=(s+t)//2;s=max(0,min(cen-length//2,max(0,num-length)));t=min(num,s+length)
  path,metadata,ends,keys=L.vs[i]
  k=bisect.bisect_right(ends,s);frames=[];count=0
  while k<len(ends) and (ends[k-1] if k else 0)<t:
   kind,x,y,n,_=struct.unpack_from('<BIIII',metadata,17*k)
   before=ends[k-1] if k else 0
   lo=max(0,s-before);hi=min(n,t-before)
   if hi>lo:
    count+=1
    if kind==0:frames.extend(range((x+lo)//32,(x+hi-1)//32+1))
   k+=1
  total_reads+=len(frames);total_unique+=len(set(frames));total_pieces+=count;max_dup=max(max_dup,len(frames)-len(set(frames)))
 result[str(length)]={'avg_pieces':round(total_pieces/1000,3),'avg_base_frame_decode_calls':round(total_reads/1000,3),'avg_unique_base_frames':round(total_unique/1000,3),'fraction_base_frame_calls_redundant':round((total_reads-total_unique)/total_reads,3) if total_reads else 0,'max_duplicate_calls_in_one_query':max_dup}
(ROOT/'round7_frame_accounting_results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
