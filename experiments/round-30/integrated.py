#!/usr/bin/env python3
"""Round 30: FTS5 to compressed source and two-hop title-mention retrieval.

This executable is designed for the pinned OpenSPG/KAG HotpotQA subset, but the
complete raw corpus must be supplied locally. Do not compare toy fixture results
with independently authored QA or claim that a linked mention entails an answer.

All candidates in one question are indexed, never chosen using gold labels.
The two-hop variants share the same candidates and source reader. Physical
payload and SQLite index bytes are measured from real files, but time is warm
and CPU/metadata costs must be interpreted with care.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, re, sqlite3, statistics, tempfile, time
from pathlib import Path
from filebacked_bench import build, read_spans

K_VALUES=(2,3,5)
POLICIES=('fts','dynamic_bridge','link_index')
UPSTREAM_SHA1='7dbdf068a437f0577043667ffee3a20f0a602154'
UPSTREAM_COMMIT='fdab15b3929d2ee40dfcdd388f90233096a6afc9'

def words(s):return re.findall(r'[^\W_]+',s.lower(),flags=re.UNICODE)
def canon(s):return ' '.join(words(s))
def git_blob_sha(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def load_json(path,require_pinned=True):
    blob=Path(path).read_bytes()
    if require_pinned and git_blob_sha(blob)!=UPSTREAM_SHA1:raise ValueError('input Git blob SHA-1 differs from upstream pinned corpus')
    rows=json.loads(blob)
    if not isinstance(rows,list):raise ValueError('expected an array')
    for row in rows:
        if not row.get('question') or not row.get('context') or not row.get('supporting_facts'):raise ValueError('incomplete question')
        ctx=dict(row['context'])
        if any(title not in ctx or sid<0 or sid>=len(ctx[title]) for title,sid in row['supporting_facts']):raise ValueError('missing gold source sentence')
    return rows

def fts_document_rank(db,question,source_count):
    # SQLite FTS5 bm25 score uses a negative score, lower is better. The index
    # is line-level; retain the best matching sentence per source as the score.
    terms=list(dict.fromkeys(words(question)))
    expr=' OR '.join('"'+w.replace('"','')+'"' for w in terms)
    if not expr:return list(range(1,source_count+1)),{}
    hits=db.execute('''SELECT l.source_id,bm25(lines_fts) FROM lines_fts
      JOIN lines l ON lines_fts.rowid=l.line_id WHERE lines_fts MATCH ?''',(expr,)).fetchall()
    scores={}
    for sid,negative in hits:scores[sid]=max(scores.get(sid,0),-negative)
    return sorted(range(1,source_count+1),key=lambda sid:(-scores.get(sid,0),sid)),scores

def canonical_title_edges(row):
    # No source labels are used: only candidate title metadata and body text.
    ctx=row['context'];titles=[' '+canon(t)+' ' for t,_ in ctx];edges=[]
    for i,(_,ss) in enumerate(ctx):
        body=' '+canon(' '.join(ss))+' '
        for j,tit in enumerate(titles):
            if i!=j and len(tit)>4 and tit in body:edges.append((i+1,j+1))
    return edges

def run_question(row,layout,size,root,policies=POLICIES,validate_bytes=True):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    docs=[];raws=[]
    for i,(title,sents) in enumerate(row['context']):
        # One line per source sentence, plus a title header. Exact UTF-8 offsets
        # are obtained from the persisted source file; no gold coordinate input.
        blob=(title+'\n'+'\n'.join(s.replace('\n',' ') for s in sents)+'\n').encode('utf-8')
        path=root/f'doc_{i:03d}.txt';path.write_bytes(blob);docs.append(path);raws.append(blob)
    store=root/'store';st=time.perf_counter_ns();build(store,docs,layout,size);build_ns=time.perf_counter_ns()-st
    db=sqlite3.connect(store/'index.sqlite');fd=os.open(store/'frames.zst',os.O_RDONLY)
    try:
        ranking,scores=fts_document_rank(db,row['question'],len(docs))
        link_start=time.perf_counter_ns()
        edges=canonical_title_edges(row)
        db.execute('CREATE TABLE IF NOT EXISTS title_links (src INTEGER NOT NULL,dst INTEGER NOT NULL,PRIMARY KEY(src,dst))')
        db.executemany('INSERT OR IGNORE INTO title_links VALUES (?,?)',edges)
        db.commit()
        link_build_ns=time.perf_counter_ns()-link_start
        def fetch_doc(sid):
            target=raws[sid-1]
            got,cb,frames=read_spans(db,fd,sid,[(0,len(target))])
            if validate_bytes and got[0]!=target:raise AssertionError('source hash / reconstructed bytes mismatch')
            return got[0],cb,frames
        results={}
        for method in policies:
            picked=[];compressed=0;framen=0;query_ns=0;decode_ns=0;metadata_ns=0
            for _ in range(min(max(K_VALUES),len(docs))):
                st=time.perf_counter_ns();best=None;bv=-1e50
                for sid in ranking:
                    if sid in picked:continue
                    score=scores.get(sid,0)
                    if picked and method in ('dynamic_bridge','link_index'):
                        if method=='link_index':
                            ts=time.perf_counter_ns()
                            is_link=any(db.execute('SELECT 1 FROM title_links WHERE src=? AND dst=?',(p,sid)).fetchone() for p in picked)
                            metadata_ns+=time.perf_counter_ns()-ts
                        else:
                            # We charge source reads when the source is selected,
                            # so the acquired text is in the in-memory pool below.
                            is_link=any((' '+canon(row['context'][sid-1][0])+' ') in (' '+canon(acquired[p])+' ') for p in picked)
                        if is_link:score+=2.0
                    if score>bv+1e-10 or (abs(score-bv)<1e-10 and (best is None or sid<best)):
                        best=sid;bv=score
                query_ns+=time.perf_counter_ns()-st
                if best is None:break
                picked.append(best)
                st=time.perf_counter_ns();blob,cb,nf=fetch_doc(best);decode_ns+=time.perf_counter_ns()-st
                compressed+=cb;framen+=nf
                # Acquisition cache. A policy is NEVER allowed to inspect source
                # contents of unselected documents at retrieval time.
                if _==0:acquired={}
                acquired[best]=blob.decode('utf-8',errors='strict').split('\n',1)[1]
                selected_titles={row['context'][x-1][0] for x in picked}
                gold_titles={t for t,_ in row['supporting_facts']}
                evidence={str(k):int(gold_titles<=({row['context'][x-1][0] for x in picked[:k]})) for k in K_VALUES if k<=len(picked)}
            results[method]={'picked_titles':[row['context'][i-1][0] for i in picked], 'complete_docs':evidence,
              'payload_read_bytes_all5':compressed,'frames_decoded_all5':framen,
              'score_and_selection_us':round(query_ns/1000,2),'decoding_us':round(decode_ns/1000,2),
              'link_metadata_us':round(metadata_ns/1000,2)}
        return {'question_id':row.get('_id'),'question_type':row.get('type'),'candidates':len(docs),'edge_count':len(edges),
        'build_ms':round(build_ns/1e6,3),'link_build_ms':round(link_build_ns/1e6,3),'sqlite_bytes':(store/'index.sqlite').stat().st_size,
        'payload_bytes':(store/'frames.zst').stat().st_size,'source_bytes':sum(map(len,raws)),
        'policies':results}
    finally:db.close();os.close(fd)

def benchmark(rows,layout='fixed',size=512):
    results=[]
    with tempfile.TemporaryDirectory(prefix='cdg-r30-') as td:
        for i,row in enumerate(rows):results.append(run_question(row,layout,size,Path(td)/f'q{i:04d}'))
    out={'questions':len(results),'layout':layout,'frame_size':size,'source':'user-supplied; checksum expected unless --allow-fixture',
      'note':'FTS5 BM25 ranks best matching source LINE; not equivalent to Round 25 document-BM25. Builds are done separately per question and included in storage/build totals, not per-query online latency.',
      'total_build_ms':round(sum(x['build_ms']+x['link_build_ms'] for x in results),1),'mean_persistent_bytes':round(statistics.mean(x['sqlite_bytes']+x['payload_bytes'] for x in results)),
      'mean_source_bytes':round(statistics.mean(x['source_bytes'] for x in results)), 'methods':{},'per_question':results}
    for method in POLICIES:
        out['methods'][method]={}
        for k in K_VALUES:
            out['methods'][method][str(k)]={'complete_docs':sum(x['policies'][method]['complete_docs'].get(str(k),0) for x in results),
             'n':len(results)}
        out['methods'][method]['mean_payload_read_bytes_5']=round(statistics.mean(x['policies'][method]['payload_read_bytes_all5'] for x in results))
        out['methods'][method]['mean_decode_us_5']=round(statistics.mean(x['policies'][method]['decoding_us'] for x in results),1)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--layout',choices=['whole','fixed','lines'],default='fixed');ap.add_argument('--frame-size',type=int,default=512)
    ap.add_argument('--allow-fixture',action='store_true',help='Only for source tests, never publish as the upstream HotpotQA benchmark')
    a=ap.parse_args();rows=load_json(a.data,require_pinned=not a.allow_fixture)
    out=benchmark(rows,a.layout,a.frame_size)
    out['input_sha256']=hashlib.sha256(a.data.read_bytes()).hexdigest();out['verified_upstream_blob']=not a.allow_fixture
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({'questions':out['questions'],'layout':out['layout'],'methods':out['methods']},indent=2))
if __name__=='__main__':main()
