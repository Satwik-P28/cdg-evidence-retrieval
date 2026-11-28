# R198-R199: persistent adaptive search, transfer and finite-grid oracle

Actual local execution on Python standard library source. R197 prior 81 unique development trials, R198 three new file-disjoint cohorts (24 source files each, 16 development/8 holdout, 240/120 synthetic known-file queries per cohort). Same 144 configurations, 75% physical archive caps relative to complete individual baseline per cohort, fixed 2048 context and 4096 decode bytes. Four policies, three seeds, 16 trials each. 576 logical trials, 192 unique archive builds, 384 reused measurements, 221792 source verification checks in unique development builds. All checks passed. Random forests with 32 trees; fixed historical blend weight 8/(8+n); transfer fixed R197 prior; continual pools completed development measurements from all policies on earlier cohorts, not an isolated lifelong learner. No holdout labels enter fitting. Holdout feasibility repair uses separate size-only builds with no queries; all selected configurations happened to fit without repair. File identities disjoint but same stdlib distribution. Seeds reuse queries; 1080 aggregate holdout evaluations, only 360 distinct query instances.

| policy | development hits (aggregate /2160) | holdout hits /1080 | feasible development trials /144 | holdout wins/ties/losses vs random |
|---|---:|---:|---:|---|
| random |1831|887|118|0/9/0|
| cold RF |1856|890|81|4/3/2|
| fixed transfer |1860|908|79|4/5/0|
| continual |1860|906|90|4/4/1|

R199 exhaustive development-only grid: 432 configurations across 3 cohorts, 240 new builds and 192 reused; 484754 total source checks across all unique development builds. Oracle maximum feasible hit counts 207,210,203 (240 each). Random finds optimal hit count 6/9, cold7/9, transfer9/9, continual9/9. Total regrets 29,4,0,0. Search 16/144 configurations; historical measurement and training costs not included. Replay after integrating oracle into same script: all 432 results reused, zero new builds, exact cohort outcome equality. Persistent cache keyed by corpus/query/budget/evaluator identity, not a proof against all dependency changes. No independent relevance labels or QASPER ML result; no novelty or broad generalization claim. Transfer explores more infeasible configurations than random; next experiment should test feasibility-aware acquisition and corpus-conditioned historical weighting, then real train/dev QASPER integration.

## Artifact provenance
Exact executed local code and raw records in CDG-R198-R199-adaptive-harness.zip supplied in conversation. Local artifacts not copied into this repository commit; report preserves digest references. 
- cdg_adaptive_test.py SHA256 08d9692efae6c718483f1fde67c7f35d4ba8880be1ec80d28dfbee4ea44407a7
- cdg_r197.json SHA256 cd00d1471e989b3d254983b2b56ebb136816422b2672b41f51368f165a81e97d
- cdg_r198.json SHA256 c0b935e563b56cf7283457419b09979113351cf16b5ee6f81a249db7cbe28ff0
- cdg_r199_oracle.json SHA256 42306e850fc67f436ccd957f00cd4647b2dab9110c43c6b9c748b6256a535ed5
- cdg_trials.sqlite SHA256 fd8a09b1c63665dd1bd8f7da1af4c78228a9a886aa8d5204779d2765e706791c

R196 hosted QASPER raw results preserved at parent commit 3e1b366e. Compact R102 independent baseline remains primary. R198-R199 is exploratory search allocation, not an improvement in generated-answer quality.
