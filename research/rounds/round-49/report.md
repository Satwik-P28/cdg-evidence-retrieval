# Round 49: Historical FTS5 Posting Density versus BM25 and Phrase Semantics

**Date:** 2026-11-17. **Status:** executed on GitHub Actions, CI run 44030005042 after correcting the ranking-overlap denominator for empty queries. Three regression tests passed. Inputs: 12 authentic pinned historical uv README revisions, 2,833 indexed non-empty line rows, 120 source-derived keyword probes, 36 source-derived phrase probes. No independent QA or semantic entailment.

## Hypothesis

Full historical FTS5 posting detail and column-size metadata occupy more space than necessary for simple keyword match sets. Could a smaller index preserve the retrieval semantics CDG requires?

Six existing SQLite FTS5 variants were built independently and vacuumed:

| Mode | SQLite file bytes | Exact keyword row sets | Full BM25 top-3 exact order / 120 | Phrase query supported / 36 |
| --- | ---: | --- | ---: | ---: |
| full | 196,608 | Yes | 120 | 36 |
| full_no_columnsize | 163,840 | Yes | 37 | 36 |
| column | 196,608 | Yes | 24 | 0 |
| column_no_columnsize | 163,840 | Yes | 24 | 0 |
| none | 163,840 | Yes | 24 | 0 |
| none_no_columnsize | 131,072 | Yes | 24 | 0 |

The full reference returned 48 matched phrase rows across 36 queries. The full_no_columnsize index preserved those phrase matches, but did not preserve the full BM25 rank order. For the other four variants SQLite rejected those phrase queries due to insufficient position detail.

The initial comparison implementation erroneously compared all modes' row-ID-sorted top three with the reference BM25 ranking; also empty result sets were counted as 0% similarity. Both errors were corrected before the successful final run. The three tests include an assertion that the reference compares identically with itself for all 120 keyword queries.

## Inference

1. If the retrieval contract **only requires exhaustive keyword row membership**, the index with detail=none,columnsize=0 is a valid candidate in this specific experiment and uses 33% fewer bytes. More operators, filters, corpus scales and adversarial query tests remain untested.
2. If the retrieval contract requires **phrase search**, detail=full remains necessary in these modes. Omitting column-size metadata preserves phrase membership but changes BM25 scoring and top-3 order on most tested queries.
3. If the contract requires **the reference BM25 top-3 order and phrase matching**, none of the reduced configurations is a drop-in replacement.
4. Optimizing only the number of stored bytes would silently degrade actual retrieval behavior. This could distort both answer completeness and evidence selection.

The CPU timings are narrow warm measurements affected by the fact that six variants were built in one process, and keyword parity validation has extra overhead. Do not claim general query-speed improvements from the measured microseconds.

## Next experiment

A **two-tier historical index** could retain full current-generation FTS5 ranking and phrase support while storing a compact old-generation index for keyword filtering. Ranked or phrase historical queries would either need to reconstruct an appropriate full index or explicitly accept a changed ranking contract. Benchmark the full cost of that reconstruction and verify true BM25 order, not just keyword parity. This hypothesis is tested in Round 50.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-49 -p 'test_*.py' -v
    python experiments/round-49/fts_detail.py --out experiments/round-49/results.json

See CI run 44030005042 for code execution and raw output. The six modes are SQLite's existing FTS5 features, not CDG-created index designs. Documentation: https://www.sqlite.org/fts5.html .

**No general RAG superiority or novel compression is demonstrated.**
