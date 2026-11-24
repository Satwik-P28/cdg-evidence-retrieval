# R142: native Git pack at NewsEdits scale

Status: implemented, measurements pending.

Extend R134/R137/R138 to frozen nested AP cohorts (10,009 and 74,364 derived revisions). Reproduce exact source manifest, query hash, snapshot and CDG payload and complete archive sizes from R138. Native Git hash-object --stdin-paths batches real blob writes; use R134 actual pack-objects, compression 9, window 10, depths 1/8/50, one thread, no reuse and path hints. Permit offline cross-document and future-object delta selection and exact-object deduplication. Charge .pack/.idx/sidecars and compacted identical retrieval/provenance database with per-revision SHA1 pointer; exclude scratch loose objects and generic empty repo scaffolding. Record exact duplicates.

Additional layout controls coalesce identical encoded frames for both snapshot and CDG, retaining per-revision dependency metadata and byte-for-byte frame equality checks. They are finalized read-only archives, not valid append-mode layouts (offsets need not form a contiguous generation sequence); do not use transactional writer or contiguous audit on them. Their reconstruction cost metrics must match the original arms exactly. Charge all pointer metadata, header, state and frame bytes.

All seven arms use identical historical positional ranking, native active snapshot oracles, receipt bodies, and exact source bytes. Randomized source read order fixed across arms; timing descriptive with differing IPC. Validate each source read and 256 rank checks per arm. No claim of equal incremental/crash guarantees for Git or coalesced representations. No semantic QA result. Report losses rather than tune post hoc.

## Verified results

R142 both jobs passed on e3258cb7 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45511038427). Full AP has 41,282 unique source objects, 33,082 duplicate revision occurrences. Transactional CDG 223,142,857 B; coalesced CDG 215,190,054 B; coalesced snapshots 240,460,559 B; Git depth-one 214,888,975 B. Coalesced CDG premium 0.1401%, transactional CDG premium 3.84%; mean decode 1.64283 vs Git1 1.39757; maximum decode 2.48765 vs 32.58966 (92.37% lower), maximum activation 1.5 vs 19.10818. All seven arms on both nested cohorts: 590,611 exact readbacks, 3,584 ranking comparisons, zero observed score error. Coalescing is finalized read-only, not transactional. Git average logical decoding wins; no CPU or I/O superiority claim.

| Revisions | Policy | Complete B | Mean decode | Max decode | Max activation |
|---:|---|---:|---:|---:|---:|
| 74364 | snapshot | 312521715 | 1.0000 | 1.0000 | 1.0000 |
| 74364 | bounded_anchor | 223142857 | 1.6428 | 2.4877 | 1.5000 |
| 74364 | snapshot_coalesced | 240460559 | 1.0000 | 1.0000 | 1.0000 |
| 74364 | bounded_anchor_coalesced | 215190054 | 1.6428 | 2.4877 | 1.5000 |
| 74364 | git_pack_depth1 | 214888975 | 1.3976 | 32.5897 | 19.1082 |
| 74364 | git_pack_depth8 | 215040168 | 1.4361 | 22.4914 | 12.8679 |
| 74364 | git_pack_depth50 | 214965895 | 1.4584 | 44.3464 | 20.5990 |
| 10009 | snapshot | 42846800 | 1.0000 | 1.0000 | 1.0000 |
| 10009 | bounded_anchor | 30691764 | 1.6459 | 2.4826 | 1.4983 |
| 10009 | snapshot_coalesced | 33415658 | 1.0000 | 1.0000 | 1.0000 |
| 10009 | bounded_anchor_coalesced | 29820949 | 1.6459 | 2.4826 | 1.4983 |
| 10009 | git_pack_depth1 | 29657017 | 1.4379 | 14.4250 | 9.9435 |
| 10009 | git_pack_depth8 | 29566234 | 1.5139 | 30.1449 | 14.9159 |
| 10009 | git_pack_depth50 | 29557987 | 1.5352 | 38.9305 | 14.9159 |
