#!/usr/bin/env python3
"""R69: human-labeled RAGTruth faithfulness diagnostic, no model training.

Dataset source snapshots pinned by Git commit + blob SHA-1, downloaded transiently.
The original responses and source text remain upstream and are never emitted.
Methods are fixed, naive and label-blind. Metrics are against RAGTruth human
annotations, not a demonstration of hallucination prevention.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
UPSTREAM="ParticleMedia/RAGTruth"
REVISION="c103204b9ce28d6bbad859304bf30de72b8ed8fe"
BLOBS={
    "dataset/response.jsonl":"f9ae5913fb9976684f3e13be3cd3465062db54cc",
    "dataset/source_info.jsonl":"119277774009f110aa58596b93f9512f62594a89",
}
SAMPLE_SALT="CDG-R69-RAGTRUTH-QA-TEST-GROUPS-v1"
MAX_TEST_SOURCE_GROUPS=128
POLICIES=("accept_all","reject_all","content_overlap","source_quadgram","number_entity_guard","joint_lexical")
STOP=frozenset(("the a an is are was were it its to for from and or of in on with "
                "at by that this as be been being have has had do did does how why "
                "what when which where who there their than then also one two three "
                "they them his her our your not into over about after before can "
                "could would should will may might any each all based given").split())
TOKEN=re.compile(r"[^\W_]+",flags=re.UNICODE)
SENTENCE=re.compile(r"[^.!?\n]+(?:[.!?]+|$)",flags=re.UNICODE)
NUMERIC=re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
PROPER=re.compile(r"\b(?:[A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,})*\b")


def git_blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()


def download(path,fetch=None):
    if path not in BLOBS:
        raise ValueError("unrecognized upstream data path")
    url=f"https://raw.githubusercontent.com/{UPSTREAM}/{REVISION}/{path}"
    if fetch is None:
        with urlopen(Request(url,headers={"User-Agent":"CDG-RAGTruth-validation/1.0"}),
                     timeout=120) as resp:
            raw=resp.read(70_000_001)
    else:
        raw=fetch(url)
    if len(raw)>70_000_000 or git_blob(raw)!=BLOBS[path]:
        raise ValueError("upstream RAGTruth Git blob digest/size check failed")
    parsed=[json.loads(line) for line in raw.splitlines() if line.strip()]
    return parsed,{"git_blob":BLOBS[path],"sha256":hashlib.sha256(raw).hexdigest(),
                   "raw_bytes":len(raw),"rows":len(parsed),"url":url}


def select_sources(response_rows,source_by_id,group_cap=MAX_TEST_SOURCE_GROUPS):
    # A source group is a shared input across six generated responses.
    # No train sources are included. Sample by source IDs to prevent leakage
    # across responses to the same context. No human label is read in selection.
    candidates={str(x["source_id"]) for x in response_rows
                if x.get("split")=="test"
                and str(x.get("source_id")) in source_by_id
                and source_by_id[str(x["source_id"])].get("task_type")=="QA"}
    ranked=sorted(candidates,key=lambda sid:(
        hashlib.sha256((SAMPLE_SALT+"|"+sid).encode()).hexdigest(),sid))
    if len(ranked)<group_cap:
        raise ValueError(f"too few QA test sources: {len(ranked)} for {group_cap}")
    selected=set(ranked[:group_cap])
    sample=[x for x in response_rows if x.get("split")=="test"
            and str(x.get("source_id")) in selected]
    return sample,{
        "available_test_source_groups":len(candidates),
        "selected_source_groups":len(selected),
        "source_id_digest":hashlib.sha256("\n".join(sorted(selected)).encode()).hexdigest(),
        "response_count":len(sample),
    }


def source_text(source_info):
    if source_info.get("task_type")=="QA":
        info=source_info.get("source_info",{})
        if isinstance(info,dict):
            return str(info.get("passages",""))
        raise ValueError("QA source_info must have passages dictionary")
    info=source_info.get("source_info")
    if isinstance(info,str):
        return info
    return json.dumps(info,sort_keys=True,ensure_ascii=False)


def words(value):
    return [x.casefold() for x in TOKEN.findall(str(value))]


def content_words(value):
    return [x for x in words(value) if len(x)>=4 and x not in STOP]


def source_ngrams(value,n):
    w=words(value)
    return set(tuple(w[i:i+n]) for i in range(max(0,len(w)-n+1)))


def fragments(text):
    # This is a deterministic sentence-like split, not a semantic claim parser.
    spans=[(m.start(),m.end(),m.group()) for m in SENTENCE.finditer(text)
           if m.group().strip()]
    return spans or ([(0,len(text),text)] if text else [])


def sentence_flags(sentence,source):
    source_bag=set(content_words(source))
    observed=content_words(sentence)
    coverage=sum(tok in source_bag for tok in observed)/max(1,len(observed))
    ngrams4=source_ngrams(source,4)
    reply_ngrams=source_ngrams(sentence,4)
    literal_quadgram=any(x in ngrams4 for x in reply_ngrams)
    # Proper names or numbers are not automatically true/false. Treat lexical
    # novelty only as a source-grounding warning with explicit false positives.
    numbers=set(NUMERIC.findall(source))
    names={x.casefold() for x in PROPER.findall(source)}
    introduced_number=any(n not in numbers for n in NUMERIC.findall(sentence))
    introduced_name=any(x.casefold() not in names for x in PROPER.findall(sentence))
    guard=int(introduced_number or introduced_name)
    return {
        "content_overlap":coverage<0.55 if observed else False,
        "source_quadgram":not literal_quadgram if reply_ngrams else False,
        "number_entity_guard":bool(guard),
        "joint_lexical":(coverage<0.55 if observed else False) or bool(guard),
    }


def predictions(response,source):
    by_policy={key:[False]*len(response) for key in POLICIES}
    for start,end,sentence in fragments(response):
        flags=sentence_flags(sentence,source)
        for method in POLICIES:
            if method=="reject_all":flag=True
            elif method=="accept_all":flag=False
            else:flag=flags[method]
            for j in range(start,end):
                by_policy[method][j]=flag
    return by_policy


def annotated_masks(row):
    response=row.get("response","")
    annotations=row.get("labels",[]) or []
    if not isinstance(response,str) or not isinstance(annotations,list):
        raise ValueError("unexpected response/labels schema")
    label=[False]*len(response)
    true_implicit=[False]*len(response)
    invalid=[]
    for item in annotations:
        start,end=item.get("start"),item.get("end")
        if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(response):
            invalid.append("range")
            continue
        if response[start:end]!=item.get("text"):
            invalid.append("text_mismatch")
        value=item.get("implicit_true",False)
        truthy=(value is True or str(value).casefold()=="true")
        for j in range(start,end):
            label[j]=True
            if truthy:true_implicit[j]=True
    strict=[x and not t for x,t in zip(label,true_implicit)]
    return label,strict,invalid


def one_confusion(predicted,truth):
    tp=sum(x and y for x,y in zip(predicted,truth))
    fp=sum(x and not y for x,y in zip(predicted,truth))
    fn=sum(not x and y for x,y in zip(predicted,truth))
    tn=sum(not x and not y for x,y in zip(predicted,truth))
    return (tp,fp,fn,tn)


def ratios(tp,fp,fn):
    p=tp/(tp+fp) if tp+fp else 0.0
    r=tp/(tp+fn) if tp+fn else 0.0
    f=2*p*r/(p+r) if p+r else 0.0
    return {"precision":round(p,5),"recall":round(r,5),"f1":round(f,5)}


def evaluate(response_rows,source_rows,group_cap=MAX_TEST_SOURCE_GROUPS):
    sources={str(row["source_id"]):row for row in source_rows}
    if len(sources)!=len(source_rows):
        raise ValueError("duplicate source IDs")
    records,sample=select_sources(response_rows,sources,group_cap)
    if len({str(x.get("id")) for x in records})!=len(records):
        raise ValueError("duplicate response IDs")
    counts={policy:{"char":Counter(),"response":Counter(),
                    "strict_char":Counter(),"strict_response":Counter()}
            for policy in POLICIES}
    overview=Counter()
    per_group={}
    span_faults=Counter()
    for row in records:
        sid=str(row["source_id"])
        source=source_text(sources[sid])
        response=row.get("response","")
        gold,strict,bad=annotated_masks(row)
        for kind in bad:span_faults[kind]+=1
        if not response:
            overview["empty_response"]+=1
        if row.get("quality")!="good":
            overview["non_good_quality"]+=1
        overview["labelled_response"]+=int(any(gold))
        overview["strict_labelled_response"]+=int(any(strict))
        overview["human_annotated_chars"]+=sum(gold)
        overview["strict_annotated_chars"]+=sum(strict)
        overview["total_response_chars"]+=len(response)
        if sid not in per_group:
            per_group[sid]={
                "response_count":0,"source_sha256":hashlib.sha256(source.encode()).hexdigest(),
                "source_utf8_bytes":len(source.encode())}
        per_group[sid]["response_count"]+=1
        flags=predictions(response,source)
        for method,mask in flags.items():
            for task,truth in (("char",gold),("strict_char",strict)):
                tp,fp,fn,tn=one_confusion(mask,truth)
                counts[method][task].update(tp=tp,fp=fp,fn=fn,tn=tn)
            for task,truth in (("response",gold),("strict_response",strict)):
                truth_is_pos=int(any(truth))
                predicted_is_pos=int(any(mask))
                counts[method][task].update(tp=int(predicted_is_pos and truth_is_pos),
                                            fp=int(predicted_is_pos and not truth_is_pos),
                                            fn=int(not predicted_is_pos and truth_is_pos),
                                            tn=int(not predicted_is_pos and not truth_is_pos))
    metrics={}
    for policy,bytarget in counts.items():
        metrics[policy]={}
        for task,c in bytarget.items():
            x={key:int(c[key]) for key in ("tp","fp","fn","tn")}
            x.update(ratios(x["tp"],x["fp"],x["fn"]))
            metrics[policy][task]=x
    return {
        "n":len(records),"sample":sample,"human_label_overview":dict(overview),
        "annotation_offset_audit":dict(span_faults),
        "question_group_count":len(per_group),
        "group_response_count_histogram":dict(Counter(
            g["response_count"] for g in per_group.values())),
        "source_sha_list_digest":hashlib.sha256("\n".join(
            sorted(g["source_sha256"] for g in per_group.values())).encode()).hexdigest(),
        "methods":metrics,
        "limitations":[
            "QA test responses from RAGTruth, human spans describe existing model outputs; no CDG answer generation or hallucination suppression",
            "source character exactness is not evidence entailment or causal attribution",
            "simple lexical novelty methods have no learned semantics; thresholds fixed before results",
            "positive response = at least one human-annotated span; character metrics micro-average and heavily weight longer responses",
            "implicit_true spans excluded only from alternate strict target, not original human unsupported label",
            "dataset QA subset and source-group sampling, not all RAGTruth tasks or full test split",
            "data fetched temporarily; source/response raw text never in committed numerical outputs",
            "no model/tokenizer/inference latency, retrieval index, or revision-history costs in R69 detector comparison",
        ]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=parser.parse_args()
    response,res_provenance=download("dataset/response.jsonl")
    sources,src_provenance=download("dataset/source_info.jsonl")
    result=evaluate(response,sources)
    result["upstream"]={
        "revision":REVISION,"response":res_provenance,"sources":src_provenance,
        "source_license_note":"RAGTruth GitHub dataset and underlying source corpora have distinct license/usage terms; no raw text redistributed",
    }
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(result,indent=2)+"\n")
    print("ROUND69",json.dumps({
        "n":result["n"],"sample":result["sample"],
        "annotations":result["human_label_overview"],
        "annotation_faults":result["annotation_offset_audit"],
        "response_detection":{m:result["methods"][m]["response"]
                              for m in POLICIES},
        "strict_detection":{m:result["methods"][m]["strict_response"]
                            for m in POLICIES}},sort_keys=True))


if __name__=="__main__":
    main()
