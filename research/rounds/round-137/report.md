# R137: commit-last transactional packed source storage

Status: all four original-code jobs passed.

A single SQLite BEGIN IMMEDIATE serializes cooperating writers. File header identity and committed end offset are stored in SQLite. Under the lock, reject a truncated committed prefix and truncate only orphan suffix bytes. Append the new frame, fsync the file, then write source pointer, revision, origin, FTS5, ledger and end offset in one SQLite FULL-synchronous transaction. Publish by SQLite commit. Never truncate on ambiguous commit error; resolve visibility under a fresh writer transaction. Readers use explicit SQLite snapshots and pread into the immutable committed prefix; old readers never reference orphan suffixes. No global monkeypatch in the packed reader.

Process-death audit at before-write, partial-write, written, synced, source, index, ledger, meta and commit. Verify pinned readers, exact generation visibility, complete audits, recovery/truncation and retry. Additional corruption tests for wrong file identity and committed truncation. Validate four frozen cohorts with identical snapshot and bounded-anchor payload sizes, historical native BM25 oracle and identical receipt bodies. Compare total bytes including header and state metadata, append latency including fsync, read work and source exactness. Two matched transactional packed arms; prior inline timings are descriptive cross-run comparisons only.

Assumptions: local Linux filesystem, cooperating writers, immutable committed prefix, correctly implemented fsync and SQLite durability, no external file mutation, no compaction. Crash during initial archive creation, actual power loss, malicious modifications, filesystem corruption and concurrent noncooperating writers are not proven. Revision atomicity only. Before making a power-loss claim, need fault-injection filesystem tests. 
## Verified results

All four original-code jobs passed on 17e8c5ef, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45501430997. Across two packed arms and four cohorts: 3,590 exact source readbacks, 2,560 historical rank comparisons, 640 pinned receipt comparisons, zero observed score error, 36 enumerated process-death cases (additional duplicate unit executions not counted). All nine stages per corpus recovered with expected generation visibility and successful retry, including old pinned readers. Packed snapshot and bounded payload totals match frozen controls. Packed transactional archive adds 4,128 bytes relative to R135 finalized CDG on each corpus, remaining between -0.19% and +1.25% of finalized native depth-1 Git bytes. The comparison is storage/readback parity only, not Git update parity. Append latency includes per-frame fsync; no same-run inline timing arm. Process death is not power loss, cooperating writers only, no file creation crash or compaction guarantee.

| Corpus | Policy | Archive B | Payload B | Append median us | Read median us | Mean decode | Max decode |
|---|---|---:|---:|---:|---:|---:|---:|
| k8sdocs | snapshot | 2868934 | 1234598 | 1275.43 | 28.39 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor | 1983512 | 349176 | 1353.57 | 39.58 | 1.7797 | 2.2496 |
| gitdocs | snapshot | 8362561 | 4176417 | 2063.23 | 27.61 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor | 5070939 | 884795 | 1805.60 | 44.52 | 1.8203 | 2.1584 |
| bips | snapshot | 6987580 | 3051292 | 1545.94 | 36.51 | 1.0000 | 1.0000 |
| bips | bounded_anchor | 4504702 | 568414 | 1620.41 | 52.22 | 1.8559 | 2.0696 |
| cpython | snapshot | 8604488 | 4406056 | 2912.61 | 84.29 | 1.0000 | 1.0000 |
| cpython | bounded_anchor | 4943715 | 745283 | 3250.46 | 122.72 | 1.8557 | 2.0360 |
