# R119: Atomic historical statistics and ranking receipts

**Status: PASS. Six tests and original-source CI [45287792108](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45287792108).**

Extend R116's atomic source/index writes and R118's public native Unicode61
tokenizer and phrase-count API with a per-generation token count, cumulative
total and SHA-256 corpus prefix commitment. Insert source, index, revision
mapping, length ledger, head and generation in one transaction. Independently
audit all ledger rows against actual FTS5 token positions and the ordered
source-identity hash chain. Process termination at source, index, ledger,
meta and postcommit boundaries tests visibility and recovery.

The portable canonical receipt body binds cutoff, supported query, scope,
scorer configuration, prefix hash, document count, total tokens, per-phrase
DF, ordered top-ten scores encoded as IEEE float hex, and exact source
identities. Reconstruct every returned source before issuance. Replay in an
explicit snapshot compares the canonical body against a separately supplied
expected digest. A receipt digest is not a signature; independently trusted
metadata and identical scoring arithmetic are required. This is not a
cryptographic proof of completeness or malicious-storage resistance.

Use the last 45 hash-ranked articles not selected by R114–117 (same
Versions release, not a new dataset). Compare independently rebuilt native
prefix and final FTS5 ranks. Issue prefix receipts while a reader is pinned,
commit remaining revisions on a second connection, replay in the pinned
and fresh reader snapshots. Audit every source and ledger row. Compare
physical and append-WAL overhead against identical source/index archive
without ledger. External receipt bytes counted separately; not persisted.
This comparator isolates marginal ledger costs, not feature-equivalent
temporal system performance. No actual chronological global edit trace,
user query logs, power loss, arbitrary FTS grammar, or novel scoring claim.

Related work: https://sqlite.org/fts5.html ; https://sqlite.org/isolation.html ;
https://arxiv.org/abs/2411.04051 ; https://doi.org/10.1145/3787449 .

## Verified results

45 remaining hash-ranked articles, 256 revisions, prefix 128. Independent native full-content oracle checks: 160 prefix and 160 final query/scope combinations; 604 prefix and 754 final ranked hits, exact ordered identities and zero observed BM25 score error. All 160 prefix receipts replay identically in the pinned reader and later snapshot. All 256 original source byte sequences reconstructed; all 256 ledger rows audited against native token positions and the chained prefix commitment. Five process-termination stages passed (source, index, ledger, meta, postcommit). Six regression tests passed, including malformed receipt fields and the distinction between a changed trusted digest and a valid alternative request with its own digest.

| Metric | Base source+index | Atomic ledger |
|---|---:|---:|
| Complete SQLite bytes | 1253376 | 1269760 |
| WAL bytes before checkpoint | 19504112 | 20583552 |

Incremental physical archive overhead: 16384 B (1.307%). WAL growth: 5.534%. Exported 160 canonical receipt bodies occupy 160685 B plus 5120 B if digests are stored as raw 32-byte values (hex encoding doubles digest bytes). Exported receipts are not persisted in the measured SQLite archive. Baseline is a marginal overhead comparator, not a feature-equivalent temporal retrieval system.

## Scientific disposition

The source/index/statistics atomic integration passed on this cohort. This is a reproducible artifact result, not a proof of completeness, cryptographic authentication, power-loss tolerance, arbitrary FTS grammar, or production scalability. Actual latest-head-only BM25 corpus statistics are still unsupported: the heads scope filters candidates while preserving all-history prefix statistics. A further experiment must explicitly compare that different scoring contract to a rebuilt index of only active versions.

Strong prior-art comparisons include Staudinger et al. (2024), Reproducible Hybrid Time-Travel Retrieval in Evolving Corpora (https://arxiv.org/abs/2411.04051), and TimIR (2025), which already supports recreating historical sparse rankings for reproducible research (https://repositum.tuwien.at/handle/20.500.12708/224602). The contribution cannot be framed as the invention of time-travel retrieval. Compare compact integrated source archives and receipt costs with versioned posting/statistics systems, with actual historical validity intervals and independent workloads.
