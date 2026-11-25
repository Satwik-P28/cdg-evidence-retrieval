# R144 provenance-bound receipt v2

Status: implemented, execution pending.

Fix the confirmed R143 origin metadata commitment gap. Separate domain-separated SHA256 chain seeded by exact manifest bytes; each generation commits to canonical generation, article, ordinal, source SHA256, origin identifier, timestamp, blob SHA1 and rank prefix. SQLite AFTER INSERT ON rank_ledger trigger inserts provenance prefix in the same transaction as R137 ingestion. Writers register deterministic UDFs on their own connection. Missing prior state fails closed. No migration of legacy archives; new format.

Receipt v2 wraps the unchanged ranking body, manifest hash, provenance root and per-hit origin records. Replay checks the externally retained trusted receipt digest and independently recomputes the requested metadata prefix, verifies the stored chain, reissues historical ranking and verifies exact hit bytes including Git-style blob hash. Changing metadata even with internally recomputed roots cannot reproduce the old external commitment absent a hash collision. Does not authenticate the publisher, protect against loss/replacement of the external commitment, or verify every non-hit source frame on every replay. Full audit remains separate. O(c) prefix verification is an explicit cost, not a constant-time proof.

Nine negative tests (including non-hit origin mutation and forged recomputed chain), nine process-death stages with pinned readers and retries. Both nested NewsEdits cohorts; matched v1/v2 packed builds, identical source payload totals, rank bodies, fixed 16-query subset across four cutoffs, exact replays, full audits, storage and descriptive timing. Report overhead and negative results; no claim of power-loss durability or attack resistance beyond the stated commitment model.
## Initial execution failure and correction

Both jobs on e1d33f03 failed before acquisition because cdg_origin_entry was registered with arity 8 rather than the actual 9. Original run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45513228682. Corrected registration, added direct SQL/Python equivalence regression; retain all original adversarial tests and frozen experiment. No measurement yet.


## Verified results

Corrected R144 commit 0e4ce97d passed both jobs (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45568478507). 19 unit tests per job: nine mutation cases, nine process-death stages, SQL UDF regression. Both v1/v2 arms on both nested AP cohorts: 256 historical ranking/replay checks, zero observed score error, 168,746 audited source occurrences (one complete audit per arm/cohort, repeated audits not counted). Identical compressed payloads. Full AP v2 adds 3,080,192 B (1.38%) and 5.11% median append latency in this run, but median replay rises from 45.217 to 393.885 ms (8.71x), p95 49.850 to 626.075 ms. Linear metadata-prefix scan is expensive. V2 binds manifest and origin rows against a trusted external digest; no publisher authentication or full nonhit-source verification per replay. Timings descriptive, sequential builds.

| Revisions | Receipt | Complete archive B | Append median us | Replay median us | Replay p95 us |
|---:|---|---:|---:|---:|---:|
| 74364 | v1 | 223142857 | 1093.43 | 45217.02 | 49850.16 |
| 74364 | v2 | 226223049 | 1149.30 | 393884.73 | 626075.08 |
| 10009 | v1 | 30691764 | 1028.61 | 6142.74 | 7009.25 |
| 10009 | v2 | 31109556 | 1053.82 | 47086.75 | 74877.05 |
