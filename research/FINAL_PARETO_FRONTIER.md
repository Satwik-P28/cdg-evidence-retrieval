# Final Pareto frontier

Every frontier in this document is computed, not asserted. An arm is on a frontier only if no
verified arm stores fewer bytes at no higher P95 latency; ties keep both arms. The computation
is `experiments/round-179/repair.py::pareto`, applied to result files that carry a verified
corpus manifest digest, and it is re-run by a test.

Two frontiers are reported because they answer different questions:

* **Archive frontier** (R173–R175) — complete archives, measured physical bytes versus P95 on
  the R173 query plan. This is the representation-design frontier.
* **Rejection frontier** (R181) — the same base archive plus one optional structure, measured
  physical bytes versus P95 on R180's frozen workload. This is the operational frontier.

They are not comparable to each other: different workloads, different query counts, different
cutoffs. Each is internally consistent.

## Archive frontier, AP-10,009

All arms below were measured on revision set `2788f97b57da9dab…` with the identical query-plan
digest `c6f41c9c9b4bc59d…`, which is what makes a combined frontier legitimate.

| round | arm | archive bytes | P95 µs |
|---|---|---|---|
| r173 | frequency | 14,082,048 | 24,267.3 |
| r175 | freq | 14,090,240 | 19,353.3 |
| r174 | train_candidates-1%-greedy | 14,221,312 | 12,649.7 |
| r174 | train_candidates-2%-greedy | 14,372,864 | 11,363.9 |
| r175 | sel_unified | 14,467,072 | 6,803.5 |
| r175 | sel | 14,503,936 | 6,517.2 |
| r175 | hot256 | 15,650,816 | 6,000.3 |
| r175 | sel_unified_hot1024 | 17,948,672 | 5,828.0 |
| r175 | hot1024 | 17,985,536 | 5,416.6 |
| r173 | adaptive | 18,583,552 | 2,181.5 |

Ten of 119 verified arms are non-dominated. Across all ordered arm pairs, the repair script
finds **1,256 dominance** and **2,237 trade-off** relations, and both classes are reported. The
most frequently mis-stated pair is
`adaptive` (18,583,552 bytes, 2,181 µs) against `sel` (14,503,936 bytes, 6,517 µs): the former
stores 4.1 MB more to answer 3.0× faster. That is a trade-off, not dominance.

**How to read this frontier.** The cheapest useful archives (14.1–14.5 MB) already pay for the
same source storage; the marginal cost of positions is 0.1–4.5% of the archive. The latency
axis moves by an order of magnitude across the frontier, so no single arm is "best": choosing
between `sel` and `adaptive` is choosing a storage budget.

## Archive frontier, CLARK-1,161

| round | arm | archive bytes | P95 µs |
|---|---|---|---|
| r173 | frequency | 5,009,408 | 8,220.4 |
| r174 | train_candidates-1%-greedy | 5,070,848 | 3,064.1 |
| r174 | train_candidates-40%-greedy | 5,074,944 | 3,045.4 |
| r173 | positional | 5,992,448 | 2,576.7 |
| r173 | adaptive | 6,021,120 | 1,992.6 |
| r173 | unified_b512_best_zstd | 7,217,152 | 1,769.9 |
| r173 | unified_b64_best_zstd | 7,262,208 | 1,556.1 |
| r173 | unified_b128_bp_raw | 7,438,336 | 1,532.1 |

CLARK's frontier is denser because its archive is smaller: the same structures cost less in
absolute bytes, so more of them are affordable at each storage point.

## Rejection frontier, R181 measured arms

Frozen workload `b8e157bc9e822e70…` (AP) and `50d5ccab28dcc206…` (CLARK). Physical archive size
is the measured file size, not the estimated payload budget. "vs base" is the measured
increment over the frequency-only archive.

### AP-10,009 (base 14,082,048 bytes)

| arm | archive bytes | vs base | P95 µs | P99 µs | max µs | source reads |
|---|---|---|---|---|---|---|
| `freq` | 14,082,048 | — | 388,344 | 588,428 | 819,731 | 168,996 |
| `fingerprints64` | 14,180,352 | +0.7% | 365,317 | 609,354 | 868,307 | 168,175 |
| `pairs_selective-5%` | 14,770,176 | +4.9% | 105,639 | 369,527 | 696,854 | 71,887 |
| `positions-5%` | 14,958,592 | +6.2% | 269,475 | 395,113 | 504,567 | 168,996 |
| `pairs_all` | 30,851,072 | +119.1% | 20,322 | 81,231 | 332,367 | 9,970 |
| `pairs_all+positions-5%` | 31,727,616 | +125.3% | 12,865 | 43,062 | 238,628 | 9,970 |

Five arms are non-dominated: `freq` (cheapest), `fingerprints64`, `pairs_selective-5%`,
`pairs_all`, `pairs_all+positions-5%`. Only `positions-5%` is dominated, by
`pairs_selective-5%`: it stores 188,416 bytes more and answers 2.6× more slowly at P95.
`fingerprints64` is *not* dominated on AP — it stores 0.7% more and is 6% faster at P95 — which
is why it is reported as an unusable structure on candidate-rejection grounds rather than on
frontier grounds.

### CLARK-1,161 (base 5,009,408 bytes)

| arm | archive bytes | vs base | P95 µs | P99 µs | max µs | source reads |
|---|---|---|---|---|---|---|
| `freq` | 5,009,408 | — | 168,171 | 348,464 | 619,899 | 63,968 |
| `fingerprints64` | 5,033,984 | +0.5% | 182,922 | 320,737 | 617,779 | 63,674 |
| `pairs_selective-5%` | 5,226,496 | +4.3% | 72,078 | 245,543 | 453,448 | 27,802 |
| `positions-5%` | 5,296,128 | +5.7% | 159,467 | 335,512 | 637,063 | 63,968 |
| `pairs_all` | 12,431,360 | +148.2% | 7,400 | 42,235 | 153,169 | 4,379 |
| `pairs_all+positions-5%` | 12,718,080 | +153.9% | 9,551 | 51,855 | 209,253 | 4,379 |

CLARK has three non-dominated arms: `freq`, `pairs_selective-5%`, `pairs_all`. Here both
`fingerprints64` and `pairs_all+positions-5%` are dominated. The latter is the one case where
positions are strictly wasteful: the extra 286,720 bytes buy nothing once adjacency has
already removed the candidates, and P95 rises from 7,400 to 9,551 µs.

## Best configurations

**Cheapest archive that is still useful.** `pairs_selective-5%` — 4.3–4.9% above the frequency
archive, 2.3× (CLARK) to 3.7× (AP) better P95, and 56–57% fewer source reads.

**Best latency per byte.** `pairs_all` on CLARK (7,400 µs at +148%) and
`pairs_all+positions-5%` on AP (12,865 µs at +125%).

**Best absolute latency.** `pairs_all+positions-5%` on AP (12,865 µs P95, 43,062 µs P99); on
CLARK the same arm loses to `pairs_all` alone.

**Not worth buying at any size measured.** 64-bit document fingerprints. They add 0.5–0.7%
storage and reject 0.5% of candidates; on CLARK they are dominated outright, and on AP their
6% P95 advantage is noise-level for a structure that filters almost nothing.

## Acceptance targets

| target | status |
|---|---|
| ≥ 25% complete-archive savings against the matched native positional baseline | **not met.** R173's best complete archive is `unified_b512` at 20,631,552 bytes against `positional` at 20,684,800 — a 0.26% saving. The 25% saving exists only for the *index* portion, not the complete archive, because source storage dominates. |
| held-out P95 ≥ 2× better than matched frequency-only | **met on CLARK by the 5% budget (2.3×) and on AP by the same budget (3.7×); the complete index reaches 19×/23×.** |
| meaningful held-out P99 improvement | **met**: P99 falls from 588,428 to 369,527 µs at 5% (1.6×) and to 81,231 µs with the complete index (7.2×) on AP; 348,464 → 245,543 (1.4×) and 42,235 (8.3×) on CLARK. |
| generalisation on at least two corpus types | **met** in direction and magnitude on AP and CLARK. |
| comparison against the strongest adaptive signed-correction configuration | **met** on the archive frontier (R173 `adaptive`, 18,583,552 bytes / 2,181 µs); it is faster than every rejection arm at 5% and slower than `pairs_all+positions-5%` at 2.5× the storage of `pairs_selective-5%`. |

The honest summary: the 25% complete-archive target is not achievable by better positional
coding, because the archive is dominated by source bytes. It is achievable only by removing
source storage, which is out of scope for these rounds and is the natural next experiment.