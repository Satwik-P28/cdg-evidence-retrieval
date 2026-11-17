# Round 57: Fixed Global Evidence Budgets Across Selected Documents

**Date:** 2026-11-17. **Status:** 256 SHA-locked HotpotQA distractor development questions, split into two fixed 128-question partitions, executed successfully in GitHub Actions run 44164933775. Six dedicated regression tests passed. This is an exploratory extension after the aggregate Round 54/55 results were inspected, not a new independent dataset family or genuine unobserved test set.

## Hypothesis

When five documents are retrieved, assigning two sentences to every document can waste scarce sentence budget on distractors and fail to expose multiple support sentences in the highest-relevance documents. Test whether a single global **at-most-ten-sentence** budget, allocated by retrieval rank and exact title-link signals without labels, improves complete annotated supporting-sentence recovery at matched compressed frame traffic.

The benchmark preserves the original R25 BM25 or exact-title bridge document choices. Sentence rankers: FTS5 BM25, local BM25, and title-mention-first. Allocation rules, fixed before the run: uniform two each, uniform with reallocation of unused slots, front-loaded 4/3/1/1/1, balanced 3/3/2/1/1, reversed 1/1/2/3/3, source-link-weighted greedy, global source-plus-sentence rank, deterministic random control. The same user query and original source texts are used for every policy. Gold annotations enter **only** scoring.

The dataset is the first 256 IDs of Round 54's frozen 512-question SHA sort. First 128 were previously examined under Round 56; the second 128 had not been measured for sentence allocation. A few genuine development cases have fewer than five candidates, so the experiment properly selects only available documents and never pads or silently drops questions.

## Observed bridge + FTS5 results

The document-level upper bound is **107/128** on the discovery subset and **109/128** on the second partition. At most 10 sentences may be selected overall, with fewer when sources are short.

| Allocation | Complete annotated support, discovery /128 | Second partition /128 |
| --- | ---: | ---: |
| Uniform two per document | 79 | 80 |
| Uniform two plus recycling | 81 | 84 |
| Front-loaded 4/3/1/1/1 | **86** | 88 |
| Balanced 3/3/2/1/1 | 80 | **91** |
| Global source + sentence rank | 82 | 89 |
| Title-link weights | 82 | 82 |
| Reverse 1/1/2/3/3 | 50 | 61 |
| Deterministic random | 34 | 29 |

The front-loaded rule improved recovery in **both** partitions relative to uniform. Recycling the 0.4-0.5 unused sentence positions explains part, but not all, of the gain: discovery 86 vs 81 and second partition 88 vs 84. Balanced allocation was best in the second partition (91) but barely improved the first (80), illustrating distribution sensitivity and possible nonuniform document-level supporting fact density.

Ideal per-query unique gear512 compressed bytes:
- Discovery: uniform2 **1,601.328 B**, front 4/3/1/1/1 **1,558.977 B**, balanced **1,576.961 B**.
- Second partition: uniform2 **1,578.531 B**, front **1,526.719 B**, balanced **1,540.172 B**.

Thus front-loading has a **narrow local two-objective win** over uniform allocation for both measured partitions: more complete supporting-fact sets under the at-most-ten sentence budget and slightly fewer unique compressed frames activated. This is not a claim of general production read speed: the relevant raw source text and BM25 sentence index were already available, the source docs are short, and the whole-source Zlib archives remained smaller than content-defined frame archives in earlier rounds.

The shared FTS sentence index occupies **1,396,736 bytes** for the 256 question-local contexts, exceeding the source archive sizes: whole Zlib **963,532 B**, gear512 **1,009,612 B**. Upfront candidate scoring, persistent index creation and query/reader/model token costs remain part of the actual system.

## Decisions

- **Keep as a candidate:** rank-frontloaded sentence budget with FTS5 for the tested multihop retrieval setting. It earns additional study because both partitions show the same direction over uniform and recycling controls.
- **Retain:** balanced allocation, global rank, random and reversed controls. Balanced performed better on the second partition, so there is no evidence of a single universal weighting.
- **Reject:** an unsupported claim of new retrieval theory, guaranteed support completeness, end-to-end RAG speedup, or hallucination mitigation.
- **Next:** test the same frozen allocations on independent corpora and actual query traces. Measure full retrieval/index build, compression, cache, model/verifier and answer-quality cost. If the gain is merely due to rank bias on HotpotQA distractor pools, report that limitation.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-57 -p 'test_*.py' -v
    python experiments/round-57/budget_router.py --out experiments/round-57/results.json

Full outputs and CI logs: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44164933775 . Input is the same SHA-verified HotpotQA CC BY-SA 4.0 development dataset mirror, downloaded transiently without redistribution.
