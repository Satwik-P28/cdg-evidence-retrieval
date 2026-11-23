# R119: Atomic historical statistics and ranking receipts

Status: pending original-source CI.

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
