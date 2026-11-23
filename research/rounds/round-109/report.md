# CDG Round 109: Materialized Term-Seekable Logical Posting Index

**Date:** 2026-11-23. **Pre-CI status:** 9 local unit/fixture tests passed. No production corpus numerical result is asserted until GitHub Actions completes.

## Why this round

R108 confirmed BARM-R compressed sampled logical QASPER and SciFact FTS5 posting-gap lists more compactly than its varint, StreamVByte-format scalar, and in-sample partitioned Elias-Fano references. This is not proof of any native physical index benefit because a production search index also needs a term dictionary, per-term seek offsets and B-tree pages. We now materially store **the same selected docID-only logical inverted lists** in separate SQLite tables, one per codec, and test exact term lookup and AND/OR operations.

## Original sources, sampling and fairness

- Reuse SHA-locked QASPER v0.3 and SciFact source readers and exactly the frozen R108 five-band 1,950-term-per-corpus hash-minimal selection procedure. No gold judgments, query lists or target codec sizes are used for selection.
- Build the same conventional original contentless FTS5 title/body index. After selection, construct six separate external SQLite stores with exactly the same term dictionary/metadata schema: `CREATE TABLE postings (term TEXT PRIMARY KEY, df INTEGER NOT NULL CHECK(df>0), payload BLOB NOT NULL) WITHOUT ROWID` and 4,096-byte page size.
- Codecs: BARM-R, the variable partitioned-Elias-Fano *DP reference*, varint, scalar StreamVByte-format reference, fixed block bitpack, and Zlib9-compressed independently framed varints. They all use existing R108 exact decoders.
- Include actual on-disk SQLite `.sqlite` file sizes after VACUUM/committed transactions, payload byte totals, and the remaining physical page/lexicon overhead. These external database sizes are now genuinely materialized rather than simulations.
- Predetermine 384 single-term and 128 paired queries by a dataset/code-independent SHA256 rank. Verify exact result equality for *every selected term* during archive creation, every sampled random seek, and AND/OR set combinations; cross-check each queried term against native original FTS5 `MATCH` row IDs.
- Report warm median/p95 term lookup + Python decoder wall time as descriptive one-runner observations only, not hardware-controlled comparative performance. No indexing SIMD library or cold SSD measurements occur.

## Limits and critical comparator caveat

The original FTS5 index stores token positions/frequencies and ranking-support metadata that the experimental docID-only SQLite table does not. Therefore FTS5 byte size is *not* a feature-matched denominator. Even materialized BARM saving vs the other external-table baselines cannot be called a production native FTS5 compression improvement.

R109 tests *only* the 1,950-stratified-term sample per dataset, not a complete invertible replacement for a full corpus search index. A publication-level follow-up must implement a complete index with phrase/frequency semantics and compare tuned C/C++ codecs with fair decoded random seek performance.

## Reproduce

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-109
python experiments/round-109/seekable_index.py --dataset qasper --out experiments/round-109/ci-qasper.json
python experiments/round-109/seekable_index.py --dataset scifact --out experiments/round-109/ci-scifact.json
```

GitHub workflow: `.github/workflows/cdg-r109-seekable-index.yml`.