#!/usr/bin/env python3
"""Round 29: actual FTS5 query->line coordinate->file-backed zstd span retrieval.

Questions deliberately constructed from indexed source lines. This evaluates
integration and resource cost, NOT independently-authored QA or multihop recall.
"""
from __future__ import annotations
import argparse, hashlib, json, random, re, sqlite3, statistics, os, time, tempfile, sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from filebacked_bench import build,read_spans

STOP={'the','and','for','from','with','that','this','were','into','have','been','which','their','would','about','under','because','only','than','some','more','does','each','are','not','our','its','but','can','also','such','then','will','has','was','one','two','all','may','per','how','did','use','used','using','when','what','where','why','who','will','could','into','round','research','data','source','sources','evidence','retrieval','document','documents','results','result','query','queries','model','models','baseline','experiment','method','figure','table','paper','study','work','system','systems','cost','costs','real','actual','reported'}

def words(x):return re.findall(r'[^\W_]+',x.lower(),flags=re.UNICODE)

def eligible_lines(inputs):
    out=[]
    for sid,p in enumerate(inputs,1):
        pos=0
        for raw in p.read_bytes().splitlines(keepends=True):
            txt=raw.decode('utf-8',errors='replace').strip()
            if 90<=len(raw)<=650 and not txt.startswith('|') and not txt.startswith('```'):
                terms=[]
                for w in words(txt):
                    if len(w)>=5 and w not in STOP and not w.isnumeric() and w not in terms:terms.append(w)
                if len(terms)>=7:out.append({'source_id':sid,'low':pos,'high':pos+len(raw),'text':txt,'terms':terms})
            pos+=len(raw)
    return out

def make_tasks(inputs,n=160,seed=29026):
    rng=random.Random(seed);pool=eligible_lines(inputs)
    rng.shuffle(pool)
    # Prefer a varied selection instead of repeatedly sampling the largest report.
    tasks=[];cnt={}
    for r in pool:
        if cnt.get(r['source_id'],0)>=max(1,n//len(inputs)):continue
        # Two terms are deliberately drawn from a target line, a closed-world weak question.
        # Avoid exact full-sentence search; still source-derived and consequently leaked.
        unique=sorted(r['terms'],key=lambda w:(-len(w),w))
        a,b=rng.sample(unique[:min(len(unique),12)],2)
        task={'id':len(tasks),'source_id':r['source_id'],'low':r['low'],'high':r['high'],'terms':[a,b], 'query':a+' '+b}
        tasks.append(task);cnt[r['source_id']]=cnt.get(r['source_id'],0)+1
        if len(tasks)>=n:break
    return tasks

def fts_query(db,terms,limit):
    phrase=' OR '.join('"'+w.replace('"','')+'"' for w in terms)
    return db.execute('''SELECT l.line_id,l.source_id,l.raw_start,l.raw_end, bm25(lines_fts) AS s
      FROM lines_fts JOIN lines l ON l.line_id=lines_fts.rowid
      WHERE lines_fts MATCH ? ORDER BY s ASC,l.line_id ASC LIMIT ?''',(phrase,limit)).fetchall()

def run_layout(inputs,tasks,root,layout,size,warm_repeats=3):
    start_build=time.perf_counter();build(root,inputs,layout,size);build_ms=(time.perf_counter()-start_build)*1000
    db=sqlite3.connect(root/'index.sqlite');fd=os.open(root/'frames.zst',os.O_RDONLY)
    ground={i:p.read_bytes() for i,p in enumerate(inputs,1)}
    trials=[];ranks={1:0,3:0,5:0};query_cost=[];read_cost=[];bytes_read=[];nframes=[];false_positive=0;byte_fail=0
    try:
      # Warm-up separate from reported queries; repeated sweeps capture local run-to-run jitter.
      for task in tasks[:min(10,len(tasks))]:fts_query(db,task['terms'],5)
      for repeat in range(warm_repeats):
        order=list(tasks);random.Random(1000+repeat).shuffle(order)
        for t in order:
            st=time.perf_counter_ns();hits=fts_query(db,t['terms'],5);dt=(time.perf_counter_ns()-st)/1000
            query_cost.append(dt)
            # Ranking measure is line identity. A hit on another relevant line is not counted.
            for k in [1,3,5]:ranks[k]+=int(any(sid==t['source_id'] and lo==t['low'] for lid,sid,lo,hi,score in hits[:k]))
            st=time.perf_counter_ns();frame_b=0;frame_n=0
            for lid,sid,lo,hi,score in hits[:3]:
                got,bc,nf=read_spans(db,fd,sid,[(lo,hi)]);frame_b+=bc;frame_n+=nf
                if got[0]!=ground[sid][lo:hi]:byte_fail+=1
            rt=(time.perf_counter_ns()-st)/1000;read_cost.append(rt);bytes_read.append(frame_b);nframes.append(frame_n);trials.append(dt+rt)
        
    finally:db.close();os.close(fd)
    def pct(xs,p):return round(sorted(xs)[int(p*(len(xs)-1))],2)
    db_bytes=(root/'index.sqlite').stat().st_size;payload_bytes=(root/'frames.zst').stat().st_size
    return {'layout':layout,'frame_size':size,'source_count':len(inputs),'task_count':len(tasks),'repeated_measurements':len(trials),'build_ms':round(build_ms,2),'sqlite_bytes':db_bytes,'payload_bytes':payload_bytes,'persistent_total_bytes':db_bytes+payload_bytes,'exact_target_line_recall_at_k':{str(k):round(v/len(trials),4) for k,v in ranks.items()},'mean_compressed_bytes_read_at_3':round(statistics.mean(bytes_read),2),'mean_frames_decoded_at_3':round(statistics.mean(nframes),2),'fts_p50_us':pct(query_cost,.5),'fts_p95_us':pct(query_cost,.95),'read_decode_p50_us':pct(read_cost,.5),'read_decode_p95_us':pct(read_cost,.95),'full_p50_us':pct(trials,.5),'full_p95_us':pct(trials,.95),'roundtrip_errors':byte_fail,'cold_cache_controlled':False,'queries_label_leaked':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--files',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--tasks',type=int,default=160);p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    tasks=make_tasks(a.files,a.tasks)
    with tempfile.TemporaryDirectory(prefix='cdg-r29-') as td:
        result=[run_layout(a.files,tasks,Path(td)/f'{l}_{s}',l,s,a.repeats) for l,s in [('whole',0),('fixed',512),('lines',512),('fixed',2048),('lines',2048)]]
    output={'status':'local file-backed full query to spans experiment; constructed lexical queries, NOT real QA or HotpotQA','input_files':[{'name':x.name,'sha256':hashlib.sha256(x.read_bytes()).hexdigest(),'bytes':x.stat().st_size} for x in a.files],'tasks':len(tasks),'seed':29026,'retrieval_scoring':'SQLite FTS5 bm25 over line text, OR of two tokens drawn from gold target line. Target line identity only, no semantic support assessment.','select_k':3,'runs':result}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'n':len(tasks),'runs':result},indent=2))
if __name__=='__main__':main()
