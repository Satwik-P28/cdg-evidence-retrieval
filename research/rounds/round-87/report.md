# CDG Round 87: Transactional FTS5 / Compressed-Source Index

**Date:** 18 November 2026. **Status: six adversarial regression tests and full original SciFact 5,183-source/300-claim CI passed, GitHub Actions 44267489408.** An ordinary SQLite atomic transaction combines existing FTS5 contentless-delete indexing with compressed source BLOB storage and SHA256 verification. This is an established database integration pattern, not a novel retrieval/compression algorithm or proof of power-loss durability.

## Motivation and control

R86 measured a strong source-readable architecture: conventional FTS5's contentless index plus external R48 whole-Zlib source archive and source-ID-to-slot mapping. It kept every original SciFact top-10 BM25 ranking and used **8,609,749 retained bytes**, versus **14,544,896** for a conventional full-content FTS5 source-reader. But an external archive and SQLite index must be maintained consistently across two separately managed storage systems.

R87 tests a known single-database alternative. Each row holds \`(rowid,doc_id,compressed_zlib,sha256_digest,utf8_len,generation)\` in a normal SQLite table, and a **contentless-delete FTS5** table stores term postings and document size without source text. Both structures are updated in one SQLite \`BEGIN IMMEDIATE\` transaction and \`COMMIT\` or \`ROLLBACK\`. The original R83/R84 fixed BM25 query policy remains title weight 5, abstract 1, up to 28 OR-separated claim terms. All source and label inputs are from the immutable SciFact original release SHA \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.

SQLite FTS5 contentless-delete prior art is documented at https://www.sqlite.org/fts5.html , section 4.4.2. No independent claim that this feature is original research.

## Tests that actually executed

Six deterministic tests:
1. Original UTF-8 source bytes, source ID and generation checks.
2. Failure injected after compressed source update before index mutation: transaction rolls back both.
3. Failure injected after FTS deletion/reinsert but before commit: transaction rolls back both.
4. Successful update: original full-text query no longer matches, new query does; decompressed SHA-verified source changed and generation increments.
5. Failure-injected deletion leaves original source and search rankings intact; successful deletion removes both.
6. Deliberately corrupted compressed BLOB and trailing compressed bytes fail closed; full-content/source-archive/atomic rankings match for a synthetic corpus.

**Limit:** Deterministic Python exceptions within a live process are **not** a process kill, kernel crash or storage power loss. SQLite guarantees transactional semantics in general, but the experiment did not fault-inject these deployment failures.

## Full original SciFact numerical result (CI 44267489408)

**[FACT]** On 5,183 source abstracts and 300 development claim queries, **100% top-ten BM25 rowid rankings matched** across all three indexes: full-content FTS5, contentless FTS5 and single-database contentless-delete FTS5 with compressed sources. Gold source Recall@1 136/188 (.723404), @3 156/188 (.829787), @5 166/188 (.882979), @10 179/188 (.952128), unchanged from R83/R84/R86.

**[FACT]** Every top-one retrieved source (300/300) was decompressed from a normal SQLite BLOB and matched its immutable original source bytes after SHA-256 and byte-length validation. Combined source bytes verified **489,287**, measured in-process warm decompress+SHA time **0.00507 s** for all 300 reads.

### Persistence size, sources, and tradeoff

| Architecture | Retained bytes | Change versus ordinary full FTS |
| --- | ---: | ---: |
| Original source-readable full-content SQLite FTS5 alone | **14,544,896** | Baseline |
| R86: contentless index + separate whole-Zlib CAS + doc-ID mapping | **8,609,749** | -40.81% |
| **R87: one SQLite contentless-delete index + compressed source BLOB + SHA** | **9,236,480** | **-36.50%** |

R87 uses **5,308,416 fewer persisted bytes** than the conventional full-text source-reader and **626,731 more bytes** than R86's separate-compressed-archive composition. This is a trade-off rather than strict dominance: R87 avoids a two-store consistency requirement but adds normal SQLite source-row and unique-doc-ID B-tree overhead. These bytes exclude WAL/journal during active updates and any historical versions.

**[FACT]** 300-query measured wall time: full FTS5 **0.34671 s**, contentless external control **0.34574 s**, atomic one-DB **0.35211 s**. The variation is too small to claim a latency advantage from one sequential run. Full build+VACUUM of atomic DB **0.43160 s**, in-process query + read only; no p95/p99 or cold SSD measurements.

## Decision

**KEEP:** R87 as a simpler transactional source-index proof of concept: same ranked results, exact original bytes, fail-closed source corruption detection, and rollback under two injected failure points. The architecture provides a measured **36.50% retained-byte reduction** versus the conventional contentful FTS5 SciFact baseline.

**DO NOT PROMOTE YET:** A general crash-consistency theorem, production throughput, multi-writer read stability, journal-compaction durability or hallucination reduction. Source bytes can be authentic yet evidence may be semantically wrong. This experiment does not run a generation model or independent source-claim human annotations through R87.

**NEXT:** subprocess-based kill-at-transaction-boundaries test, WAL/DELETE-mode consistency checks, bulk update distributions, concurrent readers, migration and history, recovery from malformed archive payloads, and independent larger corpora with repeated cold I/O. Compare total source selection, decompression, model inference, and wrong-answer acceptance cost with the strong ordinary FTS baselines.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-87 -p 'test_*.py' -v
    python experiments/round-87/atomic_source_db.py --out experiments/round-87/ci-results.json

Verified CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44267489408 . Only aggregate outcomes are stored; original SciFact claims, abstracts and labels remain upstream.
