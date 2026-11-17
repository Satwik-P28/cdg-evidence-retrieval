# Round 53: Independent Cross-Implementation Reproduction of HotpotQA-Derived Evidence Retrieval

**Date:** 2026-11-17. **Status:** completed successfully in GitHub Actions run **44031324682**. The original Round 25 Python retriever fetched the exact Git SHA-pinned upstream 100-question HotpotQA-derived sample and its aggregate output **matched the previous independent JavaScript analysis**. Seven original R25 Python unit tests and two new Round 53 mapping checks passed, alongside the entire existing cross-round regression suite. No original source dataset bytes were added to the CDG repository.

## Motivation and hypothesis

Round 25 had an apparent improvement from exact title mention/bridge expansion over plain BM25 on curated authentic multihop contexts, but only the independently written JavaScript evaluator had been used on the complete corpus. The separate Python implementation had local unit tests and a reproducibility script but had **not** independently run the entire 100-question pinned input. This left the scientific record dependent on one implementation of the full dataset evaluation.

We reran the source **as written**, with the unchanged pinned OpenSPG/KAG revision fdab15b3929d2ee40dfcdd388f90233096a6afc9 and Git blob SHA-1 7dbdf068a437f0577043667ffee3a20f0a602154. Before scoring, the script checked all annotated gold supporting sentence references against the supplied question-local paragraph sets. The full input was downloaded only into a temporary directory and discarded.

## Reproduced results

| Policy | Complete gold titles @2 | @3 | @5 |
| --- | ---: | ---: | ---: |
| BM25 | **33/100** | **46/100** | **62/100** |
| Exact title-mention bridge | **46/100** | **64/100** | **84/100** |
| MMR | **32/100** | **47/100** | **62/100** |

The Python full-data results also agreed with JavaScript on the **paired success/failure category counts** and all tracked **complete gold-sentence recovery among top-two ranked sentences per selected document**, for each policy and each K in {2, 3, 5}. The Round 53 script emitted an explicit result: same_as_independent_js = true, mismatches = [].

The bridge policy adds an observed title-reference bonus after selecting a paragraph, and remains a conventional iterative graph-expansion heuristic. It is not presented as novel. The test covers 78 bridge and 22 comparison questions, with about ten candidate paragraphs per question and gold-bearing paragraphs already present.

## What was and was not established

**Established:** independent language implementations reproduce exactly the same reported complete-document evidence recovery, paired outcomes and sentence-top-2 recovery on this one locked input. The downloaded input matches the original pinned Git blob.

**Not established:** held-out evaluation, open-corpus retrieval, end-to-end generated answers or factual entailment, compression speedup, index build cost or physical storage I/O, statistical generalization, optimality or novelty of title-mention expansion.

The 100 cases are a curated upstream training sample, not a randomized independently acquired held-out test. This is cross-implementation reproduction of a prior narrow result, **not a new independent test distribution**.

## Research decision and next falsifier

Keep the observed gain on this sample as a reproducible baseline and proceed to a genuinely independently held-out multihop dataset. The next controlled test should compare:
1. plain BM25 on fixed candidate pools;
2. exact title mention expansion;
3. precomputed title-link adjacency (removes repeated scanning);
4. query-type-gated bridge expansion, with gate fixed or trained on disjoint data;
5. independent source-byte spans from CDG's versioned frames and complete index/metadata/read cost.

Primary metric: complete supporting-document and sentence coverage at equal K and total acquisition cost. Secondary metrics: poor-case penalties on comparison questions, freshness and source version safety, physical read amplification, and supported-answer acceptance if an actual verifier/generator is introduced.

Kill the CDG-specific planner claim if a simple title-link index plus standard seekable compression matches the same complete-evidence recovery at lower total cost.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-25 -p 'test_*.py' -v
    python -W error::ResourceWarning -m unittest discover -s experiments/round-53 -p 'test_*.py' -v
    python experiments/round-53/repro_r25.py --strict --out experiments/round-53/results.json

The last command requires network access to the pinned upstream raw repository, validates the Git blob SHA before reading, computes a compact summary and aborts if JavaScript and Python aggregate results disagree. It does not redistribute the original corpus.

**Data provenance:** original sample in OpenSPG/KAG, file kag/open_benchmark/hotpotqa/data/qa_train.json, pinned revision as above; historical Round 25 report and results document the methodology and licensing caveats. CI execution: GitHub Actions run 44031324682.
