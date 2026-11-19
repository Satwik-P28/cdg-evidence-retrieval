#!/usr/bin/env python3
"""R94: frozen 3-way NLI verdicts from physically retrieved SciFact evidence.

Study retrieved-source verified verdict *yield* under R92 10/12 MiB budgets.
Never score an unrelated unannotated source as correct/incorrect based on a
different gold claim-document pair. No free-form generated answer is created.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
for r in ("round-72","round-80","round-83","round-86","round-87",
          "round-88","round-90","round-92"):
    sys.path.insert(0,str(HERE.parent/r))
from scifact_data_probe import fetch,parse,digests
from contentless_cas import make_fts,query_fts,document_bytes,EXPECTED_RELEASE_SHA
from atomic_source_db import read
from old_source_incremental import create_legacy_contentless
from snapshot_kill_probe import retrieve_snapshot
from storage_budget_eval import (
    annotated_gold,deterministic_order,budget_prefix_count,
    bootstrap_diff,BUDGETS_BYTES
)
from controlled_facts import load_pinned_model
from zero_shot_nli import MODEL_ID,MODEL_LOCK

SEEDS=(11,37,71)
BUDGETS=BUDGETS_BYTES
MAX_MODEL_TOKENS=384
MODEL_BATCH=12
DECISION_THRESHOLD=0.50
LABELS=("SUPPORT","CONTRADICT","ABSTAIN")


def verdict_from_probabilities(probabilities):
    """Frozen three-way policy. Neutral is not misclassified as contradiction."""
    p={str(k).lower():float(v) for k,v in probabilities.items()}
    if set(p)!={"entailment","contradiction","neutral"}:
        raise ValueError("invalid three-way NLI label map")
    if any(not 0<=v<=1 for v in p.values()):
        raise ValueError("invalid model probability")
    if p["entailment"]>=DECISION_THRESHOLD and p["entailment"]>=p["contradiction"]:
        return "SUPPORT"
    if p["contradiction"]>=DECISION_THRESHOLD and p["contradiction"]>p["entailment"]:
        return "CONTRADICT"
    return "ABSTAIN"


def retrieved_entries(db,corpus,cases,compressed):
    """Actual index-selected source material, with SHA checks.

    Labels are joined only AFTER selecting the retrieved source and are
    never given to query generation, corpus construction, or model scoring.
    """
    corpus_by_rid={i+1:row for i,row in enumerate(corpus)}
    out=[]
    for case in cases:
        if compressed:
            result=retrieve_snapshot(db,case["claim"],1)
            if result:
                rid,receipt=result[0]
                row=corpus_by_rid[rid]
                source=receipt["source_bytes"]
                if receipt["doc_id"]!=str(row["doc_id"]):
                    raise AssertionError("compressed identity mismatch")
            else:
                rid=None
                source=None
        else:
            result=query_fts(db,case["claim"],1)
            rid=result[0] if result else None
            if rid is not None:
                title,abstract=db.execute(
                    "SELECT title,abstract FROM sources WHERE rowid=?", (rid,)
                ).fetchone()
                source=(title+"\n"+abstract).encode("utf8")
            else:
                source=None
        if rid is None:
            out.append({"claim_id":case["id"],"source_id":None,
                        "claim":case["claim"],"source":None,
                        "human_label_for_selected_doc":None})
            continue
        row=corpus_by_rid[rid]
        if source!=document_bytes(row):
            raise AssertionError("source byte exactness or indexing failed")
        sid=str(row["doc_id"])
        out.append({
            "claim_id":case["id"],"source_id":sid,
            "claim":case["claim"],"source":source.decode("utf8"),
            "human_label_for_selected_doc":case["labels"].get(sid),
        })
    if len(out)!=len(cases):
        raise AssertionError("retrieved cohort changed")
    return out


def build_scenarios(corpus,cases,budgets=BUDGETS,seeds=SEEDS):
    """Fixed storage-cap hashes as R92; never use gold in source choice."""
    scenarios={}
    pairs={}
    with tempfile.TemporaryDirectory() as root:
        p=Path(root)
        compact=create_legacy_contentless(p/"complete_compressed.sqlite",corpus)
        compact_size=(p/"complete_compressed.sqlite").stat().st_size
        try:
            for budget in budgets:
                if compact_size>budget:
                    raise AssertionError("compressed complete source exceeds budget")
            full_rows=retrieved_entries(compact,corpus,cases,True)
            scenarios["compressed_full"]={
                "rows":full_rows,"documents":len(corpus),
                "sqlite_source_index_bytes":compact_size}
        finally:compact.close()
        for seed in seeds:
            ordered=deterministic_order(corpus,seed)
            for budget in budgets:
                n,size,_=budget_prefix_count(p,ordered,budget)
                selected=ordered[:n]
                file=p/"selected.sqlite"
                db,_=make_fts(file,selected,False)
                try:
                    if file.stat().st_size>budget:
                        raise AssertionError("conventional source/index exceeded cap")
                    name=f"conventional_{budget}_seed{seed}"
                    scenarios[name]={
                        "rows":retrieved_entries(db,selected,cases,False),
                        "documents":n,"sqlite_source_index_bytes":size,
                        "budget_bytes":budget,"seed":seed}
                finally:
                    db.close()
                    file.unlink(missing_ok=True)
        for name,entry in scenarios.items():
            for row in entry["rows"]:
                if row["source_id"] is None:continue
                identity=(row["claim_id"],row["source_id"])
                if identity in pairs:
                    if (pairs[identity]["source"]!=row["source"] or
                            pairs[identity]["claim"]!=row["claim"]):
                        raise AssertionError("different materialization for same claim-source")
                pairs[identity]=row
    return scenarios,pairs


def score_nli(pairs):
    """Pinned prior-art DeBERTa NLI. Fixed threshold, no fitting to SciFact."""
    lock=json.loads(MODEL_LOCK.read_text())
    revision=lock["revision"]
    tokenizer,model,torch,params=load_pinned_model(MODEL_ID,revision)
    labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
    if set(labels.values())!={"entailment","contradiction","neutral"}:
        raise ValueError("checkpoint label map changed")
    keys=sorted(pairs)
    outputs={}
    tokens=0
    truncations=0
    start=time.perf_counter()
    try:
        for batch_start in range(0,len(keys),MODEL_BATCH):
            chosen=keys[batch_start:batch_start+MODEL_BATCH]
            docs=[pairs[key]["source"] for key in chosen]
            claims=[pairs[key]["claim"] for key in chosen]
            # Count truncation independently; only-first caps document, not
            # the scientific claim. The original is never shortened in store.
            lengths=[len(tokenizer(d,c,add_special_tokens=True,
                                   truncation=False)["input_ids"])
                     for d,c in zip(docs,claims)]
            truncations+=sum(x>MAX_MODEL_TOKENS for x in lengths)
            enc=tokenizer(docs,claims,return_tensors="pt",padding=True,
                          truncation="only_first",max_length=MAX_MODEL_TOKENS)
            tokens+=int(enc["attention_mask"].sum().item())
            with torch.inference_mode():
                p=torch.softmax(model(**enc).logits,dim=-1).tolist()
            for key,vec in zip(chosen,p):
                prediction=verdict_from_probabilities({
                    labels[i]:float(prob) for i,prob in enumerate(vec)})
                outputs[key]=prediction
        if len(outputs)!=len(pairs):
            raise AssertionError("score count mismatch")
        return outputs,{
            "model_id":MODEL_ID,"revision_sha":revision,
            "parameter_count":params,
            "unique_claim_source_pairs_scored":len(keys),
            "original_inputs_over_384_tokens":truncations,
            "model_input_tokens":tokens,
            "cpu_wall_seconds":round(time.perf_counter()-start,3),
            "decision_policy":"P(entailment)>=.5 support, P(contradiction)>=.5 contradict, else abstain",
            "training":"Released third-party checkpoint; no CDG fit or label-based calibration",
        }
    finally:
        del model
        gc.collect()


def claim_ids(cases):
    """Round-83/92 annotated_gold records use original SciFact 'id', not 'claim_id'."""
    ids=[str(row["id"]) for row in cases]
    if len(ids)!=len(set(ids)):
        raise AssertionError("duplicate annotated SciFact claim ids")
    return ids


def evaluate_scenario(rows,model_results,expected_case_ids):
    if len(rows)!=len(expected_case_ids):
        raise AssertionError("case count mismatch")
    if [row["claim_id"] for row in rows]!=expected_case_ids:
        raise AssertionError("retrieval sequence drift")
    counts={
        "annotated_source_retrieved":0,
        "unannotated_source_retrieved":0,
        "empty_retrieval":0,
        "correct_annotated_verdict":0,
        "wrong_annotated_verdict":0,
        "abstained_on_annotated":0,
        "predicted_support_unannotated":0,
        "predicted_contradict_unannotated":0,
        "abstained_unannotated":0,
    }
    binary=[]
    for row in rows:
        if row["source_id"] is None:
            counts["empty_retrieval"]+=1
            binary.append(0)
            continue
        pred=model_results[(row["claim_id"],row["source_id"])]
        human=row["human_label_for_selected_doc"]
        if human is None:
            counts["unannotated_source_retrieved"]+=1
            if pred=="SUPPORT":
                counts["predicted_support_unannotated"]+=1
            elif pred=="CONTRADICT":
                counts["predicted_contradict_unannotated"]+=1
            else:
                counts["abstained_unannotated"]+=1
            binary.append(0)
        else:
            if human not in ("SUPPORT","CONTRADICT"):
                raise AssertionError("invalid human label")
            counts["annotated_source_retrieved"]+=1
            if pred==human:
                counts["correct_annotated_verdict"]+=1
                binary.append(1)
            elif pred=="ABSTAIN":
                counts["abstained_on_annotated"]+=1
                binary.append(0)
            else:
                counts["wrong_annotated_verdict"]+=1
                binary.append(0)
    n=len(rows)
    if (counts["annotated_source_retrieved"]
        +counts["unannotated_source_retrieved"]
        +counts["empty_retrieval"])!=n:
        raise AssertionError("outcome rows did not partition")
    return {
        **counts,
        "claims_with_human_annotated_evidence":n,
        "verified_pair_verdict_yield":round(
            counts["correct_annotated_verdict"]/n,6),
        "conditional_verdict_accuracy_on_annotated_only":(
            round(counts["correct_annotated_verdict"]
                  /counts["annotated_source_retrieved"],6)
            if counts["annotated_source_retrieved"] else None),
        "UNVERIFIED_NOT_INCORRECT":"Retrieved docs without SciFact doc-specific annotations are not judged wrong",
    },binary


def run(corpus,claims,seeds=SEEDS,budgets=BUDGETS):
    cases=annotated_gold(claims,corpus)
    scenarios,pairs=build_scenarios(corpus,cases,budgets,seeds)
    model_predictions,model_meta=score_nli(pairs)
    baseline=claim_ids(cases)
    outcomes={}
    success={}
    for name,item in scenarios.items():
        metrics,binary=evaluate_scenario(item["rows"],model_predictions,baseline)
        outcomes[name]={
            "documents":item["documents"],
            "source_index_bytes":item["sqlite_source_index_bytes"],
            "budget_bytes":item.get("budget_bytes"),
            "seed":item.get("seed"),
            "source_label_outcomes":metrics,
        }
        success[name]=binary
    ctrl=success["compressed_full"]
    paired={}
    for name in outcomes:
        if name=="compressed_full":continue
        paired[name]=bootstrap_diff(ctrl,success[name],seed=int(
            hashlib.sha256(name.encode()).hexdigest()[:8],16))
    return {
        "round":94,
        "cohort":{
            "full_corpus_docs":len(corpus),
            "dev_claims":len(claims),
            "dev_claims_with_gold_evidence":len(cases),
            "budgets":list(budgets),
            "seeds":list(seeds),
            "human_label_scope":"selected claim-document only",
            "source_selection": "R92 SHA-ordered budget prefixes, label independent",
        },
        "model":model_meta,
        "outcomes":outcomes,
        "paired_full_compressed_vs_conventional":paired,
        "limitations":[
            "This is pretrained claim-source label verification, not free-form generated RAG answers",
            "No human label for wrong/unannotated retrieved source; yields are certified lower bounds, not accuracy",
            "SciFact model may have encountered published dataset or similar scientific claims in training",
            "Human annotation is only doc-specific; other sources could also independently support or refute claim",
            "Only pretrained NLI xsmall with untuned 0.50 threshold; model can bottleneck evidence quality",
            "PubSciFact same dev claims reused across multiple document-selection seeds",
            "Static post-VACUUM SQLite size; no model weights, RAM, concurrent updates or SSD cold reads in budgets",
            "Pretrained model inference time reflects warm CPU GitHub runner and 384-token truncation",
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default=str(HERE/"ci-results.json"))
    a=ap.parse_args()
    tar,raw=fetch()
    source_sha=digests(tar)["sha256"]
    if source_sha!=EXPECTED_RELEASE_SHA:
        raise AssertionError("original release SHA changed")
    corpus,claims,_=parse(raw)
    result=run(corpus,claims)
    result["original_scifact_sha256"]=source_sha
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND94",json.dumps({
        "sha":source_sha,
        "cohort":result["cohort"],
        "model":result["model"],
        "outcomes":result["outcomes"],
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
