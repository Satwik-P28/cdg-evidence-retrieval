#!/usr/bin/env python3
"""R107 independently reproduced pretrained dense, lexical and hybrid evidence.

Official SHA-locked QASPER v0.3 DEV original paper question/paragraph
expert evidence annotations. Compare conventional BM25 (R97), two frozen
public pretrained embedding models, and fixed RRF k=60 fusion, without
looking at human DEV labels when ranking or setting fusion weights.

Charge source/FTS SQLite bytes, dense on-disk float32 vector arrays,
frozen safetensors model file bytes and CPU encoding time separately.
Every retrieval regime searches only the QASPER question's supplied paper.

No generation, answer truth, hallucination mitigation, no source-byte
compression novelty. Published models MAY have seen data domain / papers.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
for r in ("round-86","round-96","round-97","round-102"):
    sys.path.insert(0,str(HERE.parent/r))
from qasper_source_probe import fetch as fetch_qasper
from qasper_paragraph_retrieval import load_dev,paper_rank,gold_recall
from contentless_cas import document_bytes,make_fts
from train_only_zstd_dictionary import DEV_SHA

RRF_K=60
MAX_TOKENS=256
BATCH_SIZE=32
BOOTSTRAPS=1000
MODEL_SPECS={
    "MiniLM-L6": {
        "name":"sentence-transformers/all-MiniLM-L6-v2",
        "revision":"1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "pool":"mean",
        "query_prefix":"",
    },
    "BGE-small-v1.5":{
        "name":"BAAI/bge-small-en-v1.5",
        "revision":"5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "pool":"cls",
        "query_prefix":"Represent this sentence for searching relevant passages: ",
    },
}
K=(1,3,5,10)


def ensure_original_source_docs(docs):
    hashes=[]
    for d in docs:
        raw=document_bytes(d)
        if raw!=(str(d["title"])+"\n"+" ".join(d["abstract"])).encode("utf8"):
            raise AssertionError("original QASPER source encoding changed")
        hashes.append(hashlib.sha256(raw).digest())
    if len(set(str(x["doc_id"]) for x in docs))!=len(docs):
        raise AssertionError("original source identity collision")
    return {
        "source_documents_exact":len(docs),
        "source_sha256_receipts":len(hashes),
        "original_raw_bytes":sum(len(document_bytes(d)) for d in docs),
    }


def encode_texts(model,tokenizer,texts,pool,max_length=MAX_TOKENS,
                 batch_size=BATCH_SIZE):
    """Frozen transformer encoder with documented source-specific pooling."""
    import numpy as np
    import torch
    if pool not in ("mean","cls"):
        raise ValueError("pool must be mean or CLS")
    result=[]
    at_limit=0
    start=time.perf_counter()
    model.eval()
    with torch.inference_mode():
        for i in range(0,len(texts),batch_size):
            batch=texts[i:i+batch_size]
            encoded=tokenizer(
                batch,padding=True,truncation=True,
                max_length=max_length,return_tensors="pt")
            at_limit+=sum(int(row.sum().item()==max_length)
                          for row in encoded["attention_mask"])
            output=model(**encoded).last_hidden_state
            if pool=="cls":
                pooled=output[:,0,:]
            else:
                weights=encoded["attention_mask"].unsqueeze(-1)
                pooled=(output*weights).sum(dim=1)/weights.sum(dim=1).clamp(min=1)
            pooled=torch.nn.functional.normalize(pooled,p=2,dim=1)
            result.append(pooled.cpu().numpy().astype("float32"))
    if not result:
        raise ValueError("no input text to encode")
    array=np.concatenate(result,axis=0)
    if array.ndim!=2 or array.shape[0]!=len(texts):
        raise AssertionError("embedding count or shape mismatch")
    if not np.isfinite(array).all():
        raise AssertionError("encoder generated nonfinite vector")
    return array,{
        "vectors":len(texts),"dimension":array.shape[1],
        "source_texts_tokenized_at_max_window":at_limit,
        "encoding_seconds":round(time.perf_counter()-start,5),
        "max_source_or_question_input_tokens":max_length,
        "batch_size":batch_size,
    }


def frozen_embedding_model(spec):
    """Download only published pinned safe tensors; no remote custom code."""
    import torch
    from transformers import AutoModel,AutoTokenizer
    from huggingface_hub import hf_hub_download
    if len(spec["revision"])!=40:
        raise ValueError("model revision must be full immutable SHA")
    if spec["pool"] not in ("mean","cls"):
        raise ValueError("unexpected pooling")
    t0=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(
        spec["name"],revision=spec["revision"],trust_remote_code=False)
    model=AutoModel.from_pretrained(
        spec["name"],revision=spec["revision"],trust_remote_code=False,
        use_safetensors=True)
    model.eval()
    raw_model=hf_hub_download(
        repo_id=spec["name"],filename="model.safetensors",
        revision=spec["revision"])
    model_file=Path(raw_model)
    digest=hashlib.sha256(model_file.read_bytes()).hexdigest()
    param_bytes=sum(p.numel()*p.element_size() for p in model.parameters())
    return model,tokenizer,{
        "model_name":spec["name"],
        "model_repo_revision":spec["revision"],
        "model_safetensors_sha256":digest,
        "model_safetensors_file_bytes":model_file.stat().st_size,
        "model_parameter_tensor_bytes_in_memory":param_bytes,
        "model_parameter_count":sum(p.numel() for p in model.parameters()),
        "checkpoint_load_seconds":round(time.perf_counter()-t0,5),
        "embedding_pool":spec["pool"],
        "query_instruction":spec["query_prefix"],
    }


def dense_rank(cases,doc_vectors,query_vectors):
    import numpy as np
    if len(cases)!=len(query_vectors):
        raise AssertionError("question/embedding identity mismatch")
    if len(doc_vectors)==0:
        raise AssertionError("no article paragraphs")
    ranks={}
    t0=time.perf_counter()
    for idx,case in enumerate(cases):
        start=int(case["row_start"])
        end=int(case["row_end"])
        if end<start:
            ranks[case["id"]]=[]
            continue
        arr=doc_vectors[start-1:end]
        scores=arr@query_vectors[idx]
        if not np.isfinite(scores).all():
            raise AssertionError("nonfinite retrieval score")
        # Stable tie-break by original source rowid, not ground truth.
        ids=np.arange(start,end+1,dtype=np.int64)
        order=np.lexsort((ids,-scores))
        ranks[case["id"]]=ids[order].tolist()
    return ranks,round(time.perf_counter()-t0,5)


def rrf_rank(rank_sources,k=RRF_K):
    """RRF on full paper-scoped ranks, no human gold or fitted weights."""
    if not rank_sources:
        raise ValueError("no retrieval ranking inputs")
    if k<1:raise ValueError("RRF rank constant must be positive")
    vals=defaultdict(float)
    for ranks in rank_sources:
        if len(ranks)!=len(set(ranks)):
            raise AssertionError("one rank list repeats original evidence source")
        for i,rid in enumerate(ranks,1):
            vals[int(rid)]+=1.0/(k+i)
    return sorted(vals,key=lambda rid:(-vals[rid],rid))


def fuse_cases(ranks_by_model,cases,k=RRF_K):
    names=tuple(ranks_by_model)
    if len(names)<2:
        raise ValueError("require at least two independent rank sources")
    result={}
    for c in cases:
        result[c["id"]]=rrf_rank(
            [ranks_by_model[name][c["id"]] for name in names],k)
    return result


def evidence_metrics(cases,ranks):
    basic=gold_recall(cases,ranks)
    eligible=[c for c in cases if c["gold_rowids"]]
    gold_tokens=sum(len(c["gold_rowids"]) for c in eligible)
    hist={}
    for k in K:
        matched=sum(len(c["gold_rowids"]&set(
            ranks.get(c["id"],[])[:k])) for c in eligible)
        hist[str(k)]={
            "gold_paragraph_mentions_hit":matched,
            "gold_paragraph_union_denominator":gold_tokens,
            "fraction":round(matched/gold_tokens,6)
                      if gold_tokens else None,
        }
    return {
        "any_one_gold_paragraph_recall":basic,
        "gold_annotator_union_paragraph_coverage":hist,
        "warning":"Annotator-union evidence is NOT a minimal necessary joint witness: different expert answers can cite alternative paragraphs",
    }


def paper_cluster_bootstrap(cases,candidate,incumbent,k=10,reps=BOOTSTRAPS):
    """Paper-cluster bootstrap for descriptive paired hit differences."""
    randomizer=random.Random(107_2026+k)
    eligible=[c for c in cases if c["gold_rowids"]]
    by_paper=defaultdict(list)
    for c in eligible:
        id=c["id"]
        new=int(bool(set(candidate[id][:k])&c["gold_rowids"]))
        old=int(bool(set(incumbent[id][:k])&c["gold_rowids"]))
        by_paper[c["paper"]].append(new-old)
    papers=sorted(by_paper)
    total=sum(map(len,by_paper.values()))
    diff=sum(sum(v) for v in by_paper.values())/total
    draws=[]
    for _ in range(reps):
        cluster=[papers[randomizer.randrange(len(papers))]
                 for j in range(len(papers))]
        observations=[x for p in cluster for x in by_paper[p]]
        draws.append(sum(observations)/len(observations))
    draws.sort()
    n=len(draws)
    return {
        "metric":"paired any-expert-paragraph Recall@"+str(k),
        "delta_fraction":round(diff,6),
        "paper_cluster_bootstrap_bounds_95pct":[
            round(draws[int(0.025*(n-1))],6),
            round(draws[int(0.975*(n-1))],6)],
        "bootstraps":reps,
        "clusters":len(papers),
        "eligible_questions":total,
        "important_limit":"One public dataset and pretrained checkpoints; bootstrap reflects clustering not future domain transfer",
    }


def run():
    import numpy as np
    import torch
    torch.set_num_threads(2)
    source=fetch_qasper()
    if source["dev"]["sha256"]!=DEV_SHA:
        raise AssertionError("official QASPER original release SHA changed")
    docs,cases,cohort=load_dev(source["dev"]["data"])
    exact=ensure_original_source_docs(docs)
    source_texts=[str(row["title"])+"\n"+" ".join(row["abstract"])
                  for row in docs]
    question_texts=[c["claim"] for c in cases]
    with tempfile.TemporaryDirectory() as scratch:
        folder=Path(scratch)
        index=folder/"bm25.sqlite"
        from contentless_cas import make_fts as fts_builder
        db,_=fts_builder(index,docs,False)
        try:
            bm25={}
            bm_t0=time.perf_counter()
            for case in cases:
                bm25[case["id"]]=paper_rank(
                    db,case["claim"],case["row_start"],
                    case["row_end"],max(0,case["row_end"]-case["row_start"]+1))
            bm_sec=time.perf_counter()-bm_t0
            fts_bytes=index.stat().st_size
            doc_model={}
            vectors={}
            rankings={"BM25":bm25}
            for shortname,spec in MODEL_SPECS.items():
                model,tok,meta=frozen_embedding_model(spec)
                D,docstats=encode_texts(
                    model,tok,source_texts,spec["pool"])
                Q,questats=encode_texts(
                    model,tok,[spec["query_prefix"]+s for s in question_texts],
                    spec["pool"])
                if len(D)!=len(docs) or len(Q)!=len(cases):
                    raise AssertionError("dense model did not encode all sources")
                path=folder/(shortname+".npy")
                np.save(path,D,allow_pickle=False)
                disk_bytes=path.stat().st_size
                rankings[shortname],ranking_seconds=dense_rank(cases,D,Q)
                doc_model[shortname]={
                    **meta,
                    "document_embeddings":docstats,
                    "question_embeddings":questats,
                    "document_vectors_float32_payload_bytes":int(D.nbytes),
                    "document_vectors_npy_file_bytes":disk_bytes,
                    "question_vectors_ephemeral_bytes":int(Q.nbytes),
                    "scoped_dense_ranking_seconds":ranking_seconds,
                    "persistent_FTS5_and_embedding_bytes_without_model":fts_bytes+disk_bytes,
                    "persistent_FTS5_embedding_and_model_safetensors_bytes":
                        fts_bytes+disk_bytes+meta["model_safetensors_file_bytes"],
                }
                del D,Q,model,tok
            for name in list(rankings):
                for c in cases:
                    vals=rankings[name][c["id"]]
                    if any(not c["row_start"]<=rid<=c["row_end"] for rid in vals):
                        raise AssertionError("dense/lexical retrieved wrong article")
                    if len(vals)!=len(set(vals)):
                        raise AssertionError("duplicate ranked original paragraph")
            rankings["RRF_BM25_MiniLM"]=fuse_cases(
                {"lexical":bm25,"dense":rankings["MiniLM-L6"]},cases)
            rankings["RRF_BM25_BGE"]=fuse_cases(
                {"lexical":bm25,"dense":rankings["BGE-small-v1.5"]},cases)
            rankings["RRF_BM25_BGE_MiniLM"]=fuse_cases(
                {"lexical":bm25,
                 "bge":rankings["BGE-small-v1.5"],
                 "minilm":rankings["MiniLM-L6"]},cases)
            scoring={}
            for name,ranks in rankings.items():
                scoring[name]={
                    "evidence":evidence_metrics(cases,ranks),
                    "paired_vs_BM25_at_1":paper_cluster_bootstrap(
                        cases,ranks,bm25,1),
                    "paired_vs_BM25_at_10":paper_cluster_bootstrap(
                        cases,ranks,bm25,10),
                }
            # Exact decoded original evidence provenance for every retrieved top10.
            verified=0
            for name,ranks in rankings.items():
                for c in cases:
                    for rid in ranks[c["id"]][:10]:
                        raw=document_bytes(docs[rid-1])
                        if hashlib.sha256(raw).digest()!=hashlib.sha256(
                                source_texts[rid-1].encode("utf8")).digest():
                            raise AssertionError("retrieved source bytes lost")
                        verified+=1
            return {
                "round":107,
                "source":"QASPER 0.3 original DEV full text, article known",
                "official_dev_sha256":DEV_SHA,
                "original_corpus":cohort,
                "original_source_provenance":exact,
                "lexical_source_readable_fts5_bytes":fts_bytes,
                "lexical_fts5_topk_scoping_seconds":round(bm_sec,5),
                "pretrained_model_components":doc_model,
                "evaluated_retrieval_methods":list(scoring),
                "retrieval_eligible_gold_metrics":scoring,
                "retrieved_source_top10_original_sha_verified":verified,
                "no_dev_label_or_question_fitting_of_rank_weights":True,
                "rrf_constant":RRF_K,
                "dense_max_input_tokens":MAX_TOKENS,
                "notes":[
                    "Pretrained model weights may have seen publicly available QASPER papers or related training text; cannot prove training exclusion",
                    "The question supplies the correct paper ID; this is paragraph localization, not global paper selection",
                    "Dense vectors model weights and FTS5 bytes are separate persistent cost categories; tokenizer/cache/activation RAM not included",
                    "All-original source docs and original indexed title/body remain unchanged; no compression method under test here",
                    "Any-one gold paragraph recall and gold-annotator-union coverage do not mean a full logically sufficient evidence set",
                    "No answer generator, answer F1 or hallucination reduction measured",
                    "No learned reciprocal-rank-fusion weight or dev-label tuning",
                    "Frozen public MiniLM and BGE weights plus fixed max token window; BGE and MiniLM original training distribution unknown",
                    "One GitHub Actions CPU runner with warm OS cache, no cold SSD throughput replication",
                ],
            }
        finally:
            db.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=p.parse_args()
    result=run()
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND107",json.dumps({
        "source":result["original_source_provenance"],
        "bm25_bytes":result["lexical_source_readable_fts5_bytes"],
        "models":{k:{
            "model_sha":v["model_repo_revision"],
            "model_file_bytes":v["model_safetensors_file_bytes"],
            "embedding_vectors_bytes":v["document_vectors_npy_file_bytes"],
            "model_dim":v["document_embeddings"]["dimension"],
            "source_texts_at_max_window":v["document_embeddings"][
                "source_texts_tokenized_at_max_window"],
            "encode_seconds":v["document_embeddings"]["encoding_seconds"],
        } for k,v in result["pretrained_model_components"].items()},
        "ranking":{k:{
            "r1":v["evidence"]["any_one_gold_paragraph_recall"]["recall"]["r1"],
            "r5":v["evidence"]["any_one_gold_paragraph_recall"]["recall"]["r5"],
            "r10":v["evidence"]["any_one_gold_paragraph_recall"]["recall"]["r10"],
            "delta_r10":v["paired_vs_BM25_at_10"],
        } for k,v in result["retrieval_eligible_gold_metrics"].items()},
        "receipts_verified":result["retrieved_source_top10_original_sha_verified"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
