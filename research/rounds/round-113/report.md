# CDG Round 113: Source-only cost-aware archive layout under retrieval and revision tradeoffs

**Date:** November 23, 2026. **Status:** PASS. Both original SHA-locked QASPER CI runs completed successfully: first seven-policy exploratory baseline [45281936081](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45281936081), then 11-policy extended post-hoc falsification [45282426620](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45282426620). 25 deterministic planner tests passed. No novel performance superiority established.

## Research question

Can a fixed, source-only static planner select whole-paper, group-of-four and individually compressed original QASPER paragraph representations such that the physically persisted SQLite archive has favorable **actual** source read/decode and WAL update costs, without needing access history or evidence labels? This specifically follows R106's negative history-over-length controls, but does not attempt to predict source edit timestamps.

### Relation to prior art (critical)

1. Rong et al., ICDE 2024, **OREO**, prove guarantees for online data layout reorganization with unpredictable queries. Our algorithm is a simple static per-paper multi-choice knapsack, **not** OREO and has no worst-case guarantee: https://arxiv.org/abs/2405.04984 .
2. RocksDB integrated BlobDB and 2026 direct-write partitioned blob files demonstrate key/value separation and partitioned storage for read/write amplification; such techniques are prior art: https://rocksdb.org/blog/2026/06/20/blob-direct-write-partitioned-blob-files.html .
3. The 2024 PVLDB paper **Partition, Don't Sort!** demonstrates partition choice strongly affects compression in cloud ingestion: https://www.vldb.org/pvldb/vol17/p3456-hansert.pdf .
4. SQLite WAL bytes are *logical on-disk WAL file growth*, not SSD physical write traffic, and depend on page/transaction boundaries: https://www.sqlite.org/wal.html .

## Source-only planner, frozen before outcomes

- TRAIN-only 64-KiB Zstandard dictionary from original SHA-locked QASPER TRAIN; DEV articles only supply source bytes and paragraph boundaries, without QASPER questions or evidence labels for selection.
- For paper $p$ and layout $l$, exact compressed BLOB sizes and static uniform-paragraph read/rewrite proxies are measured by applying the same shared TRAIN dictionary and Zstd9 compressor. The total byte proxy is measured payload plus **32 bytes per compressed block and 56 bytes plus doc-ID length per original paragraph**. These are engineering assumptions, not calibrated or guaranteed SQLite page sizes.
- Block-oriented read proxy: $R_{pl}=\sum_{b\in p}|b|\operatorname{rawBytes}(b)$ where $|b|$ is paragraph count, and write proxy $W_{pl}=\sum_{b\in p}|b|\operatorname{compressedBytes}(b)$, assuming uniform independent paragraph requests and edits. Actual QASPER requests and edit hotspots are withheld from layout selection.
- Balanced score relative to all-paper uses $0.5(R_{p,\mathrm{paper}}-R_{pl})/\sum R_{q,\mathrm{paper}} + 0.5(W_{p,\mathrm{paper}}-W_{pl})/\sum W_{q,\mathrm{paper}}$. Exact dynamic programming on **upward-rounded 128-byte proxy increments** selects the best of three layouts per paper under 35% or 65% of the all-individual predicted extra proxy bytes. This is exact only for the quantized additive proxy optimization, not for physical SQLite pages.
- Reference arms: all-paper, all-group4, all-individual, length-only and stable-hash selections with a matching 35% proxy budget.

## Falsification protocol

Compare all seven archives under physically measured persistence bytes, verified original top-ten QASPER source inflation, and actual SQLite WAL growth across 24 independent fixed synthetic edits. Every original source and document ranking must match; after updates, all live source byte receipts and rankings must match an independently rebuilt full-text index.

**Predeclared decision gate:** The planner is worth further work only if, at comparable actual SQLite bytes, it improves actual original-QASPER read amplification without an unacceptable artificial update/WAL penalty. A planner solution at a larger physical archive size does not automatically beat a smaller baseline. Failure to fit 8MiB must be reported; a proxy budget is NOT a guaranteed file-size constraint. Use observed Pareto non-dominance, not an arbitrary scalar ranking of dissimilar metrics.

## First seven-arm original-source results (CI 45281936081)

All 281 DEV articles, 13,266 original paragraphs, 1,005 QASPER questions and 24 artificial edit transactions are checked per arm. Read amplification and WAL sizes are measured, not predicted. Original FTS5 ranks and post-revision source reconstruction match exactly.

| Archive policy | Actual source+FTS SQLite bytes | Original-question top10 decoded byte amplification | 24-edit WAL appended bytes | Strict 8MiB fit? |
|---|---:|---:|---:|---|
| all_paper | 7,831,552 | 4.231430x | 5,088,232 | Yes |
| all_group4 | 8,413,184 | 2.222632x | 4,696,832 | No |
| all_individual | 8,470,528 | 1.000000x | 4,577,352 | No |
| length_budget_35 | 8,196,096 | 2.630215x | 4,865,752 | Yes |
| hash_budget_35 | 8,093,696 | 2.877715x | 4,985,232 | Yes |
| planner_balanced_35 | 8,409,088 | 2.283562x | 4,700,952 | **No** |
| planner_balanced_65 | 8,404,992 | 1.497650x | 4,659,752 | **No** |

R113's observed physical 8MiB budget **invalidates both initial planner arms**, even though their proxy budgets were feasible. The 65% planner shows an interesting but limited three-dimensional Pareto result versus `all_group4`: 8,192 fewer SQLite bytes, 32.6% fewer QASPER source decode bytes and 37,080 fewer WAL bytes. This is not an across-baseline or physical-budget victory. `all_individual` still improves read/WAL while costing more physical bytes. The planner used the original DEV source bytes, and the same QASPER DEV has been used repeatedly in prior rounds, so treat this as exploratory rather than independent publication validation.

## Second original-source CI: four extra exploratory controls

**After inspecting the seven-arm run**, we added R106's existing 50/25 paper-length/hash policies and two extra lower proxy budgets for the planner. This is a post-hoc sensitivity study, not a new preregistered primary hypothesis. All 11 policies were evaluated on the same SHA-locked original DEV, same 1,005 questions, and same 24 artificial edits, with all original/source and post-edit FTS5 differential checks passing. Full data in `experiments/round-113/results-eleven-arm.json`.

| Additional arm | Physical source+FTS5 bytes | Top10 decoded-byte amplification | Synthetic 24-edit WAL appended bytes | Strict 8MiB fit? |
|---|---:|---:|---:|---|
| length_50_25 (established R106 control) | 8,429,568 | 1.683641x | 4,647,392 | No |
| hash_50_25 (established R106 control) | 8,318,976 | 1.99361x | 4,680,352 | Yes |
| planner_balanced_25 (post-hoc proxy fraction) | 8,249,344 | 2.720257x | 4,845,152 | Yes |
| planner_balanced_30 (post-hoc proxy fraction) | 8,339,456 | 2.478228x | 4,696,832 | Yes |

The exact unrounded top-ten amplification values for all 11 arms are in the JSON. The **dominance falsifier is unequivocal**: `hash_50_25` uses **20,480 fewer physical bytes**, **fewer decoded source bytes**, and **16,480 fewer WAL bytes** than `planner_balanced_30`. Thus a stable-hash source placement rule strictly dominates the best *initially suggested under-8MiB* high-coverage balanced planner configuration under all three measured resources. The 25% planner is not strictly dominated across all three: compared with `length_budget_35`, its WAL is slightly lower but its decode amplification and file bytes are worse.

The source-only 65% planner remains a distinct non-dominated storage/read/WAL point but **exceeds 8 MiB**; it therefore does not establish superiority at the fixed budget. The original seven-arm and extended 11-arm runner results agree on each common policy. The 65% plan's smaller physical file size versus 35% demonstrates that SQLite page allocation and compression-layout interactions defeat simple monotone assumptions about the proxy fraction. A binary search on proxy fractions cannot be advertised as a guaranteed physical-budget solver.

## Final disposition, next falsification

**REJECT the present source-only balanced knapsack planner as a general improvement.** The optimized proxy is not a robust predictor of physical SQLite layout cost or original-query read savings, and a conventional stable-hash layout wins in one concrete, relevant 8MiB comparison. No new algorithmic result is ready for a main-track paper. Keep this as a transparent negative-control experiment within the multi-objective evidence-archive line, not as a standalone compression breakthrough.

A stronger follow-up should use an **actual physical-size feasibility oracle** (build and measure SQLite archives before observing queries), dynamic migration cost that includes snapshot safety, and genuinely time-stamped independent edit/read histories. If the chosen physical layout cannot beat appropriate static controls on independent traces, stop optimizing this branch.

Wikimedia publishes per-article pageview time series and time-stamped revision histories, which can offer a better externally validated stress setting. They do *not* supply paragraph-level RAG query logs, so using them would evaluate article-level storage access and revisions only. Important direct prior art: Verma, Setia and Demartini's **WikECD** (ACM Transactions on the Web, 2026) already studies versioned Wikipedia compression and random-revision retrieval. OReO (ICDE 2024), RocksDB (2026 partitioned blob files), WikECD and baseline static grouping must all be considered for a true novelty claim.

## Scientific limitations

- Offline per-paper layout optimization and code/metadata cost models have substantial prior art and are not independently sufficient for a systems novelty claim.
- QASPER DEV questions are not used to choose layouts, but the archive builder sees original DEV papers; QASPER DEV has also been repeatedly studied in prior CDG rounds.
- No human revision history exists in QASPER. 24 deterministic revisions are an artificial stress scenario, not a stochastic population of real-world editing.
- The planner does not migrate blocks while readers have open snapshots. `build_archive` creates a new archive per static arm.
- Source receipts and unchanged BM25 rankings do not establish a new evidence retrieval or generated answer-level improvement.
- No native FTS5 index rewriting, model weights/vector index bytes, cold-SSD measurements or other independent dataset available in this round.