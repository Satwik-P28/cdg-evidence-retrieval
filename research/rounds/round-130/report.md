# R130: matched delta baseline protocol

Status: implementation staged; no measured R130 result yet.

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
