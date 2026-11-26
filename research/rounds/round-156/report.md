# R156 reversible positional self-index feasibility

Status: all three original-code jobs passed.

Closest prior art: Word-based Self-Indexes for Natural Language Text (https://lbd.udc.es/Repository/Publications/Drafts/1336418345210_borrador.pdf), Towards Efficient Positional Inverted Index (https://www.mdpi.com/1999-4893/10/1/30), Universal Indexes for Highly Repetitive Document Collections (https://www.sciencedirect.com/science/article/pii/S0306437916301132), Fast and flexible word searching on compressed text (https://doi.org/10.1145/348751.348754). Shared text/index storage and word-based self-indexes are established. No claim that self-indexing is new. SQLite FTS5 instance vocabulary provides term, document and token offset (https://www.sqlite.org/fts5.html).

Test actual index-assisted byte-exact reconstruction: derive canonical predictor by joining the ordered native normalized tokens with spaces, encode raw source as Zstd dictionary residual against predictor, select only if feasible and cheaper than literal; fallback otherwise. Decode predictor from persisted native positional postings, not a duplicate forward token store. Verify exact raw bytes and SHA256. Deduplicate raw content and encoded frames; retain revision identities. Test unsharded and shards of at most 512/128 unique contents; query all shards, use same active BM25 statistics and multiplicity. No arbitrary index scan byte bound; shard row cap not a byte cap. Single extraction may be extremely slow, even if payload falls. Explicitly compare random individual reads, residual-only reads and one-pass batch transposition; no inference from payload size alone.

Four matched finalized source+index subsets: R149 local marginal encoding with unsharded quotient FTS; self-index residuals unsharded, 512 and 128. All store exact source digests/lengths, recipes, physical frame BLOBs, content mappings, active statistics and native FTS. Same marginal payload must reproduce R149 on AP. This omits R151 provenance and transaction infrastructure equally; not a full archive comparison or claim of bounded activated index bytes. Exact all-source reconstruction after reopening, all 80 probes/four cutoffs native oracle, 12 uniform random reads plus 8 residual-only where available, one shuffled query pass. Both AP cohorts and CLARK. Retain losses. A viable result would motivate optimizing postings extraction and explicit byte-budgeted shard admission, then full transactional integration.

## Verified results

All three R156 jobs passed on 82908b15 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45882890268). Full AP marginal 148,455,424 B vs unsharded self-index 109,293,568 B (26.38% reduction); payload 51,804,679 vs 24,251,132 B (53.19% reduction). Median random read over 12 samples 47.25 us vs 1.143 s. 512 and 128 shards: 121,499,648 and 138,362,880 B; read medians 16.690 and 4.781 ms; query median 1.776 and 8.844 ms vs marginal 0.348 ms. CLARK 5,988,352 -> 3,981,312 B unsharded, median read 27.171 us -> 47.902 ms. All 342,136 source checks and 3,840 native rank comparisons passed. Read samples small, warm descriptive. Finalized source+index subset only, no provenance/transaction or physical byte-bound claim; shard size is object count. Full inverted-posting extraction impractical; R157 will materialize compressed forward predictor and replace positional postings with presence-only filtering, compare direct raw decode control.

| Corpus | Revisions | Arm | Physical B | Payload B | Median read us | Median query us |
|---|---:|---|---:|---:|---:|---:|
| ap | 74364 | marginal | 148455424 | 51804679 | 47.250 | 347.873 |
| ap | 74364 | self_unsharded | 109293568 | 24251132 | 1143346.008 | 332.440 |
| ap | 74364 | self_512 | 121499648 | 24251132 | 16690.454 | 1776.048 |
| ap | 74364 | self_128 | 138362880 | 24251132 | 4781.251 | 8843.878 |
| ap | 10009 | marginal | 20680704 | 7149439 | 34.186 | 316.129 |
| ap | 10009 | self_unsharded | 15331328 | 3365491 | 196657.709 | 310.645 |
| ap | 10009 | self_512 | 16605184 | 3365491 | 20291.122 | 550.908 |
| ap | 10009 | self_128 | 18788352 | 3365491 | 5547.042 | 1179.639 |
| clark | 1161 | marginal | 5988352 | 2538073 | 27.171 | 175.868 |
| clark | 1161 | self_unsharded | 3981312 | 1016466 | 47902.061 | 171.845 |
| clark | 1161 | self_512 | 4161536 | 1016466 | 21642.755 | 212.782 |
| clark | 1161 | self_128 | 4591616 | 1016466 | 5955.357 | 343.576 |
