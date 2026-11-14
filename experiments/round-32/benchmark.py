#!/usr/bin/env python3
"""Deterministic 10-update full rebuild vs per-source/frame CAS comparison."""
import argparse,hashlib,json,statistics,tempfile,time
from pathlib import Path
from incremental_store import Store,stored_bytes

TERMS=['evidence','retrieval','source','compression','index','research','bridge','frame','cost','result','document','accuracy','model','version','storage']

def update(b:bytes, step:int, kind:str):
    """Change one ASCII alphabetic byte near a rotating source position.

    Equal-size uses an ASCII letter replacement; insert adds one ASCII byte.
    """
    pos=(step*127+100)%len(b)
    for delta in range(len(b)):
        i=(pos+delta)%len(b)
        if 65<=b[i]<=90 or 97<=b[i]<=122:break
    if kind=='replace':return b[:i]+(b'Z' if b[i]!=90 else b'Y')+b[i+1:]
    return b[:i]+b'X'+b[i:]

def run(sources:dict[str,bytes],mode:str,frame_size:int):
    with tempfile.TemporaryDirectory() as td:
        base=Path(td)
        full=Store(base/'full',full_rebuild=True,frame_size=frame_size)
        incremental=Store(base/'cas',full_rebuild=False,frame_size=frame_size)
        history=[];inputs=dict(sources);pinned=None;old_receipt=None;old_data=None
        for step in range(11):
            if step:
                target=sorted(inputs)[(step-1)%len(inputs)]
                inputs[target]=update(inputs[target],step,mode)
            records={}
            for key,engine in [('full',full),('cas',incremental)]:
                start=time.perf_counter_ns();build=engine.publish(inputs)
                build_ms=(time.perf_counter_ns()-start)/1e6
                start=time.perf_counter_ns();reader=engine.reader();open_ms=(time.perf_counter_ns()-start)/1e6
                answers=[];times=[]
                for term in TERMS:
                    st=time.perf_counter_ns();hits=reader.search(term,5);times.append((time.perf_counter_ns()-st)/1000)
                    answers.append([(x['receipt']['name'],x['receipt']['start'],x['receipt']['end'],x['text']) for x in hits])
                if key=='full':baseline_answers=answers
                else:
                    if answers!=baseline_answers:raise AssertionError('search parity')
                name=sorted(inputs)[0]
                # Raw source bytes must reconstruct from physical frames.
                receipt=reader.receipt(name,0,len(inputs[name]))
                if reader.read(receipt)!=inputs[name]:raise AssertionError('roundtrip')
                records[key]={'build_ms':round(build_ms,3),'reader_open_ms':round(open_ms,3),'warm_median_query_us':round(statistics.median(times),3),'written_bytes':build['new_written_bytes'],'stored_bytes':stored_bytes(engine.root),'generation':build['generation']}
                if step==0 and key=='cas':pinned=reader;old_receipt=reader.receipt(name,0,min(200,len(inputs[name])));old_data=reader.read(old_receipt)
                if step and key=='cas':
                    try:reader.read(old_receipt)
                    except ValueError:pass
                    else:raise AssertionError('stale receipt accepted')
                    if pinned.read(old_receipt)!=old_data:raise AssertionError('old reader invalid')
            history.append({'step':step,'changed':None if step==0 else target,**records})
        return {'mode':mode,'frame_size':frame_size,'source_count':len(sources),'initial_source_bytes':sum(map(len,sources.values())),'updates':10,'history':history,'cold_cache':False,'notes':'5 source-derived reports, 15 shared literal query terms. Source-level index reuse; content-addressed individually compressed line frames; no GC; no ANN/global ranking; timing exploratory.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--files',nargs='+',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--frame-size',type=int,default=512);a=ap.parse_args()
    sources={f'report_{i+1:02d}.md':p.read_bytes() for i,p in enumerate(a.files)}
    result={'source_hashes':{f'report_{i+1:02d}.md':hashlib.sha256(p.read_bytes()).hexdigest() for i,p in enumerate(a.files)},'runs':[run(sources,'replace',a.frame_size),run(sources,'insert',a.frame_size)]}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'runs':[{'mode':r['mode'],'final':r['history'][-1]} for r in result['runs']]},indent=2))
if __name__=='__main__':main()
