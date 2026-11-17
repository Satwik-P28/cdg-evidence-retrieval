# Round 38: Authentic Versioned Source Text versus Semantic Temporal Validity

**Scope:** This round evaluates 12 genuine historical GitHub README revisions, **not** factual reversals, independently authored questions, LLM answer quality, or physical SSD throughput. Source snapshots were fetched from `astral-sh/uv` with exact commits and Git blob IDs pinned.

## Why this direction matters

The previous synthetic Round 37 case proved that sorting by latest revision does not establish temporal applicability, but its simple title/version policy had access to fixture-friendly labels. Before adding learned semantic methods, we tested historical membership using authentic source revisions to identify what source-version filtering solves on its own.

Prior research: HoH (Ouyang et al., ACL 2025) https://aclanthology.org/2025.acl-long.301/ ; FRESCO (Meta) https://github.com/facebookresearch/fresco ; Stale-Document Poisoning (Ahmed et al., 2026) https://arxiv.org/abs/2609.31342 ; bitemporal semantics https://docs.xtdb.com/about/time-in-xtdb.html .

## Data, labels and leakage

The input has 12 dated README revisions spanning 2024-12-16T19:15:03Z through 2026-07-08T13:08:32Z. We convert each revision to distinct whitespace-trimmed lines and compare adjacent revisions. Every line changed at a transition, of length 25–320 characters with at least four space-delimited words, yields a gold-derived exact membership query at the snapshot where the line existed. This produces **77** checks: 34 removed-line and 43 added-line targets. No query is independently authored, and exact line changes often reflect formatting, not factual correction.

## Results

| Membership test | Correct / queries | What it means |
| --- | ---: | --- |
| Historical as-of pinned snapshot | 77/77 | Expected by construction, not algorithmic superiority |
| Latest-only snapshot | 30/77 | Old text often missing in present-day README |
| Any historical snapshot | 77/77 | Cannot say *when* the line applied |

Total raw text across stored revisions: **120601 bytes**. A single concatenation of all distinct whitespace-trimmed lines has **9882 bytes**. These figures exclude a decodable history map and indexing overhead and **are not compressed storage measurements**. They do not establish that deduplication wins against Git delta packs, Zstandard or an optimized versioned database.

## Main result

[FACT] Git commit IDs + blob digests provide verifiable document identity and commit-time history, not claim-level real-world effective dates. [NEGATIVE] A simple as-of index handles this deliberately narrow historical membership test exactly; CDG-specific adaptive graphs or neural verifiers add no demonstrated value here. [UNCERTAIN] A change in a Markdown source line can be stylistic rather than semantic. Claim-level bitemporal annotation is missing.

## Next falsifiable experiment

Obtain and evaluate independently labeled factual reversals from HoH / FRESCO, including original dated sources and exact citation spans; establish the meaning of *valid time* separately from *indexing time*, with delayed ingestion and retroactive corrections. Compare ordinary temporal SQL, BM25 plus time filtering, classical temporal rerankers, and CDG byte/version receipts at matched complete-evidence recovery, supported-answer coverage, false acceptance, update cost and compressed-read cost.

## Reproduce

```bash
node experiments/round-38/temporal_bench.js research/rounds/round-38/uv_readme_revisions.json experiments/round-38/recomputed.json
node experiments/round-38/test_temporal.js
```

The inputs are genuine publicly accessible upstream README text. Check the upstream license before redistributing outside private research contexts.
