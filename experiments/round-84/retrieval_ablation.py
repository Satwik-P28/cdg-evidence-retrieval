#!/usr/bin/env python3
"""R84: tune conventional SciFact BM25 retrieval on train, verify on dev.

Reproduction of original SciFact TF-IDF baseline and SQLite FTS5/BM25 title
boost + query budget ablations, without neural model or proprietary software.
Use *all* 5,183 source abstracts. Official SciFact release bytes are already
SHA-locked by R83. The test/dev rankings do not select parameters.
"""
from __future__ import annotations
import argparse,hashlib,io,json,random,re,sqlite3,statistics,sys,tarfile,tempfile,time
from pathlib import Path
from collections import Counter,defaultdict
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'round-83'))
from scifact_data_probe import fetch,parse,digests
from scifact_eval import tfidf_ranks,TOKEN,STOP

K=(1,3,5,10)
VARIANTS=tuple((weight,budget) for weight in (1.0,3.0,5.0,10.0)
               for budget in (12,28))
TRAIN_SELECTION_KEY='recall_at_5'
SEED=84197
BOOTSTRAP_REPS=2000
MEMBER_TRAIN='data/claims_train.jsonl'


def train_claims_from_verified_archive(archive):
    """Original full archive SHA is checked *before* this function is called."""
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tf:
        names={m.name for m in tf.getmembers() if m.isfile()}
        if MEMBER_TRAIN not in names:
            raise ValueError('no original SciFact training claims')
        member=tf.getmember(MEMBER_TRAIN)
        if not 0<member.size<5_000_000:
            raise ValueError('unexpected train member size')
        reader=tf.extractfile(member)
        if reader is None:
            raise ValueError('unreadable train member')
        content=reader.read(member.size+1)
    cases=[json.loads(line) for line in content.splitlines() if line.strip()]
    if len({str(r['id']) for r in cases})!=len(cases):
        raise AssertionError('SciFact train IDs repeated')
    return cases,{'original_train_jsonl_sha256':hashlib.sha256(content).hexdigest(),
                  'original_train_rows':len(cases),'member':MEMBER_TRAIN}


def annotated_claims(rows,corpus_ids):
    """Only claims with an annotated gold source, never guessed negatives."""
    output=[]
    for r in rows:
        gold={str(sid) for sid,v in (r.get('evidence') or {}).items()
              if sid in corpus_ids and v}
        if gold:
            output.append({'id':str(r['id']),'claim':str(r['claim']),'gold':gold})
    return output


def query_tokens(claim,max_terms):
    terms=[]
    used=set()
    for tok in TOKEN.findall(claim.lower()):
        if len(tok)<3 or tok in STOP or tok in used:
            continue
        used.add(tok)
        terms.append(tok)
        if len(terms)>=max_terms:
            break
    return terms


def recall_at_k(rows,ranked,k):
    if not rows:
        raise ValueError('no gold annotated source claims')
    return sum(int(bool(row['gold'].intersection(ranked.get(row['id'],[])[:k])))
               for row in rows)/len(rows)


def compute_metrics(rows,ranked):
    return {'n':len(rows), **{
            'recall_at_'+str(k):round(recall_at_k(rows,ranked,k),6)
            for k in K}}


def fts_rank_all(corpus,queries,max_k=10):
    """One shared persistent full-corpus index, varied query and BM25 weights."""
    start=time.perf_counter()
    outputs={}
    costs={}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'scifact_ablation.sqlite'
        conn=sqlite3.connect(str(path))
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE sources USING fts5(title, abstract, tokenize='unicode61')")
            conn.executemany("INSERT INTO sources(rowid,title,abstract) VALUES(?,?,?)",
                             [(i+1,str(row['title']),' '.join(row['abstract']))
                              for i,row in enumerate(corpus)])
            conn.commit()
            retained=path.stat().st_size
            ids=[str(x['doc_id']) for x in corpus]
            for title_weight,limit in VARIANTS:
                name=variant_name(title_weight,limit)
                per_claim={}
                skipped=0
                query_start=time.perf_counter()
                for row in queries:
                    tokens=query_tokens(row['claim'],limit)
                    if not tokens:
                        per_claim[str(row['id'])]=[]
                        skipped+=1
                        continue
                    query=' OR '.join('"'+t+'"' for t in tokens)
                    hits=conn.execute(
                        "SELECT rowid FROM sources WHERE sources MATCH ? "
                        "ORDER BY bm25(sources,?,?),rowid LIMIT ?",
                        (query,title_weight,1.,max_k)).fetchall()
                    per_claim[str(row['id'])]=[ids[int(rowid)-1] for (rowid,) in hits]
                outputs[name]=per_claim
                costs[name]={
                    'title_bm25_weight':title_weight,
                    'abstract_bm25_weight':1.0,
                    'max_unique_query_tokens':limit,
                    'queries':len(queries),
                    'unmatched_or_empty_queries':skipped,
                    'query_wall_seconds':round(time.perf_counter()-query_start,4),
                }
            return outputs,{
                'index_bytes':retained,
                'index_build_seconds':round(time.perf_counter()-start-
                    sum(v['query_wall_seconds'] for v in costs.values()),4),
                'variants':costs,
                'index_scope':'same 5,183 source abstracts, reused for all variants',
                'query_language':'OR quoted Unicode alphanumeric terms with R83 fixed STOP list',
            }
        finally:
            conn.close()


def variant_name(title_weight,limit):
    if title_weight not in (1.,3.,5.,10.) or limit not in (12,28):
        raise ValueError('variant is not predeclared')
    return f'fts_title{int(title_weight)}_terms{limit}'


def choose_on_train(train,ranked_by_variant,metrics):
    """No access to dev scores, doc labels, or dev retrieval quality."""
    choices=[]
    for name in sorted(ranked_by_variant):
        m=metrics[name]['train']
        choices.append((m['recall_at_5'],m['recall_at_1'],
                        -int(name.split('_terms')[-1]),
                        name))
    # Sort by train recall@5; then recall@1; then fewer query terms;
    # then lexical name for deterministic ties.
    ranked=sorted(choices,key=lambda x:(-x[0],-x[1],-x[2],x[3]))
    return ranked[0][3]


def bootstrap_delta(rows,a,b,k=1,reps=BOOTSTRAP_REPS,seed=SEED):
    if len(rows)<5:
        raise ValueError('too few claims for grouped bootstrap')
    rng=random.Random(seed)
    gain=[]
    for r in rows:
        correct_a=int(bool(r['gold'].intersection(a.get(r['id'],[])[:k])))
        correct_b=int(bool(r['gold'].intersection(b.get(r['id'],[])[:k])))
        gain.append(correct_b-correct_a)
    observed=sum(gain)/len(rows)
    deltas=[]
    for _ in range(reps):
        sample=[gain[rng.randrange(len(gain))] for _ in rows]
        deltas.append(sum(sample)/len(sample))
    deltas.sort()
    return {'delta_recall_b_minus_a':round(observed,6),
            'claim_level_bootstrap_95ci':[
                round(deltas[int(.025*(reps-1))],6),
                round(deltas[int(.975*(reps-1))],6)],
            'paired_n':len(rows),
            'caveat':'claim-bootstrap not source-document-cluster confidence; claims share abstract topics'}


def run():
    archive,raw=fetch()
    corpus,dev,validated=parse(raw)
    train,train_info=train_claims_from_verified_archive(archive)
    if set(str(r['id']) for r in train)&set(str(r['id']) for r in dev):
        raise AssertionError('SciFact train/dev claim identifier leak')
    corpus_ids={str(x['doc_id']) for x in corpus}
    train_gold=annotated_claims(train,corpus_ids)
    dev_gold=annotated_claims(dev,corpus_ids)
    all_claims=train+dev
    # Existing original SciFact TF-IDF routine uses the whole original corpus
    # and exact authors' model: independent baseline, no fitted dev labels.
    tfidf,tfidf_cost=tfidf_ranks(corpus,all_claims,max(K))
    fts,fts_cost=fts_rank_all(corpus,all_claims,max(K))
    metrics={
        'official_SciFact_TFIDF':{
            'train':compute_metrics(train_gold,tfidf),
            'dev':compute_metrics(dev_gold,tfidf)}
    }
    for name,ranks in fts.items():
        metrics[name]={
            'train':compute_metrics(train_gold,ranks),
            'dev':compute_metrics(dev_gold,ranks)}
    choice=choose_on_train(train_gold,fts,metrics)
    incumbent='fts_title5_terms28'
    comparison={
        'selected_on_train_only':choice,
        'locked_reference':incumbent,
        'chosen_vs_TFIDF_dev_at1':bootstrap_delta(
            dev_gold,tfidf,fts[choice],1),
        'chosen_vs_TFIDF_dev_at5':bootstrap_delta(
            dev_gold,tfidf,fts[choice],5),
        'chosen_vs_R83_FTS5_dev_at1':bootstrap_delta(
            dev_gold,fts[incumbent],fts[choice],1),
        'chosen_vs_R83_FTS5_dev_at5':bootstrap_delta(
            dev_gold,fts[incumbent],fts[choice],5),
    }
    outcome={
        'upstream':{
            'archive_sha256':digests(archive)['sha256'],
            'original_sciFact_derived_train_member':train_info,
            'source_lock_verification':'R83 official corpus+dev member SHA and release SHA, read before train member',
        },
        'counts':{
            'corpus_docs':len(corpus),
            'train_claims_all':len(train),'train_claims_with_evidence':len(train_gold),
            'dev_claims_all':len(dev),'dev_claims_with_evidence':len(dev_gold)},
        'experiment':{
            'retriever_variants':list(fts),
            'selection_uses_only_train_recall_at5_then_recall_at1_then_shorter_query':True,
            'r83_incumbent_FTS5':incumbent,
            'all_eval_variant_metrics_are_exploratory_except_train_selected_policy':True,
            'official_TFIDF_control':tfidf_cost,
            'shared_fts_index':fts_cost},
        'per_policy_recall':metrics,
        'train_selected_comparison':comparison,
        'limitations':[
            'this is conventional full corpus lexical retrieval, not a new RAG algorithm',
            'train-only policy choice prevents dev outcome peeking but the methods are developed using a public benchmark also used by others',
            'all indexed source texts immutable and original, but indexed size does not include compressed source manifests',
            'BM25 queries and term budgets are constrained to eight fixed candidate policies predeclared before evaluation; only one policy promoted by train',
            'SciFact gold source recall is not judgment of factual accuracy, and unannotated retrieved docs may provide valid support',
            'the benchmark splits are distinct claims but share source abstracts and topics; claim bootstrap may underestimate corpus correlation',
            'the 5,183-source corpus and warm SQLite index exclude cold SSD I/O and incremental update measurements',
            'all variants score the same source data and use one index build; query CPU timings can fluctuate with workload/order',
            'dataset claims and corpus abstracts are never redistributed; only aggregate recall/hashes in artifacts',
        ],
    }
    print('ROUND84_GRID',json.dumps({name:{'train':row['train'],'dev':row['dev']}
         for name,row in metrics.items()},sort_keys=True),flush=True)
    print('ROUND84',json.dumps({
        'upstream_sha':outcome['upstream']['archive_sha256'],
        'counts':outcome['counts'],
        'selected':choice,
        'train_chosen':metrics[choice]['train'],
        'dev_chosen':metrics[choice]['dev'],
        'dev_original_FTS5':metrics[incumbent]['dev'],
        'dev_TFIDF':metrics['official_SciFact_TFIDF']['dev'],
        'paired_delta':comparison,
    },sort_keys=True),flush=True)
    return outcome


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=a.parse_args()
    Path(args.out).write_text(json.dumps(run(),indent=2)+'\n')


if __name__=='__main__':
    main()
