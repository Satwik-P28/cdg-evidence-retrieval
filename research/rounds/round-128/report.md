# R128: Proposal-prioritized verified historical ranking

**Status: PASS. Two regression tests and full pinned-corpus [CI 45490217290](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45490217290).**

Uno (Sahoo et al., arXiv:2609.04010) inspires the separation of cheap
proposal and authoritative verification, not direct use of diffusion.
For exact historical BM25, a draft from the previous cutoff can seed
the top-k heap; candidates are skipped only when a current-snapshot safe
score bound is strictly below the heap threshold. Never truncate phrase
DF or reuse stale scores. Compare full sort, heap, block bounds (16/64
article IDs), prior-result draft + bounds, and adversarially unhelpful
draft. At fixed positive TF, BM25 contribution is monotone in length:
for each TF within a block, the shortest matching document gives an
upper bound, then maximize across TF groups and sum across phrases.
Strict inequality preserves ties. Audit every bound against every exact
score outside timing; include construction overhead in timed ranking.
Native exact phrase counts prepared outside timing for all arms; this
does not measure compressed reads, retrieval latency or independent data.
Related work: Ding and Suel, Faster Top-k Document Retrieval Using
Block-Max Indexes (SIGIR 2011); this is a narrow rank-stage diagnostic,
not a full BMW reproduction or new pruning algorithm.

## Results

445 articles, 2,504 revisions, 43,147 terms; 159 queries at each of four cutoffs, 636 exact rankings and 3,204 ranked positions per method. All six methods and exhaustive score reference matched native FTS5 with zero observed score error. Tests include 100 randomized multi-term fixtures with both AND/OR and exact tied-score row-ID order under unhelpful proposals. Every block bound audited against exact scores. Five randomized warm rank-stage timing passes. Native exact term/phrase frequencies are prepared outside timing identically for every method.

| Method | Final candidates scored | Pruned candidates | Bound contribution evaluations | Median us | p95 us |
|---|---:|---:|---:|---:|---:|
| sort | 12502 | 0 | 0 | 8.390 | 330.212 |
| heap | 12502 | 0 | 0 | 9.219 | 385.284 |
| bound16 | 3902 | 8600 | 9161 | 16.237 | 321.660 |
| bound64 | 8976 | 3526 | 5741 | 16.389 | 409.436 |
| draft16 | 3989 | 8513 | 9161 | 17.497 | 344.541 |
| draft64 | 9009 | 3493 | 5741 | 17.098 | 426.365 |
| bad_draft16 | 4115 | 8387 | 9161 | 17.977 | 357.884 |

At the final cutoff, bound16 skips 8,600/12,502 full candidate scores (68.79%), but calculates 9,161 additional per-term bound contributions. Median 16.237 us vs exhaustive sort 8.390 us (1.94x slower); p95 is slightly lower (321.660 vs 330.212 us). Previous-cutoff proposal scores 742 seed candidates, prunes 8,513, median 17.497 us and p95 344.541 us. It does not improve the already bound-ordered control. Across cutoffs bound16 prunes 31,617/46,801 candidates (67.56%). These are full scoring candidates skipped, not saved model calls, compressed bytes, or end-to-end retrieval work. On-demand upper-bound construction is expensive; no persisted bound metadata or physical I/O measured. No independent corpus, representative workload, diffusion model, or new WAND algorithm. Do not claim acceleration.

## Decision

Reject rank-stage speculation as a default. The next plausible variant would use inexpensive persisted current-snapshot-safe block summaries and exact DF, charge all metadata and benchmark actual avoided compressed reads on independent histories. Prioritize integrated source archive, independent chronological validation and the manuscript first. Uno's distribution-preserving sampler is adjacent inspiration, not a CDG component. See [transfer audit](../../uno-transfer-audit.md) and [paper draft](../../paper/manuscript-v0.1.md).
