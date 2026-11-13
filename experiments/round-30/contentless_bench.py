#!/usr/bin/env python3
"""Round 30: byte-identical FTS5 retrieval using stored-body and contentless indexes.

Uses real local reports and real zstd frames. Source text is absent from the
contentless SQLite lines table, and is recoverable only through compressed frames.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sqlite3, statistics, tempfile, time
from pathlib import Path
from filebacked_bench import build, compress, chunks, line_spans, read_spans

def build_contentless(root:Path,inputs:list[Path],layout='fixed',size=512):
    root.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(root/'index.sqlite')
    conn.execute('PRAGMA journal_mode=DELETE');conn.execute('PRAGMA synchronous=FULL')
    conn.executescript('''
    CREATE TABLE sources (source_id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,version INTEGER NOT NULL,sha256 TEXT NOT NULL,raw_len INTEGER NOT NULL);
    CREATE TABLE frames (source_id INTEGER NOT NULL, raw_start INTEGER NOT NULL, raw_end INTEGER NOT NULL,payload_offset INTEGER NOT NULL,payload_length INTEGER NOT NULL,PRIMARY KEY(source_id,raw_start));
    CREATE TABLE lines (line_id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL,raw_start INTEGER NOT NULL,raw_end INTEGER NOT NULL);
    CREATE INDEX frames_source_end ON frames(source_id,raw_end);
    CREATE INDEX lines_source_start ON lines(source_id,raw_start);
    CREATE VIRTUAL TABLE lines_fts USING fts5(body, content='');
    ''')
    with (root/'frames.zst').open('wb') as archive:
        for sid,p in enumerate(inputs,1):
            b=p.read_bytes();conn.execute('INSERT INTO sources VALUES (?,?,?,?,?)',(sid,p.name,1,hashlib.sha256(b).hexdigest(),len(b)))
            for start,part in chunks(b,layout,size):
                compressed=compress(part);offset=archive.tell();archive.write(compressed)
                conn.execute('INSERT INTO frames VALUES (?,?,?,?,?)',(sid,start,start+len(part),offset,len(compressed)))
            for start,end,text in line_spans(b):
                conn.execute('INSERT INTO lines (source_id,raw_start,raw_end) VALUES (?,?,?)',(sid,start,end))
                line_id=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.execute('INSERT INTO lines_fts(rowid,body) VALUES (?,?)',(line_id,text))
    conn.commit();conn.close()

def query(db,q,k=5):
    return db.execute('''SELECT l.line_id,l.source_id,l.raw_start,l.raw_end,bm25(lines_fts) AS rank
       FROM lines_fts JOIN lines l ON l.line_id=lines_fts.rowid
       WHERE lines_fts MATCH ? ORDER BY rank,l.line_id LIMIT ?''',(q,k)).fetchall()

def compare(inputs,layout='fixed',size=512):
    with tempfile.TemporaryDirectory(prefix='cdg-r30-contentless-') as td:
        base=Path(td);root_a=base/'external';root_b=base/'contentless'
        t=time.perf_counter_ns();build(root_a,inputs,layout,size);build_a=(time.perf_counter_ns()-t)/1e6
        t=time.perf_counter_ns();build_contentless(root_b,inputs,layout,size);build_b=(time.perf_counter_ns()-t)/1e6
        a=sqlite3.connect(root_a/'index.sqlite');b=sqlite3.connect(root_b/'index.sqlite');fa=os.open(root_a/'frames.zst',os.O_RDONLY);fb=os.open(root_b/'frames.zst',os.O_RDONLY)
        texts={i:p.read_bytes() for i,p in enumerate(inputs,1)}
        terms=['compression','evidence','retrieval','memory','source','system','graph','document','framework','model','time','cost','research','benchmarks','result','citation','byte','index']
        comparisons=[];times={'external':[],'contentless':[]};readbytes={'external':[],'contentless':[]};issues=[]
        try:
            for term in terms:
                prev=None
                for name,conn,fd in [('external',a,fa),('contentless',b,fb)]:
                    t=time.perf_counter_ns();rows=query(conn,term,5)
                    pieces=[];bytes_acc=0
                    for _,sid,lo,hi,_ in rows:
                        got,compressed,_=read_spans(conn,fd,sid,[(lo,hi)]);bytes_acc+=compressed
                        if got[0]!=texts[sid][lo:hi]:issues.append((name,term,sid,lo,'bytes mismatch'))
                        pieces.append((sid,lo,hi,got[0]))
                    times[name].append((time.perf_counter_ns()-t)/1000)
                    readbytes[name].append(bytes_acc)
                    if prev is None:prev=pieces
                    elif prev!=pieces:issues.append((name,term,'ranking mismatch'))
                comparisons.append({'term':term,'hits':len(prev)})
        finally:
            a.close();b.close();os.close(fa);os.close(fb)
        def sizes(root):return {'sqlite':(root/'index.sqlite').stat().st_size,'payload':(root/'frames.zst').stat().st_size,'total':(root/'index.sqlite').stat().st_size+(root/'frames.zst').stat().st_size}
        return {'sources':len(inputs),'input_bytes':sum(p.stat().st_size for p in inputs), 'layout':layout,'frame_size':size,
          'external':{**sizes(root_a),'build_ms':round(build_a,2),'median_query_and_decode_us':round(statistics.median(times['external']),2),'mean_payload_read_bytes':round(statistics.mean(readbytes['external']),2)},
          'contentless':{**sizes(root_b),'build_ms':round(build_b,2),'median_query_and_decode_us':round(statistics.median(times['contentless']),2),'mean_payload_read_bytes':round(statistics.mean(readbytes['contentless']),2)},
          'queries':len(terms),'query_details':comparisons,'mismatches':issues,'status':'real local storage bytes and warm search/read/decode; terms hand-selected from topic, no QA and no cold cache control'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--files',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--frame-size',type=int,default=512);a=p.parse_args()
    out=compare(a.files,size=a.frame_size);out['sources_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.files};a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('query_details','sources_sha256')},indent=2))
if __name__=='__main__':main()
