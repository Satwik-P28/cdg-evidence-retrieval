# R148: final feature-matched control

Status: both original-code jobs passed.

R147's 29.50% complete-archive saving versus R138 snapshots confounds compression and exact-frame deduplication; the v2 origin ledger is also absent in the snapshot and Git controls. Compare snapshot and bounded-anchor encodings under the exact same integrated R147 writer, frame catalog, origin trigger, manifest, index, query plan and receipt protocol. Both nested frozen AP cohorts. All 64 v2 receipts must have identical ordered digest fingerprints across arms; every revision must reconstruct, both bounds must hold, all 256 native rank checks must agree. Compare complete finalized physical bytes including catalog, ledger and sidecar. R147 bounded-anchor deterministic size/cost must reproduce; R142 coalesced payload and frame count must match each arm. Report storage reduction against the matched snapshot control, not a new algorithm. Descriptive sequential-build timing only. Git is an external finalized control without v2 provenance or update parity. No new system features.

## Verified results

Both R148 jobs passed on 3860a079 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45695155698). Fully matched v2 transactional deduplicated snapshots vs bounded anchors: 34,087,402 -> 30,525,461 B (10.45%) and 245,412,623 -> 220,334,630 B (10.22%). Full payload 77,308,655 -> 52,029,958 B. Same ordered receipt commitment fingerprints; 168,746 exact source reads, 1,024 rank comparisons, 256 batch receipt replays, zero observed score error. Full matched median append 745.8 vs 868.9 us, descriptive. This supersedes unmatched snapshot reduction as the incremental encoding effect. Both cohorts nested; Git lacks v2/update parity.
