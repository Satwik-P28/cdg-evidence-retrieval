# R130: matched delta baseline protocol

Status: completed; both final corpus jobs passed.

Parent: R129, main 5d2b8b783375c20cf05f68f00fce343edcb99175. Reuse its exact upstream pins, cohort salt, path selection, query plan and four cutoffs. The cohorts are independent of the original Wikipedia development set, but are now reused validation cohorts, not fresh held-out data.

## Policies fixed before execution
- snapshot: independent Zstd frames.
- prev1/2/4/8: immediate-predecessor dictionary when frame savings are positive and depth limit permits; otherwise independent frame.
- anchor4/8: latest literal anchor within four/eight ordinals when frame savings are positive (R115 policy, not a strict periodic schedule).
- prev_budget: immediate predecessor only if it is literal, with the exact R129 activation, decode, and frame-saving thresholds.
- bounded_anchor: unchanged R129 search over up to four preceding literal anchors.

Identical source frame schema, positional FTS, native active BM25 oracle, historical ledger, Git provenance, evidence receipts, durability and compaction. Recover only candidates needed by the respective policy during append; no future revision data or workload-derived tuning. All exact source reads, receipt equality, pinned/reopen checks and process-death stages are required for every arm. Same Zstd level and dictionary encoder.

Report complete SQLite bytes, source payload, depth histogram, logical activated bytes and decoded bytes, maximum per-source ratios, descriptive append/read/rank/receipt timings. Pareto membership uses five deterministic objectives: complete archive bytes, aggregate decoded amplification, maximum decoded ratio, maximum activated ratio, maximum dependency depth. Strict dominance requires no worse on all and better on at least one. Do not remove dominated CDG points. Timing is not a deterministic Pareto objective. No physical I/O or actual workload claim.

## Prior-art warning
WikECD (https://doi.org/10.1145/3787449) already uses dynamic anchor selection and revision retrieval; Principles of Dataset Versioning (https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/) formalizes storage/recreation tradeoffs. The proposed bounds are specific to this encoder and retrieval contract, not a claim to invent delta compression or budget-aware versioning. These controls are not full external system reproductions. R131 should include a broader codec and budget sweep, and R132 should include repeated independent runners and scaling.

## Interpretation gate
Compare bounded_anchor against prev_budget to isolate multi-anchor search, and against all depth-one arms to quantify costs. If no advantage survives matched budgets, narrow the paper to a systems evaluation with negative findings. Do not cite R130 results until both corpus jobs complete and the manifests match R129.

## Results

Both final jobs passed on commit a327ad56d530968f7732d30b7f74a3e9b9c99476, run https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45493072346. Exact R129 manifests and query plans matched. Across nine arms, 6750 source readbacks, 5760 historical ranking comparisons, 90 process-death stage checks, zero observed rank-score error. CDG is nondominated on both corpora using the five declared objectives; it is the smallest of the tested one-hop policies. The depth-8 chains are smaller by 57,344 B (CPython) and 69,632 B (BIPs); CDG incurs 1.11%/1.48% more archive bytes but 53.93%/53.79% less aggregate decoded work. Compared to the matched-budget immediate predecessor, CDG reduces archive size by 24.29%/19.57% at higher aggregate decoded work. Compared with anchor8 the reduction is only 1.32%/1.44%. Neither general compression superiority nor timing superiority follows. The R130 cohorts are reused validation, and depth-8 may be preferable for storage-only workloads.

| Corpus | Policy | Archive B | Payload B | Mean decode ratio | Max decode ratio | Max activation ratio | Depth |
|---|---|---:|---:|---:|---:|---:|---:|
| bips | prev_budget | 5943296 | 1652336 | 1.4692 | 2.1435 | 1.2024 | 1 |
| bips | prev1 | 5943296 | 1650415 | 1.4700 | 2.2849 | 1.6256 | 1 |
| bips | snapshot | 7589888 | 3051292 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | prev8 | 4710400 | 610268 | 4.0162 | 9.4258 | 1.6898 | 8 |
| bips | prev4 | 4894720 | 771101 | 2.7875 | 5.8305 | 1.6464 | 4 |
| bips | anchor4 | 4952064 | 794612 | 1.7600 | 2.2851 | 1.6263 | 1 |
| bips | prev2 | 5365760 | 1175193 | 1.9074 | 3.1263 | 1.2519 | 2 |
| bips | anchor8 | 4849664 | 672462 | 1.8119 | 2.2992 | 1.6530 | 1 |
| bips | bounded_anchor | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| cpython | prev_budget | 6881280 | 2357525 | 1.4681 | 2.0363 | 1.0837 | 1 |
| cpython | prev1 | 6881280 | 2357525 | 1.4681 | 2.0363 | 1.0837 | 1 |
| cpython | snapshot | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | prev8 | 5152768 | 804822 | 4.0278 | 8.9986 | 1.2038 | 8 |
| cpython | prev4 | 5521408 | 1139618 | 2.7395 | 5.0647 | 1.2038 | 4 |
| cpython | anchor4 | 5586944 | 1169022 | 1.7427 | 2.0360 | 1.0961 | 1 |
| cpython | prev2 | 6123520 | 1689774 | 1.9029 | 3.0446 | 1.1059 | 2 |
| cpython | anchor8 | 5279744 | 868378 | 1.8148 | 2.0360 | 1.1523 | 1 |
| cpython | bounded_anchor | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
