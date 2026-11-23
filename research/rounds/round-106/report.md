# CDG Round 106: Materialized Hybrid Source Archive with Pseudo-Historical QASPER Access

**Date:** 22 November 2026 (GitHub Actions completed 23 November UTC).
**Status:** PASS. Fifteen regression tests plus full original SHA-locked QASPER DEV, **nine** physically materialized mixed-layout SQLite archive arms, held-out question reads, 60 actual SQLite WAL source revisions per arm, 13,266 original/live source receipts per arm and full FTS5 differential. **Final exact-head CI:** https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45102546445 .

## Hypothesis and mandatory disclosure

R101–105 showed a reproducible three-resource tradeoff: (i) static physical source+FTS5 archive bytes, (ii) decompressed bytes needed to materialize retrieved original evidence, and (iii) compressed source BLOB rewrites/SQLite WAL growth during source edits. Can a **history-based hot/cold source allocation** outperform simple **paper-length** or stable **hash-based** source allocation under actual full-source+index bytes?

**The crucial caveat:** QASPER contains no actual timestamps of user queries and no human source revision log. We create a SHA-fixed pseudo-history by dividing the original 1,005 DEV question IDs into 494 fit and 511 held-out question IDs; the same 281 papers can appear in both sides. Hence this is a **transductive pseudo-historical access evaluation**, *not prospective real-world access logs, chronological held-out telemetry, or unseen-document generalization*. We separately synthesize 60 artificial source edits per archive with a fixed hot/diffuse distribution and NEVER report the original human answer labels as still valid after editing source texts.

## Source provenance, exact evidence and model controls

- Original source QASPER TRAIN member SHA256: 9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4. DEV member SHA256: 2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93. Dictionary trained on **TRAIN original source paragraphs** only, with original train/dev article-ID disjointness, no human labels or question text.
- All **13,266 original DEV paragraphs** retained in every storage layout. A single source-trained 64 KiB Zstd9 dictionary is included and charged **once within each SQLite archive**.
- A new truly mixed physical layout stores original source paragraphs either (A) as independently compressed SHA-verified rows in source_individual or (B) as compressed source_blocks with separately SHA-verified original per-paragraph source_receipts, offsets and generations. One source rowid lives in exactly one representation; no duplicate original text is stored in the alternative table. The same original ordinary contentless FTS5 postings, paper scope, source IDs and text remain unchanged.
- All original query results are evaluated against **the same fixed original BM25 title5/body1** index, and all **1,005/1,005** top-ten rankings are unchanged under each source layout. Held-out evidence paragraph Recall@10 remains **336/459 = 73.20%** among 459 questions with independently exact human text evidence; the other 52 of 511 held-out questions lack exact text evidence and are excluded. This is evidence acquisition, **not generated answer correctness**.
- Two primary usage metrics from the held-out 511 original DEV queries: top1 and top10 **exact original source decoded-byte amplification**, with one decompressed block cache per question and no cross-question cache.
- Separate 60 synthetic source revision transactions in SQLite WAL FULL synchronous with wal_autocheckpoint=0. Every mutation uses exact old-source assisted FTS5 deletion, atomic new postings and original SHA source/repaired block receipt updates. Every variant verified all 13,266 expected live source bytes and all **1,005/1,005** top-ten rankings against a separately rebuilt conventional full-content FTS5 after edits.
- Physical SQLite byte numbers include the single shared dictionary, source provenance receipts, FTS postings and all codec metadata. They **cannot** be directly compared across schema changes to R102/103 without charging their corresponding metadata.

## Layout-selection procedures

Three static pure arms: every original paper's paragraphs individual, in groups of 4, or all together in one original paper block.

Six mixed arms use the same paper counts under a particular percentage rule:
- History 25/25, original paragraph source read bytes per paper based on 494 fitting questions' actual BM25 top-ten ranks only. 25% of papers individual, 25% group4, remaining approximately 50% whole paper.
- History 50/25 uses 50% individual, 25% group4, remaining 25% whole paper.
- Paper-length 25/25 and 50/25, using only original number of paragraphs per paper, not human QA annotations.
- Source-ID stable hash 25/25 and 50/25.
- Matching source-layout capacity within each ratio is unit-tested. No held-out query text, evidence labels or synthetic revision results are used to choose the layouts.

**Exploratory qualification:** The length_50_25 and hash_50_25 controls were added after viewing the first seven-policy held-out run. Those two additional comparisons are not preregistered. The final nine-policy result is a more complete **exploratory** sensitivity study, not a prospective learned-policy selection.

## Final exact-head full original-source results

All bytes are real persisted SQLite main-file bytes. Top1/top10 decoded amplification represents the original uncompressed bytes inflated by Zstd source decoding divided by the actual requested original paragraph bytes. WAL is cumulative on-disk WAL growth over 60 artificial edits, NOT physical flash write bytes. Source write ratio is sum of newly encoded compressed source/block BLOB bytes divided by the 60 originally submitted edited source UTF8 bytes.

| Policy | Physical source+FTS database B | Heldout top1 decode amp | Heldout top10 decode amp | Revised BLOB/original source ratio | WAL B during edits |
| --- | ---: | ---: | ---: | ---: | ---: |
| **All paragraphs independently compressed** | 8,470,528 | **1.000x** | **1.000x** | 0.3822x | **6,031,712** |
| **All papers groups of 4** | 8,413,184 | 4.113x | 2.228x | 1.2073x | 6,324,232 |
| **All original papers as one group** | **7,831,552** | 42.788x | 4.312x | 14.3228x | 7,148,232 |
| **History 25/25** | 8,146,944 | 21.195x | 2.854x | 6.6809x | 6,641,472 |
| **History 50/25** | 8,273,920 | 12.836x | 2.147x | 4.0832x | 6,402,512 |
| **Paper length 25/25** | 8,302,592 | 15.731x | 2.314x | 2.4445x | 6,278,912 |
| **Stable SHA 25/25** | 8,196,096 | 21.072x | 2.831x | 4.8039x | 6,546,712 |
| **Paper length 50/25** | 8,429,568 | **7.192x** | **1.639x** | **1.0990x** | **6,159,432** |
| **Stable SHA 50/25** | 8,318,976 | 10.789x | 2.021x | 2.0005x | 6,254,192 |

The physically materialized source archives reflect differing metadata choices from R103, and include all original paragraphs in all arms.

### Binding-byte interpretation

- At **8 MiB = 8,388,608 B**, the all-individual, all-group4 and paper-length 50/25 arms **do not fit**. Among the five compliant mixed designs, history 50/25 yields 2.147x held-out top10 decoded-byte inflation at 8,273,920 B, while stable SHA 50/25 yields a *lower* 2.021x inflation and lower WAL bytes at a slightly higher physical archive cost of 8,318,976 B. Neither is a strict winner across all resources.
- At **9 MiB = 9,437,184 B**, all nine candidates fit. Paper-length 50/25 achieves the lowest held-out top1/top10 byte inflation among the mixed arms (7.192x and 1.639x) and lowest synthetic-edit WAL growth among those mixed designs. It is larger than the other mixed archives, so no unconditional advantage.
- The full **all-individual** archive has lowest held-out decode amplification (1x) and lowest WAL traffic in the artificial update scenario; it cannot fit within the strict 8 MiB budget. Thus an identical-source compressed source representation under a hard byte limit must choose a real cost tradeoff, not a free compression-only improvement.

### Negative result: access history does not dominate simple source features

Holding allocations at **25% individual, 25% group4, 50% whole-paper**, history selected based on 494 fit queries had **2.854x** held-out top10 decoded bytes versus **2.314x** for the corpus-only paper-length method, with more synthetic WAL bytes. The history method was smaller by 155,648 B, so there is a real storage/read tradeoff rather than outright domination.

At matched **50/25** allocations, paper length achieved 1.639x heldout top10 inflation versus 2.147x for the historical access policy, again at higher persistent bytes. Stable source hashing also outperformed history on heldout top10 inflation at both layout ratios. This specifically **falsifies an unqualified claim that fitting to these pseudo-historical BM25 access counts improves future retrieval access efficiency**.

Mechanistic hypothesis, NOT proven: QASPER questions are provided with a known paper ID; many papers have only a few questions. Original paper length predicts both the potential decompression penalty and number of original source paragraphs that can share a compressed frame, whereas the accidental pseudo-history may be sparse/noisy. This needs a distinct validation protocol and real timestamped source access to test.

## Relation to established prior art

RocksDB's time-aware tiered storage design explicitly discusses the difficulty of predicting keys from per-key access history: https://rocksdb.org/blog/2022/11/09/time-aware-tiered-storage.html . RocksDB also documents pre-trained dictionary compression and caching: https://rocksdb.org/blog/2021/05/31/dictionary-compression.html . Adaptive source layout and hot/cold tiering **are not original conceptual inventions here**. This experiment supplies a controlled and reproducible evidence-source manifestation with full SHA provenance, FTS parity and real SQLite archive/WAL accounting, not a theory of universal layout optimality.

## Unresolved costs and next experiment

- **No in-place live layout migration is implemented** in R106. Archive build time is measured and retained per arm, but cannot be substituted for atomic migration latency or the cost of swapping a block while old reader snapshots remain active.
- The sample train/test partition uses the **same original papers** on both sides and random hash rather than real timestamps. Test on genuine source revision/access traces or fresh independent papers with a predeclared source-feature policy before publication.
- No model weights, dense source embeddings or generated answer facts are counted here. The retrieval model remains simple BM25, whose source relevance is a separate limitation.
- Next sensible falsifier: **strong pretrained dense/hybrid retrievers**, measuring true model/vector bytes and independent expert annotated paragraph Recall under the same question paper scope, followed by generated answer attribution. The stronger static/append/update findings cannot by themselves establish reduced hallucination.

## Reproduction

Install Brotli 1.1.0 and zstandard 0.23.0. Run 15 unit tests under experiments/round-106 then execute experiments/round-106/trace_adaptive_archive.py. GitHub workflow .github/workflows/cdg-r106-hybrid-history.yml.

**Final verified CI including matching 50/25 controls:** https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45102546445 . Earlier seven-arm successful exploratory CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45102318408 . The intermediate expanded run failed only in terminal printing due to an absent metadata key; the final source-count field and test were corrected and a complete exact-head CI succeeded.
