#!/usr/bin/env python3
"""R96 source-only preflight for independent QASPER science QA evidence.

Reads official upstream tar with immutable SHA lock. Extracts train/dev
JSON only, strictly bounds size and never persists original paper/question
text or labels in output. Audits paragraph-level evidence coverage and
article/QA split integrity before any new benchmark comparison.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from urllib.request import urlopen,Request

HERE=Path(__file__).resolve().parent
URL="https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz"
EXPECTED_SHA="a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a"
EXPECTED_ARCHIVE_BYTES=10835856
MAX_ARCHIVE_BYTES=35_000_000
MAX_JSON_MEMBER=40_000_000
MIN_PAPERS={"train":800,"dev":250}
MAX_PAPERS={"train":1100,"dev":450}
WS=re.compile(r"\s+")


def normalize(s):
    return WS.sub(" ",s).strip() if isinstance(s,str) else ""


def extract_official(blob):
    digest=hashlib.sha256(blob).hexdigest()
    if digest!=EXPECTED_SHA:
        raise AssertionError("QASPER official release SHA-256 mismatch "+digest)
    if len(blob)!=EXPECTED_ARCHIVE_BYTES:
        raise AssertionError("official tar archive byte length mismatch")
    picked={}
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as t:
        members=[x for x in t.getmembers() if x.isfile()]
        for member in members:
            name=member.name.lower()
            if not name.endswith(".json"):
                continue
            candidates=[]
            for tag in ("train","dev"):
                if re.search(r"(?:^|[-_/])"+tag+r"(?:[-_./]|$)",name):
                    candidates.append(tag)
            if len(candidates)!=1:
                continue
            tag=candidates[0]
            if tag in picked:
                raise AssertionError("multiple official source members for "+tag)
            if not 0<member.size<=MAX_JSON_MEMBER:
                raise AssertionError("unexpected QASPER member byte length")
            reader=t.extractfile(member)
            if reader is None:
                raise AssertionError("cannot read source member")
            data=reader.read(MAX_JSON_MEMBER+1)
            if len(data)!=member.size:
                raise AssertionError("source member truncated")
            obj=json.loads(data)
            if not isinstance(obj,dict):
                raise AssertionError("official QASPER JSON should map article ids")
            picked[tag]={"name":member.name,"data":obj,
                         "sha256":hashlib.sha256(data).hexdigest(),
                         "bytes":len(data)}
    if set(picked)!={"train","dev"}:
        raise AssertionError("missing release train/dev: found "+str(sorted(picked)))
    return picked


def fetch():
    with urlopen(Request(URL,headers={
        "User-Agent":"CDG-QASPER-original-source-audit/1.0"
    }),timeout=120) as response:
        blob=response.read(MAX_ARCHIVE_BYTES+1)
    if len(blob)>MAX_ARCHIVE_BYTES:
        raise AssertionError("official tar over byte cap")
    return extract_official(blob)


def article_paragraphs(article):
    """Only textual paragraphs, keeping stable section/position identifiers."""
    full=article.get("full_text")
    if isinstance(full,dict):
        titles=full.get("section_name",[])
        sections=full.get("paragraphs",[])
        if not isinstance(titles,list) or not isinstance(sections,list) or len(titles)!=len(sections):
            raise AssertionError("QASPER parallel section arrays changed")
        iterator=zip(titles,sections)
    elif isinstance(full,list):
        iterator=[(x["section_name"],x["paragraphs"]) for x in full]
    else:
        raise AssertionError("QASPER full_text schema unrecognized")
    out=[]
    for section_idx,(title,paragraphs) in enumerate(iterator):
        if title is None:
            title=""
        if not isinstance(paragraphs,list) or not isinstance(title,str):
            raise AssertionError(
                "QASPER bad section: title="+type(title).__name__
                + " paragraphs="+type(paragraphs).__name__)
        for paragraph_idx,text in enumerate(paragraphs):
            if not isinstance(text,str):
                raise AssertionError("QASPER paragraph text not string")
            if normalize(text):
                out.append({
                    "section":section_idx, "paragraph":paragraph_idx,
                    "section_title":title,
                    "text":text,
                })
    return out


def questions(article):
    """Normalize the official raw dictionary or HF-aligned array schema."""
    qas=article.get("qas")
    if isinstance(qas,list):
        for item in qas:
            if not isinstance(item,dict):
                raise AssertionError("unexpected QASPER qas item")
            yield item
    elif isinstance(qas,dict):
        fields=("question","question_id","answers")
        if any(not isinstance(qas.get(k),list) for k in fields):
            raise AssertionError("unknown QASPER parallel qas arrays")
        if len({len(qas[k]) for k in fields})!=1:
            raise AssertionError("qas parallel columns differ in length")
        for q,ident,a in zip(qas["question"],qas["question_id"],qas["answers"]):
            yield {"question":q,"question_id":ident,"answers":a}
    else:
        raise AssertionError("unknown QASPER QA representation")


def answer_evidences(answer_record):
    """One annotation contains answer dict. No labels inferred from absent."""
    if not isinstance(answer_record,dict):
        raise AssertionError("QASPER answer annotation must be dict")
    a=answer_record.get("answer",answer_record)
    if isinstance(a,list):
        for item in a:
            yield from answer_evidences(item)
        return
    if not isinstance(a,dict):
        raise AssertionError("QASPER answer nested dict changed")
    evidence=a.get("evidence",[])
    if not isinstance(evidence,list) or not all(isinstance(x,str) for x in evidence):
        raise AssertionError("invalid QASPER evidence array")
    yield evidence


def source_probe(papers):
    counts=Counter()
    article_id=set()
    question_keys=set()
    examples=[]
    for pid,article in papers.items():
        if not isinstance(pid,str) or not isinstance(article,dict):
            raise AssertionError("invalid article")
        if pid in article_id:
            raise AssertionError("duplicate article id")
        article_id.add(pid)
        paragraph_rows=article_paragraphs(article)
        paragraph_by_norm={}
        for j,p in enumerate(paragraph_rows):
            paragraph_by_norm.setdefault(normalize(p["text"]),[]).append(j)
        counts["articles"]+=1
        counts["text_paragraphs"]+=len(paragraph_rows)
        counts["paragraph_bytes"]+=sum(len(p["text"].encode("utf8"))
                                       for p in paragraph_rows)
        for item in questions(article):
            qid=item.get("question_id")
            question=item.get("question")
            if not isinstance(qid,str) or not isinstance(question,str) or not question:
                raise AssertionError("invalid QA identifiers")
            qkey=(pid,qid)
            if qkey in question_keys:
                raise AssertionError("repeated QA in article")
            question_keys.add(qkey)
            counts["questions"]+=1
            answers=item.get("answers",[])
            if not isinstance(answers,list):
                raise AssertionError("answers must be list")
            for a in answers:
                for evidence in answer_evidences(a):
                    counts["annotation_instances"]+=1
                    if evidence:
                        counts["annotations_with_any_evidence"]+=1
                    matching=set()
                    for text in evidence:
                        n=normalize(text)
                        if not n:
                            counts["empty_evidence_strings"]+=1
                            continue
                        if n.startswith("FLOAT SELECTED"):
                            counts["table_figure_evidence"]+=1
                            continue
                        found=paragraph_by_norm.get(n,[])
                        counts["evidence_strings_total_nonfloating"]+=1
                        if found:
                            matching.update(found)
                            counts["evidence_strings_exact_paragraph_matched"]+=1
                        else:
                            counts["evidence_strings_unmatched"]+=1
                    if matching:
                        counts["annotations_with_at_least_one_exact_paragraph"]+=1
            examples.append(len(paragraph_rows))
    return {
        "counts":dict(counts),
        "paper_paragraph_distribution":{
            "min":min(examples),"max":max(examples),
            "mean":round(sum(examples)/len(examples),3)},
        "unique_questions":len(question_keys),
        "schema":"paper-keyed QASPER 0.3 full_text paragraphs, expert evidence exact paragraph/string audit",
        "known_limits":[
            "Some gold answers may only cite figure/table or non-paragraph evidence",
            "Exact paragraph match is strict and can miss semantically equivalent snippets",
            "Questions are paper-scoped, unlike global SciFact abstract retrieval",
            "No retrieval or answer model executed in source preflight",
            "No paper text, questions or evidence copied to repository outputs",
        ],
    }


def run():
    members=fetch()
    result={"round":96,"url":URL,"original_sha256":EXPECTED_SHA,
            "archive_bytes":EXPECTED_ARCHIVE_BYTES,"splits":{}}
    split_ids={}
    for split,entry in members.items():
        stats=source_probe(entry["data"])
        n=stats["counts"]["articles"]
        if not MIN_PAPERS[split]<=n<=MAX_PAPERS[split]:
            raise AssertionError("unexpected article count for "+split+": "+str(n))
        split_ids[split]=set(entry["data"])
        result["splits"][split]={
            "upstream_member":entry["name"],
            "member_sha256":entry["sha256"],
            "member_bytes":entry["bytes"],
            **stats,
        }
    overlap=split_ids["train"]&split_ids["dev"]
    if overlap:
        raise AssertionError("article ID appears in both train and dev")
    result["train_dev_article_id_overlap"]=0
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default=str(HERE/"ci-results.json"))
    args=parser.parse_args()
    result=run()
    Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("ROUND96",json.dumps(result,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
