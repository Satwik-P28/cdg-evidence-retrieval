# R182 — Cost-aware execution

## The question

R181 showed that a pair filter is worth its bytes and that positions sometimes are. A query
does not need to use one strategy: a phrase built from index-covered tokens is answerable
from positions, a phrase whose pairs are stored can be rejected cheaply, and a phrase with
neither is best answered from the source. This round asks whether choosing per query, from a
calibrated cost model, beats committing to one strategy.

## Setup

One archive carries both optional structures — a 5% vocabulary pair index and 5% of the
positional budget, `archive_bytes` 5,476,352 against a 5,009,408 base (+9.3%). Five fixed
strategies are measured on it (`source`, `positions`, `pairs_source`, `pairs_positions`) plus
`planner`, on the same archive, the same queries and the same order, so differences are not
storage artefacts.

Cost model, fitted by least squares on the **training split only** over
`(µs, source_reads, blocks_activated, pair_bytes)`:

| coefficient | value |
|---|---|
| µs per source read | 466.97 |
| µs per activated block | 1,274.77 |
| µs per activated pair byte | 240.13 |

Calibration used 815 training queries / 2,445 samples. Held-out splits never enter the fit.
The planner offers a mode only when it is executable: positions require every token of the
phrase to have a directory entry and a block containing the candidate; a pair may only be
promised when the index stores it, or — in a complete index — when its absence proves zero
survivors. Both rules have tests.

## Results, CLARK-1,161

P95 in µs. Every one of the 25 arm-splits reported `score_error` 0.0.

| strategy | A/train | A/validation | A/held-out | B/held-out | C/evaluation |
|---|---:|---:|---:|---:|---:|
| `source` | 193,370 | 121,896 | 126,311 | 136,435 | 186,834 |
| `positions` | 129,497 | 142,029 | 128,191 | 89,281 | 123,960 |
| `pairs_source` | **48,858** | **45,293** | 54,010 | **16,250** | 51,248 |
| `pairs_positions` | 68,148 | 87,054 | 84,390 | 36,036 | 83,818 |
| `planner` | 60,789 | 50,955 | **52,563** | 17,760 | **48,843** |

Median in µs, same arms:

| strategy | A/train | A/validation | A/held-out | B/held-out | C/evaluation |
|---|---:|---:|---:|---:|---:|
| `source` | 2,085 | 1,718 | 1,323 | 1,255 | 1,930 |
| `pairs_source` | 1,274 | 1,422 | 1,353 | 854 | 1,577 |
| `planner` | 1,870 | 1,569 | **1,204** | 885 | **1,338** |

Source reads fall from 37,717 to 15,643 in the training split (−58.5%) and from 63,968 to
27,802 at the temporal evaluation cutoff, matching R181's measured rejection rate.

## Results, AP-10,009

Archive 15,646,720 B against a 14,082,048 B base (+11.1%), 8,014 pairs and 615 position
terms. Calibrated rates: 368.7 µs per source read, 645.2 µs per block, 8.3 µs per pair byte
(834 training queries, 2,502 samples).

| strategy | A/train | A/validation | A/held-out | B/held-out | C/evaluation |
|---|---:|---:|---:|---:|---:|
| `source` | 362,668 | 320,177 | 321,742 | 390,073 | 334,394 |
| `positions` | 348,952 | 329,028 | 339,628 | 349,580 | 299,325 |
| `pairs_source` | 66,411 | 76,409 | 114,261 | 90,816 | 82,045 |
| `pairs_positions` | **62,548** | **50,121** | **92,592** | 85,675 | **66,811** |
| `planner` | 80,990 | 83,507 | 97,446 | **79,742** | 86,638 |

Source reads at the temporal cutoff fall from 168,996 to 71,887 (−57.5%) and candidate
rejections reach 97,109, reproducing R181's AP rejection rate.

## What the numbers say

**The pair filter is the dominant fixed strategy.** On CLARK, `pairs_source` is the best
fixed arm on four of five splits at P95, and `pairs_positions` is consistently worse than
`pairs_source` — once adjacency has removed the candidates, paying for block decoding does
not help.

**Per-query planning does not beat the best fixed arm overall.** On CLARK the planner wins
two of five splits at P95 (A/held-out 52,563 vs 54,010; C/evaluation 48,843 vs 51,248) and on
AP one of five (B/held-out 79,742 vs 85,675). It loses the rest, on AP by up to 24% against
`pairs_positions`. That is reported as a negative result: the pair filter is already
near-optimal for almost every query, so there is little left for a planner to exploit, and a
model fitted to the mean cannot anticipate the tail. The
planner's value is not speed but robustness — it degrades to `source` when a phrase has
neither structure, which is what a fixed `pairs_positions` arm cannot do. Mode counts on
C/evaluation record 796 pair-mode queries and 44 source-mode queries.

**Calibration matters more than the objective.** An earlier version of this runner used a
byte-based model and produced planner P95 of 135,445 µs against 72,078 µs for a fixed arm —
worse than not planning at all, because bytes are a poor proxy for the cost of a source read.
The least-squares fit on measured microseconds is what makes the planner competitive. Both
versions are recorded here; only the calibrated one is reported as a result.

## Bugs found by the tests and by the first run

* The rate branch read `self.has_pairs` instead of `filters.has_pairs()`, which raised on
  every planning query.
* A missing pair in a **complete** index predicted `n` survivors instead of zero: the code
  set `known = False` but then fell back to the unfiltered count.
* Pair selection used the rejection-per-byte rule rather than the vocabulary rule, so the
  archive stored pairs that queries never use: candidates rejected fell from ~58% to 1.5%
  and the first CLARK run showed no benefit from the pair filter at all. The corrected run
  is the one reported above.
* Filter counters were cumulative across arms, so later arms looked busier than they were.
  Counters are now reported as per-query deltas.

## Limitations

* Neither corpus shows the planner beating the best fixed arm overall, so the round's headline
  is a negative result. On AP `pairs_positions` wins four of five splits; on CLARK
  `pairs_source` wins four of five.
* Warm cache, logical activation. `blocks_activated` is a counter, not a page-fault count.
* The planner is fitted on one corpus and does not transfer: the coefficients encode the
  frame sizes and block layout of this archive.
* A better model (separating pair-index lookups from source reads, or modelling tail
  behaviour rather than the mean) might beat the best fixed arm; that was not measured.