# R143 adversarial transactional archive validation

Status: implemented, pending hosted execution.

Challenge R137 with four/eight simultaneous cooperating writer processes, one deliberately exiting at partial write, fsync-complete, metadata-complete or post-commit, and a reader holding an old SQLite snapshot. All acknowledged operations must appear exactly once in generation order, actual committed source contents must match independently generated inputs, logical bounds must hold, and final ranks must equal rebuilt native active-snapshot indexes. Two fixed seeds; actual process scheduling uncontrolled. Six additional cases: short positive writes, ENOSPC, EIO, fsync failure, exception before commit and exception after commit. Test reconciliation and retry without deleting committed bytes. These are Python-level injections, not SQLite VFS/power-loss simulations.

Receipt negative controls: flip frame bytes, pointer outside prefix, pointer to wrong source, change source digest, change origin commit/timestamp. The R137 v1 receipt commits to source digests/rank ledger, but the origin row is not included in that commitment. Expect the first four mutations to fail replay and origin mutation to reproduce the old receipt; preserve this known gap, not a passing tamper-resistance claim. Future v2 should bind manifest and origin-prefix commitment in the same transaction, with trusted external receipt root and explicit validation. No assertion of authenticated publisher provenance or defense against fully malicious writers. 


## Verified results

R143 both stress jobs passed on 24b5114b (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45511276311). 1,280 acknowledged operations across eight concurrent process-death cases, 1,290 committed source checks, 168 pinned-reader checks, 96 native rank comparisons, 12 injected failure cases. All expected commit visibility and retry conditions pass. Eight source/pointer corruption cases rejected; two origin-metadata mutations leave v1 receipt unchanged, confirming known provenance-binding gap. Python fault injection, not VFS or power-loss validation.
