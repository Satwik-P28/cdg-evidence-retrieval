# Research decisions, 12 November 2026

## Keep

**Exact source-coordinate representation.** Evidence should carry source version, canonicalizer identifier, ordered spans, access scope, and where verified an explicit map to original raw bytes. Supports noncontiguous fragments without pretending that a min-max bounding range is the actual evidence.

**Set-level evidence requirements.** Some answers require multiple complementary facts. Evaluate complete support, not only top-k relevance.

**Conditional complexity.** Ordinary retrieval works well when discriminative query terms exist. Extra graph reasoning should only be used when the predicted benefit exceeds retrieval and computational costs.

**Read-cost accounting.** Marginal frame activation is a union-cost problem across candidate witnesses and already-activated frames. Measure it on compressed archives, not just in a byte-count model.

## Reject or downgrade

- Passage similarity as a correctness certificate.
- Exact quote alignment as entailment verification.
- Oracle witness cost improvements as deployable gains.
- One universally optimal frame size or neighbor boost.
- Synthetic high success rates as evidence of real-world superiority.
- Dependency prediction without calibration and out-of-distribution stress.
- Complexity that cannot beat BM25 or simple evidence expansion at matched budgets.

## Open hypotheses

- Learn query-conditioned dependencies from source structure and cross-document relationships without leakage of annotated gold sets.
- Gate graph reasoning by whether available observations distinguish plausible evidence sets.
- Jointly choose complete witnesses and physical frame activations, preserving exact provenance receipts.
- Recover gracefully from version changes and ACL invalidation without stale pointers.

## Next milestones

1. Independently authored multihop QA benchmark with held-out source families and exact evidence annotations.
2. Frozen tokenizer and reader; equal-cost baselines including hybrid ranker and set-selection.
3. True seekable Zstd and content-defined framing, storage index accounting and p50/p95 cold/warm retrieval.
4. Calibrated confidence and abstention; report support/citation/answer quality separately.
5. Ablations: no dependency model; no gating; no physical cost; no exact coordinate map.
