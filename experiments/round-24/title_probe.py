#!/usr/bin/env python3
"""Round 24: title-discovery diagnostic on authentic HotpotQA-derived questions.

This is NOT a full HotpotQA benchmark. The title index is deliberately built
from the union of gold supporting titles in BOTH supplied subsets. This is
label-derived candidate-set leakage, and there are NO passage texts, true
multi-hop chains, answer generation, or full corpus distractors.

Source files must be obtained from the pinned upstream commit and verified with
Git blob SHA-1 before execution. No network dependency during evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

SOURCES = {
    "dev_questions.json": "553bca588cda339747dbdbffd876be4d4c9ef72d",
    "test_questions.json": "b76819e1aaa08f7146f781184cd4f935eef5b79c",
}
UPSTREAM = "https://github.com/surpradhan/rag-benchmark/tree/c9dc6c350accb3c07629f0465e57d38756a006b0/data/processed"
K_VALUES = (1, 2, 3, 5, 10)


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)


def git_blob_sha(blob: bytes) -> str:
    return hashlib.sha1(f"blob {len(blob)}\0".encode() + blob).hexdigest()


def load(path: Path, verify: bool = True) -> list[dict]:
    blob = path.read_bytes()
    if verify and git_blob_sha(blob) != SOURCES[path.name]:
        raise ValueError(f"Git blob SHA mismatch for {path}")
    data = json.loads(blob)
    assert isinstance(data, list)
    for row in data:
        assert row["question"] and len(row["supporting_titles"]) == 2
        assert row["type"] in ("bridge", "comparison")
    return data


def rank_title_bm25(question: str, terms: list[list[str]], tf: list[Counter], df: Counter, avg_length: float, names: list[str]) -> list[tuple[int,float]]:
    N = len(names)
    q = set(words(question))
    scored = []
    for i, t in enumerate(terms):
        s = 0.0
        for w in q:
            v = tf[i][w]
            if v:
                idf = math.log(1.0 + (N - df[w] + .5) / (df[w] + .5))
                s += idf * 2.2 * v / (v + 1.2 * (.25 + .75 * len(t) / avg_length))
        scored.append((i, s))
    return sorted(scored, key=lambda a: (-a[1], names[a[0]]))


def jaccard(a: list[str], b: list[str]) -> float:
    x, y = set(a), set(b)
    return len(x & y) / (len(x | y) or 1)


def mmr(rank: list[tuple[int,float]], terms: list[list[str]], names: list[str], k: int = 10, lam: float = .75) -> list[int]:
    pool = rank[:50]
    selected: list[int] = []
    max_score = pool[0][1] or 1.0
    for _ in range(k):
        choices = [(lam * score / max_score - (1-lam) * max((jaccard(terms[i], terms[j]) for j in selected), default=0.0), names[i], i) for i, score in pool if i not in selected]
        if not choices:
            break
        # Largest value, then lexically smallest name on ties.
        maxv = max(x[0] for x in choices)
        winners = [x for x in choices if abs(x[0] - maxv) <= 1e-10]
        selected.append(min(winners, key=lambda x:x[1])[2])
    return selected


def evaluate(dev: list[dict], test: list[dict]) -> dict:
    allrows = dev + test
    names = sorted(set(t for r in allrows for t in r["supporting_titles"]))
    terms = [words(t) for t in names]
    tf = [Counter(t) for t in terms]
    df = Counter(w for t in terms for w in set(t))
    avg_length = sum(map(len, terms)) / len(terms)
    out = {"unit":"document-title identity, NOT article or sentence retrieval", "title_pool":"union of gold supporting titles across both subsets (leakage)", "title_count":len(names), "subsets":{}}
    for split, rows in (("dev",dev),("test",test)):
        stats={typ:{"n":0,"bm25":{str(k):{"any":0,"complete":0} for k in K_VALUES},"mmr":{str(k):{"any":0,"complete":0} for k in K_VALUES}} for typ in ("all","bridge","comparison")}
        for r in rows:
            rank=rank_title_bm25(r["question"],terms,tf,df,avg_length,names)
            selected={"bm25":[i for i,_ in rank[:10]],"mmr":mmr(rank,terms,names)}
            gold=set(r["supporting_titles"])
            for typ in ("all",r["type"]):
                stat=stats[typ]
                stat["n"] += 1
                for policy, inds in selected.items():
                    for k in K_VALUES:
                        present=len(gold & {names[i] for i in inds[:k]})
                        stat[policy][str(k)]["any"] += int(present > 0)
                        stat[policy][str(k)]["complete"] += int(present == len(gold))
        out["subsets"][split]=stats
    return out


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--allow-unverified-input",action="store_true",help="For tests only. Not for public reported numbers.")
    a=p.parse_args()
    dev=load(a.data_dir/"dev_questions.json",not a.allow_unverified_input)
    test=load(a.data_dir/"test_questions.json",not a.allow_unverified_input)
    result=evaluate(dev,test)
    result["source_git_blobs"]=SOURCES
    result["source_commit"]="c9dc6c350accb3c07629f0465e57d38756a006b0"
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Evaluated {len(dev)} dev and {len(test)} test questions; {result['title_count']} titles")
    for split in ("dev","test"):
        for typ in ("all","bridge","comparison"):
            m=result["subsets"][split][typ]
            print(split,typ,m["n"], "complete@2",m["bm25"]["2"]["complete"], "MMR",m["mmr"]["2"]["complete"])

if __name__ == "__main__":
    main()
