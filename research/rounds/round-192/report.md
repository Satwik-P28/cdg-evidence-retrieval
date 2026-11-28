# R192: shared-window-aware marginal path selection

R191 independent local synthetic results show the per-child token cost proxy can select chains that increase total patch storage because it ignores already-shared rows. Start with all direct correction windows, maintain exact window reference counts across the finalized archive, update counts as each operator is selected in increasing content ID order. For candidate replacement z of direct m, estimate difference in total distinct window cost and use mapping cost, plus link overhead. Quotient model charges len(w)+6 for each distinct window and 4 per use; adaptive model charges min(n*(len(w)+6),len(w)+6+6*n) for n uses, proxy only. Neither is physical page optimization; no claim of globally optimal path selection. Keep same depth and cumulative path cost limits as R191. Real hosted comparison: positional, signed, local path4, quotient4, adaptive4. All source/rank/DF/TF checks, physical archive sizes, separate preparation, same R188 query plan. No RH theorem transfer.

Local executed quotient-only test, same two seeds and four synthetic regimes as R191, 65536 additional exact checks, all passed. Total R191+R192 local checks 196608. Patch-only SQLite full quotient storage (not adaptive writer): 

| Regime (both seeds) | Direct B | Local path4 B | Marginal path4 B |
|---|---:|---:|---:|
| Accumulating |81920|69632|69632|
| Localized |49152|53248|53248|
| Revert |36864|40960|40960|
| Scattered |155648|172032|155648|

Scattered active correction expansions local/marginal: 960/758 (191), 861/705 (192). Marginal selects vector difference for 12/13 children, local selects zero. No runtime measurement. Synthetic revert arm has explicit 4KiB empty parent table, real builder avoids creating an empty table. No claim of universal improvement. R192 local adaptive model untested, hosted comparison pending. Actual local scripts/results in accompanying R191-R192 zip. R191 hosted 46180974772 static checks and unit tests passed all jobs, CLARK corpus step passed; AP pending at report time. 
