#!/usr/bin/env python3
"""Round 45: gold-ID-blind temporal source retrieval on PRISM-Edit TimeConflict.

Uses the 91 existing records and their same-release QA variants. Labels are NOT
independently established truth. No LLM generator, semantic entailment, or broad
RAG performance claim. Source row IDs are only used in the evaluator.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import statistics
import time
import zlib
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT.parent/'round-41'/'timeconflict'
RELATIONS=('P26','P35')
MONTHS={name.lower():index+1 for index,name in enumerate(
    ('January','February','March','April','May','June','July','August',
     'September','October','November','December'))}
STOP=set('who what when was is were be are the a an to of for from has have had been '
         'married spouse husband wife president head state leader government country '
         'during between and in on since which whom did does at with as'.split())


def read_data(location=DATA):
    rows=[]
    qa=[]
    serial=0
    for rel in RELATIONS:
        raw=(location/'factual'/f'conflicts_{rel}.jsonl').read_text(encoding='utf8').splitlines()
        items=[json.loads(line) for line in raw if line.strip()]
        byid={int(item['id']):item for item in items}
        for item in items:
            serial+=1
            rows.append({'key':serial,'relation':rel,'upstream_id':int(item['id']),
                         'record':item})
        with (location/'text_factual'/f'conflicts_{rel}.csv').open(encoding='utf-8-sig',newline='') as file:
            for item in csv.DictReader(file):
                for answer in json.loads(item['qas']):
                    for question in answer['question']:
                        qa.append({'relation':rel,'upstream_id':int(item['id']),
                                   'question':question,'answer':answer['answer']})
    return rows,qa


def month_end(year,month):
    if month==12:return date(year+1,1,1).toordinal()-1
    return date(year,month+1,1).toordinal()-1


def question_window(question,strict=True):
    month=re.search(r'\b('+'|'.join(MONTHS)+r')\s+((?:19|20)\d\d)\b',
                    question,re.IGNORECASE)
    years=[int(x) for x in re.findall(r'\b(?:19|20)\d\d\b',question)]
    if month:
        year=int(month.group(2));mon=MONTHS[month.group(1).lower()]
        return ((f'{year:04d}-{mon:02d}-01',date.fromordinal(month_end(year,mon)).isoformat())
                if strict else (f'{year:04d}-{mon:02d}-{date.fromordinal(month_end(year,mon)).day:02d}',)*2)
    if len(years)>1:
        low,high=min(years),max(years)
        return ((f'{low}-01-01',f'{high}-12-31') if strict
                else (f'{(low+high)//2}-07-01',)*2)
    if years:
        y=years[0]
        return ((f'{y}-01-01',f'{y}-12-31') if strict else (f'{y}-07-01',)*2)
    return None


def source_interval(source):
    match=re.fullmatch(r'(\d{4}-\d\d-\d\d)\s+to\s+(\d{4}-\d\d-\d\d|\.\.\.)',
                       source['time_range'])
    if not match:raise ValueError('unexpected time range '+source['time_range'])
    return match.group(1),('9999-12-31' if match.group(2)=='...' else match.group(2))


def select_fact(record,window,strict):
    if window is None:return None,'no_time'
    lo,hi=window
    covering=[]
    partial=[]
    for section in ('before_object','after_object'):
        obj=record[section]
        start,end=source_interval(obj)
        if start<=lo and hi<=end:
            covering.append(obj['label'])
        elif start<=hi and lo<=end:
            partial.append(obj['label'])
    distinct=set(covering)
    if len(distinct)==1 and (not strict or not partial):
        return next(iter(distinct)),'answered'
    if not covering and not partial:
        return None,'no_interval'
    return None,'ambiguous'


def tokens(question):
    found=re.findall(r'[^\W_]+',question.casefold(),flags=re.UNICODE)
    return [t for t in found if len(t)>1 and t not in STOP and not t.isdigit()]


class Index:
    def __init__(self,rows):
        self.rows={row['key']:row for row in rows}
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE VIRTUAL TABLE docs USING fts5(subject,body)')
        self.payload={}
        for row in rows:
            record=row['record']
            subject=record['subject']['label']
            body=(f"{record['relation_label']} {record['subject'].get('description','')} "
                  f"{record['before_object']['label']} {record['before_object']['time_range']} "
                  f"{record['after_object']['label']} {record['after_object']['time_range']}")
            self.db.execute('INSERT INTO docs(rowid,subject,body) VALUES(?,?,?)',
                            (row['key'],subject,body))
            source=json.dumps(record,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
            self.payload[row['key']]=(hashlib.sha256(source).hexdigest(),zlib.compress(source,6))
        self.db.commit()

    def search(self,question,k=5):
        lexical=tokens(question)
        if not lexical:return []
        query=' OR '.join('"'+t.replace('"','""')+'"' for t in lexical)
        return [id for (id,) in self.db.execute(
            'SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY bm25(docs,15.0,1.0),rowid LIMIT ?',
            (query,k)).fetchall()]

    def exact(self,question):
        matches=[key for key,row in self.rows.items()
                 if row['record']['subject']['label'].casefold() in question.casefold()]
        return sorted(matches,key=lambda k:(-len(self.rows[k]['record']['subject']['label']),k))

    def choose(self,question,method,k=5):
        fts=self.search(question,k)
        if method=='bm25':
            return fts[0] if fts else None
        if method=='exact':
            names=self.exact(question)
            return names[0] if len(names)==1 else None
        if method=='hybrid':
            names=[key for key in self.exact(question) if key in fts]
            return names[0] if len(names)==1 else (fts[0] if fts else None)
        raise ValueError(method)

    def inspect(self,key):
        sha,frame=self.payload[key]
        blob=zlib.decompress(frame)
        if hashlib.sha256(blob).hexdigest()!=sha:
            raise ValueError('source digest mismatch')
        return json.loads(blob),len(frame)

    def close(self):
        self.db.close()


def evaluate(rows,qa,k=5):
    index=Index(rows)
    unique={(row['relation'],row['upstream_id']):row['key'] for row in rows}
    records=len(rows)
    out={'records':records,'questions':len(qa),'topk':k,'topk_contains_gold':0,'methods':{}}
    for method in ('bm25','exact','hybrid'):
        for time_mode in ('latest','point','window'):
            out['methods'][method+'_'+time_mode]={
                'source_found':0,'answered':0,'correct':0,
                'incorrect':0,'abstained':0,'compressed_bytes_read':0,
                'source_lookup_p50_us':0}
    latencies={key:[] for key in out['methods']}
    try:
        for item in qa:
            q=item['question']
            gold=unique[(item['relation'],item['upstream_id'])]
            if gold in index.search(q,k):
                out['topk_contains_gold']+=1
            for method in ('bm25','exact','hybrid'):
                started=time.perf_counter_ns()
                source=index.choose(q,method,k)
                elapsed=(time.perf_counter_ns()-started)/1000
                for mode in ('latest','point','window'):
                    key=method+'_'+mode
                    stats=out['methods'][key]
                    latencies[key].append(elapsed)
                    if source is None:
                        stats['abstained']+=1
                        continue
                    stats['source_found']+=int(source==gold)
                    record,compressed=index.inspect(source)
                    stats['compressed_bytes_read']+=compressed
                    if mode=='latest':
                        predicted=record['after_object']['label'];state='answered'
                    else:
                        strict=(mode=='window')
                        predicted,state=select_fact(record,question_window(q,strict),strict)
                    if state=='answered':
                        stats['answered']+=1
                        if predicted==item['answer']:
                            stats['correct']+=1
                        else:
                            stats['incorrect']+=1
                    else:
                        stats['abstained']+=1
        for key,stats in out['methods'].items():
            stats['source_lookup_p50_us']=round(statistics.median(latencies[key]),3)
            stats['correct_per_question']=round(stats['correct']/len(qa),4)
            stats['incorrect_per_answered']=round(stats['incorrect']/stats['answered'],4) if stats['answered'] else None
        return out
    finally:
        index.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(ROOT/'results.json'))
    args=parser.parse_args()
    rows,qa=read_data()
    result=evaluate(rows,qa)
    print('ROUND45',json.dumps(result,sort_keys=True))
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
