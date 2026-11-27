# Phase 0 audit: state entering R173

Parent commit `7731bebece0afbe052ca51e4e6dfeaec0eb4f85d` on
`research/round-165-r172-selective-positions`. Local branch
`research/round-173-r178-block-postings`. Audited 2026-11-27.

## Hosted CI state, verified through the GitHub API

| Run | Commit | Workflow | Result |
|---|---|---|---|
| 45919978067 | `7731bebe` | CDG research checks | completed success |
| 45919907862 | `537f3a30` | CDG research checks | completed success |
| 45919907942 | `537f3a30` | CDG R172 selective positions | **2 of 3 jobs success, AP 100000 still in progress at inspection** |

`cdg-r172-ap-10000` and `cdg-r172-clark-10000` artifacts exist (2,696 and 2,446
bytes, not expired). Artifact *download* requires an authenticated token, which
this environment does not hold, so R172's raw JSON was **not** retrieved. Instead
the R172 configuration was re-executed locally from the same frozen inputs:

* AP corpus `ap-matched-sentences.db`, SHA-256 frozen by
  `experiments/round-136/newsedits_scale.py`.
* Target 10,000 → 10,009 revisions, source manifest
  `2788f97b57da9dabb24ace843b8f4b9b0993fc1041c9dfcca228ab6e26a79857` (asserted).
* CLARK checkout `b93f898780b3cf40fedd4e9a00c51af9a27688bc`, manifest
  `1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f` (asserted).
* Local re-run reproduced R172's five archive sizes **byte for byte**
  (20,684,800 / 18,583,552 / 14,082,048 / 15,392,768 / 23,080,960) and zero score
  error on 640 rank checks. Latencies differ from CI (different machine) and are
  therefore always compared within one run, never across runs.

The AP 74,364-revision numbers quoted below are **CI-reported only** and were not
re-executed here (see limitations).

## Strongest validated results carried into R173

1. **Source layer.** Bounded marginal delta recipes over a finalized archive
   (R149) give 77,455,360 B for 74,364 AP revisions, versus 143,298,560 B for
   revision-expanded storage (R150) and 144,404,480 B for the naive revision
   control (R152). Every recovered revision is byte-identical to the original and
   bounded by `2*decoded <= 5*raw`, `2*activated <= 3*zstd(raw)`.
2. **Exact frequency layer.** R158/R170 frequency postings give 101,048,320 B
   (R158) and 95,735,808 B (R170 CI) at AP 74,364 with exact BM25 and document
   frequency, but tail latency is unusable (175,065 µs p95 R158; 86,210 µs R171
   CI) because phrase candidates decode source documents.
3. **Signed corrections.** R165's one-hop lemma (edit windows separated by
   ≥ 2(L-1) unchanged tokens) is proved and randomized-tested; R167 ordinal runs
   and the adaptive shared/direct policy give 132,964,352 B at AP 74,364 with zero
   ranking error, the best *positional-exact* archive size measured before R173.
4. **Native positional control.** SQLite FTS5 positional archive: 148,459,520 B at
   AP 74,364, 20,684,800 B at AP 10,009, 5,992,448 B at CLARK 1,161. This is the
   feature-matched baseline that every positional claim must beat.
5. **Correctness oracles.** Native FTS5 `bm25` ordering plus `cdg_count`/`cdg_length`
   parity, byte-exact source recovery for every revision, and committed
   `query_plan_sha256` make ranking regressions detectable. R173 keeps the identical
   contract.

## Failed hypotheses and negative controls (keep)

| Hypothesis | Outcome |
|---|---|
| Presence-only index (R157/R158) | 91,381,760 B but 438 s-scale p95 (438,356 µs); source fallback dominates |
| Content-defined fragment quotient (R154/R155) | best fragment arm 73,670,656 B but p95 13,737 µs and 831 µs median; loses to plain marginal |
| Token-ID tape (R170/R171) | 171,671,552 B; one-hop tape selected only 2,171/8,373 candidates and increased the file |
| Text joint tape (R171) | payload cut 40,276,317 from 51,804,679 but total file grew |
| Fixed top-DF selective positions (R172) | storage 15,392,768 B but **no** candidate reduction: 7,132 source reads, identical to frequency; only top512 changed anything |
| Full custom positions, whole-list decode (R172) | 23,080,960 B and p95 39,314 µs — worse than native on both axes |
| R156 sharded self-index | 109,293,568 B at 64 shards, 121,499,648 B at 512; latency degrades with shard count |

## Pareto frontier entering R173 (AP 10,009, one run, verified)

| Configuration | Archive bytes | median µs | p95 µs | exact ranks |
|---|---|---|---|---|
| frequency (no positions) | 14,082,048 | 503.0 | 24,267.3 | yes |
| frequency + top32 positions (R172) | 15,392,768 | 468.5 | 25,825.4 | yes |
| adaptive signed corrections (R167) | 18,583,552 | 258.1 | 2,181.5 | yes |
| native positional FTS5 | 20,684,800 | 276.1 | 2,775.0 | yes |
| frequency + all positions (R172) | 23,080,960 | 464.8 | 39,314.2 | yes |

The frontier is `{14.08 MB @ 24 ms} → {18.58 MB @ 2.2 ms} → {20.68 MB @ 2.8 ms}`.
**No custom positional representation has ever beaten the native index on both
axes.** R173's question is therefore narrow: can block addressing move the
23.08 MB / 39 ms point down to or below the native point?

## Experimental inconsistencies to fix

1. R172 decoded whole term lists, so its "selective" policy could not reject
   candidates; the top-K knob changed storage without changing work. R173 must
   report *decoded* and *activated* bytes, not storage alone.
2. R172's `all_positions` control duplicates frequency postings. A fair positional
   archive should either charge both (duplex) or neither (unified). R173 reports
   both accountings.
3. Cross-round latency comparisons mix machines and passes. R173 compares only
   arms inside one process run and states samples, p50/p95/p99.
4. R172's storage sweep of block metadata did not exist; block directories were not
   charged. R173 charges directory bytes per term and real `dbstat` pages end to end.
5. Selection in R172 was by full-archive document frequency, which is not a work
   model. R174 must separate statistics-only from workload-trained policies with
   disjoint train/validation/held-out query splits.

## Mechanisms that compose without duplicating prior work

* R149 marginal source recipes — unchanged source layer, shared by all arms.
* R158 frequency postings — the candidate generator and (in R173 unified arms)
  a redundant structure that block count streams can replace.
* R167 signed corrections — orthogonal: it answers phrases without positions for
  *changed* documents. R175 tests mixing it with block positions.
* R163/R164 dictionary facilities — orthogonal to positional addressing.
* R173 block directory — new addressable layer; the only new persistent structure.

## Consequences for this round series

R173 is a measured negative-or-marginal result generator: block addressing helps
the custom positional path a lot (39.3 ms → 5.5 ms p95 at AP 10,009) but does not
overtake native FTS5 on AP. R174 must therefore stop asking "full positions or
none" and ask **which terms deserve positions under a byte budget**, with block
addressing making selective coverage genuinely cheap. R175 then mixes
representations per region. R176 supplies external encoder baselines so the storage
claim is not self-referential. R177 stresses correctness on adversarial inputs.

## Addendum: R172 CI run completed

Checked after the audit above was written: workflow run `45919907942`
("CDG R172 selective positions", head `537f3a3`) is **completed / success** —
created 2026-11-27T00:59:05Z, finished 2026-11-27T01:14:15Z. All three jobs,
including the AP 100,000 revision arms, concluded successfully.

What this does and does not give us: it confirms the R172 pipeline runs at
100,000 revisions and that its artefacts were produced, but the artefacts still
cannot be downloaded from this environment (the download endpoint returns 401
without a token). Consequently no 74,364-revision *number* in R173–R178 is used as
evidence; those figures remain labelled CI-reported.
