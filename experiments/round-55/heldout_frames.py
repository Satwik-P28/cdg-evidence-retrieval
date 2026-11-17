#!/usr/bin/env python3
"""Round 55: evidence-complete retrieval versus exact compressed source materialization.

Run on first 128 IDs from R54's SHA-locked HotpotQA dev selection.
All original source paragraphs are required for BM25 document selection; FTS5
sentence indexing is built and charged, never treated as a zero-cost oracle.
The policy quality and byte read are separately measured. No answer generation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
R54=HERE.parent/'round-54'/'heldout_dev.py'
R48=HERE.parent/'round-48'/'evidence_bridge.py'
R25=HERE.parent/'round-25'/'bridge_probe.py'
STOP=frozenset('the is are were was who which what when where how did does and '
               'from with have has this that for into about could would can '
               'many much of an to as on in a at by'.split())
CONFIGS={
    'whole_json':('whole','json-zlib'),
    'fixed512_binary':('fixed512','binary-zlib'),
    'gear512_binary':('gear512','binary-zlib'),
    'gear512_json':('gear512','json-zlib'),
}
K_VALUES=(2,5)
POLICIES=('bm25','bridge')


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


class SentenceIndex:
    def __init__(self,db_path,questions):
        self.helper=module('cdg_r25_r55',R25)
        self.db=sqlite3.connect(db_path)
        self.db.execute('CREATE TABLE spans(rid INTEGER PRIMARY KEY, q INTEGER NOT NULL, d INTEGER NOT NULL, sid INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX spans_q_d ON spans(q,d)')
        self.db.execute("CREATE VIRTUAL TABLE fts USING fts5(text, content='')")
        self.records={}
        self.original_blobs=[]
        start=time.perf_counter_ns()
        for qid,row in enumerate(questions):
            for did,(title,sentences) in enumerate(row['context']):
                original=b''.join(s.encode('utf8') for s in sentences)
                self.records[(qid,did)]=len(self.original_blobs)
                self.original_blobs.append(original)
                pos=0
                for sid,sentence in enumerate(sentences):
                    stop=pos+len(sentence.encode('utf8'))
                    rid=self.db.execute(
                        'INSERT INTO spans(q,d,sid,start,end) VALUES(?,?,?,?,?)',
                        (qid,did,sid,pos,stop)).lastrowid
                    if sentence.strip():
                        self.db.execute('INSERT INTO fts(rowid,text) VALUES(?,?)',(rid,sentence))
                    pos=stop
                if pos!=len(original):
                    raise AssertionError('wrong UTF8 sentence offsets')
        self.db.commit()
        self.db.execute('VACUUM')
        self.db.commit()
        self.build_ms=(time.perf_counter_ns()-start)/1e6
        self.db_bytes=Path(db_path).stat().st_size

    def choose(self,qid,did,question,limit=2):
        terms=[x for x in dict.fromkeys(self.helper.words(question))
               if len(x)>=3 and x not in STOP]
        if terms:
            query=' OR '.join('"'+word.replace('"','""')+'"' for word in terms[:24])
            rows=self.db.execute('''SELECT spans.sid,spans.start,spans.end
                FROM fts JOIN spans ON spans.rid=fts.rowid
                WHERE fts MATCH ? AND spans.q=? AND spans.d=?
                ORDER BY bm25(fts),spans.rid LIMIT ?''',
                (query,qid,did,limit)).fetchall()
        else:
            rows=[]
        if len(rows)<limit:
            extras=self.db.execute('''SELECT sid,start,end FROM spans
                WHERE q=? AND d=? ORDER BY sid''',(qid,did)).fetchall()
            ids={x[0] for x in rows}
            rows+= [x for x in extras if x[0] not in ids][:max(0,limit-len(rows))]
        return rows[:limit]

    def close(self):
        self.db.close()


def selected_query_trace(rows,index):
    """Freeze document choices and FTS sentence choices, independent of frames."""
    helper=module('cdg_r54_r55',R54)
    choices={}
    lookup_us=[]
    for qid,row in enumerate(rows):
        for policy in POLICIES:
            selected=helper.select(row,policy)
            if len(selected)<5:
                raise AssertionError('unexpected fewer than five candidate docs')
            choices[(qid,policy)]={}
            for did in selected[:5]:
                begin=time.perf_counter_ns()
                spans=index.choose(qid,did,row['question'])
                lookup_us.append((time.perf_counter_ns()-begin)/1000)
                for sid,lo,hi in spans:
                    original_sent=row['context'][did][1][sid].encode('utf8')
                    ref=index.original_blobs[index.records[(qid,did)]]
                    if ref[lo:hi]!=original_sent:
                        raise AssertionError('index byte span not a true source sentence')
                choices[(qid,policy)][did]=spans
            choices[(qid,policy)]['ranked_docs']=selected
    return choices,round(statistics.median(lookup_us),3)


def decode_evidence(reader,doc_id,spans):
    logical=0
    gross_compressed=0
    frame_ids=set()
    for lo,hi in spans:
        receipt=reader.receipt(doc_id,lo,hi)
        data,compressed=reader.read(receipt,pin_generation=doc_id)
        expected=reader.archive.read(doc_id,lo,hi)[0]
        if data!=expected:
            raise AssertionError('receipt reconstruction mismatch')
        gross_compressed+=compressed
        logical+=len(data)
        pos=0
        for frame in reader.manifests[doc_id]['frames']:
            end=pos+frame['len']
            if end>lo and pos<hi:
                frame_ids.add(frame['sha'])
            pos=end
    return logical,gross_compressed,frame_ids


def experiment(rows):
    r48=module('cdg_r48_r55',R48)
    r54=module('cdg_r54_audit_r55',R54)
    with tempfile.TemporaryDirectory() as home:
        idx=SentenceIndex(Path(home)/'sentences.sqlite',rows)
        choices,search_p50=selected_query_trace(rows,idx)
        results={}
        try:
            for label,(frames,manifest) in CONFIGS.items():
                begin=time.perf_counter_ns()
                reader=r48.VersionedReader(idx.original_blobs,frames,manifest)
                build_ms=(time.perf_counter_ns()-begin)/1e6
                if reader.pack.decode(reader.packed_manifest,manifest)!=reader.manifests:
                    raise AssertionError('manifest decode mismatch')
                for i,blob in enumerate(idx.original_blobs):
                    original,_=reader.read(reader.receipt(i,0,len(blob)),pin_generation=i)
                    if original!=blob:
                        raise AssertionError('full source fails lossless roundtrip')
                by_policy={}
                for policy in POLICIES:
                    byk={}
                    for k in K_VALUES:
                        questions=len(rows)
                        doc_complete=0
                        sentence_complete=0
                        full_traffic=[]
                        selected_traffic=[]
                        selected_logical=[]
                        net_frame_traffic=[]
                        for qid,row in enumerate(rows):
                            ranked=choices[(qid,policy)]['ranked_docs'][:k]
                            titles={row['context'][i][0] for i in ranked}
                            gold={title for title,_ in row['supporting_facts']}
                            valid=r54.support_reference_issue(row) is None
                            doc_complete+=int(valid and gold.issubset(titles))
                            selected={(row['context'][d][0],sid)
                                      for d in ranked
                                      for sid,lo,hi in choices[(qid,policy)][d]}
                            sentence_complete+=int(valid and all((t,s) in selected
                                                      for t,s in row['supporting_facts']))
                            full_traffic_one=0
                            selected_traffic_one=0
                            selected_logical_one=0
                            touched=set()
                            for did in ranked:
                                doc_id=idx.records[(qid,did)]
                                fullblob=idx.original_blobs[doc_id]
                                _,compressed,frame_ids=decode_evidence(
                                    reader,doc_id,[(0,len(fullblob))])
                                full_traffic_one+=compressed
                                snippets=choices[(qid,policy)][did]
                                logical,compressed,ids=decode_evidence(
                                    reader,doc_id,[(lo,hi) for _,lo,hi in snippets])
                                selected_traffic_one+=compressed
                                selected_logical_one+=logical
                                touched.update(ids)
                            full_traffic.append(full_traffic_one)
                            selected_traffic.append(selected_traffic_one)
                            selected_logical.append(selected_logical_one)
                            net_frame_traffic.append(sum(len(reader.archive.frames[x]) for x in touched))
                        byk[str(k)]={
                            'questions':questions,
                            'complete_gold_documents':doc_complete,
                            'complete_gold_sentences_fts_top2':sentence_complete,
                            'mean_compressed_bytes_full_documents':round(statistics.mean(full_traffic),2),
                            'mean_compressed_bytes_selected_sentences_gross':round(statistics.mean(selected_traffic),2),
                            'mean_compressed_bytes_selected_sentences_dedup_query':round(statistics.mean(net_frame_traffic),2),
                            'mean_uncompressed_selected_sentence_bytes':round(statistics.mean(selected_logical),2),
                        }
                    by_policy[policy]=byk
                results[label]={
                    'archive_bytes':reader.size(),
                    'sentence_index_bytes':idx.db_bytes,
                    'combined_index_archive_bytes':idx.db_bytes+reader.size(),
                    'build_archive_ms':round(build_ms,3),
                    'policies':by_policy}
            return {
                'sample_size':len(rows),'documents_archived':len(idx.original_blobs),
                'index_build_ms':round(idx.build_ms,3),
                'fts_sentence_lookup_p50_us':search_p50,
                'retrieval_methods':list(POLICIES),'frame_methods':results,
                'limitations':[
                    '512-question dev subset is reduced to its first 128 SHA-ranked IDs; no tuning',
                    'candidate full documents remain read upfront for doc-level per-question BM25 and bridge',
                    'FTS sentence index built from all candidate source sentences, and its bytes charged',
                    'source-spans are exact bytes; selected sentence recall is annotation match, not entailment',
                    'compressed bytes counted for frame traffic, not actual SSD transfers or cache misses',
                    'index + archive footprint excludes Python objects and training/model tokens',
                    'same candidate pool with gold docs; not open-corpus retrieval or answer generation']}
        finally:
            idx.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    p.add_argument('--sample-size',type=int,default=128)
    args=p.parse_args()
    helper=module('cdg_r54_loader_r55',R54)
    if args.sample_size<=0 or args.sample_size>helper.FROZEN_SAMPLE_SIZE:
        raise ValueError('sample must be within prespecified R54 selection')
    rows=helper.locked_sample(helper.load_development())[:args.sample_size]
    result=experiment(rows)
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND55',json.dumps({
        'n':result['sample_size'],
        'index_bytes':next(iter(result['frame_methods'].values()))['sentence_index_bytes'],
        'layouts':{k:{'archive_bytes':v['archive_bytes'],
                      'k2_bridge':v['policies']['bridge']['2'],
                      'k5_bridge':v['policies']['bridge']['5']}
                   for k,v in result['frame_methods'].items()}},sort_keys=True))


if __name__=='__main__':
    main()
