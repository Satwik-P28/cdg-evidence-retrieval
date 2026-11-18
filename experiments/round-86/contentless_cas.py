#!/usr/bin/env python3
"""R86: source-compressed CAS with contentless FTS5, exact BM25 ranking control.

Replicate the strong R83/R84 title5/terms28 full-content FTS5 baseline.
Switch ONLY FTS5's built-in document storage to content='' (retain docsize)
and retrieve actual source bytes from SHA-bound R48 whole-Zlib CAS.
Tests quality/space/integrity/cost on the entire original locked SciFact corpus.
This is conventional SQLite index+compressed store composition, NOT a novel
retriever, compressor, or model for semantic factuality.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
from collections import defaultdict

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-83'))
sys.path.insert(0,str(HERE.parent/'round-84'))
from scifact_data_probe import fetch,parse,digests,LOCK
from retrieval_ablation import query_tokens

R48=HERE.parent/'round-48'/'evidence_bridge.py'
WEIGHT_TITLE=5.0
WEIGHT_ABSTRACT=1.0
MAX_QUERY_TERMS=28
K=(1,3,5,10)
EXPECTED_RELEASE_SHA="11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"


def load_r48():
    spec=importlib.util.spec_from_file_location('r48_index_only86',R48)
    if spec is None or spec.loader is None:
        raise ImportError('R48 reader missing')
    obj=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=obj
    spec.loader.exec_module(obj)
    return obj


def document_bytes(row):
    if not isinstance(row['title'],str) or not isinstance(row['abstract'],list):
        raise ValueError('unexpected SciFact document schema')
    return (row['title']+'\n'+' '.join(row['abstract'])).encode('utf8')


def make_fts(db_path,corpus,contentless):
    """Equivalent FTS5 index postings and docsize, different stored source text."""
    db=sqlite3.connect(str(db_path))
    db.execute('PRAGMA page_size=4096')
    db.execute('PRAGMA journal_mode=DELETE')
    schema="CREATE VIRTUAL TABLE sources USING fts5(title, abstract, tokenize='unicode61'"
    if contentless:
        schema+=", content=''"
    schema+=")"
    db.execute(schema)
    db.executemany(
        "INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
        [(idx+1,str(row['title']),' '.join(row['abstract']))
         for idx,row in enumerate(corpus)])
    db.commit()
    db.execute('VACUUM')
    db.commit()
    bytes_on_disk=db_path.stat().st_size
    return db,{
        'database_bytes':bytes_on_disk,
        'page_count':db.execute('PRAGMA page_count').fetchone()[0],
        'sqlite_version':sqlite3.sqlite_version,
        'source_text_recoverable_from_fts':not contentless,
        'config':"title abstract tokenize unicode61"+(" content='' " if contentless else ''),
        'note':'includes FTS5 index, docsize and embedded SQLite page overhead; not journal, RAM, or model',
    }


def query_text(claim):
    terms=query_tokens(claim,MAX_QUERY_TERMS)
    if not terms:
        return None
    # Only regex extracted Unicode alphanumerics, all quoted, passed as SQL param.
    return ' OR '.join('"'+t+'"' for t in terms)


def query_fts(db,claim,k=10):
    q=query_text(claim)
    if q is None:
        return []
    hits=db.execute(
        "SELECT rowid FROM sources WHERE sources MATCH ? "
        "ORDER BY bm25(sources,?,?),rowid LIMIT ?",
        (q,WEIGHT_TITLE,WEIGHT_ABSTRACT,k)).fetchall()
    return [int(x[0]) for x in hits]


def compute_rankings(db,claims,k=10):
    t0=time.perf_counter()
    ranks={str(x['id']):query_fts(db,x['claim'],k) for x in claims}
    return ranks,time.perf_counter()-t0


def label_recall(corpus,claims,ranking):
    mapping={str(i+1):str(row['doc_id']) for i,row in enumerate(corpus)}
    gold_cases=[]
    for row in claims:
        target={str(x) for x,v in (row.get('evidence') or {}).items() if v}
        if target:
            gold_cases.append((str(row['id']),target))
    if not gold_cases:
        raise ValueError('no annotated claims')
    return {
        'denominator':len(gold_cases),
        **{'recall_at_'+str(k):{
            'hits':sum(bool(target.intersection(
                mapping[str(i)] for i in ranking.get(cid,[])[:k]))
                        for cid,target in gold_cases),
        } for k in K},
    }


def validate_ranks(a,b):
    if set(a)!=set(b):
        raise AssertionError('query count mismatch')
    changed={key:(x,b[key]) for key,x in a.items() if x!=b[key]}
    if changed:
        raise AssertionError(
            'contentless FTS BM25 rank changed: '+str(len(changed))+' differing queries')


def materialize_top1(corpus,claims,rank,archive):
    source=[document_bytes(row) for row in corpus]
    total_activation=0
    requested=0
    t0=time.perf_counter()
    receipt_count=0
    for row in claims:
        ranked=rank[str(row['id'])]
        if not ranked:
            continue
        # In archive API a source slot is a generation, not a temporal version.
        slot=ranked[0]-1
        expected=source[slot]
        receipt=archive.receipt(slot,0,len(expected))
        back,traffic=archive.read(receipt,pin_generation=slot)
        if back!=expected:
            raise AssertionError('original source differs after contentless-ranked CAS materialization')
        requested+=len(back)
        total_activation+=traffic
        receipt_count+=1
    return {
        'verified_top1_source_reads':receipt_count,
        'uncompressed_bytes_materialized':requested,
        'logical_compressed_frame_bytes_activated':total_activation,
        'warm_memory_receipts_seconds':round(time.perf_counter()-t0,5),
    }


def compare(corpus,claims,create_archive=True):
    if len({str(row['doc_id']) for row in corpus})!=len(corpus):
        raise AssertionError('duplicate source document IDs')
    if len({str(row['id']) for row in claims})!=len(claims):
        raise AssertionError('duplicate claim IDs')
    with tempfile.TemporaryDirectory() as d:
        directory=Path(d)
        out={}
        ranks={}
        for mode in ('full_content','contentless'):
            start=time.perf_counter()
            db,meta=make_fts(directory/(mode+'.sqlite'),corpus,mode=='contentless')
            meta['index_construction_wall_seconds']=round(time.perf_counter()-start,5)
            ranks[mode],wall=compute_rankings(db,claims,k=max(K))
            meta['rank_all_queries_wall_seconds']=round(wall,5)
            if mode=='contentless':
                example=db.execute("SELECT title,abstract FROM sources WHERE rowid=1").fetchone()
                if example!=(None,None):
                    raise AssertionError('contentless FTS persisted accessible source text')
            else:
                value=db.execute("SELECT title,abstract FROM sources WHERE rowid=1").fetchone()
                if value!=(corpus[0]['title'],' '.join(corpus[0]['abstract'])):
                    raise AssertionError('full FTS did not retain original fields')
            db.close()
            out[mode]=meta
        validate_ranks(ranks['full_content'],ranks['contentless'])
        ranking=ranks['contentless']
        label_stats=label_recall(corpus,claims,ranking)
        for k in K:
            label_stats['recall_at_'+str(k)]['rate']=round(
                label_stats['recall_at_'+str(k)]['hits']/label_stats['denominator'],6)
        documents=[document_bytes(row) for row in corpus]
        archive=None
        archive_info={}
        if create_archive:
            r48=load_r48()
            t0=time.perf_counter()
            archive=r48.VersionedReader(documents,'whole','binary-zlib')
            archive_info={
                'source_utf8_bytes':sum(map(len,documents)),
                'persistent_whole_zlib_CAS_with_manifest_bytes':archive.size(),
                'source_id_to_slot_mapping_json_bytes':len(json.dumps(
                    [str(row['doc_id']) for row in corpus],
                    separators=(',',':')).encode('utf8')),
                'build_seconds':round(time.perf_counter()-t0,5),
            }
            archive_info.update(materialize_top1(corpus,claims,ranking,archive))
        return {
            'ranked_source_corpus_docs':len(corpus),
            'query_count':len(claims),
            'all_top10_rowid_rankings_identical':True,
            'full_content_fts':out['full_content'],
            'contentless_fts':out['contentless'],
            'gold_evidence_recall':label_stats,
            'contentless_index_savings_bytes':
                out['full_content']['database_bytes']-out['contentless']['database_bytes'],
            'archive':archive_info,
            'retained_size_comparison':{
                'full_fts_alone':out['full_content']['database_bytes'],
                'contentless_fts_plus_archive_plus_source_ID_mapping':
                    out['contentless']['database_bytes']+
                    archive_info.get('persistent_whole_zlib_CAS_with_manifest_bytes',0)+
                    archive_info.get('source_id_to_slot_mapping_json_bytes',0),
                'full_fts_plus_archive_duplicate_source_bytes':
                    out['full_content']['database_bytes']+
                    archive_info.get('persistent_whole_zlib_CAS_with_manifest_bytes',0)+
                    archive_info.get('source_id_to_slot_mapping_json_bytes',0),
            },
        }


def run():
    tar,raw=fetch()
    if digests(tar)['sha256']!=EXPECTED_RELEASE_SHA:
        raise AssertionError('original SciFact release changed')
    corpus,dev,counts=parse(raw)
    result=compare(corpus,dev)
    result['upstream']={
        'url':'https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz',
        'sha256':digests(tar)['sha256'],
        'source':'Original allenai/scifact, source/claim licenses in Round 83',
    }
    result['scope']={
        'baseline':'Full-content SQLite FTS5 BM25 title5/abstract1, first28 source-only query terms',
        'intervention':'Same postings and BM25 scoring but FTS5 contentless + separately SHA verified whole Zlib CAS',
        'strongest_claim':'Identical rank and recall + measured storage accounting for original source retrieval',
        'non_claims':[
            'no changed model input except source re-materialization',
            'no new semantic verifier or hallucination mitigation',
            'no cold SSD reads, fsync cost, durable update or transaction journal test',
            'no production concurrency cache/p99, no CAS incremental updates',
            'no first-class RAG generation or novel compression algorithm',
            'contentless FTS5 is an existing documented SQLite feature',
            'per-source manifest and doc-slot mappings are memory/storage overhead included in report as applicable',
        ],
    }
    print('ROUND86',json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    Path(args.out).write_text(json.dumps(run(),indent=2)+'\n')
