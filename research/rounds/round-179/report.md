# R179 — Repairing the methodology of rounds 173–178

## Why this round exists

The R174 hosted matrix (run `45926879483`, large-AP job `140270152160`) produced a
result that no summary in R173–R178 recorded:

| split | queries | P95 |
|---|---|---|
| training | 59 | 12,973 µs |
| validation | 14 | 178,982 µs |
| held-out | 7 | 1,316,938 µs |

Held-out source reads were 36,816. A policy selected on 22 terms looked excellent where
it was fitted and was roughly two orders of magnitude worse where it mattered. That is a
generalisation failure, and it is the reason this round audits the measurement
apparatus before any new method is proposed.

This round changes **no retrieval code**. It re-reads the committed result files, checks
each one against the corpus manifest it claims, and recomputes every comparison that
appeared in R173–R178 prose. `experiments/round-179/repair.py` produces
`results-repair.json` and `research/rounds/round-179/tables.md`; the tables in the
publication documents are generated from these files, never typed by hand.

## What was wrong, and what the data now says

### 1. Pareto frontiers were asserted, not computed

`frontiers` are now derived: an arm is on the frontier only if no verified arm stores
fewer bytes at no higher P95. Ties keep both arms, so iteration order cannot narrow a
frontier. Over 119 verified arms the recomputed AP frontier has **10** members and the
CLARK frontier **8**. Several frontier members were absent from the R173–R178 narrative,
and several arms described as "best" are strictly dominated and no longer appear.

The AP query plan digest `c6f41c9c…` is **identical** across R173, R174 and R175, which
is what makes a single combined frontier legitimate rather than an apples-to-oranges
comparison of different workloads.

### 2. Training, validation and held-out results were aggregated

R174 reported a single latency block per arm. The stored JSON did keep per-split
measurements, so the correction is mechanical: `split_separation` and `heldout_table`
recompute every arm's train/validation/held-out P95, P99 and maximum separately. The
aggregate is still reported, labelled `all`, and is never used as evidence about
generalisation.

The effect is not cosmetic. On AP, `train_candidates-1%-greedy` has a held-out P95 of
1,178 µs against a train P95 of 11,909 µs, because its 20 selected terms happen to cover
the held-out phrases. The same arm on the larger corpus did the opposite. Neither number
is meaningful without the workload that produced it — which is R180's subject.

### 3. Split sizes were described in prose

`split_size_declarations_consistent` reads the split sizes from the result files. AP is
**57/11/12** queries (train/validation/held-out), CLARK **46/20/14**. Both differ from the
prose that accompanied them, and both are small: 12 and 14 held-out queries, evaluated at
4 cutoffs with 2 passes, i.e. 96 and 112 measurements per arm.

### 4. "The matched positional baseline cannot reconstruct sources" — refuted

Every complete-archive arm is built on the same versioned source archive and records
`source_checks` equal to the revision count with zero reconstruction error. Reconstruction
is a property of the archive, not of the term index, so the claim is false and is removed
from every document. The native positional arm reconstructs all 10,009 AP revisions.

### 5. `bytes_per_query_median` contained a latency

In R174 this field held `query.median_us`. The corrected value divides a logical storage
activation counter by the number of rank checks, and it reports **which counters it
used**, because R174's stored work blocks contain no positional block activation:

| basis | arms | value |
|---|---|---|
| `storage_bytes_activated` | R173, R175 | full logical activation |
| `posting_bytes+source_activated_bytes` | R174 | frequency postings plus source frames only |

The latency keeps its own key (`latency_median_us`). All figures remain logical
activation, never physical page I/O.

### 6. Estimated budgets were reported as physical budgets

`budget_correction` separates three quantities for every budgeted arm: the estimated
payload budget (a fraction of the frequency archive), the selected payload plus directory
bytes, and the **measured** archive increment after `VACUUM`. Across 41 AP arms the
structural overhead the estimate omits has median **19.4%** of the estimate and maximum
**71.7%** (10,745 to 1,207,504 bytes). A "1% budget" arm therefore occupies between 1.08%
and 1.72% of the frequency archive. Any storage claim that quotes the estimate alone is
wrong by up to 72%.

### 7. External-baseline superiority was overstated

`check_external_comparability` compares payload plus directory against payload plus
directory, and marks anything else incomparable:

| ours | external | ours | external | margin |
|---|---|---|---|---|
| positional blocks b512 best+zstd | flat SIMD-BP128 docid+tf+positions | 8,244,651 | 8,741,439 | **−5.68%** |
| positional blocks b512 best+zstd | flat delta-varint docid+tf+positions | 8,244,651 | 8,913,198 | **−7.50%** |

Both of our figures include the 496,808-byte block directory. The R176 frequency-codec
comparison (Elías–Fano 3,468,822 versus our 3,048,885) is a *frequency-posting* comparison
and is not comparable to these positional totals; the documents now say so instead of
combining them into a single superiority claim.

### 8. "Dominance" where the data shows a trade-off

Across 336 ordered pairs of verified arms, `relation` finds **125 dominance** and **211
trade-off** relations. Both classes are reported. The single most repeated error was
describing the adaptive signed-correction arm (18,583,552 bytes, P95 2,181 µs) as
dominating the selective arms (14,467,072 bytes, P95 6,804 µs); it stores 4.1 MB more to
answer 3.1× faster, which is a trade-off.

### 9. P99 and maximum were missing

Every latency block already stored P99 and maximum. They are now reported next to P95 in
every table, including per split.

### 10. Tables are generated, not transcribed

`build_tables` emits the provenance, frontier, held-out, corrected-bytes, external and
claims tables. A test asserts that rebuilding the tables from the committed JSON
reproduces the file.

## Preserved flaws

The R173–R178 documents are **not edited to look better**. They remain in the repository
as published, and this round records what they got wrong. The corrections above are
additive: a reader can still see the original claim next to its refutation.

## Hosted results

R173, R175, R176 and R177 hosted matrices completed successfully. Their `RESULT_JSON`
records were not retrievable from this environment: there is no `gh` client and no
`GITHUB_TOKEN`, so job logs and artifacts are not readable, and the artifact endpoint
answers 401 without a token. Rather than assert numbers that cannot be re-read, this round
recomputes everything from the committed result files and state machine, and the larger-AP
scale point is re-measured directly (see `round-181`/`round-182`, which report the frozen
workload's baseline on AP-10,009 with P99 and maximum).

This is a limitation of the audit, not a decision to skip it: every number in the repaired
tables can be reproduced by running `python experiments/round-179/repair.py`.

## Limitations

* No physical I/O instrumentation and no cold-cache measurement; all bytes are logical
  activation of stored structures.
* The repaired R174 arms cannot charge positional block activation because their stored
  work counters do not contain it. New rounds record `storage_bytes_activated` explicitly.
* Dominance and trade-off are computed on (archive bytes, P95) only; P99 and maximum are
  reported but are not part of the frontier relation.
* The frontier mixes rounds measured at different times on the same machine class; timing
  noise is not modelled, so adjacent frontier points should be read as ties.
