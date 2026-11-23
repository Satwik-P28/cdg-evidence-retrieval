# CDG Round 109: Materialized Term-Seekable Logical Posting Index

**Date:** 2026-11-23. **Status:** PASS. 9 local unit/fixture tests and original SHA-locked QASPER/SciFact source benchmarks passed in GitHub Actions [45249285543](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45249285543). Aggregate machine-readable results: `experiments/round-109/results-qasper.json` and `results-scifact.json`.

## Why this round

R108 confirmed BARM-R compressed sampled logical QASPER and SciFact FTS5 posting-gap lists more compactly than its varint, StreamVByte-format scalar, and in-sample partitioned Elias-Fano references. This is not proof of any native physical index benefit because a production search index also needs a term dictionary, per-term seek offsets and B-tree pages. We now materially store **the same selected docID-only logical inverted lists** in separate SQLite tables, one per codec, and test exact term lookup and AND/OR operations.

## Original sources, sampling and fairness

- Reuse SHA-locked QASPER v0.3 and SciFact source readers and exactly the frozen R108 five-band 1,950-term-per-corpus hash-minimal selection procedure. No gold judgments, query lists or target codec sizes are used for selection.
- Build the same conventional original contentless FTS5 title/body index. After selection, construct six separate external SQLite stores with exactly the same term dictionary/metadata schema: `CREATE TABLE postings (term TEXT PRIMARY KEY, df INTEGER NOT NULL CHECK(df>0), payload BLOB NOT NULL) WITHOUT ROWID` and 4,096-byte page size.
- Codecs: BARM-R, the variable partitioned-Elias-Fano *DP reference*, varint, scalar StreamVByte-format reference, fixed block bitpack, and Zlib9-compressed independently framed varints. They all use existing R108 exact decoders.
- Include actual on-disk SQLite `.sqlite` file sizes after VACUUM/committed transactions, payload byte totals, and the remaining physical page/lexicon overhead. These external database sizes are now genuinely materialized rather than simulations.
- Predetermine 384 single-term and 128 paired queries by a dataset/code-independent SHA256 rank. Verify exact result equality for *every selected term* during archive creation, every sampled random seek, and AND/OR set combinations; cross-check each queried term against native original FTS5 `MATCH` row IDs.
- Report warm median/p95 term lookup + Python decoder wall time as descriptive one-runner observations only, not hardware-controlled comparative performance. No indexing SIMD library or cold SSD measurements occur.

## Executed numerical results: full SQLite database bytes

**All six stores use identical selected terms, features, and physical schema.** Physical byte count includes term strings, primary B-tree pages, metadata and encoded payload. The original FTS5 bytes listed separately below provide context only and are **not feature-equivalent**.

| Materialized external docID-only store | QASPER DEV (1,950 terms; 144,717 postings) | SciFact (1,950 terms; 116,186 postings) |
| --- | ---: | ---: |
| **BARM-R** | **212,992 B** | **155,648 B** |
| Variable-partition EF reference | 241,664 B | 188,416 B |
| Bitpack | 270,336 B | 188,416 B |
| Zlib9 varint frames | 286,720 B | 208,896 B |
| Framed varint | 307,200 B | 237,568 B |
| Scalar StreamVByte-format | 348,160 B | 274,432 B |
| Original standard full FTS5 index (not feature-equivalent) | 4,505,600 B | 4,644,864 B |

Measured BARM physical store savings over identical-schema varint stores: **30.67% QASPER** and **34.48% SciFact**. Versus the in-sample variable-partition EF reference: **11.86% QASPER** and **17.39% SciFact**. These percentages apply to the hashed sample and reduced docID-only feature contract, **not** full actual CDG index compression.

Every arm passed all **384** deterministic selected term lookups checked against the actual original FTS5 `MATCH` row IDs, and **128** exact AND/OR pairs. Result reconstruction after storage was byte-exact for every selected term. Corrupted `df` count guards were exercised in local fixtures.

### Nontrivial cost: decoding

Warm one-runner Python + SQLite median (ms per selected term):

| Codec | QASPER median / p95 | SciFact median / p95 |
| --- | ---: | ---: |
| BARM-R | **0.01920 / 0.40405** | **0.02093 / 0.25906** |
| Variable EF | 0.01422 / 0.16857 | 0.01396 / 0.09289 |
| Varint | 0.01078 / 0.05833 | 0.01013 / 0.03330 |
| StreamVByte-format scalar | 0.01086 / 0.10268 | 0.01222 / 0.06072 |

BARM therefore took ~1.78x QASPER and ~2.07x SciFact **median** versus varint in this implementation; the p95 gap was larger. Python reference decoder construction, branch handling, data skew, VM scheduling, and SQLite page-cache states all matter. These exploratory sequential timings are neither randomized paired native-machine measurements nor a reliable production latency ratio. Results include no physical cold-device I/O measurement.

**Decision:** BARM survives the stricter *materialized storage* test, but has a material speed penalty in Python. The next step is to optimize the exact BARM bit decoder and compare CPU costs at identical source/token/query semantics, with failure-fuzz tests. Native SIMD comparison and complete index/ranking semantics remain necessary for any publishable codec claim.

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