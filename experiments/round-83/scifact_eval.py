#!/usr/bin/env python3
"""R83: independent-of-CDG synthetic SciFact expert-annotated evidence control.

Reproduce SciFact authors' TF-IDF retrieval, compare FTS5/BM25, then score
source-conditioned gold and retrieved evidence with published models.
Published model weights and SciFact annotations are third-party prior work.
Never assign gold truth labels to arbitrary retrieved documents.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-80'))
from controlled_facts import load,load_pinned_model,nli_scores,minicheck_scores
from factcg_control import infer as factcg_scores
from scifact_data_probe import fetch,parse,digests,LOCK,UPSTREAM

R48=HERE.parent/'round-48'/'evidence_bridge.py'
SAMPLE_SALT='CDG-R83-SCIFACT-DEV-GOLD-DOC-CLAIMS-v1'
SAMPLE_PER_LABEL=30
TOP_K=(1,3,5,10)
POLICIES=('gold_oracle','tfidf_top1','fts5_top1')
SCHEMA='scifact_claim_doc_support_v1'
TOKEN=re.compile(r'[^\W_]+',re.UNICODE)
STOP=frozenset('the a an is are was were been have has had for from at of in to on by with and or that this its his her they it not as be do does did will which where when who if then can may could should'.split())


def doc_text(x):
    return str(x['title'])+'\n'+' '.join(x['abstract'])


def source_claim_labels(row):
    labels={}
    for key,rationales in row['evidence'].items():
        lab={x['label'] for x in rationales}
        if len(lab)!=1:raise AssertionError('ambiguous SciFact rationale labels')
        val=next(iter(lab))
        if val not in ('SUPPORT','CONTRADICT'):raise AssertionError('unexpected label')
        labels[str(key)]=val
    return labels


def select_gold(claims,corpus_ids):
    """Fixed label-balanced annotated claim-doc pairs, unique doc and claim IDs."""
    items={'SUPPORT':[],'CONTRADICT':[]}
    for row in claims:
        claimid=str(row['id'])
        for sid,label in source_claim_labels(row).items():
            if sid in corpus_ids:
                items[label].append((claimid,sid,row))
    selected=[]
    used_claim=set()
    used_doc=set()
    for label in ('SUPPORT','CONTRADICT'):
        ranked=sorted(items[label],key=lambda x:(
            hashlib.sha256((SAMPLE_SALT+'|'+label+'|'+x[0]+'|'+x[1]).encode()).hexdigest(),
            x[0],x[1]))
        count=0
        for cid,sid,row in ranked:
            if cid in used_claim or sid in used_doc:continue
            selected.append({
                'claim_id':cid,'gold_doc_id':sid,'claim':row['claim'],
                'label':label,'supported':int(label=='SUPPORT'),
                'gold_doc_labels':source_claim_labels(row),
            })
            used_claim.add(cid)
            used_doc.add(sid)
            count+=1
            if count==SAMPLE_PER_LABEL:break
        if count!=SAMPLE_PER_LABEL:
            raise ValueError('cannot create distinct-source balanced sampled gold pairs')
    selected.sort(key=lambda r:(r['label'],r['claim_id'],r['gold_doc_id']))
    identity='\n'.join(r['claim_id']+'|'+r['gold_doc_id']+'|'+r['label']
                       for r in selected).encode()
    return selected,hashlib.sha256(identity).hexdigest()


def tfidf_ranks(corpus,claims,k=10):
    """Faithful SciFact author TF-IDF document text and hyperparameters.
    Their tie ranking is scores.argsort()[::-1]; match exactly.
    """
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    t0=time.perf_counter()
    vectorizer=TfidfVectorizer(stop_words='english',ngram_range=(1,1))
    vectors=vectorizer.fit_transform(
        [str(row['title'])+' '.join(row['abstract']) for row in corpus])
    queries=vectorizer.transform([r['claim'] for r in claims])
    similarities=vectors@queries.T
    output={}
    for j,claim in enumerate(claims):
        col=similarities[:,j].toarray().reshape(-1)
        ranked=col.argsort()[::-1]
        output[str(claim['id'])]=[str(corpus[i]['doc_id']) for i in ranked[:k]]
    return output,{
        'wall_seconds_build_and_all_queries':round(time.perf_counter()-t0,3),
        'docs':vectors.shape[0],'vocabulary_terms':vectors.shape[1],
        'sparse_array_bytes_without_vocabulary_or_runtime':int(
            vectors.data.nbytes+vectors.indices.nbytes+vectors.indptr.nbytes),
        'reference':'allenai/scifact/verisci/inference/abstract_retrieval/tfidf.py',
        'stop_words':'english','ngram_range':[1,1],
        'corpus_text':'title + joined abstract sentences, no separator',
        'rank_ties':'scores.argsort()[::-1] (as original authors)',
    }


def fts5_ranks(corpus,claims,k=10):
    """Conventional SQLite Unicode FTS5/BM25, a separate retrieval control."""
    t0=time.perf_counter()
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'scifact_fts.sqlite'
        db=sqlite3.connect(str(path))
        try:
            db.execute("CREATE VIRTUAL TABLE sources USING fts5(title, abstract, tokenize='unicode61')")
            db.executemany("INSERT INTO sources(rowid,title,abstract) VALUES (?,?,?)",
                           [(i+1,row['title'],' '.join(row['abstract']))
                            for i,row in enumerate(corpus)])
            db.commit()
            index_bytes=path.stat().st_size
            output={}
            skipped=0
            for row in claims:
                terms=[]
                used=set()
                for tok in TOKEN.findall(row['claim'].lower()):
                    if len(tok)<3 or tok in STOP or tok in used:continue
                    used.add(tok)
                    terms.append(tok)
                    if len(terms)>=28:break
                if not terms:
                    output[str(row['id'])]=[]
                    skipped+=1
                    continue
                # All tokens come from Python word regex; no quoted user SQL.
                q=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
                hits=db.execute(
                    "SELECT rowid FROM sources WHERE sources MATCH ? "
                    "ORDER BY bm25(sources,5.0,1.0),rowid LIMIT ?",(q,k)
                ).fetchall()
                output[str(row['id'])]=[str(corpus[i-1]['doc_id']) for (i,) in hits]
            return output,{
                'wall_seconds_build_and_all_queries':round(time.perf_counter()-t0,3),
                'persistent_index_bytes':index_bytes,
                'queries_no_content_terms':skipped,
                'query_policy':'OR first 28 distinct unicode word tokens, length>=3 minus fixed stop set',
                'bm25_weights':{'title':5.0,'abstract':1.0},
            }
        finally:
            db.close()


def retrieval_metrics(claims,corpus_ids,ranked):
    evaluated=[r for r in claims
               if any(s in corpus_ids for s in source_claim_labels(r))]
    if not evaluated:raise ValueError('no gold evidence claims')
    by_label={}
    for label in ('all','SUPPORT','CONTRADICT'):
        subset=[r for r in evaluated if label=='all' or
                label in source_claim_labels(r).values()]
        recall={}
        for k in TOP_K:
            matches=0
            for row in subset:
                target=set(source_claim_labels(row))&corpus_ids
                returned=set(ranked.get(str(row['id']),[])[:k])
                matches+=int(bool(target&returned))
            recall[f'recall_at_{k}']={
                'hits':matches,'denom':len(subset),
                'rate':round(matches/len(subset),5) if subset else None}
        by_label[label]={'n':len(subset),'recall':recall}
    return by_label


def verify_archived_evidence(corpus,selected,tfidf,fts):
    """Retrieved source ID -> full SHA-bound original source bytes -> model text.
    Whole and gear each reconstruct the same selected route text, with oracle
    source-array slot identity (not a historical revision).
    """
    r48=load('cdg_r48_r83',R48)
    blobs=[doc_text(row).encode('utf8') for row in corpus]
    id_index={str(row['doc_id']):i for i,row in enumerate(corpus)}
    t0=time.perf_counter()
    readers={name:r48.VersionedReader(blobs,name,'binary-zlib')
             for name in ('whole','gear512')}
    build_seconds=time.perf_counter()-t0
    routes={key:[] for key in POLICIES}
    cost={name:{'bytes_activated':0,'reads_verified':0,
                'warm_read_seconds':0.0} for name in readers}
    for row in selected:
        cid=row['claim_id']
        chosen={
            'gold_oracle':row['gold_doc_id'],
            'tfidf_top1':tfidf[cid][0],
            'fts5_top1':fts[cid][0] if fts.get(cid) else row['gold_doc_id'],
        }
        if not fts.get(cid):
            raise ValueError('empty FTS5 source hit; no oracle fall-through allowed')
        for policy,sid in chosen.items():
            i=id_index[sid]
            original=blobs[i]
            assert original
            recovered={}
            for name,reader in readers.items():
                t1=time.perf_counter()
                receipt=reader.receipt(i,0,len(original))
                retrieved,logical_traffic=reader.read(receipt,pin_generation=i)
                elapsed=time.perf_counter()-t1
                if retrieved!=original:
                    raise AssertionError('byte-exact source receipt failed')
                recovered[name]=retrieved
                cost[name]['bytes_activated']+=logical_traffic
                cost[name]['reads_verified']+=1
                cost[name]['warm_read_seconds']+=elapsed
            if recovered['whole']!=recovered['gear512']:
                raise AssertionError('archive formats returned different evidence')
            routes[policy].append({
                'claim_id':cid,'selected_doc_id':sid,
                'gold_doc_id':row['gold_doc_id'],
                'gold_doc_labels':row['gold_doc_labels'],
                'claim':row['claim'],'doc':recovered['whole'].decode('utf8'),
                'supported':row['supported'],'label':row['label'],
                'selected_doc_has_annotation':sid in row['gold_doc_labels'],
                'selected_doc_annotation':row['gold_doc_labels'].get(sid),
            })
    return routes,{
        'corpus_original_source_utf8_bytes':sum(map(len,blobs)),
        'source_count':len(blobs),
        'archive_build_wall_seconds':round(build_seconds,3),
        'archives':{name:{
            'persistent_bytes_including_manifest':reader.size(),
            'route_source_readbacks':cost[name]['reads_verified'],
            'mean_compressed_activation_per_route':round(
                cost[name]['bytes_activated']/max(1,cost[name]['reads_verified']),3),
            'warm_memory_read_seconds_total':round(cost[name]['warm_read_seconds'],5),
        } for name,reader in readers.items()},
        'note':'Archive slot index is a distinct source doc, not a temporal generation; no physical SSD read or revisions',
    }


def classify_predictions(routes,probs,name):
    """Only retrieved source with a human annotated doc label can be scored.
    For arbitrary retrieved sources output response acceptance, not accuracy.
    """
    if len(probs)!=len(routes):raise AssertionError('model prediction count drifted')
    out={}
    for policy in POLICIES:
        pairs=[(row,float(score)) for row,score in zip(routes,probs)
               if row['route']==policy]
        if not pairs:raise ValueError('missing policy route')
        positives=[int(score>.5) for _,score in pairs]
        annotated=[(r,p) for (r,_),p in zip(pairs,positives)
                   if r['selected_doc_has_annotation']]
        matrix=Counter()
        for r,p in annotated:
            gold=int(r['selected_doc_annotation']=='SUPPORT')
            matrix.update(tp=int(p and gold),fp=int(p and not gold),
                          fn=int(not p and gold),tn=int(not p and not gold))
        tp,fp,fn,tn=[matrix[k] for k in ('tp','fp','fn','tn')]
        support_recall=tp/(tp+fn) if tp+fn else 0
        contradiction_rejection=tn/(tn+fp) if tn+fp else 0
        out[policy]={
            'pairs':len(pairs),
            'model_supported_predictions_on_originally_supported_claims':sum(
                p for (r,_),p in zip(pairs,positives) if r['label']=='SUPPORT'),
            'model_supported_predictions_on_originally_contradictory_claims':sum(
                p for (r,_),p in zip(pairs,positives) if r['label']=='CONTRADICT'),
            'no_human_label_for_selected_doc_pairs':len(pairs)-len(annotated),
            'human_annotated_doc_pairs':len(annotated),
            'only_annotated_pairs_confusion':{
                'tp':tp,'fp':fp,'fn':fn,'tn':tn,
                'balanced_accuracy':round((support_recall+contradiction_rejection)/2,5)
                    if tp+fn and tn+fp else None},
            'WARNING':'Do not score wrong-document predictions against the original gold doc label',
        }
    return out


def evaluate():
    tar,raw=fetch()
    corpus,claims,counts=parse(raw)
    id_set={str(r['doc_id']) for r in corpus}
    selected,sample_sha=select_gold(claims,id_set)
    tfidf,tfidf_meta=tfidf_ranks(corpus,claims,10)
    fts,fts_meta=fts5_ranks(corpus,claims,10)
    retrieval={
        'official_author_tfidf':retrieval_metrics(claims,id_set,tfidf),
        'sqlite_fts5_bm25':retrieval_metrics(claims,id_set,fts),
    }
    route_dict,storage_meta=verify_archived_evidence(corpus,selected,tfidf,fts)
    flat=[]
    for policy in POLICIES:
        for r in route_dict[policy]:
            flat.append({**r,'route':policy})
    source_text=[r['doc'] for r in flat]
    cases=[{'claim':r['claim'],'doc':r['doc']} for r in flat]
    nli,nli_meta=nli_scores(cases,source_text)
    mc,mc_meta=minicheck_scores(cases,source_text)
    cg,cg_meta=factcg_scores(cases,source_text)
    scored={
        'generic_nli':classify_predictions(flat,nli,'generic_nli'),
        'minicheck':classify_predictions(flat,mc,'minicheck'),
        'factcg':classify_predictions(flat,cg,'factcg'),
    }
    for policy in POLICIES:
        for name in scored:
            if scored[name][policy]['pairs']!=len(selected):
                raise AssertionError('route sample changed after scoring')
    return {
        'dataset':'SciFact scientific abstract verification dev, AllenAI',
        'dataset_provenance':{
            'official_source':UPSTREAM,
            'archive_sha256':digests(tar)['sha256'],
            'members':{key:digests(value) for key,value in raw.items()},
            'license':'annotations CC BY 4.0; abstracts ODC-By 1.0'},
        'schema_counts':counts,
        'sample':{
            'gold_doc_claim_pairs':len(selected),
            'label_counts':dict(Counter(x['label'] for x in selected)),
            'source_id_claim_pair_sha256':sample_sha,
            'selection':'30 label-balanced source-unique and claim-unique annotated dev pairs, SHA-sorted, no model outcomes',
        },
        'retrieval':{
            'metrics':retrieval,
            'official_tfidf':tfidf_meta,'fts5':fts_meta},
        'archive':storage_meta,
        'models':{'generic_nli':nli_meta,'minicheck':mc_meta,'factcg':cg_meta},
        'source_conditioned_model_outcomes':scored,
        'limitations':[
            'SciFact is independent of CDG synthetic fixtures, but publicly released models may have encountered this benchmark or similar training examples',
            'nondeployable human oracle chooses the annotated evidence abstract; retrieval is evaluated separately',
            'an arbitrary retrieved abstract has NO original gold claim-doc label, so model accept/reject on wrong source cannot count as correct hallucination classification',
            'only 60 source-unique and claim-unique annotated pairs are model-scored, label-balanced subset of dev; full 300 claims used for retrieval recall',
            'source text from the original expert-labeled SciFact corpus, no original text/annotations redistributed',
            'TF-IDF is author-equivalent but model ranking differences in tied sparse scores may exist',
            'SQLite FTS5 is a conventional separate keyword BM25 control, not a CDG semantic breakthrough',
            'whole and gear512 archives use distinct source slots, not actual temporal revisions',
            'read timings are in-memory Python, not OS cold SSD I/O or transactional durability',
            'only annotated same-source model predictions are classified with human labels',
            'model input caps differ: NLI 384, MiniCheck/FactCG 2048 and FactCG instruction template; CPU performance not matched architecture comparison',
            'we did not train, fine-tune, generate, edit or mitigate an answer; only detect support for externally annotated claims',
        ],
    }


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=p.parse_args()
    result=evaluate()
    Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND83',json.dumps({
        'data_sha':result['dataset_provenance']['archive_sha256'],
        'sample':result['sample'],
        'retrieval':result['retrieval'],
        'archives':result['archive'],
        'gold_oracle_confusion':{
            m:data['gold_oracle']['only_annotated_pairs_confusion']
            for m,data in result['source_conditioned_model_outcomes'].items()},
        'retrieved_annotated_pair_counts':{
            m:{route:out['human_annotated_doc_pairs']
               for route,out in data.items()} for m,data in result['source_conditioned_model_outcomes'].items()},
        'model_costs':result['models'],
    },sort_keys=True))
