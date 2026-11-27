# R166: signed edit-window quotient and adaptive halo identity

Status: implemented; hosted validation pending. Based on R165 commit b32dca5ea6b077dd63b3f39d56ecc7fddac96bf8. R165 completed all three jobs (run 45896704596), 9,216 ranking checks and 342,136 source reconstruction checks over four policies. AP 74,364 revisions: positional archive 148459520 bytes; aligned multi 138670080; independent multi 136331264. Independent FTS 61104128 vs 73351168 bytes; median query 517.055 vs 571.161 us; p95 5484.744 vs 6968.072 us; median preparation 21907.4125 vs 14069.036 us. CLARK admits zero deltas and adds 20480 bytes. Source alignment alone has not won.

## Mechanism
For child c, define m(c,w)=number of positive windows equal to token sequence w minus number of negative windows equal to w. Then TF(c,p)=TF(base(c),p)+sum_w m(c,w) TF(w,p). This is exact by rearrangement of a finite sum, not a hash-based approximation. Discard zero coefficients and empty windows; intern complete token tuples across all children in a single FTS table. Persist signed coefficients in a WITHOUT ROWID mapping and build an active-only reverse mapping per snapshot. Query scans unique matching windows and expands signed multiplicities; no source decoding. Identical anchor candidates and admission cost in each matched pair, checked by statistics. Storage includes mapping pages. No change in source archive.

Adaptive halo identity: use halo m-1 and group edit regions separated by fewer than 2(m-1) equal tokens for maximum phrase length m. Shorter query-specific windows can reduce token processing, but storing separate per-length indexes is not assumed beneficial. This round tests the identity separately and retains a single L=8 persistent index. No claim of arbitrary-length phrases.

Controls: original positional, aligned single, aligned multi, independent multi, aligned quotient multi, independent quotient multi; AP 10k/74k and CLARK. Compare complete archive, FTS bytes, delta mappings, distinct window count and tokens, coefficient L1, expansions, preparation and warm query latency. Native snapshot oracle, byte-exact source checks, tests for identical window reuse, signed cancellation, adaptive halo and overlap. No performance claim until hosted results. The first iteration deliberately reuses the R165 workflow on a separate compatible branch; output JSON round=166 distinguishes results.

Prior art: He/Suel positional fragment indexing https://research.engineering.nyu.edu/~suel/papers/frag.pdf ; Gagie et al. Document Retrieval on Repetitive String Collections https://arxiv.org/abs/1605.09362 ; Universal Indexes for Highly Repetitive Document Collections https://arxiv.org/abs/1604.08897 ; Document Listing on Repetitive Collections with Guaranteed Performance https://arxiv.org/abs/1707.06374 . Interning, delta indexes and compressed retrieval are established. Claim only measured tradeoffs of this exact representation and later source/index sharing if demonstrated. Global token tuple interning has transient RAM cost; no transactional integration; preparation may worsen. If total archive savings do not exceed mapping overhead, retain independent multi.


## Local falsification probe and dense-row control

An independent local copy of the multi-splice adaptive window kernel and sparse signed multiset passed 137,032 pair/length frequency-map comparisons: 16,129 exhaustive binary pairs (length 0..6) and 1,000 random multi-edit pairs, each tested at lengths 1..8. The test compares all n-gram frequencies, including spurious terms. RapidFuzz 3.14.3; seed 166. This is local algorithm evidence, not hosted corpus validation.

A synthetic SQLite FTS5 patch-subsystem probe with 5,000 children, one replacement each, 15 tokens per nonempty window, and controlled sharing exposed the sparse-rowid confound. All arms optimize and VACUUM. Dense baseline uses cid<<1 plus sign, possible only because the synthetic probe has exactly one pair per child; quotient charges the full patch_use table.

| Distinct window pairs | Sparse baseline bytes | Dense baseline bytes | Quotient bytes |
|---:|---:|---:|---:|
| 1 | 761856 | 573440 | 126976 |
| 10 | 761856 | 573440 | 131072 |
| 100 | 765952 | 577536 | 151552 |
| 1000 | 770048 | 581632 | 258048 |
| 5000 | 786432 | 593920 | 712704 |

At zero sharing quotient loses 20% vs the dense direct-address synthetic baseline, despite appearing to beat sparse row IDs. At high sharing quotient wins. No source or whole archive in this synthetic probe. The corpus dense control now assigns consecutive row IDs, charges the same mapping table as quotient, preserves raw signed windows without merging/cancellation, and fixes the independent anchor policy. It is not a universally optimal dense direct-address encoding. Compare sparse/dense/quotient separately and avoid attributing all storage gains to sharing. First hosted R166 run 45915371243 passed all three unit-test steps and CLARK end-to-end as observed before dense-control revision; the AP corpus results were not yet complete at that observation. New commit requires fresh CI.
