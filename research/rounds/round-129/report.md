# R129: Independent first-parent Git histories, integrated archive evaluation

**Status: PASS for both independent corpora.** Frozen protocol was committed before execution at `1d5689e1872cecfed507abff2ad34a476c4fa746`. [Original-code CI run 45491997407](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45491997407), CPython job 138792469140 and BIPs job 138792469847, both successful; each ran three unit tests.

Two independent repositories: CPython v3.13.0 (commit 60403a5409ff2c3f3b07dd2ca91a7a3e096839c7) library documentation and Bitcoin BIPs (commit 0d99ffd39fdaf75209c43b1f8ec3fbbc23f10814) specification text. Use last 400 path-touch first-parent commit snapshots at pinned commit; common baseline is first selected commit's first parent. Hash-select 80 paths existing at baseline using fixed salt. Exclude and report sampled paths missing in any observed snapshot. Include exact blob bytes and commit/blob IDs, source SHA-256, timestamps, version ordinals and per-commit generation boundaries. Baseline seeding and multi-file changes ordered by path; evaluate only complete commit snapshots. This is ancestry chronology, not wall-clock timestamp sorting; record regressions. No new files, deletions or rename semantics. PSF license for CPython; per-document license declarations for BIPs. No source blobs redistributed.

Matched controls: Zstd independent snapshots versus R115 bounded one-hop anchors (unchanged thresholds, last four literal anchors, avoid reconstructing irrelevant historical frames). Both use R120 native full positional FTS5, identical atomic ledger/validity/stats, provenance rows and stored corpus manifest. Same source bytes, metadata, queries, append transaction policy and full synchronous WAL. All source/index/metadata bytes and WAL file size before checkpoint charged; final SQLite files VACUUMed. External receipt export bytes reported separately. Query plan selected from baseline native active snapshot; evaluate four commit-boundary cutoffs (deduplicate unchanged generation cutoffs). Independently rebuilt native active indexes; exact cross-policy receipt identity, source reads for every retained revision, one pinned-reader replay across later appends, fresh and reopen replay, native score/rank verification, ten process-death stages across both source policies. Randomized warm rank/receipt timing interleaved across policies; append timing separate build order. No cold device I/O, actual physical write amplification, semantic relevance or power loss claims.

This is an independent chronological evaluation of the strongest integrated source/archive contract, not another tuned Versions experiment. Do not assert generality if either dataset fails or savings disappear. Full origin manifest audited separately; rank receipt binds source SHA-256 and ordinal, not an authenticated Git metadata chain.

## Results

| Corpus | Documents | Revisions | Original source bytes | Snapshot archive B | Anchor archive B | Reduction |
|---|---:|---:|---:|---:|---:|---:|
| cpython | 80 | 355 | 15653966 | 9166848 | 5210112 | 43.16% |
| bips | 80 | 395 | 10814604 | 7589888 | 4780032 | 37.02% |

Both complete databases include the full positional native FTS5 index, version/source rows, Git origin rows, corpus metadata, validity intervals, active statistics and hash-chain rank ledger. No extra compact index is substituted. Snapshot baseline is independently compressed Zstandard level 6, not uncompressed text. No sampled paths disappeared at observed snapshots, and no selected committer timestamps regressed. CPython has 66 edited documents; BIPs has 80. Queries evaluated at complete observed Git snapshots: CPython generations 80,135,266,355; BIPs 80,187,333,395. The initial 80 versions are seeded from one actual baseline state, not reconstructed from their individual creation commits.

| Corpus | Policy | Source payload B | WAL file B before checkpoint | Append median us | Source lookup median us | Rank median us | Receipt median us |
|---|---|---:|---:|---:|---:|---:|---:|
| cpython | snapshot | 4406056 | 58969592 | 2005.949 | 144.189 | 100.066 | 1240.712 |
| cpython | bounded_anchor | 745283 | 54322232 | 2222.061 | 157.633 | 98.469 | 1220.470 |
| bips | snapshot | 3051292 | 63439792 | 1263.396 | 72.847 | 73.218 | 1043.347 |
| bips | bounded_anchor | 568414 | 59575232 | 1278.658 | 69.733 | 72.567 | 898.301 |

| Corpus | Anchor dependency depth 1 | Mean decoded bytes / requested source bytes | Max activated bytes / independent frame | Max decoded bytes / nonempty source |
|---|---:|---:|---:|---:|
| cpython | 275 | 1.8557 | 1.1583 | 2.0360 |
| bips | 314 | 1.8559 | 1.2077 | 2.0696 |

All 750 source revisions reconstructed under each policy (1,500 exact readbacks). Each corpus has 80 queries and four cutoffs: 320 exact native rank comparisons per policy per corpus (640 per policy combined), 3,378 ordered hit positions per policy across corpora, zero observed score error. Cross-policy receipt bodies and digests identical. Each policy per corpus passed 80 pinned-reader replays and 80 fresh historical replays, and 320 post-VACUUM reopen replays. Ten process-death stages per corpus (five per policy, 20 executions overall; repeated fixture, not 20 distinct fault mechanisms). Raw receipt exports not stored in measured archives: 397,017 B CPython and 410,807 B BIPs per policy. Source read timing measured once per revision interleaved across policies. Three randomized warm rank/receipt passes (960 samples per policy per corpus). No cold-cache or device I/O measurement. Both corpora built snapshot then anchor on separate CI jobs; append timing is exploratory and subject to order effects. Small rank/receipt timing differences are not evidence of speedup.

The anchor policy reduces compressed source payload by 83.09% in CPython and 81.37% in BIPs; integrated archive reductions are 43.16% and 37.02%. Aggregate decoded-source amplification rises to approximately 1.86x in both. Activated payload over all requests can be larger than snapshot payload even when storage is lower. The measured maxima respect the policy's 1.5x encoded activation and 2.5x decoded-byte bounds. WAL file sizes are pre-checkpoint allocated logical files, not device write traffic. No statistical claim of generalization from two corpora. Cohorts are baseline-sampled; survival filter excludes deletions but happened to exclude none here. Git first-parent snapshots are genuine repository states, not complete wall-clock edit histories across every branch. Corpus origin manifest is separately audited, not cryptographically committed by existing rank receipt. The native index is retained in both arms; no claim of improved native search algorithm.

## Reproduction

- CPython: [results and manifest](../../../experiments/round-129/results-cpython.json), manifest SHA-256 `b385e695dd75995df21ee467c3c2bec67415a27300446c0bffdc24c3e76eac83`.
- BIPs: [results and manifest](../../../experiments/round-129/results-bips.json), manifest SHA-256 `4108f00c68c7c62ca43e7d460f79ef137528eb2c956447e57354fb69a164239b`.
- Original-code CI above. Data source commits are pinned, source bytes are fetched from upstream at runtime, and source blobs are not committed to this repository. Query plans are included in results.

## Decision

Retain bounded-anchor + native full-detail FTS5 as the paper's main measured system, with compressed independent snapshots + identical FTS5/receipt metadata as its principal control. This is a successful integrated storage result on two independent text histories, not a new compression primitive or general IR improvement. Next: independent runner repetition, stronger source delta baseline (e.g., preceding-revision Zstd dictionary and bounded chain), append time versus history length, and adversarial review of existing temporal retrieval/provenance work. Avoid expanding into Uno until manuscript evaluation is complete.
