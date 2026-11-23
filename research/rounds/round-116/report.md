# R116: Atomic version-bound search and evidence reconstruction

**Status: PASS. Original-source CI [45285985036](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45285985036), 9 tests passed.**

Integrate R115 bounded-anchor encoding with a single atomic SQLite database,
full native contentless positional FTS5 index of every retained revision,
monotone ingestion generations, current-head mapping and immutable version
receipts. Each receipt binds the observed snapshot generation, indexed
generation, article, revision ordinal and reconstructed SHA-256. Readers
must explicitly hold a transaction during search and reconstruction.
A later transaction can replay the exact old receipt (not necessarily the
old ranking); invalid identity/generation/hash is rejected.

Use the next 100 hash-ranked articles after the 200 selected for R114/115,
pinned Versions repository. The deterministic round-robin ingestion is
synthetic global order preserving within-article chronological order.
Build independent full-content FTS5 controls at prefix and final states;
compare all-history and latest-as-of-snapshot *filtered* query results with
the same whole-history BM25 scoring statistics. Test 48 hashed single terms
and 16 actual adjacent-token phrases selected from prefix vocabulary only.
This is not a true historical timestamp or actual access log.

For each policy (snapshot, prev2, bounded_anchor), hold a reader transaction
open while another connection appends remaining revisions; verify pinned
scores and old receipts, then replay old receipts in a fresh snapshot.
Verify every source revision and test all 4 process-death stages via child
os._exit(77): source insert, FTS/mapping insert, generation/head update,
postcommit. Check recovered table counts, FTS visibility and current head.
These tests do not emulate OS crash, power loss, disk corruption, or prove
general correctness. SQLite WAL snapshot isolation is established prior art.

Also compare prefix ranks to filtering the *final* FTS index by generation:
global corpus statistics can drift, so a cutoff is not a reproducible rank
snapshot. No answer-quality or novel temporal indexing claim.
Prior art: https://arxiv.org/abs/2411.04051 ;
https://sqlite.org/isolation.html ; https://sqlite.org/wal.html ;
https://sqlite.org/fts5.html ; https://doi.org/10.1145/3787449 .

## Executed original-source results

Pinned input manifest SHA-256 `fd24e20eff865dd34567f7b94b1323cb86c3cd4046b09a7d47118547dc14f7a7`; 100 articles disjoint from the 200 previously sampled articles, 556 revisions, ingestion prefix 278. 64 fixed prefix-derived queries (48 terms and 16 exact adjacent-token phrases) at both scopes and both snapshots, 256 independent full-content FTS5 differential checks per arm. All scores matched exactly on the runner, with exact ordered row identities. Each policy returned 574 prefix receipts and 714 final receipts, verified against the original source bytes; replayed 355 earlier all-history receipts after writer commits and fully read back 556 versions. All 64 all-history queries were stable within the pinned reader transaction while the writer committed 278 additional revisions. All four crash stages passed for each policy. These are actual process-death tests using os._exit, not power loss or fsync/device-level fault injection.

| Policy | Complete SQLite B | Encoded source payload B | Appended WAL B | Final requested-source decode amplification | Final activated compressed B |
|---|---:|---:|---:|---:|---:|
| snapshot | 3,166,208 | 969,040 | 44,891,552 | 1.0000 | 1,686,039 |
| prev2 | 2,461,696 | 563,141 | 43,659,672 | 1.6936 | 1,891,227 |
| bounded_anchor | 2,535,424 | 554,017 | 43,853,312 | 1.5395 | 1,870,565 |

Bounded anchors save 19.924% complete database storage versus independently compressed snapshots and reduce final decoded bytes by 9.10% relative to prev2, but use 2.995% more physical storage and 0.444% more WAL than prev2. WAL grew 43.85 MB even for the bounded policy: the full index and transaction costs are important. The WAL count includes schema construction and a final integrity check, and is a file-size measurement rather than physical SSD traffic. Source payload bytes alone do not predict physical SQLite bytes: bounded_anchor has less encoded source payload than prev2 but a larger complete database. Bounds were checked on retrieved receipts at prefix and final states. No latency improvement is claimed.

## Reproducibility failure: immutable source bytes do not imply immutable scores

For each of the three policies, using the final FTS index and filtering to the original ingestion generation changed 12/64 ordered top-ten result lists and 64/64 score-or-rank signatures. This deliberately retains final global BM25 statistics, despite limiting eligible rows to the prefix. The retained reader snapshot, in contrast, preserved all 64 original signatures. The negative result replicates a known mechanism in temporal retrieval literature, not a novel discovery. Latest-head filtering also uses whole-history corpus statistics (not head-only corpus statistics). Source receipts identify historical bytes, not a commitment to the scoring corpus or original query.

## Decision and next gates

The integrated prototype is a stronger systems artifact than isolated codec results. It exploits SQLite's established snapshot isolation, transaction durability semantics and native FTS5, rather than inventing those guarantees. The dataset is filtered and processed; global ingestion generations and queries are synthetic; no actual access log, FTS index migration, long-running concurrent stress, temporal timestamp semantics, authenticated receipts, or RAG outcome has been measured. Next compare rank replay using a compact, versioned corpus-statistics ledger against prefix rebuilds and retained native-index snapshots. Use a proper independent BM25 oracle including document count, token length sum, term/phrase document frequencies and exact candidates. Measure complete physical bytes and query costs, not just payloads. A new method must beat established temporal-index alternatives before claiming novelty.
