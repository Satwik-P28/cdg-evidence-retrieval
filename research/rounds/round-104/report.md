# CDG Round 104: Atomic Grouped Source Revisions, FTS5 Consistency and SIGKILL Recovery

**Date:** November 19, 2026. **Verified:** eleven original-source/transaction tests and full SHA-locked QASPER 120-edit differential PASSED. [GitHub Actions 44471679356](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44471679356).

## Why this round matters

R101–103 found a storage versus decompression-amplification Pareto frontier for losslessly compressed original QASPER evidence paragraphs. Those archives were static. Editing one paragraph can also change its block hash, following byte offsets, source receipt, index postings and source version. It is unsafe to treat a static source archive as a complete dynamic research backend without atomic revision and coherent snapshot evidence.

R89 found a separate indexing defect in the tested SQLite configuration: FTS5 contentless_delete=1 with DELETE + INSERT inflated hidden BM25 aggregate statistics under revisions. R90 reproduced the existing ordinary-contentless FTS5 special old-text delete command instead. R104 extends that prior-art approach to grouped blocks.

## Exact revision transaction

A single SQLite BEGIN IMMEDIATE transaction first validates a source paragraph's original doc ID, section title/body, receipt SHA256 and offsets, block digest, paper ID and generation. It deletes the old FTS5 postings using the exact SHA-verified prior title and abstract, then inserts the new postings at the same rowid. It replaces the exact source range in the original block, recompresses using the existing Brotli5 or dictionary-backed Zstd codec, and updates the block SHA, byte length and generation. It then updates the target original paragraph receipt SHA and length and offsets of every following paragraph **within that block**, and commits. Pre-commit failure rolls all of these back together. Read-side ranking and source receipt materialization occur inside a single SQLite transaction.

The generation migration initializes existing static source blocks and paragraph receipts at generation 1. The original serialization is title + newline + body, so a newly submitted title containing a newline is rejected rather than ambiguously interpreted.

## Original source workload and controls

- Original QASPER v0.3 TRAIN SHA256: 9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4. Original DEV SHA256: 2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93. Zero train/dev article ID overlap, with the dictionary trained on original TRAIN source text only.
- Original DEV corpus 281 articles, 13,266 paragraph sources, 1,005 question texts. Blocks of four paragraphs with Zstd9 and a 64 KiB independently trained dictionary.
- Exactly **120 deterministic synthetic source revisions affecting 81 distinct source rowids**, combining hot and diffuse revisions and variable UTF-8 byte-length changes.
- An independent conventional **full-content SQLite FTS5** index received the same revised source text. Full original source receipts and global FTS statistics were independently checked.
- After all 120 revisions, **13,266/13,266** current sources reconstructed byte-exact from trusted original inputs plus synthetic edits.
- **1,005/1,005** original QA question top-ten rankings matched the independently revised conventional FTS5, with exact global FTS index statistics and SQLite/FTS structural integrity.
- Human QASPER gold evidence was NOT scored after changing scientific source paragraphs; the original labels need not remain true after edits.

## Actual OS process kill tests

Ten actual subprocess SIGKILL cases, five kill stages in each of DELETE rollback-journal and WAL modes. The five stages were after old FTS posting deletion, after new FTS insertion, after compressed block replacement, after source receipt replacement, and immediately after transaction COMMIT.

For all **8 pre-COMMIT kills**, recovery returned the original source text and version 1. For both **post-COMMIT kills**, recovery returned the new source text and version 2. Core SQLite and FTS5 integrity checks passed. This demonstrates observed process-termination rollback/commit behavior, not physical power-loss durability or independent kernel/storage fault injection.

An additional WAL read transaction was interleaved with a separate writer commit between search ranking and original source materialization. The reader's transaction observed coherent old evidence and a subsequent transaction observed the committed new evidence. This addresses the R88 torn-transaction source mismatch in the grouped archive.

## Eleven regression controls

Tests cover changed source byte lengths and following offsets, 50 repeated hot-source edits versus conventional FTS5 global stats, four exception rollback stages, post-COMMIT exception semantics, wrong source ID, malformed section title, corrupted old source SHA, WAL interleaved snapshot, all 10 actual SIGKILL states, Brotli5 source fallback, and unaffected offsets in other blocks.

## Scope and scientific decision

**KEEP:** Atomic SHA-verified block and receipt revisions, ordinary-contentless FTS old-source deletion, SQLite coherent snapshots, and real process-kill recovery. This is correctness infrastructure, not a novel compressor or semantic retriever.

**NOT SHOWN:** Power-loss durability, production multiwriter throughput, p95/p99 source revision latency, persistent WAL growth under repeated edits, network filesystem safety, arbitrary title/newline serialization, free-form answer factuality or hallucination suppression. Recompressing whole affected blocks may substantially increase revision write amplification; it must be measured before selecting group sizes for mutable research data.

**NEXT:** R105 should measure exact write amplification, transaction latency and persistent WAL growth across block size and source codecs, rather than extrapolating the static storage frontier into an update-heavy workload. Follow with generated-answer citation and human grounding on an independent dataset.

## Reproduce

Run the unit test discovery in experiments/round-104, then run experiments/round-104/atomic_grouped_updates.py with an output JSON path. Pinned packages: Brotli 1.1.0 and zstandard 0.23.0. Files: experiments/round-104/atomic_grouped_updates.py, experiments/round-104/test_atomic_grouped_updates.py, .github/workflows/cdg-r104-group-atomicity.yml.

Verified full source SHA and crash results: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44471679356 .
