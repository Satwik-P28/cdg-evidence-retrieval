# CDG Round 105: Dynamic Grouped Evidence Write Amplification and WAL Growth

**Date:** November 19, 2026. **Status:** PASS. Eleven original source, revision identity and physical WAL regression tests, plus full SHA-locked original QASPER 17-arm x 120 synthetic update benchmark, independently rebuilt FTS5 differential and all-source readback passed [GitHub Actions 44472491663](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44472491663).

## Question

Rounds 101–103 established that original QASPER paragraphs can be stored in fully authenticated, shared-dictionary compressed source blocks. Whole-paper Zstd9/dictionary reduced static total SQLite source+index bytes to 7,811,072 B versus the strong individual Zstd9/dictionary archive at 8,687,616 B. But R104 identified a mechanism that might reverse the practical preference: changing one source recompresses its **entire enclosing block**, updates its receipt offsets and FTS5 postings and appends SQLite transaction pages to WAL.

Round 105 evaluates that mechanism with **the same original source data and 120 identical mutations per arm**, separating three resources: post-VACUUM idle physical bytes, compressed payload BLOB bytes re-encoded for a source edit, and cumulative SQLite WAL bytes appended with automatic checkpointing explicitly disabled. We also measure serial warm transaction duration, but do not extrapolate it to a new machine or concurrent p99.

## Frozen controlled data and complete archive variants

- Original QASPER train SHA256: 9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4. Original dev SHA256: 2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93. **Zero overlapping articles**. Dictionary was trained on original train source paragraphs alone, not dev texts or human QA labels.
- Source corpus **13,266 QASPER DEV original paragraph records**, **1,005 original question texts** used *only* to verify final retrieval rankings against an independently rebuilt full-content FTS5 control.
- Exactly **120 deterministic synthetic source revisions** per arm, **81 distinct original rowids**, mixing repeated hot edits and diffuse edits. Synthetic body changes vary original UTF-8 length. Human expert evidence labels were **not reused** after editing source facts.
- **17 archive implementations:** two strong *individual source* controls (Brotli5, Zstd9 with 64 KiB train-only dictionary), plus five paper-local original paragraph block choices **1/4/8/16/whole paper** × three compressors **Brotli5, zstd3+train-only dictionary, zstd9+train-only dictionary**.
- Every revision uses the original source-assisted FTS5 special old-text deletion in one SQLite transaction. Source paragraph identity, original source SHA, block SHA, receipt offsets, all generation metadata and index postings remain linked.
- SQLite in WAL mode with synchronous FULL and **wal_autocheckpoint=0**. Record accumulated WAL file-byte growth after each committed revision, without interim checkpoints. At the end separately checkpoint(TRUNCATE), VACUUM and checkpoint(TRUNCATE) to measure post-revision compacted main SQLite bytes. This deliberately stresses uncheckpointed WAL accumulation and is **not** a production default or a direct SSD physical write counter.
- After all 120 edits, **read and SHA-verify all 13,266 current source receipts per arm** against the original corpus plus the exact deterministic edits. Compare global FTS BM25 index statistics and all **1,005 original question top-10 ranked rowids** against an independently rebuilt source-readable conventional FTS5 index. All 17 arms passed.

## Detailed measured results

All byte figures are literal SQLite on-disk bytes (decimal abbreviations in discussion only). The "rewritten BLOB ratio" is **sum of newly encoded compressed source block BLOB bytes touched by the 120 transactions / sum of newly submitted original source UTF-8 bytes**, not physical device write amplification.

| Layout | Codec | Initial idle bytes | Final compacted idle bytes | Rewritten BLOB/source ratio | Median edit ms | p95 edit ms | WAL accumulated bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Individual paragraph | Brotli5 | 9,506,816 | 9,519,104 | **0.534×** | **0.626** | 1.069 | 9,220,592 |
| **Individual paragraph** | **zstd9 + dict** | **8,687,616** | 8,699,904 | **0.406×** | **0.886** | 1.359 | **9,175,272** |
| 1 paragraph block receipt | Brotli5 | 10,268,672 | 10,280,960 | 0.534× | 1.127 | 1.625 | 9,673,792 |
| 1 paragraph block receipt | zstd3 + dict | 9,588,736 | 9,596,928 | 0.422× | 1.454 | 2.033 | 9,809,752 |
| 1 paragraph block receipt | zstd9 + dict | 9,478,144 | 9,486,336 | 0.406× | 1.511 | 2.315 | 9,710,872 |
| 4 paragraph block | Brotli5 | 9,117,696 | 9,125,888 | 1.738× | 1.206 | 1.873 | 9,797,392 |
| **4 paragraph block** | **zstd9 + dict** | **8,474,624** | **8,486,912** | **1.370×** | **1.528** | 2.084 | **9,752,072** |
| 4 paragraph block | zstd3 + dict | 8,679,424 | 8,683,520 | 1.471× | 1.533 | 2.055 | 9,657,312 |
| 8 paragraph block | Brotli5 | 9,154,560 | 9,162,752 | 2.823× | 1.265 | 1.780 | 9,871,552 |
| 8 paragraph block | zstd3 + dict | 8,712,192 | 8,716,288 | 2.466× | 1.509 | 2.263 | 9,867,432 |
| 8 paragraph block | zstd9 + dict | 8,454,144 | 8,462,336 | 2.277× | 1.630 | 2.675 | 9,916,872 |
| 16 paragraph block | Brotli5 | 8,994,816 | 8,998,912 | 4.745× | 1.401 | 2.025 | 9,694,392 |
| 16 paragraph block | zstd3 + dict | 8,863,744 | 8,867,840 | 4.311× | 1.553 | 2.046 | 9,682,032 |
| 16 paragraph block | zstd9 + dict | 8,593,408 | 8,597,504 | 3.955× | 1.784 | 2.474 | 9,653,192 |
| Whole paper block | Brotli5 | 8,003,584 | 8,011,776 | 16.620× | 2.008 | 4.695 | 12,075,752 |
| Whole paper block | zstd3 + dict | 8,024,064 | 8,028,160 | 16.394× | 1.810 | 2.992 | 11,898,592 |
| **Whole paper block** | **zstd9 + dict** | **7,811,072** | **7,819,264** | **14.834×** | **2.546** | **5.660** | **11,787,352** |

All 17 archives retained exactly **13,266/13,266** live original evidence sources matching trusted synthetic revisions, preserved conventional FTS5 statistics and returned exactly the same **1,005/1,005** query top-ten rankings.

## Strong conclusions, constrained to this workload

**[FACT]** Whole-paper zstd9 + 64 KiB training-only dictionary saves **876,544 static bytes** versus its strongly comparable individually decoded zstd9+dictionary reference, about **10.09%** of the reference's initial source+index archive. But the whole-paper setup rewrites compressed block payload equal to **14.834×** the original bytes submitted for mutation, compared with **0.406×** for independently encoded source, **36.5×** the reference ratio. These are byte ratios, not an independent physical flash write counter.

**[FACT]** Median original update transaction was **2.546 ms** for whole-paper zstd9/dict, compared with **0.886 ms** for independent zstd9/dict in this warm single-runner measurement. Do not claim a universal 2.87× speed difference: data-dependent source length, Python overhead, dictionary preparation and SQLite page behavior all contribute.

**[FACT]** WAL accumulated bytes after 120 updates reached **11,787,352 B** whole-paper zstd9/dict versus **9,175,272 B** individual zstd9/dict. Counting the initial idle main SQLite file *plus this uncheckpointed WAL*, the former temporarily used approximately **19.60 MB**, while the latter used **17.86 MB**. Thus a smaller idle source archive can use **more live disk space during a revision burst** if checkpointing is delayed. This is a designed uncheckpointed WAL stress test, not an inevitable production setting.

**[FACT]** Group-of-4 zstd9/dict used **8,474,624 B** initial source+index versus independent zstd9/dict **8,687,616 B**, saving **212,992 B**, but rewrote 1.370× versus 0.406× newly submitted source bytes, and accumulated a slightly larger WAL file. A small static byte advantage may not justify higher revision costs.

**[NEGATIVE]** No universal monotonic block-size frontier: group16 can use *more* static bytes than group8 for zstd9/dict, and WAL page writes can be lower for some larger groups despite higher compressed payload rewrite. Neither static compressed length nor source BLOB rewrite count alone predicts WAL physical file growth.

## Methodological cautions

- This experiment measures literal SQLite WAL file bytes appended with auto-checkpoint disabled. WAL frame growth is a useful proxy for SQLite transactional page traffic, **not direct SSD bus writes**, compressed-byte network bandwidth or user-visible disk throughput.
- Timings are single serial GitHub Actions runner measurements, no randomized method ordering or independent hardware repeats. No confident hardware speed claims or p99 production guarantees.
- Test edits are synthetic, not real scholarly paper corrections. Original human answer evidence labels are not valid after mutating texts, so **no post-revision answer factuality or hallucination result** is claimed.
- Full block recompression, snapshot-safe read and old-text FTS deletion are standard components, not new compression mathematics.
- One user workload (120 fixed hot/diffuse source edits) and one original source domain. The size/read/update tradeoff may reverse for append-heavy data, very long documents, strongly related paragraphs or alternate retention policies.

## Research direction

**KEEP:** the three-resource source archive frontier: persistent bytes, source decompression amplification and **live revision/WAL amplification**. This is a defensible design principle for a local research evidence system.

**Candidate architecture, not yet implemented:** an adaptive *hot/cold* archive: immutable cold papers use large grouped dictionary blocks; mutable sources stay independently decodable with dictionary compression. Any source transition requires an atomic source-ID mapping/migration and version-preserving index, with controlled evaluation against strong static, uniformly grouped and independently compressed baselines.

**NEXT:** Train an update-hotness / query-access policy only from independent observed historical access traces; evaluate on a heldout source-revision/query trace and a complete byte/CPU/WAL/token budget. Then evaluate human-annotated generated-answer provenance on QASPER/RAGTruth. The current methods are sound engineering combinations but not yet a demonstrated new scientific compression/RAG algorithm.

## Reproduce

Pinned codec dependencies Brotli==1.1.0 and zstandard==0.23.0. Run unit test discovery in experiments/round-105, then run experiments/round-105/update_write_frontier.py with an output JSON path.

Code: experiments/round-105/update_write_frontier.py, experiments/round-105/test_update_write_frontier.py and .github/workflows/cdg-r105-write-amplification.yml. Full exact-head artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44472491663 .
