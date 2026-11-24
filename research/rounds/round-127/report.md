# R127: Compact crossing-phrase intervals and selective term-frequency dispatch

**Status: PASS. Two regression tests and pinned original-corpus [CI 45431333970](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45431333970).**

R126 eliminates most positional reconstruction cost by splitting exact
phrase occurrences into within-fragment counts and first-boundary counts,
but both auxiliary representations exceed native FTS5 in physical bytes.
Reuse the R122/R123 local-ordinal gap-coded interval format, front-coded
shared blocks and native selected-list decoder for crossing phrases.
Test 4/16 KiB grouping, a cardinality-selected hot-term layer (>=128
coalesced intervals), and a complete TF layer. Every layout retains the
entire R125 min64_coalesced positional index and applications; auxiliary
dictionary, dispatch membership and all SQLite bytes charged. Single-term
requests use compact counts when present according to the declared policy;
phrases use native fragment-local counts plus compact crossing counts.
Exact historical source-derived positions, TF and crossing records audited;
every persisted sidecar interval compared; sampled full phrase counts and
rankings compared to independently rebuilt native active FTS5. Same R126
query plan and corpus; compare sparse direct join and native controls in
same run. No new corpus, arbitrary grammar, online WAL, source payload,
physical device I/O, or novel codec claim.

## Results

445 articles, 2,504 revisions, 1,663,050 original normalized positions. 36,005 crossing intervals expand to 79,333 positive phrase/version records. 316,448 TF intervals expand to 754,641 original term/version records. Every persisted interval in all five layouts compared against expected records (915,082 interval checks across layouts, not independent trials). All layouts retain the complete positional fragment base. 183 queries at four historical cutoffs, 732 ranking comparisons per method, including 320 phrase-containing queries, 3,336 ordered hits, 30,147 positive native frequency pairs, zero observed score error. Two regression tests passed.

| Layout | SQLite bytes | Fast-path terms | Final median us | Final phrase median us | Final common-term median us | Final p95 us |
|---|---:|---:|---:|---:|---:|---:|
| base | 4255744 | - | - | - | - | - |
| sparse_join | 5332992 | - | 138.940 | 129.678 | 8587.650 | 9022.659 |
| boundary4 | 4780032 | 0 | 160.240 | 159.679 | 8072.432 | 8718.771 |
| boundary16 | 4603904 | 0 | 168.675 | 169.788 | 8070.798 | 8688.885 |
| hot4 | 4947968 | 301 | 161.112 | 153.298 | 681.356 | 832.088 |
| all4 | 5849088 | 43147 | 136.305 | 158.827 | 680.840 | 822.800 |
| all16 | 5713920 | 43147 | 146.054 | 165.956 | 671.352 | 831.507 |
| native_history | 4657152 | - | 109.365 | 93.655 | 1474.470 | 1603.762 |

Boundary16 is 53,248 B smaller than native historical FTS5 (1.14%), but substantially slower (final median 168.675 vs 109.365 us and p95 8,688.885 vs 1,603.762 us). Hot4 selects 301 of 43,147 terms by coalesced interval cardinality >=128, without query log training. Its 4,947,968 B is 6.24% greater than native. Final common-term median 681.356 vs native 1,474.471 us (2.16x), p95 832.088 vs 1,603.762 us (1.93x). It is 12.60x faster than sparse_join on common terms, but overall median 161.112 us and phrase median 153.298 us are worse than native 109.365 and 93.655 us. All4 reduces term-only median to 97.322 us vs native 146.094 us, at greater physical storage. Hot4 reduces returned fragment application rows from 47,963 to 8,159 for the final unique-phrase/term probes. All4 returns 6,922. These are logical result counts, not page reads or internal FTS5 visits. Timings are matched within R127 only, not directly comparable to R126's other runner. Prepared active maps and decoder state excluded, three randomized warm passes; p95 is over the finite benchmark mixture, not a production service guarantee.

## Decision

Keep native historical FTS5 as default. Compact boundary16 narrowly beats its physical storage under the restricted phrase contract but loses latency. Hot4 is an experimental workload-dependent Pareto alternative; selective TF materially improves common-term and tail latency at a modest physical premium but loses median and phrase latency. Complete TF sidecar is not justified on this corpus relative to hot4 for tail latency. Do not claim novelty from combining established codecs, cardinality-based selection, fragment indexing and boundary correction. The corpus has been used repeatedly for tuning, query plan is constructed from the first prefix, global ordering is synthetic, all layouts are offline, and source bytes, WAL, online updates, cold-cache behavior and independent history are not measured. Exact normalized positions are retained, but arbitrary native FTS5 grammar is not supported.

Next: prioritize independent chronological revision histories and a feature-matched end-to-end compressed source archive (including all mappings, WAL, exact-source receipts). Evaluate a byte-budgeted selective TF policy on held-out workloads rather than tuning another threshold on the same corpus.
