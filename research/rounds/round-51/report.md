# Round 51: Historical FTS LRU Caching Can Recover Rebuild Cost But Consumes More Memory

**Date:** 2026-11-17. **Status:** executed successfully in GitHub Actions run 44030392915, three Round 51 regression tests passed. All cached queries were compared with complete historical FTS5 BM25 order or phrase result sets. Same 12 pinned uv README versions as R50, with three constructed 90-query traces each. This is not a realistic production trace, tail-latency or model answer study.

## Setup

The Round 50 baseline has a 155,648-byte two-tier index. Historical phrase or ranked search rebuilds the requested generation's full-detail FTS5 index in memory. Test LRU limits 0, 1, 2, 4, and 12 cached historical generations. Compare with a conventional single 196,608-byte all-generation full FTS5 index. Caches are empty at start and SQLite in-memory page count is measured; Python dictionary and connection overhead are not counted.

Synthetic distributions:
- Hot: 80% queries to generation zero, rest randomly among older versions.
- Uniform: random older generation.
- Recent: 60% newest generation, remaining requests among last three older versions.

All queries compare exact source row IDs and order to the ordinary full FTS5 reference.

## Results, as originally measured in Round 51

| Distribution | Policy | Cache hits / 90 | Cache misses / 90 | Total query time (ms) | Median query (microseconds) | Persistent index + peak cache SQLite pages |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Hot | No cache | 0 | 90 | 110.651 | 1,204.804 | 155,648 B |
| Hot | LRU 1 | 59 | 31 | 48.185 | 158.715 | 204,800 B |
| Hot | LRU 4 | 73 | 17 | 33.308 | 151.264 | 352,256 B |
| Hot | LRU 12 | 80 | 10 | 25.638 | 151.079 | 643,072 B |
| Hot | Full reference | N/A | N/A | 37.373 | 37.828 | 196,608 B |
| Uniform | LRU 1 | 10 | 80 | 102.437 | 1,252.737 | 204,800 B |
| Uniform | LRU 4 | 37 | 53 | 74.263 | 1,252.070 | 352,256 B |
| Uniform | LRU 12 | 79 | 11 | 27.229 | 157.969 | 692,224 B |
| Uniform | Full reference | N/A | N/A | 47.025 | 41.788 | 196,608 B |
| Recent | LRU 4 | 32 | 3 | 27.323 | 158.770 | 303,104 B |
| Recent | Full reference | N/A | N/A | 58.288 | 50.236 | 196,608 B |

Metrics were measured in a single warm CI process in sequential order and are NOT robust statistically. With enough cache capacity the total 90-query time fell below the full reference in some traces, but its median latency was still higher. The cached index pages can exceed the entire conventional historical full index by 3x, even before accounting for Python and SQLite connection overhead. Persistent disk savings therefore do not imply lower peak working-set cost.

## Code-level bottleneck found

The first cache prototype scans **all row-to-span mappings in a generation for each query**, building a Python dictionary just to resolve at most three matched row IDs. It adds work per query even on a cache hit. This is not inherent to SQLite FTS5 or historical source storage and must be optimized before accepting or rejecting caching based on its reported median time.

Round 52 explicitly compares this naive scan with primary-key point and batched IN-operator lookups while preserving exact ranked/phrase output and accounting for the same in-memory index pages.

## Decision

Retain LRU caching as a conditional mechanism but **reject any blanket claim of improved performance or lower total memory.** The classical full FTS5 historical index remains the simpler default when historical ranked or phrase queries are frequent or memory is constrained.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-51 -p 'test_*.py' -v
    python experiments/round-51/cache_lab.py --out experiments/round-51/results.json

Raw results and execution logs: GitHub Actions run 44030392915. No end-to-end RAG gain or novel cache theory is claimed.
