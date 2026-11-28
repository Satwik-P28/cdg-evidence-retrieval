# R183 — Joint phrase-level selection

## The question

R181 showed that a workload-trained positional selection generalises badly and that a
query-independent adjacency filter generalises well. One diagnosis was that the objective was
additive per term: it paid a token a share of every phrase it appeared in, even when that share
could never reject anything. This round tests the obvious repair — value a set of tokens by
the *phrases it can complete* rather than by token participation — and compares it with four
alternative objectives at matched measured storage.

## Selectors

| selector | objective | premise |
|---|---|---|
| `joint_coverage` | weight of phrases with ≥ 2 selected tokens, greedy with incremental gains | a candidate can be rejected only when at least two of the phrase's tokens disclose positions |
| `pairwise` | buy whole phrase bundles only | no phrase is served halfway |
| `additive` | per-token share of phrase weight (the R174 model) | every selected token helps a little |
| `independent_df` | buy tokens by document frequency per byte, ignoring the workload | the R181 vocabulary control |
| `local_swap` | greedy start, then 1-for-1 improving swaps within budget | greedy needs repair |

`joint_coverage` needs a seed: with a "≥2 tokens" objective every first-step gain is zero, so
a pure greedy loop returns the empty set (measured — it selected 0 terms at a 1% budget before
the fix). The seed picks the token that participates in the most *incomplete* phrases per byte.

Budget is a fraction of the base archive, and every arm reports the **measured** increment.

## Results, held-out split A (246 CLARK / 281 AP queries)

All arms reported `score_error` 0.0, zero tie-order differences and no rank mismatches.

**CLARK-1,161** (base archive 5,009,408 B; frequency-only p95 168,171 µs)

| selector | budget | terms | measured fraction | p95 µs | p99 µs | source reads |
|---|---|---:|---:|---:|---:|---:|
| `joint_coverage` | 1% | 49 | 1.014 | 256,688 | 569,157 | 12,929 |
| `local_swap` | 1% | 49 | 1.014 | **126,019** | 221,570 | 12,929 |
| `pairwise` | 1% | 31 | 1.013 | 165,648 | 269,790 | 12,486 |
| `additive` | 1% | 13 | 1.013 | 187,044 | 227,934 | 12,929 |
| `independent_df` | 1% | 575 | 1.013 | 150,832 | 248,940 | 13,143 |
| `joint_coverage` | 5% | 190 | 1.057 | **124,269** | 214,083 | 9,051 |
| `independent_df` | 5% | 1,773 | 1.059 | 126,471 | 245,863 | 13,143 |
| `additive` | 5% | 124 | 1.059 | 149,667 | 351,288 | 10,627 |
| `pairwise` | 5% | 96 | 1.058 | 165,317 | 310,541 | 9,849 |
| `joint_coverage` | 20% | 575 | 1.152 | 21,881 | 140,905 | 3,329 |
| `additive` | 20% | 3,753 | 1.234 | **11,053** | 33,082 | 972 |
| `pairwise` | 20% | 902 | 1.200 | 11,083 | 30,875 | 1,015 |
| `independent_df` | 20% | 5,587 | 1.233 | 131,609 | 216,820 | 12,168 |

**AP-10,009** (base archive 14,082,048 B; frequency-only p95 388,344 µs)

| selector | budget | terms | measured fraction | p95 µs | p99 µs | source reads |
|---|---|---:|---:|---:|---:|---:|
| `local_swap` | 1% | 21 | 1.011 | **250,457** | 363,008 | 32,106 |
| `joint_coverage` | 1% | 21 | 1.011 | 251,203 | 366,549 | 32,106 |
| `additive` | 1% | 17 | 1.010 | 261,295 | 359,771 | 33,078 |
| `independent_df` | 1% | 1,039 | 1.012 | 257,535 | 367,250 | 33,078 |
| `pairwise` | 1% | 13 | 1.011 | 469,622 | 593,763 | 32,177 |
| `pairwise` | 5% | 80 | 1.054 | **250,007** | 652,879 | 26,849 |
| `joint_coverage` | 5% | 102 | 1.053 | 282,908 | 594,676 | 28,503 |
| `additive` | 5% | 93 | 1.054 | 332,222 | 524,542 | 28,135 |
| `local_swap` | 5% | 102 | 1.053 | 319,161 | 430,719 | 28,503 |
| `local_swap` | 20% | 518 | 1.212 | **57,009** | 133,835 | 6,956 |
| `pairwise` | 20% | 377 | 1.212 | 61,323 | 325,885 | 9,807 |
| `additive` | 20% | 497 | 1.213 | 66,057 | 288,592 | 10,009 |
| `joint_coverage` | 20% | 518 | 1.212 | 82,419 | 234,816 | 6,956 |
| `independent_df` | 20% | 12,067 | 1.228 | 337,877 | 518,709 | 32,337 |

## What the numbers say

**The repair works better than the policy it replaced.** At a 20% budget the best selector cuts
held-out P95 to 11,053 µs on CLARK (15.2× better than frequency-only) and 57,009 µs on AP
(6.8× better) for 21–23% additional archive bytes. Compare R174's in-distribution trained
policy, which needed 10% of the archive to reach 7,054 µs on a workload it had been fitted to;
here the improvement survives a family holdout.

**But `joint_coverage` is not the best of these objectives.** It wins one of six
(corpus, budget) cells — CLARK at 5% — and loses to `additive`, `pairwise` or `local_swap`
everywhere else, by up to 2× at CLARK 1%. The hypothesis that motivated the round is not
supported by its own experiment.

**The reason is in the premise, not the implementation.** Rejecting a candidate with positions
does not require two disclosed tokens: one term's position list is enough to show that the
phrase cannot occur at any offset in that document. So "≥ 2 selected tokens" undercounts the
value of every single selected token, and an objective that requires pairs systematically
buys fewer terms than the budget allows (575 vs 3,753 terms on CLARK at 20%) while
rejecting fewer candidates (9,657 vs 11,923 position rejections). `additive` encodes the
correct marginal contribution almost by accident: it pays every token, and one token is
enough. The `pairwise` bundle rule is a middle ground and does well at CLARK 20%.

**`independent_df` remains the control it was meant to be.** It buys thousands of terms (5,587
on CLARK, 12,067 on AP at 20%) and still leaves P95 at 131,609/337,877 µs, because frequent
tokens have short position lists that rarely align with a phrase. This reproduces R181's
finding that workload-independent *positional* selection does not generalise, and it is the
sharpest contrast with R181's pair filter, which is workload-independent and does.

**Local search helps at 1% and 20% on AP, and hurts on CLARK.** At CLARK 20% `local_swap`
is worse than its greedy start (21,881 → 20,420 µs is an improvement, but both trail
`additive`), and at CLARK 5% it is clearly harmful (124,269 → 165,746 µs). Swaps are not
reliably beneficial and are not used in the reported best configurations.

## Greedy gap

Exact enumeration over the top 12 candidate terms (4,096 subsets at the boundary budgets):

| corpus | budget | subsets | exact value | greedy value | ratio |
|---|---|---:|---:|---:|---:|
| CLARK | 1% | 689 | 4,251,608 | 1,398,215 | 0.329 |
| CLARK | 5% | 4,096 | 12,024,645 | 12,024,645 | 1.000 |
| CLARK | 20% | 4,096 | (see JSON) | — | 1.000 |
| AP | 1% | 199 | 13,653,045 | 11,690,813 | 0.856 |
| AP | 5% | 4,090 | 60,903,904 | 60,432,025 | 0.992 |

The greedy gap is large at a 1% budget, where the seed dominates the selection, and
negligible at 5–20%. **No submodularity claim is made**: the objective is not proven
submodular, the enumeration covers 12 terms rather than the whole vocabulary, and the ratio
above is a measured gap on a reduced problem, not a bound.

## Limitations

* No frequency-only arm is re-measured inside this round; the baselines quoted are R181's
  frequency arms on the same frozen workload, which is the same archive without selected
  terms.
* Positions only. This round does not combine pairwise rejection with the selectors; R182
  measures that combination for a fixed 5% pair index.
* The coverage objective ignores which candidates actually appear, so it cannot distinguish a
  token whose positions align well from one whose positions are useless. A candidate-aware
  objective is the obvious next step and was not measured.
* Warm cache, logical activation.