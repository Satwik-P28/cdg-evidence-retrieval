# CDG Round 89: Dynamic Revision Falsification of Contentless BM25 Statistics

**Date:** 18 November 2026. **Status: verified experimental negative result and an oracle-backed repair, not a production fix.** GitHub Actions [44348308648](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44348308648) completed successfully. Its independent R87 (6), R88 (6), and R89 (6) regression tests passed, followed by the full official SHA-pinned SciFact four-workload experiment.

## Why R89 exists

R86/R87 established byte-exact compressed source retrieval and *static* BM25 ranking equivalence against strong full-content FTS5 controls. R88 proved source/query retrieval must operate inside a single reader-owned snapshot transaction. Neither establishes dynamic indexing correctness or the persisted space/performance profile of real revision workloads.

R89 applies exactly 500 deterministic source revisions to each of two independent SQLite systems initialized from the same original corpus:
- **Control:** ordinary source-readable FTS5(title,abstract), updated by SQLite UPDATE.
- **Intervention:** R87 one-database contentless-delete FTS5 plus SHA-256-verified zlib6 source BLOB; its existing \`atomic_update\` writes compressed source then performs FTS5 DELETE and INSERT inside a single transaction.

Both systems retain access to the **complete original source text** and are queried with the same R83/R84 BM25 title weight 5, body weight 1, maximum 28 query tokens and OR query. Corpus: original 5,183 SciFact abstracts and 300 dev claims, release TAR SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`. The 500 artificial versions add a deterministic title marker and sentence fragment per operation. Two workloads: **diffuse** (500 distinct documents edited once); **hot** (50 distinct documents edited ten times). Both tested under DELETE rollback-journal and WAL, for four combinations. The update measurements alternate which implementation runs first.

## Verified failure: dynamic FTS global statistics drift

**[FACT]** Immediately after 500 synthetic revisions, SQLite FTS5's internal \`sources_data\` global document count for the contentless-delete implementation is **5,683**, although both \`SELECT COUNT(*) FROM sources\` and the independent full-content control still report **5,183 live documents**. The contentless index also inflates global title/abstract token totals. Standard SQLite FTS5 internal \`integrity-check\` and main \`PRAGMA integrity_check\` pass, demonstrating neither is sufficient to establish the BM25 source-statistics parity required here.

**[FACT]** With the same current original source bytes, synthetic revision events, tokenizer and query policy, only **150/300** queries retained identical top-10 rankings in the diffuse runs, and **152/300** in the hot runs. Average top-10 intersection was 9.84 and 9.8633 out of 10 respectively. In many queries ranks *within* the returned top-10 reordered; this is not a measured 50% drop in Recall, answer truth, or label accuracy. Do not infer that from top-10 identity.

**Falsified hypothesis:** replacing R87 DELETE+INSERT with a documented FTS5 contentless-delete \`UPDATE\` alone might fix statistics. A controlled trial on synthetic cases also inflated the FTS5 global count (e.g. live 15 vs reported 35 after 20 updates). That tentative change was reverted; the committed R89 branch does not modify R87's existing update code.

This is an empirical property of SQLite 3.46.1 in this workload; do not generalize to all SQLite versions, all FTS5 tables or every deletion pattern without independent tests. It is not a discovery of a new compression algorithm or proof of a SQLite security vulnerability. Contentless-delete's semantics need version-specific investigation and/or an index design change before incrementally updating production retrieval results.

## Controlled repair

The experimental \`rebuild_fts_from_structured_truth\` runs one \`BEGIN IMMEDIATE\` transaction, issues FTS5 \`delete-all\`, re-inserts every original document with its latest known synthetic revision, verifies compressed source bytes against the independent structured truth, and commits. This is **O(number of indexed documents)** and relies on original oracle corpus+revision dictionaries; it is not a validated production rebuilding API from arbitrary stored records.

**[FACT]** After repair, all four cases have the exact full-content FTS global document/column-token statistics and **300/300 identical top-10 ranked rowid lists**, plus 300/300 SHA-verified top-one source reads and SHA verification of every revised source. The rebuilding wall times in CI were **0.33260, 0.32982, 0.34167, 0.34490 seconds** across the four workloads. These times do not include cold I/O or application coordination.

## Persistent byte accounting, after updates and maintenance

Bytes include the main SQLite databases and existing WAL/SHM sidecars where present. Run \`wal_checkpoint(TRUNCATE)\`, \`VACUUM\` and a second WAL checkpoint before final steady-state comparisons.

| Mode | Workload | Full FTS initial | Compressed initial | Full FTS active | Compressed active | Full after VACUUM | Compressed after VACUUM | Post-VACUUM saved |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DELETE | diffuse | 14,544,896 | 9,236,480 | 17,039,360 | 10,362,880 | 14,712,832 | 9,281,536 | **36.9154%** |
| DELETE | hot | 14,544,896 | 9,236,480 | 17,031,168 | 10,276,864 | 14,577,664 | 9,240,576 | **36.6114%** |
| WAL | diffuse | 14,544,896 | 9,236,480 | 24,150,320 | 15,941,200 | 14,745,600 | 9,314,304 | **36.8333%** |
| WAL | hot | 14,544,896 | 9,236,480 | 24,100,928 | 15,978,784 | 14,610,432 | 9,273,344 | **36.5293%** |

The post-VACUUM results are *after* an FTS rebuild and database compaction. Do **not** describe these as purely incremental unmaintained sizes. R87 fresh initial compressed persistent size 9,236,480 B. WAL active peak samples are instantaneous at the end of update sequences, not maximum running disk use, and exclude overhead from concurrent readers and filesystem allocation.

## Wall-clock update cost in this single GitHub Actions run

| Mode | Workload | Full FTS median write ms | Compressed median write ms | Full p95 ms | Compressed p95 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| DELETE | diffuse | 0.99022 | 1.09007 | 1.72313 | 2.00446 |
| DELETE | hot | 0.97349 | 1.04533 | 1.68808 | 1.81699 |
| WAL | diffuse | 0.24669 | 0.31760 | 0.87101 | 1.03470 |
| WAL | hot | 0.25233 | 0.31918 | 0.87375 | 1.09957 |

With warm filesystem and single writer, median compressed updates were slower than the full FTS control in these experiments. No claim about independent repetitions, SSD sustained p99, amortized rebuild latency or production throughput. Rebuild wall time is reported separately and not included in per-update medians.

## Decision gate

**KEEP:** R86/R87 architecture for *static* source-exact storage comparisons; R88 snapshot read principle. Retain R89's negative dynamic result as a regression/falsification case, and the full-rebuild experiment as an explicit correctness oracle.

**BLOCK:** Any claim that R87's incremental update implementation preserves BM25 ranking/retrieval equivalence. R87 still exposes \`atomic_update\` and can return different rankings after revisions; internal integrity checks can pass despite inconsistent ranking statistics. The R89 branch intentionally leaves R87 production semantics unchanged rather than silently claiming a false one-line repair.

**NEXT:** reproduce FTS5 update bookkeeping across SQLite versions and alternative schemas; compare an external-content FTS5 index backed by decompressed/temporary text and trigger-maintained source updates, vs contentful FTS5, an epoch-switch double-buffered rebuilt contentless index, and custom BM25 calibrated on explicit *live* statistics. Validate with real corpora, snapshot consistency, update/delete/crash tests, cold reads, per-claim precision and actual generator outputs before any applied hallucination-mitigation claim.

## Provenance and reproduction

- Full dedicated CI and artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44348308648
- \`experiments/round-89/dynamic_workloads.py\`
- \`experiments/round-89/test_dynamic_workloads.py\`
- \`.github/workflows/cdg-r89-dynamic-workloads.yml\`
- SQLite FTS5 contentless-delete semantics: https://www.sqlite.org/fts5.html
- SQLite WAL and checkpoint/compaction limitations: https://www.sqlite.org/wal.html

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-87 -p 'test_*.py' -v
python -W error::ResourceWarning -m unittest discover -s experiments/round-88 -p 'test_*.py' -v
python -W error::ResourceWarning -m unittest discover -s experiments/round-89 -p 'test_*.py' -v
python experiments/round-89/dynamic_workloads.py --full --out experiments/round-89/ci-results.json
\`\`\`

Only aggregate outputs and hashed upstream provenance are persisted; published SciFact text is retrieved from its immutable SHA-pinned upstream release during CI.
