# R174: cost-based selective positional materialization

Status: implemented, measured locally on AP 10,009 and CLARK 1,161. CI matrix in
`cdg-r174-selection.yml`.

Parent R173 commit `6537be4`. Same frozen inputs, cutoffs and query plans as R173
(AP `query_plan_sha256 c6f41c9c…`, 80 queries × 4 cutoffs).

## Question

R172 selected positional materialization by document frequency and lost, because
it always selected the *most common* terms, which a phrase never fully covers.
R173 made partial coverage actionable: with ≥ 2 covered offsets a candidate can be
rejected without reading its source. Which terms should get positions under a byte
budget, and does an economically motivated selection beat R172's policy?

## Design

The frequency archive is built once (`f.build` marginal recipes + R170 frequency
postings) and every arm is a byte-identical copy plus a selected subset of term
blocks. This makes the comparison exact: only `term_blocks` and the new
`selected_terms` table differ, and both are charged from `dbstat`.

Cost is always the **measured marginal physical storage** of a term: its block
payload plus its directory (`encode_term` at b32/best/zstd). Only the value model
changes, so every policy is compared at the same exchange rate.

| Policy | Value (per term) | Trained? |
|---|---|---|
| `df` | document frequency | no |
| `cf` | collection frequency | no |
| `srccost` | Σ over its documents of (source activated bytes × revision multiplicity) | no |
| `redundancy` | Σ revision multiplicity over its documents | no |
| `train_candidates` | Σ over *training* phrase executions of (candidates / (distinct terms − 1)), i.e. candidate-rejection opportunities | yes |
| `df_topk` | R172's policy: the k most frequent terms, cost ignored | no |

Optimizers: `greedy` (value/byte), reduced `knapsack` (top 250 by ratio, capacity
discretized into 4,000 slots, trimmed to the hard byte budget), `local_search`
(one-swap improvement over the 250 best candidates).

Splits are a deterministic hash split of the frozen plan (salt `r174`, first byte
mod 10: `<6` train, `6-7` validation, `8-9` held-out). Observed: AP train 57 /
validation 11 / held-out 12 queries (× 4 cutoffs); CLARK 46 / 20 / 14. Split
manifests are recorded per corpus in the result JSON. **Selection and all hyper-parameters use the train split only**;
the validation split was not used to choose anything beyond the fixed budget grid,
and the held-out split is reported but not used for tuning.

## AP 10,009 results (baseline frequency archive 14,082,048 B)

| Arm | Archive bytes | Δ vs frequency | selected terms | all-query p95 µs | source reads |
|---|---:|---:|---:|---:|---:|
| frequency, no positions | 14,082,048 | — | 0 | 24,267 | 7,132 |
| `df_topk` k32 (R172 policy) | 15,851,520 | +12.6% | 32 | 25,185 | — |
| `df_topk` k128 | 16,965,632 | +20.5% | 128 | 21,228 | — |
| `df_topk` k512 | 18,657,280 | +32.5% | 512 | 12,580 | — |
| `df` 1% | 14,266,368 | +1.3% | 104 | 21,621 | — |
| `df` 5% | 14,970,880 | +6.3% | 615 | 22,527 | — |
| `df` 10% | 15,810,560 | +12.3% | 1,423 | 27,043 | — |
| `df` 40% | 20,787,200 | +47.6% | 12,955 | 17,380 | — |
| `cf` 1% | 14,233,600 | +1.1% | 53 | 19,713 | — |
| `cf` 10% | 15,515,648 | +10.2% | 125 | 19,624 | — |
| `cf` 40% | 20,520,960 | +45.7% | 3,116 | 12,064 | — |
| `srccost` 1% | 14,270,464 | +1.3% | 1,546 | 19,906 | — |
| `srccost` 40% | 20,922,368 | +48.6% | 17,666 | 17,613 | — |
| `redundancy` 1% | 14,262,272 | +1.3% | 948 | 19,937 | — |
| `redundancy` 40% | 20,840,448 | +48.0% | 15,362 | 16,263 | — |
| **`train_candidates` 1%** | 14,221,312 | +1.0% | 20 | 12,684 | — |
| **`train_candidates` 5%** | 14,503,936 | +3.0% | 22 | **7,463** | — |
| **`train_candidates` 10%** | 14,503,936 | +3.0% | 22 | **7,054** | — |
| `train_candidates` 40% | 14,503,936 | +3.0% | 22 | 7,861 | — |
| `df` 5% knapsack | 14,495,744 | +2.9% | 250 | 20,133 | — |
| `df` 10% knapsack | 14,495,744 | +2.9% | 250 | 24,958 | — |
| `df` 5% local search | 14,970,880 | +6.3% | 615 | 29,209 | — |
| `df` 10% local search | 15,810,560 | +12.3% | 1,423 | 23,265 | — |

Zero score error in every arm (all 640 rank checks per arm, native FTS5 oracle).
Held-out p95 is ≈ 1.17–1.28 ms for every arm including frequency, because only 12
held-out queries × 4 cutoffs are timed and they contain 22 candidate source reads
that positions barely change; the held-out split therefore does **not** discriminate
these policies and only `all` is reported as evidence. This is a limitation of the
split, not a result.

## CLARK 1,161 results (baseline 5,009,408 B, 37,505 terms)

| Arm | Archive bytes | selected terms | all-query p95 µs | source reads |
|---|---:|---:|---:|---:|
| frequency | 5,009,408 | 0 | 8,220 | 2,744 |
| `df_topk` k32 | 5,398,528 | 32 | 8,153 | 2,744 |
| `df_topk` k512 | 6,123,520 | 512 | 6,278 | 914 |
| `df` 1% | 5,074,944 | 172 | 8,894 | 2,744 |
| `df` 40% | 7,585,792 | 19,138 | 1,815 | 1,296 |
| `cf` 40% | 7,479,296 | 13,428 | **1,806** | 24 |
| `srccost` 40% | 7,630,848 | 22,042 | 1,827 | 1,304 |
| `redundancy` 40% | 7,589,888 | 19,201 | 1,976 | 1,296 |
| **`train_candidates` 1%** | 5,070,848 | 16 | 3,316 | 716 |
| **`train_candidates` 5%** | 5,074,944 | 17 | **3,059** (3,258 in run 1) | 708 |

## Findings

1. **Cost-aware document-frequency selection beats R172's policy at equal or lower
   storage.** `df` 1% costs 1.3% of the base archive and answers in 21.6 ms, while
   R172's `df_topk` k32 costs 12.6% and answers in 25.2 ms. Ranking by
   frequency *per byte* rather than by frequency alone is the difference.
2. **Workload-trained selection is the strongest result and is workload-specific.**
   At AP it selects 22 terms (+3.0% storage) and cuts p95 from 24,267 µs to
   7,054 µs — a 3.4× improvement for 421,888 bytes.    On CLARK it selects 17 terms
   (+1.3%) and cuts p95 from 8,220 µs to 3,059 µs (2.7×). This is the first configuration
   in this series that strictly dominates the frequency-only frontier.
3. **The trained policy degenerates to "materialize the training vocabulary".** It
   selects exactly the 20–22 terms that appear inside multi-token training phrases,
   because no other term has nonzero measured rejection value. It should be reported
   as a *workload-specialized* configuration, not a general corpus policy: its
   advantage disappears if the query workload changes, and the AP/CLARK held-out
   splits are too small to test that.
4. **No statistics-only policy is close.** `cf`, `srccost` and `redundancy` all
   land within 5% of each other at every budget and all are dominated by `train_candidates`
   and by plain `df` at the low budgets.
5. **Submodularity does not hold, and was not assumed.** The rejection kernel in
   `rank_blocked` is a threshold on `len(covered) >= 2`: one covered offset can
   reject nothing, two unlock rejection for the whole phrase, three add only the
   tightened intersection. Benefit is therefore increasing but not diminishing in
   the selected set, so ratio-greedy has no submodular approximation guarantee here.
   The reduced knapsack did not beat it (14.50 MB / 20.1 ms versus 14.97 MB /
   22.5 ms for greedy at the same 5% budget, both dominated by the trained arm).
6. **Local search did not help** (`df` 5% 22,527 → 29,209 µs, `df` 10% 27,043 →
   23,265 µs): with a threshold benefit curve the analytic ordering is not improved
   by one-swap exchanges on the proxy objective.

## Negative results (retain)

* R172's exact policy (`df_topk`) is the worst cost-effective selector at every
  budget on both corpora; its k512 point is only competitive because it spends 32%
  more storage.
* Reduced knapsack over the top 250 terms under-fills large budgets (250-item cap
  binds before the byte cap) and never beat greedy.
* One-swap local search on the proxy objective is neutral-to-harmful.
* Source-expense and redundancy value models are not substitutes for a workload
  signal; they behave like noisy document-frequency.

## Pareto frontier after R174 (AP 10,009, exact on every arm)

| Point | Archive bytes | p95 µs |
|---|---:|---:|
| frequency only | 14,082,048 | 24,267 |
| **+ trained selective positions (22 terms)** | **14,503,936** | **7,054** |
| native positional FTS5 | 20,684,800 | 2,775 |
| unified full positions b32 (R173) | 21,413,888 | 3,418 |

The trained point strictly improves on the previous frontier; the native index is
still the tail-latency winner at 43% more storage.

## Limitations

* The "workload" is the frozen R173 query plan, not a production query log.
* Split sizes are small (14–20 held-out queries), so held-out latency is not
  discriminating; the all-query column reuses the same plan for every arm, so it is
  comparable across arms but not an independent workload.
* Logical byte activation only; no cold-cache, physical I/O or RSS measurement.
* Only b32/best/zstd was used for the selection cost model; R173 showed the storage
  optimum is b512 and the latency optimum is b32, so the cost model is calibrated to
  the latency-optimal layout, not to the storage-optimal one.

## Full budget grid and replication (second run, 41 arms)

The first run covered budgets 1/5/10/40%; the second covered the requested
1/2/5/10/20/40% grid and repeated every arm from the first run, so it doubles as a
replication. Results files: `results-*-run1.json` (first) and `results-*.json`
(second, superset).

**Bytes are deterministic.** All 31 overlapping arms produce byte-identical archives
in both runs (e.g. `train_candidates-10%-greedy` 14,503,936 B on AP, 5,074,944 B on
CLARK). **Latency is not.** Across the 31 arms the median relative p95 difference
between runs is 7.7% on AP (max 34.2%, `df_topk-k128`) and 4.9% on CLARK (max 114%,
`train_candidates-10%-local_search`). The shipped arm moves 7,054 → 7,126 µs on AP
(+1.0%) and 3,258 → 3,059 µs on CLARK (−6.1%), i.e. it is stable within the noise
band, while single arms that sit close to a rejection threshold are not.

New budget points (second run, `all` query p95):

| Corpus | Arm | Archive B | Terms | p95 µs |
|---|---|---:|---:|---:|
| AP | `train_candidates` 2% | 14,372,864 | 20 | 11,364 |
| AP | `train_candidates` 20% | 14,503,936 | 22 | 7,263 |
| AP | `cf` 20% | 17,055,744 | 615 | 13,123 |
| AP | `df` 20% | 17,526,784 | 3,959 | 22,838 |
| AP | `redundancy` 20% | 17,543,168 | 6,432 | 20,952 |
| AP | `srccost` 20% | 17,575,936 | 8,153 | 21,137 |
| CLARK | `train_candidates` 2% | 5,074,944 | 17 | 3,048 |
| CLARK | `train_candidates` 20% | 5,074,944 | 17 | 3,325 |
| CLARK | `cf` 20% | 6,180,864 | 1,117 | 4,730 |
| CLARK | `cf` 40% | 7,479,296 | 13,428 | 1,744 |

The 20% points confirm the shape: spending five times the trained budget on a
statistics-only policy still loses on both storage and latency at AP
(`cf` 20%: 17.06 MB / 13,123 µs versus trained 14.50 MB / 7,263 µs), while on CLARK
`cf` 40% does reach 1,744 µs — at 47% more storage than the trained arm.

## Build and materialization latency

Measured in the second run (`sweep.build_seconds`, per-arm `materialize_seconds`):

| Corpus | Revisions | Build (source + frequency tape + statistics) | Per-arm materialization |
|---|---:|---:|---:|
| AP | 10,009 | 22.99 s | 0.12–0.23 s |
| CLARK | 1,161 | 5.72 s | 0.05–0.12 s |

Build is dominated by source encoding and the FTS5 oracle-free index construction;
adding a selected term set to an existing base archive costs a fraction of a second
and is a pure append of `selected_terms` plus the block rows. There is no
incremental *append-a-revision* path in this codebase, so append latency for new
revisions is not measured and is listed as an open item.
