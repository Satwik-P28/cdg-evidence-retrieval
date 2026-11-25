# R149: marginal-cost and globally reusable bounded recipes

Status: implemented, unverified. Keep R148 frozen.

## Prior-art screen

- Bhattacherjee et al., Principles of Dataset Versioning (PVLDB 2015), https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/ : storage/recreation optimization with delta graph.
- Zou et al., MeGA (USENIX ATC 2022), https://www.usenix.org/conference/atc22/presentation/zou : exact chunk dedup plus resemblance-based delta selection and restore-aware layout.
- Zhang et al., LoopDelta (USENIX ATC 2023), https://www.usenix.org/conference/atc23/presentation/zhang-yucheng : locality-aware opportunistic delta compression during inline dedup; subsequent TOS extension https://mingzhe-zhang.github.io/publications/tos2025 .
- Similarity-based Deduplication for Databases, https://www.microsoft.com/en-us/research/publication/similarity-based-deduplication-databases/ : single-pass record-level delta encoding in database storage/logging.

None of generic dedup+delta, resemblance indexing, causal encoding, or restore-aware base selection is claimed novel. Hypothesis is narrower: a source-version recipe may have zero incremental encoded-frame cost even if its standalone frame is larger; explicit logical read bounds can coexist with global exact-source recipe reuse while preserving independent revision identity. Need stronger external comparisons and fresh corpora if promising.

## Frozen ablation

1. Snapshot and exact encoded-frame dedup.
2. Original R148 per-article bounded anchor plus exact frame coalescing.
3. Marginal: same four recent literal candidates, include literal option, choose minimum incremental encoded-frame bytes plus fixed 48 B per new catalog entry, then decoded and activated work.
4. Recipe: additionally consider the best previously observed exact-source recipe (verify source identity by bytes). Its parent is an earlier global literal generation, so aliasing is not recursive. Independent revision identity remains separate.
5. Recipe-sketch: additionally allow four candidate cross-article literal anchors from four bottom hashed sampled word trigrams, latest eight generations per bucket, ranked by common bucket count and recency. No future references; at most eight delta trials per revision.

All arms produce actual Zstandard frames, exact decode verification and identical hard 2.5x decoded / 1.5x activated / 0.8x delta frame constraints. Report distinct frame payload, catalog proxy separately, logical costs, cross-article delta incidence, deterministic fingerprint and encoding elapsed time (descriptive). No physical schema or full archival storage claim. Two original AP cohorts and one alternative ordinal interleaving of small cohort; original baseline and snapshot must reproduce R142 payload/unique-frame/mean-work metrics. No hyperparameter tuning after results. The alternative order is sensitivity, not independent corpus. Fixed candidate heuristics may fail, and greedy marginal selection is not globally optimal.