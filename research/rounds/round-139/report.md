# R139: retrieval-conditioned leaf materialization

Status: both jobs passed; negative heldout result.

Prior work already studies workload-aware reconstruction/storage optimization (Bhattacherjee et al., PVLDB 2015, https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/). We do not claim that the objective or frequency-based placement is novel. Test whether actual historical retrieval hits (rather than synthetic Zipf access frequencies) provide transferable signal for bounded one-hop archive materialization.

A stored delta is a leaf under CDG's literal-parent-only contract. Replacing that leaf with its exact independently compressed frame changes no other dependencies, preserves source identity, and keeps both 2.5x decoded and 1.5x activated bounds (literal ratios 1). Its compacted payload cost is full frame minus delta frame, and its saved logical decode work per hit equals parent raw bytes. A budgeted selection has additive gains under the no-cache workload model; density greedy is a heuristic, and the fractional relaxation gives an upper bound. The source payload counterfactual excludes page-layout, rewrite and maintenance costs. This is not a new physical archive or online repacking implementation.

Use the two R138 frozen cohorts; re-encode all source frames and check payload identity totals. Select disjoint single-term training and test probes by fixed salted hash order, train only at first two cutoffs. Eligible leaves must exist by second cutoff. Evaluate heldout terms at second, third and final cutoffs. Budgets 1, 5, 10, 50 basis points of prefix source payload. Compare uniform savings density, recent, fixed-seed random, LFU, query frequency-weighted density and article-frequency-weighted density. Report both individual cutoffs and aggregate heldout costs; heldout fractional oracle is only a hindsight upper bound. No retuning if negative. Every selected full frame and every delta reconstructs exactly. No external workload labels, model responses or latency claims.

## Verified results

Both original-code jobs passed (029cabdf, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45503944736). Query-density materialization does not transfer reliably: on the full 74,364-revision cohort, at 50 bp of prefix payload (166,337 B budget), training avoided 403,380 decoded bytes, heldout avoided 5,790 of 4,999,880 bytes (0.116%); LFU saved 12,867 (0.257%), uniform saved 12,735 (0.255%). Fractional hindsight upper bound 818,703 bytes (16.37%) is not achieved or necessarily feasible as an integer allocation. At 1, 5 and 10 bp query-density saves zero heldout bytes; on nested 10,009-revision cohort it saves zero at every budget. Sparse disjoint lexical probes limit generalization; results do not establish that real access prediction is impossible. No physical rewrite or online performance claim. Exclude materialization from main contribution, retain negative result.

| Revisions | Budget bp | Policy | Extra payload B | Train saved decode B | Heldout saved decode B | Hindsight fractional upper bound B |
|---:|---:|---|---:|---:|---:|---:|
| 74364 | 1 | uniform_density | 3280 | 0 | 0 | 39707.18 |
| 74364 | 1 | recent | 3242 | 0 | 0 | 39707.18 |
| 74364 | 1 | random | 3311 | 0 | 0 | 39707.18 |
| 74364 | 1 | lfu | 3280 | 12571 | 0 | 39707.18 |
| 74364 | 1 | query_density | 3203 | 12818 | 0 | 39707.18 |
| 74364 | 1 | article_density | 3258 | 10268 | 0 | 39707.18 |
| 74364 | 5 | uniform_density | 16556 | 0 | 0 | 150552.55 |
| 74364 | 5 | recent | 16613 | 0 | 0 | 150552.55 |
| 74364 | 5 | random | 16569 | 0 | 0 | 150552.55 |
| 74364 | 5 | lfu | 16628 | 41998 | 0 | 150552.55 |
| 74364 | 5 | query_density | 16485 | 53899 | 0 | 150552.55 |
| 74364 | 5 | article_density | 16566 | 35509 | 0 | 150552.55 |
| 74364 | 10 | uniform_density | 33193 | 0 | 12735 | 271261.71 |
| 74364 | 10 | recent | 33240 | 0 | 0 | 271261.71 |
| 74364 | 10 | random | 33221 | 0 | 0 | 271261.71 |
| 74364 | 10 | lfu | 33190 | 79431 | 12867 | 271261.71 |
| 74364 | 10 | query_density | 33206 | 97684 | 0 | 271261.71 |
| 74364 | 10 | article_density | 33171 | 69666 | 0 | 271261.71 |
| 74364 | 50 | uniform_density | 166324 | 869 | 12735 | 818703.13 |
| 74364 | 50 | recent | 166238 | 0 | 0 | 818703.13 |
| 74364 | 50 | random | 166269 | 23115 | 0 | 818703.13 |
| 74364 | 50 | lfu | 166308 | 379383 | 12867 | 818703.13 |
| 74364 | 50 | query_density | 166236 | 403380 | 5790 | 818703.13 |
| 74364 | 50 | article_density | 166221 | 240190 | 5790 | 818703.13 |
| 10009 | 1 | uniform_density | 380 | 0 | 0 | 6441.85 |
| 10009 | 1 | recent | 319 | 0 | 862 | 6441.85 |
| 10009 | 1 | random | 420 | 0 | 0 | 6441.85 |
| 10009 | 1 | lfu | 438 | 1860 | 0 | 6441.85 |
| 10009 | 1 | query_density | 438 | 1860 | 0 | 6441.85 |
| 10009 | 1 | article_density | 323 | 0 | 0 | 6441.85 |
| 10009 | 5 | uniform_density | 2192 | 0 | 0 | 29711.08 |
| 10009 | 5 | recent | 2121 | 0 | 862 | 29711.08 |
| 10009 | 5 | random | 2220 | 0 | 0 | 29711.08 |
| 10009 | 5 | lfu | 2215 | 13782 | 0 | 29711.08 |
| 10009 | 5 | query_density | 2215 | 13782 | 0 | 29711.08 |
| 10009 | 5 | article_density | 2227 | 4683 | 0 | 29711.08 |
| 10009 | 10 | uniform_density | 4425 | 0 | 0 | 56019.62 |
| 10009 | 10 | recent | 4383 | 470 | 4044 | 56019.62 |
| 10009 | 10 | random | 4399 | 0 | 0 | 56019.62 |
| 10009 | 10 | lfu | 4351 | 23858 | 0 | 56019.62 |
| 10009 | 10 | query_density | 4405 | 24954 | 0 | 56019.62 |
| 10009 | 10 | article_density | 4435 | 15323 | 0 | 56019.62 |
| 10009 | 50 | uniform_density | 22162 | 7550 | 12767 | 195151.27 |
| 10009 | 50 | recent | 22180 | 11431 | 10566 | 195151.27 |
| 10009 | 50 | random | 22140 | 5640 | 0 | 195151.27 |
| 10009 | 50 | lfu | 22194 | 90674 | 13155 | 195151.27 |
| 10009 | 50 | query_density | 22202 | 97977 | 0 | 195151.27 |
| 10009 | 50 | article_density | 22200 | 61179 | 0 | 195151.27 |
