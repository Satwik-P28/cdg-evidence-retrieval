# R167: signed ordinal runs and snapshot-independent mapping

Status: implemented, validation pending. Parent R166 2f3929bf467ead21bdd78a6085bdc6f1b3554593. Revised R166 run 45915506537 passed AP 10,009 and CLARK; AP 74,364 still pending at observation. AP bytes: positional 20684800, independent sparse 19062784, independent dense mapped 18731008, independent quotient 18616320. Quotient saves 114688 bytes over dense (0.612%); sparse-to-dense 331776 of 446464 net savings (74.3%). Raw windows 8322 vs unique 7033, mapping rows 8322 and mapping bytes 102400. Query p95 1179.862 vs 1154.706 us sparse; prep 5407.6375 vs 1776.929 us. Zero score error. CLARK no deltas; quotient adds 4096 bytes beyond R165 empty patch tables.

## Mechanism

First, eliminate per-window mapping for private corrections: group direct rows by content id, encode sign in parity and assign consecutive ordinal values, rowid=2*ordinal+sign. Store only the ending ordinal and cid per nonempty run. Recover cid by lower_bound on sorted ends; sign by parity. Each nonzero coefficient is realized by abs(coefficient) signed rows. Shared windows occupy row IDs above 2*last_direct_ordinal+1 and use the exact signed mapping. There is no collision between domains. The direct-only control uses identical cancellation and grouping without sharing. Adaptive policy uses shared representation if distinct child count >1 and (sum abs(coeff)-1)*len(window)>6*distinct child count, a frozen uncalibrated proxy. It is not claimed to minimize physical bytes.

Second, load immutable patch maps once for the opened archive, not once per historical cutoff. Correctness requires active-content membership at expansion time; native query parity validates that future/inactive content cannot leak into historical ranking. Compare independent quotient eager vs identical quotient global with map_load_us separated from per-cutoff preparation. Direct run mapping uses binary search on immutable ends; global shared list expansion checks membership. No claim of bounded worst-case time for shared fanout. Report map visits, active expansions, storage, warm query and per-cutoff prep plus cold map setup.

## Controls
R166 seven arms plus independent quotient global, independent runs, independent adaptive. All independent multi policies retain same source archive, candidates, admission and selected anchors, checked by statistics. All corpus snapshots use frozen R165 query plan, native oracle, byte-exact source checks. Unit tests include run boundaries, shared/direct mixed fixture, historical inactive membership. No new corpus result until CI. All maps reside in memory; peak RSS and concurrency not evaluated. Delayed correction interning is offline and may require large transient memory; production append and transactional admission deferred. Branch reuses R165 workflow; result JSON round=167.

## Next decision
If direct runs beat full mapping and global map setup amortizes, retain both mechanisms; if sharing fails versus run-only, omit it. Do not infer joint source/index advantage from independent anchors. For ACMSE use validated older evidence and treat R167 as exploratory unless fully verified.


## Local SQLite patch-subsystem probe

Executed an independent local copy of the ordinal-run writer and resolver using SQLite FTS5; the preserved probe imports those same functions from the committed implementation. For each of six workloads and three policies, recovered the complete signed coefficient map from actual indexed rows, verified FTS phrase match membership, then compared signed frequency aggregation at three historical cutoffs for six phrases. Total 324 policy/workload/query/cutoff comparisons, all equal (108 per policy), plus complete coefficient map parity. The local probe computes TF in Python from the known window text after validating native FTS match membership; this is not a native BM25 or production archive benchmark.

| Distinct pairs (5,000 children) | Full quotient bytes | Direct runs bytes | Adaptive bytes |
|---:|---:|---:|---:|
| 1 | 126976 | 638976 | 135168 |
| 10 | 131072 | 638976 | 135168 |
| 100 | 151552 | 643072 | 155648 |
| 1000 | 258048 | 647168 | 262144 |
| 5000 | 712704 | 659456 | 659456 |
| Repeated signed coefficients, mixed | 212992 | 1445888 | 217088 |

Direct runs save 7.47% over quotient in the all-unique workload; adaptive trails quotient by 4–8 KiB on the repetitive workloads (empty run table and layout overhead). Direct replication of non-unit multiplicities can be extremely expensive: mixed fixture 34,483 direct rows, 60 shared rows, 17,080 mapped uses. Therefore adaptive does not dominate both baselines, and a future representation must avoid replicating large coefficients unnecessarily. Synthetic correction subsystem only; no full archive or latency claim. Hosted R167 run 45915803144 started for implementation commit 0da49399d77a8ffc39069d601f362bb37468bb13; report/probe-only follow-up does not change implementation.
