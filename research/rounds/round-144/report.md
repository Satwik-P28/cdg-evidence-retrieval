# R144 provenance-bound receipt v2

Status: implemented, execution pending.

Fix the confirmed R143 origin metadata commitment gap. Separate domain-separated SHA256 chain seeded by exact manifest bytes; each generation commits to canonical generation, article, ordinal, source SHA256, origin identifier, timestamp, blob SHA1 and rank prefix. SQLite AFTER INSERT ON rank_ledger trigger inserts provenance prefix in the same transaction as R137 ingestion. Writers register deterministic UDFs on their own connection. Missing prior state fails closed. No migration of legacy archives; new format.

Receipt v2 wraps the unchanged ranking body, manifest hash, provenance root and per-hit origin records. Replay checks the externally retained trusted receipt digest and independently recomputes the requested metadata prefix, verifies the stored chain, reissues historical ranking and verifies exact hit bytes including Git-style blob hash. Changing metadata even with internally recomputed roots cannot reproduce the old external commitment absent a hash collision. Does not authenticate the publisher, protect against loss/replacement of the external commitment, or verify every non-hit source frame on every replay. Full audit remains separate. O(c) prefix verification is an explicit cost, not a constant-time proof.

Nine negative tests (including non-hit origin mutation and forged recomputed chain), nine process-death stages with pinned readers and retries. Both nested NewsEdits cohorts; matched v1/v2 packed builds, identical source payload totals, rank bodies, fixed 16-query subset across four cutoffs, exact replays, full audits, storage and descriptive timing. Report overhead and negative results; no claim of power-loss durability or attack resistance beyond the stated commitment model.
## Initial execution failure and correction

Both jobs on e1d33f03 failed before acquisition because cdg_origin_entry was registered with arity 8 rather than the actual 9. Original run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45513228682. Corrected registration, added direct SQL/Python equivalence regression; retain all original adversarial tests and frozen experiment. No measurement yet.
