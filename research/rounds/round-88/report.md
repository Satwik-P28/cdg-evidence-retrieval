# CDG Round 88: Snapshot-Coherent Evidence Retrieval and Process-Kill Recovery

**Date:** 18 November 2026. **Verified:** [GitHub Actions run 44345536621](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44345536621), Python 3.11.18, SQLite 3.46.1, all six regression tests passed and the full original SHA-locked SciFact experiment completed. Results are in the run's aggregate artifact \`cdg-r88-snapshot-sigkill-results\`. No semantic hallucination-reduction or power-loss-safety claims are made.

## Observation: a real index/source consistency race remains after R87

R87 commits the compressed source row and its FTS5 postings in one SQLite write transaction. Its ordinary API still permits:
1. Reader asks \`query(db, "oldquartz")\` and receives rowid 1 based on generation 1.
2. A different connection commits an R87 \`atomic_update\` replacing both search postings and compressed source with generation 2 containing \`newnebula\`.
3. Reader asks \`read(db, 1)\` and receives valid, SHA-verified generation 2 bytes for the *old ranking*.

**Measured deterministic reproducer:** this old-index/new-source pairing occurred as constructed under SQLite WAL mode. The digest protects payload integrity, not source/ranking time coherence. This is a known time-of-check/time-of-use class of race, not a new theoretical discovery.

**Mitigation tested:** \`retrieve_snapshot(conn, claim, k)\` begins one read transaction, queries BM25 ranking, SHA-verifies source bytes before ending the transaction, and rolls back on any error. A writer committed an update between the SELECT and materialization while the reader returned the original source bytes and generation 1; after the reader transaction ended, its subsequent read saw the committed new source. This uses SQLite WAL's documented snapshot reader behavior, not novel concurrency machinery.

Implementation and tests:
- \`experiments/round-88/snapshot_kill_probe.py\`
- \`experiments/round-88/test_snapshot_kill_probe.py\`
- \`.github/workflows/cdg-r88-snapshot-crash.yml\`

## Subprocess SIGKILL failure matrix (six independent databases)

Tested DELETE rollback-journal mode with synchronous=EXTRA and WAL mode with synchronous=FULL. Each crash was \`SIGKILL\` in a separate Python process, followed by reopening the physical SQLite file(s), checking \`PRAGMA integrity_check\`, FTS5 \`integrity-check\`, SHA-256/byte length, generation and old/new search tokens.

| Journal | SIGKILL after compressed source UPDATE, before index | SIGKILL after FTS replace, before COMMIT | SIGKILL immediately after COMMIT |
| --- | --- | --- | --- |
| DELETE | old generation 1, old postings | old generation 1, old postings | new generation 2, new postings |
| WAL | old generation 1, old postings | old generation 1, old postings | new generation 2, new postings |

**FACT:** All six cases recovered the expected whole transactional state with core+FTS integrity checks passing. **LIMIT:** no power-loss, crash-at-arbitrary-machine-instruction, filesystem or SSD write-cache durability testing; the three kill locations are predetermined. The special FTS integrity check verifies the internal index, not indexed term equivalence to the compressed content; targeted old/new query tests add an independent assertion in this fixture.

## Unmodified original SciFact source-read control

Original release TAR SHA-256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`, **5,183 source documents**, **300 dev claims**, original R87 exact source encoding and FTS5 policy. Transaction-scoped top-one readbacks: **300/300 original byte-exact, SHA-verified receipts**. Static pre-update atomic DB persistent size **9,236,480 bytes**, as in R87. No change to the retrieval ranking algorithm or to gold Recall. No empirical semantic improvement is claimed.

## Latency control, intentionally limited

In CI, 600 synthetic warm reads per method, balanced alternation of call order:
- Legacy split autocommit query+source read: **median 0.031754 ms, p95 0.073629 ms**.
- Transaction-scoped query+read: **median 0.030683 ms, p95 0.076664 ms**.

The synthetic corpus has only two documents, includes no disk cold-cache regime, and uses one process for timing. Differences are not independent throughput statistics; this test does not establish snapshot transactions are universally faster, free or even equivalent under load.

## Scientific and engineering decision

**KEEP:** query and evidence-materialization in one reader-owned SQLite transaction. This fixes a demonstrated R87 caller-level race while preserving original source read integrity and retrieval behavior on the static SciFact control. The existing R87 \`query\` and \`read\` remain publicly callable and unsafe if an application combines them across concurrent updates; R88 is currently a separate experimental adapter, not a fully wired production-facing API.

**KEEP:** explicit fault matrix for process-termination recovery. FTS5 and SQLite mechanisms are existing technology.

**DO NOT CLAIM:** solution to semantic hallucinations, ground-truth accuracy gains, new storage compression, power-loss durability, complete race freedom across multiple databases, concurrency throughput improvement, or storage savings in update-heavy histories.

**NEXT:** integrate the snapshot API into any application retrieval entrypoint; evaluate simultaneous readers/writers, persistent database/WAL/journal bytes under repeated revisions, checkpoint pressure and contentless FTS5 deletion tombstones, and cross-corpus versioned-source correctness. Broader semantics requires independent claim-level annotations and a stronger verifier, not mere source hashing.

## Independent prior art and reproducibility

- SQLite WAL readers and writers/snapshot semantics: https://www.sqlite.org/wal.html
- FTS5 contentless-delete, update and integrity-check: https://www.sqlite.org/fts5.html
- SQLite synchronous and journal durability restrictions: https://www.sqlite.org/pragma.html

Reproduce:

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-88 -p 'test_*.py' -v
python experiments/round-88/snapshot_kill_probe.py --full --out experiments/round-88/ci-results.json
\`\`\`

Only aggregate test outcomes are saved as a GitHub Actions artifact; upstream SciFact corpus bytes are not copied into this repository.
