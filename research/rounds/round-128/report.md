# R128: Proposal-prioritized verified historical ranking

Status: pending original-source CI.

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
