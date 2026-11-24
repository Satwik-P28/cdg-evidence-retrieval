# R123: Native compact temporal access and physical layout ablation

**Status: PASS. Three unit tests and original-source [CI 45295041325](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45295041325).**

Implement a wire-compatible C front-coded term lookup and selected-list
varint active-ordinal filter; compare identical direct/shared16 files with
Python and C access, then test eight fixed layouts (direct, shared4/16,
rowid versus WITHOUT ROWID, 8/16 KiB pages, hybrid 4/16 KiB groups that
isolate terms with at least 128 intervals). No query labels or frequency
training beyond posting cardinality. All layouts preserve R122 local
ordinal records and source-free metadata. Collect dbstat page accounting
when available. Exhaustively verify all persisted records; check native
counts for every vocabulary term at each of four cutoffs in direct/shared16
layouts, then independently rebuilt active-only FTS5 ranking for all
methods. Separate bounded decoded-block LRU experiment (0, 64, 256 KiB)
with identical synthetic repeated query stream and two-lookups on miss.
Budget excludes Python object overhead. No actual access history or I/O
claims. Same pinned Versions corpus; term-only, no positional parity.
Native C decoder not a new codec. Source payloads and update WAL excluded.

## Results

445 articles, 2,504 revisions, 43,147 terms, 316,448 coalesced intervals. All eight persisted layouts exactly reconstructed all intervals (2,531,584 checked records). Across four cutoffs, direct and shared16 C retrieval checked **345,176 term/layout/cutoff maps** including empty matches; **544,765** positive active TF pairs per layout (1,089,530 across both). All 13 methods reproduced 412 query rankings each (2,446 returned ranked positions) with zero observed score error. Three randomized warm timing passes. Separate repeated-stream cache checks reproduced the reference ranking on every request. These are the same source revisions and query plan used previously, not independent validation.

| Layout | Physical SQLite B | Blocks | Encoded block B | Final median rank us | Final common-term median us |
|---|---:|---:|---:|---:|---:|
| direct4 | 2,420,736 | 43147 | 1,538,949 | 47.09 | 532.75 |
| shared4 | 2,519,040 | 525 | 898,826 | 70.72 | 544.56 |
| shared16 | 1,286,144 | 128 | 850,627 | 96.20 | 563.15 |
| shared16_rowid | 1,208,320 | 128 | 850,627 | 90.02 | 548.49 |
| shared16_page8 | 1,400,832 | 128 | 850,627 | 92.48 | 571.03 |
| shared16_page16 | 2,605,056 | 128 | 850,627 | 96.71 | 560.18 |
| hybrid4 | 1,302,528 | 882 | 912,407 | 57.41 | 535.13 |
| hybrid16 | 1,261,568 | 625 | 882,510 | 75.19 | 535.63 |
| packed_coalesced | 5,353,472 | - | - | 62.16 | 878.59 |
| native_history | 4,657,152 | - | - | 117.47 | 1272.92 |

Wire-identical native access is 2.52x faster than Python for direct4 (118.876 -> 47.093 us), and 8.11x for shared16 (780.283 -> 96.199 us) at final cutoff. Hybrid4 is 72.03% smaller than native historical FTS5, with 57.412 us median vs 117.466 us, and 535.125 us common-term median vs 1,272.923 us. Shared16_rowid is smallest, 74.05% smaller than native historical FTS5, with 90.021 us median. **Not feature matched:** native full FTS5 stores positions while the external indexes support only distinct term AND/OR. Native active-only snapshot median 68.629 us, common-term 437.265 us, is not a complete history. Timing includes SQL, wire lookup, filtering and Python scoring, excludes preparation and source reconstruction. Timing absolute values differ from R122 runner; compare within R123 only. No claims about device I/O or production latency.

## SQLite physical-page explanation

The shared4 WITHOUT ROWID layout is large despite smaller encoded payload than direct4. dbstat confirms unused overflow-page space. The rowid variant retains exactly the same 850,627 encoded block bytes as shared16, while changing physical pages and adding a unique term-directory index.

| Layout | blocks overflow pages | Overflow page B | Unused overflow B |
|---|---:|---:|---:|
| direct4 | 31 | 126976 | 83928 |
| shared4 | 505 | 2068480 | 1420131 |
| shared16 | 254 | 1040384 | 250002 |
| shared16_rowid | 128 | 524288 | 168 |
| shared16_page8 | 128 | 1048576 | 324490 |
| shared16_page16 | 128 | 2097152 | 1504650 |
| hybrid4 | 0 | 0 | 0 |
| hybrid16 | 63 | 258048 | 4627 |

Shared4 uses 505 overflow pages with 1,420,131 unused bytes; hybrid4's blocks table uses none (its rowid table schema and grouping both differ, so this is not a pure grouping ablation). Shared16_rowid reduces the original shared16 complete file by 77,824 B and overflow unused bytes from 250,002 to 168. Larger WITHOUT ROWID pages are not generally beneficial: identical shared16 payloads occupy 2,605,056 total B at 16 KiB pages. No inference about page cache misses from dbstat.

## Bounded decoded-wire cache

Separate 309-request synthetic repeated stream at each cutoff, 381 term lookups; cache budgets cover decoded wire bytes only, not Python object/key overhead. Zero budget uses the same directory-then-payload SQL access as the cache policies, so it is the matched cache comparison, not the one-query uncached path above.

| Layout and budget B | Hits/lookups | Decoded B | Peak decoded B | Median us |
|---|---:|---:|---:|---:|
| shared16_0 | 0/381 | 4907052 | 0 | 117.77 |
| shared16_65536 | 26/381 | 4577789 | 65526 | 110.15 |
| shared16_262144 | 109/381 | 3528127 | 262058 | 110.45 |
| hybrid16_0 | 0/381 | 2776713 | 0 | 91.12 |
| hybrid16_65536 | 38/381 | 2474950 | 65527 | 91.57 |
| hybrid16_262144 | 159/381 | 1551455 | 262124 | 83.56 |

At final cutoff hybrid16 with 256 KiB budget hits 159/381 terms, reduces decoded bytes from 2,776,713 to 1,551,455 (44.13%), and median from 91.122 to 83.562 us. This does not beat the one-SQL-lookup uncached hybrid16 (75.190 us) on this runner. Caching reduces logical activation/decode work, not necessarily latency. No actual user access trace or cross-cutoff sharing; do not claim production cache efficacy.

## Decision and next gate

Retain direct4, hybrid4 and shared16_rowid as experimental Pareto options. Hybrid4 is the strongest measured compact/latency compromise on this workload, but native FTS5 remains the default until position, phrase, and NEAR semantics are reproduced. First implement exact coalesced position-vector intervals and compare native positional rank/phrase parity and physical bytes. Then test independent corpora, actual temporal workloads, and online incremental maintenance plus WAL. The C decoder validates selected posting lists and scans block structure, not a full malicious-file verifier. The archive remains offline and source payloads excluded; no new codec or novelty claim. Compression primitives and temporal coalescing are established.
