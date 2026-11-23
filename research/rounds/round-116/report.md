# R116: Atomic version-bound search and evidence reconstruction

Status: PENDING original-source CI.

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
