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

## Partial verified results

Two 10,009-revision jobs on 2af1dea6 passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45699506275). Full cohort pending. Original order marginal policy reduces logical decoded-byte amplification from 1.645911 to 1.335114 (18.88%), payload 7,149,557 to 7,149,439 B, frame count 6,443 to 5,662. Reordered payload increases 2,104 B under marginal policy while mean work declines similarly. Global exact recipe and sketch save little incremental payload; sketch increases encoding elapsed time ~2.5x vs marginal. All source-only encodings verified, hard bounds retained. No physical archive claim; marginal looks strongest cost/complexity candidate so far. Keep all negative/neutral controls; defer promotion until full cohort and independent corpus.

| Order | Policy | Frame payload B | Unique frames | Mean decode | Max decode | Max activation |
|---|---|---:|---:|---:|---:|---:|
| reordered | snapshot | 10744266 | 5651 | 1.000000 | 1.000000 | 1.000000 |
| reordered | baseline | 7149557 | 6443 | 1.645911 | 2.482558 | 1.498306 |
| reordered | marginal | 7151661 | 5664 | 1.335178 | 2.482558 | 1.498306 |
| reordered | recipe | 7121114 | 5651 | 1.340608 | 2.482558 | 1.498306 |
| reordered | recipe_sketch | 7095772 | 5651 | 1.344906 | 2.482558 | 1.498306 |
| original | snapshot | 10744266 | 5651 | 1.000000 | 1.000000 | 1.000000 |
| original | baseline | 7149557 | 6443 | 1.645911 | 2.482558 | 1.498306 |
| original | marginal | 7149439 | 5662 | 1.335114 | 2.482558 | 1.498306 |
| original | recipe | 7122926 | 5651 | 1.340499 | 2.482558 | 1.498306 |
| original | recipe_sketch | 7096152 | 5651 | 1.345258 | 2.482558 | 1.498306 |
