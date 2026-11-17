# Round 28: File-Backed Zstandard Frames, Serialized Search Metadata, and the Cost of an Index

**Date:** 13 November 2026  
**Status:** Executed local systems benchmark; not HotpotQA or a RAG answer-quality comparison.  
**Decision:** Keep conventional SQLite plus seekable independent Zstandard frames as the immediate engineering baseline. Reject claims that the Round 27 read-traffic reductions already establish a speed or total-storage improvement.

## 1. Why this round matters

Round 25 established that observing an initial source can reveal a missing bridge to another source, but the result used a question-local candidate corpus and a simple non-neural link heuristic. Round 26 showed that selecting fewer sentences can discard necessary evidence, and modeled how frame size changes read amplification. Round 27 measured actual compressed frame payload lengths on technical reports, but *did not serialize or charge for the source index and frame lookup data*. The primary question of Round 28 is: **Does a physically materialized and indexed compressed-source store change the relative cost of the proposed layouts?**

### Hypothesis before the experiment

For short, line-oriented source spans, line-aligned independent compression may reduce compressed payload activated compared to fixed-byte frames. However, a complete search and frame-coordinate index may dominate the total footprint, and the layout with fewer compressed bytes per read may not have lower latency.

## 2. Executed implementation

[`experiments/round-28/filebacked_bench.py`](../../experiments/round-28/filebacked_bench.py) writes real `frames.zst` files containing concatenated independent Zstandard level-3 frames, via the system `libzstd` API. A separate durable `index.sqlite` stores:

- Source identifiers, file names, SHA-256 digests, versions, original byte lengths.
- Frame raw offsets and exclusive ends, payload offsets and lengths; indexed by source and raw coordinate.
- Line offsets, line text, and an **actual SQLite FTS5 full-text index** of those lines.

The storage layouts are whole-document streams, fixed-byte frames, and greedily packed line-aligned frames at capacities of 256, 512 and 2,048 raw bytes. Frame decoding calls `os.pread` with serialized file offsets followed by `libzstd` decompression; overlapping requested intervals activate each relevant frame only once within a query. Reconstructed span bytes are compared directly to the original file bytes. Source frames are stored in an ordinary file, not an official Zstd seekable archive format. FTS5 is queried to verify that the search index works, but **the workload supplies source-coordinate intervals without using FTS5 to choose them**. This is a deliberately isolated physical-read test with *oracle span coordinates*. The SQLite index is real and included in measured storage footprint; its relevance and query-planning performance are not evaluated.

Six local standard-library unit tests passed after repairing a real empty-span bug where a zero-length interval activated a frame. Tests cover Unicode and discontiguous byte restoration, independent-frame codec roundtrips, multiple source IDs, zero-length intervals, live SQLite FTS lookup, and stale version-hash detection.

## 3. Dataset and workloads

Five exact local research reports, 88,679 UTF-8 bytes in total. These are **not** the exact same five report snapshots from Round 27, so direct cross-round numerical differences must not be interpreted as improvements or regressions.

| Input file | Bytes | SHA-256 |
|---|---:|---|
| `CDG_Round19_Research_Report_2026-11-11(1).md` | 28,396 | `b8c805baef7dffaeaf355d31a0ccc23fd1aa83e411a4cbebcc54cae8cd414c02` |
| `cdg_round20_appendix.md` | 16,987 | `c03ad05bd18331e8553d3fe964595bdedbc1ee6a7a9c6d7e5b3a58fd9c947291` |
| `cdg_round21_appendix.md` | 16,372 | `1b310415d0a7f267cd83712b31e70d8d42b956ac44efcff8e71b90394f2f3c99` |
| `cdg_round22_appendix.md` | 14,371 | `49470dd86762c76fcad6eed1795c27da876972a7d7f3f67ed7411963fcf415ad` |
| `report.md` (Round 27) | 12,553 | `8ccbcdd68a07afc3738d4270103c4a1616a775899721ed439323ed570e722e9b` |

Two seeded synthetic workloads of **250 requests each** are generated from lines of at least 45 raw bytes: (a) requests for whole line intervals, (b) requests for short interior subspans. Every third request chooses a nearby second line in the same source if available. Seed 28026. Original span coordinates are known before retrieval; no semantic model or question decomposition is involved. Because query spans originate from lines, line alignment has a favorable sampling bias.

## 4. Measured persistent storage and file-backed compressed traffic

All persistent bytes shown are measured on local files, not modeled entries. They include SQLite's page allocation and the complete FTS5 index. They do not include directory entries, filesystem block allocation overhead or a separate index build log.

| Layout | Zstd payload B | SQLite B | Total B | Mean compressed B/query, whole-line | Mean compressed B/query, subspan |
|---|---:|---:|---:|---:|---:|
| Whole document | 38,689 | 233,472 | **272,161** | 12,509.3 | 12,358.4 |
| Fixed 256 | 64,533 | 241,664 | 306,197 | 641.7 | 387.0 |
| Line-aligned 256 | 66,381 | 262,144 | 328,525 | **428.8** | **317.7** |
| Fixed 512 | 58,283 | 233,472 | 291,755 | 833.9 | 623.2 |
| Line-aligned 512 | 59,785 | 241,664 | 301,449 | **556.8** | **510.5** |
| Fixed 2,048 | 48,323 | 233,472 | 281,795 | 1,986.3 | 1,833.2 |
| Line-aligned 2,048 | 48,961 | 233,472 | 282,433 | **1,765.3** | **1,718.3** |

All **500 requests per layout** returned the original requested bytes without mismatches. Figures include repeated compressed reads across distinct requests; an overlapping frame is not double-counted within a request. Source hashes are preserved in [`results.json`](../../experiments/round-28/results.json).

At 512 bytes, line-aware layout stores **9,694 additional bytes** while saving **277.1 compressed bytes/query** on whole-line requests (33.2%) or **112.7 bytes/query** on subspan requests (18.1%). A mathematically simple storage-to-read ratio is ~35 or ~86 requests respectively if a persistent byte and a retrieved byte receive exactly equal unit weights. **Those ratios are not actual latency or economic break-even thresholds.** SSD read amplification, OS caching, CPU cost, index build and source update frequency are not equally weighted.

The persistent SQLite index ranges from ~233 KB to ~262 KB, more than twice the 88.7 KB of source data. `dbstat` attributed large allocations to the line text table, FTS postings and line offset index. This small-corpus result illustrates *why measured index bytes cannot be omitted*. SQLite's page granularity and duplicated text in the line table are likely factors; it is not a universal ratio for large corpora.

## 5. Real file-backed timing, with a substantial qualification

These are single-run warm observations, in microseconds per request, including Python's SQLite lookups, actual `os.pread` of compressed payload from file descriptors, Zstandard decoding and interval assembly. The benchmark does **not** drop the OS page cache or control clock frequency. No real disk cold-read distribution is available.

| Layout | Whole-line p50 / p95 μs | Subspan p50 / p95 μs |
|---|---:|---:|
| Whole | 75.7 / 96.7 | 75.4 / 114.1 |
| Fixed 256 | 70.9 / 120.8 | 48.8 / 86.2 |
| Line-aligned 256 | 68.4 / 123.5 | 55.9 / 180.2 |
| Fixed 512 | **57.0 / 98.0** | **45.5 / 83.1** |
| Line-aligned 512 | 58.2 / 93.0 | 58.5 / 183.2 |
| Fixed 2,048 | 47.2 / 81.8 | 47.6 / 117.9 |
| Line-aligned 2,048 | 46.3 / 76.4 | 46.2 / 81.2 |

**Negative result:** The 512-byte line-aware layout reliably reduces compressed bytes read in this workload but does not deliver a measured warm p50 benefit. The large subspan p95 variation is especially untrustworthy without repeated randomized runs. If the practical objective is latency, read-byte reduction alone is an invalid surrogate.

Four additional archive+index rebuild runs per layout found observed construction times of ~16-21 ms whole, ~20 ms fixed 512, and ~22-25 ms line 512, on this machine and tiny workload. These are not robust update-throughput measurements.

## 6. Graph-of-thoughts branches

### H28-A: Evidence discovery and physical materialization are separate resource constraints

The source-query controller chooses spans, but the physical store decides which frames must be decoded. Finding relevant text cheaply cannot be assumed if search metadata is larger than the source payload. **Any optimization objective must include index structure and query execution**, not just compressed archive ratio or token count.

### H28-B: Frame-packing optimality is workload-dependent

A simple objective for comparing layouts is

\[
J(L)=\alpha\,S_{\mathrm{archive+index}}(L)+\beta\,\mathbb E[R_{\mathrm{compressed}}(q,L)]+\gamma\,\mathbb E[T_{\mathrm{lookup+decode}}(q,L)]+\delta\,C_{\mathrm{updates}}(L).
\]

The coefficient values depend on expected request volume, concurrency, hardware, source lifespan and service-level objectives. They are not identified by this experiment. Smaller frames reduce bytes activated but increase frame and offset metadata. A conditional physical layout might improve a workload-specific Pareto frontier, but database clustering, materialized views, conventional posting lists and seekable compression are strong established alternatives.

### H28-C: An FTS postings index can conflict with strict byte provenance

The prototype indexes decoded line text using replacement characters for invalid UTF-8. The raw source frames are still lossless, but FTS tokens are **not a reversible canonicalization**. A search hit is an approximate locator, not evidence that the answer is grounded. A future receipt must tie `(source SHA/version, byte spans, canonicalizer ID, index snapshot)` to an exact re-read and independently validate cited text. This is a correctness concern independent of compression ratio.

### H28-D: Mutability and authorization invalidate simple caching assumptions

A mutation test changes one source's content, checks that its stored SHA-256 differs, rebuilds a replacement store and verifies its new digest. This is **only a primitive stale-digest check**. Reads themselves do not yet enforce a hash/version contract, source edits currently trigger full rebuild, and there is no atomic index/payload switchover or ACL enforcement. Production correctness requires snapshot pinning and an update transaction boundary before the source receipt can be trusted.

### H28-E: We have not established any new retrieval algorithm

Bridge-link expansion remains a conventional iterative retrieval method. FTS5 and independent compressed frames are established engineering components. The first possibility worth further work is **a rigorously benchmarked joint materialization policy** that uses held-out evidence co-access statistics to choose grouping and index placement. The simpler null hypothesis is that ordinary compressed frames plus SQLite/FTS5 already sit on the appropriate frontier for this workload. This null must be tested, not dismissed.

## 7. Prior art and implementation conventions

- SQLite FTS5 external-content behavior and shadow-table overhead: https://www.sqlite.org/fts5.html . The prototype explicitly stores line text and uses an external-content FTS5 index. Source edits require correct updating of both or query behavior can be inconsistent.
- Zstandard seekable format: https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/zstd_seekable_compression_format.md . The prototype is **not** this file format; it uses SQLite offsets and independent concatenated Zstandard frames.
- Standard database clustering, compressed inverted indexes and physical data layout optimization cover much of this design space. No original-compressor or first-of-kind index claim is appropriate.

## 8. Reproduction and audit boundaries

From the repository, supply the five SHA-matched report files, then run:

```bash
python experiments/round-28/filebacked_bench.py \
  --files round19.md round20.md round21.md round22.md round27.md \
  --output round28_results_reproduced.json
python -m unittest discover -s experiments/round-28 -p 'test_*.py' -v
```

Requires Python 3.10+, libzstd shared library, and SQLite with FTS5. Tests and full physical benchmark **were executed locally** against the five reports listed here; source bytes are not bundled into the Round 28 experiment. The temporary on-disk archives are created and removed within the benchmark. The JSON output contains precise source hashes and every layout result. The benchmark uses actual persistent files but not real natural QA span locations, answer generation, a verified independent HotpotQA split, cold-cache SSD measurements, a production versioned index, or real ACLs.

## 9. Round 29 decision gates

1. Obtain a fully authenticated, local HotpotQA distractor subset with source text and annotations, and freeze disjoint development/evaluation subsets.
2. Use a real FTS5 query + a conventional title-link or two-hop metadata join to discover source and sentence coordinates at inference. No oracle spans.
3. Compare against BM25/FTS5, iterative bridge retrieval, FTS5 plus ordinary seekable compression, and any proposed co-access grouping at **matched evidence completeness**.
4. Report archive/index/source receipts, actual compressed bytes and data reads, warm and controlled cold trials, build/update cost, update consistency, per-query search time, complete annotated sentence recall and generated-answer grounding separately.
5. Refuse any novel systems or performance claim if the custom layout loses to existing indexing and seekable compression after complete accounting.

**Round 28 verdict:** We built the missing file-backed baseline and demonstrated how index footprint and query overhead affect the trade-off. **We did not beat a strong end-to-end RAG baseline, and we did not establish publication-level novelty.**
