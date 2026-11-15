# CDG | Technical evidence dossier for FOCUS

**Audit date:** 14 November 2026. This dossier reviews committed Round 19–32 descriptions and representative source code. It does not claim to have executed a fresh clean-room reproduction of all experiments. No publication or peer review is claimed.

## 1. Technical summary

Problem: recover a complete, source-identifiable evidence set without paying unlimited index, decompression, I/O, prompt and update costs. The implementation separates **retrieval relevance**, **source byte identity**, **generation consistency**, **semantic support**, and **system cost**. Only the first three have partial experimental implementations; semantic support by an answer generator has not been independently established.

The strongest implemented substrate, Round 32, consists of:

- SQLite FTS5 *contentless* posting segments, keyed by whole-source SHA-256.
- Independently compressed Zstandard frames, addressed by SHA-256 of **uncompressed** frame content; descriptors map source byte positions to frame identities.
- Immutable source-version descriptors and small generation manifests pointing to those descriptors.
- A generation pointer, historical pinned readers and receipts binding `(generation, source SHA-256, byte range)`.
- Tests for byte-for-byte readback, Unicode/byte-offset handling, corruption, stale receipts and failed-before-switch publication.

**Trust boundary:** This is a local single-writer experiment, not a protected multitenant archive. The code has no external-origin authentication, signed manifests, ACL checks, cross-host locking, lease-aware collection or fully proven power-failure recovery.

## 2. Evidence-to-claim map

| Claim suitable for the application | Primary committed evidence | Scope / qualification |
|---|---|---|
| 74.5% lower storage after 11 generations | `research/rounds/round-32/report.md`; `experiments/round-32/results.json`, `runs[0].history[-1]` | 5 internal reports, 10 sequential updates, all generations retained. Full rebuild is intentionally unoptimized. |
| ~19.4x median replacement update speedup | Same Round 32 report and per-generation `build_ms` values | Warm Python/SQLite/libzstd local timings. Does not compare with WAL, incremental FTS5 or a production KV store. |
| Byte-identical frame reuse and generation-bound citation | `experiments/round-32/incremental_store.py`; `test_incremental.py` | Tested local behavior, no independently trusted signature. |
| 32.3% storage reduction from FTS5 contentless schema | `research/rounds/round-30/report.md`; `experiments/round-30/contentless_all_results.json` | 5 local documents, 18 local query comparisons, existing SQLite feature. |
| Improved complete support-document discovery | `research/rounds/round-25/report.md`; `experiments/round-25/results.json` | 100 curated HotpotQA-derived questions, closed-world candidate contexts, connected-data JS evaluation; Python full-data reproduction pending. |
| Low compressed-byte traffic is not automatically low latency | `research/rounds/round-29/report.md`; `experiments/round-29/results.json` | Source-derived queries on internal reports, uncontrolled warm timings. |

## 3. Why the systems design is nontrivial

**Correctness invariant:** Every observed byte span belongs to a specified source version and generation. Offset changes must be versioned; matching text content alone cannot justify accepting a stale receipt. Frame hashes support payload identity, and source hashes support complete-source version identity, but neither establishes semantic truth.

**Storage invariant:** Frame deduplication must not silently merge authorization or citation identities. Two sources may share a frame without sharing permissions, provenance or semantic meaning. The source descriptor remains the authoritative mapping from source version and offset range to physical frame.

**Update invariant:** Replacing a single source should ideally avoid rewriting unrelated source indexes and frames. Deduplicating frames *without* deduplicating descriptors leads to metadata-driven space growth. This was an observed intermediate failure in Round 32 and motivated immutable per-source descriptors.

**Performance trade-off:** Smaller frames cut read amplification while increasing archive/index overhead and potentially increasing decompression and query dispatch calls. A single global FTS index may be faster at search than the Round 32 source-sharded design. The present sharded retrieval code orders results deterministically by source name and line ID; **its per-shard FTS scores are not globally calibrated**.

## 4. Actual experiments, not marketing claims

**R25, retrieval:** With K=2 on 100 curated HotpotQA-derived questions, complete support-document recall was 33/100 for BM25 and 46/100 for conventional title-mention expansion. Document identity is not answer correctness. An additional sentence filter lost some annotated supporting sentences.

**R26–R29, physical access:** Real frame compression was measured first on technical report bytes; exact UTF-8 spans and frame-read amplification were accounted for. Query-driven FTS5 readback later worked, but fewer compressed bytes were not a monotonic predictor of latency.

**R30, index design correction:** Removing redundant stored text from the SQLite index cut the measured total store size by 32.3% at 512-byte frames. This is better engineering use of existing technology, not novel theory.

**R31, version consistency:** Single-writer immutable generations enabled stale-receipt rejection and old-reader continuity, at the cost of significant full-rebuild write amplification.

**R32, incremental reuse:** Storing unchanged search indexes and compressed frames only once brought retained storage from 4.60 MB to 1.17 MB in the tested 11-generation workload. A complete comparison to standard incremental database implementations is still missing.

## 5. Risks a technically experienced reader will notice

1. **Weak control:** R32's full-rebuild baseline is explicitly poor at update workload; the headline improvement mainly demonstrates incremental reuse. Do not imply superiority over state-of-the-art storage.
2. **Small correlated source corpus:** Five internal research reports and repeated small edits are not diverse datasets or scale stress tests.
3. **Query ranking:** Per-source independent FTS5 indexes are searched separately and truncated by source-order, not globally ranked by one calibrated relevance score. This is not production open-corpus relevance.
4. **No true end-to-end benchmark:** External multihop question evaluation and local compressed-store execution occurred in separate experiments.
5. **No semantic entailment:** SHA-256 receipt validation checks exact bytes and generation only.
6. **Cost omissions:** Query/updates lack rigorous randomization, cold-cache measurements, CPU profiling, realistic concurrent reads, and total corpus acquisition economics.
7. **Failure modes:** Power-loss recovery, multiwriter isolation, garbage collection and content-store poisoning are incompletely modeled.
8. **Provenance hygiene:** `MANIFEST.json` is an old artifact inventory, not the current 308-file manifest. Earlier raw round archives are incomplete. No active CI workflow was present at this audit.
9. **Authorship:** Some code, analyses and writing were developed with AI assistance. The safest presentation is to discuss the validated reasoning and contributions accurately, not imply wholly unaided development.

## 6. Most important next experiment

Before trying to publish a novel paper, compare **three** implementations under identical data and queries: (1) one global SQLite FTS5 database using proper incremental updates and WAL, (2) immutable per-source FTS5 segments plus frame CAS, and (3) an ordinary versioned object store with seekable Zstandard and an index. Use unseen longer documents, different update fan-outs, deletions, retention windows, concurrent readers and measured p50/p95. Then pass independently authored multihop questions through the actual source reader and evaluate complete supporting-sentence recall, answer/citation correctness and total cost.

**Kill rule:** If ordinary SQLite plus seekable compression matches the custom design, remove or demote the custom index. Retain the parts that provide demonstrable source-version consistency and byte-reproducibility.

## 7. Jane Street framing

Lead with decisions and invariants rather than listing dozens of rounds. The substantive story is: **I identified an evidence-completeness problem, built a measurable storage prototype, found a redundant-index cost, exposed update amplification, redesigned around immutable content-addressed state and kept correcting the baselines.** The result is a technically demanding independent research project with honest unresolved questions, not an established breakthrough.
