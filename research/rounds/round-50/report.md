# Round 50: Two-Tier Historical Index, Exact Phrase and Ranking Fallback

**Date:** 2026-11-17. **Status:** GitHub Actions run 44030137355, 3 unit tests passed. All 120 keyword matches, 120 exact top-three BM25 comparisons, and 36 phrase queries matched the all-generation full-detail SQLite reference on 12 authentic uv README revisions. This is a single small corpus with synthetic/source-derived queries, not independently tested RAG QA.

## Architecture hypothesis

Round 49 falsified treating a smaller historical FTS5 index as drop-in BM25-equivalent. A two-tier design is a possible workload-specific alternative:

- Current source generation: FTS5 full-detail, supporting phrase search and full BM25 rank.
- Old source generations: slim FTS5, supporting simple keyword search with exact row IDs and generation boundaries.
- Historical ranked or phrase search: rebuild a conventional full FTS5 index for that old generation **on demand** from retained original source bytes and use the exact result instead of trusting rankings from the slim index.

This deliberately makes an expensive but explicit correctness trade-off. It is standard physical design/recomputation, not a novel retrieval theorem.

## Executed results

All values are warm Python/SQLite microbenchmarks, with queries drawn from the indexed README. Rows are generated from 12 historical versions.

| Strategy | Persistent SQLite bytes | Keyword exact matches /120 | BM25 top3 exact matches /120 | Phrase exact matches /36 | Median ranked search (microseconds) |
| --- | ---: | ---: | ---: | ---: | ---: |
| One full historical index | 196,608 | 120 | 120 | 36 | 27.442 |
| Current full + old detail none, columnsize 0 | 155,648 | 120 | 120 | 36 | 927.000 |
| Current full + old detail column, columnsize 0 | 188,416 | 120 | 120 | 36 | 922.299 |
| Current full + old detail full, columnsize 0 | 188,416 | 120 | 120 | 36 | 921.154 |

The compact old-detail-none variant reduces persistent index bytes by **20.8%**, but the median uncached ranked historical query takes roughly **34x** as long. The fallback currently constructs a full index of the selected historical generation. BM25 ranking over only that generation can differ in general from BM25 on a multi-generation global index because document frequencies and corpus lengths differ. It matched the tested top-three results here, but this is not a universal equivalence guarantee.

Phrase results matched on this dataset because the fallback includes the full source text of the selected historical generation and uses an ordinary FTS5 full index. No independent source-factual correctness is implied.

The single-file tiered implementation is simpler than maintaining a global index for every previous generation, but performance gains are workload-conditional. The minimum index size does not equal the minimum total system memory or storage once transient full FTS rebuilds are considered.

## Promotion gate

**Keep experimentally:** simple keyword historical lookup on slim index and current full retrieval; full historical query fallback where its semantics are independently validated.

**Hold for general deployment:** exact BM25 equivalence of single-generation fallback to full multi-generation ranking; independent corpora, realistic user query frequencies, physical I/O and caching.

**Reject:** claiming the 20.8% storage reduction is a free optimization without substantial historical query latency.

Round 51 tests whether LRU caching of historical full indexes recovers most of the cost and quantifies in-memory page overhead.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-50 -p 'test_*.py' -v
    python experiments/round-50/tiered_fts.py --out experiments/round-50/results.json

SQLite FTS5 ranking limitations and index variants: https://www.sqlite.org/fts5.html .
