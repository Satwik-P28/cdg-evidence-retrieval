# Round 52: Batch the Source-Span Lookup in Cached Historical FTS

**Date:** 2026-11-17. **Status:** GitHub Actions run 44030705735, two dedicated regression tests passed; 36 performance configurations executed with exact BM25/phrase result parity. This tests 12 genuine uv README revisions under three **synthetic** query-frequency distributions, four historical index cache capacities, and three conventional SQL span-lookup strategies.

## Hypothesis

Round 51 repeatedly scanned all row-to-byte-span mappings for a historical generation after FTS5 returned at most three ranked hits. This work has complexity proportional to the entire document version rather than the number of retrieved rows, even when the search index is cached. Replacing it with direct indexed row-ID queries should improve cache-hit latency without introducing new semantic approximations.

## Strategies

- **Scan:** fetch all generation span mappings and construct a Python dictionary.
- **Point:** B-tree look up each returned row ID separately.
- **Batch:** use one SQL IN statement for the small set of returned row IDs, reconstructing the result in the original FTS ranking order.

All methods use the same historical LRU cache, the same source versions, the same true source byte spans, and the same cache capacity. Every ranked and phrase retrieval must equal the full FTS5 reference.

## Executed results

Query counts: **120 per configuration**. The table shows median query time in microseconds, with all cache pages measured independently of Python object heap. Run 44030705735, Ubuntu/Python 3.13.

| Trace | Cache capacity | Scan | Point | Batch | Peak cached SQLite pages |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hot | 1 | 191.850 | 36.529 | 34.945 | 49,152 B |
| Hot | 2 | 185.328 | 35.435 | 32.335 | 98,304 B |
| Hot | 4 | 178.125 | 35.019 | 30.831 | 196,608 B |
| Hot | 12 | 181.535 | 33.733 | 29.745 | 487,424 B |
| Uniform | 1 | 1,486.243 | 1,316.090 | 1,309.680 | 49,152 B |
| Uniform | 4 | 1,345.570 | 1,310.663 | 1,322.084 | 196,608 B |
| Uniform | 12 | 183.621 | 27.547 | 28.739 | 536,576 B |
| Recent | 1 | 206.200 | 53.627 | 51.542 | 49,152 B |
| Recent | 4 | 179.574 | 35.523 | 30.782 | 147,456 B |

The **hot capacity-4 query median fell by approximately 83%**, with no change to the measured SQLite cache page footprint, by replacing scan with batch. For uniform low-cache-capacity history the dominant cost remains rebuilding the full historical index, so the row lookup strategy has little effect.

### Decisions

- **PROMOTE into the experimental code:** batched row-ID span lookup as default for cached historical search. Preserve scan and point alternatives as controls. Commit 25857db63cbea36005cbdc278dcb50ce6a8f7ebe.
- **HOLD as a general database recommendation:** the result compares small snippets from one README with 120 seeded queries per condition. Benchmark ordering, Python overhead, SQLite caching, index sizes and source length can change the marginal choice between point and batch.
- **REJECT:** any suggestion that the optimization fixes FTS cache miss costs, improves factual entailment, reduces physical SSD read amplification or supplies a new retrieval algorithm.

The full static historical FTS5 index is still the most defensible default when historical search must be fast under arbitrary generation distribution. Caches pay peak in-memory index pages and require an eviction/rebuild policy. Without a realistic trace, do not turn these small measurements into an automatic switch policy.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-52 -p 'test_*.py' -v
    python experiments/round-52/cache_lookup.py --out experiments/round-52/results.json

Experiment JSON and raw run logs in GitHub Actions run 44030705735. This is a classical SQLite implementation improvement, not a new compression result or an independently validated RAG accuracy improvement.
