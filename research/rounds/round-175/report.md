# R175: joint representation optimization

Status: implemented, measured locally on AP 10,009. CI matrix in
`cdg-r175-joint.yml`.

Parent R174 commit `a4d7953`. Same frozen inputs, cutoffs and query plan.

## Question

R173 and R174 each optimized one axis: a full positional index, or a selected
subset of terms. Real archives mix representations. Which combinations are worth
their bytes, and does any region of the archive benefit from a different strategy?

## Representations available to the optimizer

| Layer | Options | Measured cost (AP 10,009) |
|---|---|---|
| Source | R149 bounded marginal frames (kind 0 full, kind 1 one-hop delta) | 9,224,192 B frames + 495,616 B source rows |
| Term | frequency postings only | 3,059,712 B postings + 724,992 B lexicon |
| Term | block positions for selected terms (duplex) | 40–50 KB per selected term at b32/best/zstd |
| Term | block positions *replacing* postings for that term (unified) | saves that term's posting row |
| Region | native positional FTS5 over the k highest-service-cost contents | measured per layout |

Service cost for the regional choice is `revisions served × source activated bytes`,
so the hot region is the part of the archive whose phrase queries would otherwise
decode the most source.

A layout is therefore a triple (source strategy, term selection, region selection).
Seven layouts were built and measured end to end; every one keeps the same source
recipe (it won in R149/R155 and nothing in this round beats it) and the same exact
frequency index.

## Results (AP 10,009, 640 rank checks per layout, zero score error)

| Layout | Archive bytes | median µs | p95 µs | p99 µs | selected terms | hot contents | hot index B |
|---|---:|---:|---:|---:|---:|---:|---:|
| `freq` (frequency only) | 14,090,240 | 435.4 | 19,353.3 | 89,336.1 | 0 | 0 | 0 |
| **`sel` (R174 selection, 10% budget)** | 14,503,936 | 410.0 | **6,517.2** | 28,178.2 | 22 | 0 | 0 |
| `sel_unified` (postings dropped for selected terms) | 14,467,072 | 429.2 | 6,803.5 | 29,240.7 | 22 | 0 | 0 |
| `sel + hot256` | 15,650,816 | 423.9 | 6,000.3 | 21,785.3 | 22 | 256 | 1,146,880 |
| `sel + hot1024` | 17,985,536 | 449.6 | 5,416.6 | 17,378.4 | 22 | 1,024 | 3,481,600 |
| `sel + hot4096` | 24,363,008 | 366.5 | 3,625.8 | 5,436.3 | 22 | 4,096 | 9,859,072 |
| `sel_unified + hot1024` | 17,948,672 | 429.6 | 5,828.0 | 15,978.3 | 22 | 1,024 | 3,481,600 |

Reference points from the same framework: native positional FTS5 (no selection,
no hot region) 20,684,800 B / 2,775 µs p95; R173 unified full positions b32
21,413,888 B / 3,418 µs; R173 adaptive signed corrections 18,583,552 B / 2,181 µs.

## Findings

1. **Term-level selection is the only representation choice with a good exchange
   rate.** Moving 0.41 MB (2.9%) of storage into 22 block-posted terms buys
   12,836 µs of p95 (19,353 → 6,517). Every other axis is one to two orders of
   magnitude less efficient per byte.
2. **Term-level unification is real but tiny.** Dropping the duplicate posting row
   for the 22 selected terms saves 36,864 B (0.25% of the archive) at unchanged
   error. The 3.06 MB saving R173 measured requires *all* terms to be unified, which
   costs 21.4 MB in total and loses on latency.
3. **Regional native mirroring loses to the global native index at every size.**
   `sel + hot4096` spends 24.36 MB for 3,626 µs, while the plain native positional
   archive spends 20.68 MB for 2,775 µs. The hot region duplicates content already
   in the source frames: its FTS5 pages are pure overhead once the region is large
   enough to matter, and at 256 documents it buys only 517 µs for 1.15 MB.
4. **Different regions do not benefit from different representations here.** The
   service-cost ranking is smooth (top-256 contents hold 6.5% of service cost and
   cost 1.15 MB to mirror); there is no natural hot/cold boundary that makes a
   regional index pay. This is a measured negative result for the regional idea in
   *this* archive shape, not a general refutation of tiered indexes.
5. **p95 variance between runs is ~20–25% on this single machine.** `freq` measured
   19,353 µs here and 24,267 µs in R173/R174 for the same configuration and plan.
   Differences smaller than that are not evidence; the effects reported as findings
   are all ≥ 25%.

## Constraints actually checked

| Constraint | Status |
|---|---|
| Source reconstruction | every revision recovered byte-exactly in every layout |
| Historical ranking correctness | 640 rank checks per layout, zero score error, native FTS5 oracle |
| Dependency depth | source deltas one hop (unchanged); block positions one hop from the frequency index; hot region independent |
| Decoded-byte amplification | reported per layout in `decoded_bytes_per_query` |
| Activated-byte amplification | reported per layout in `activated_bytes_per_query` |
| Memory | peak RSS reported per layout (`peak_rss_kb`); process-wide, so it bounds rather than isolates |
| Storage | `dbstat` pages for every table including `term_blocks`, `selected_terms` and `hot_docs` |

## Retained fallbacks

`freq` and `sel` remain the shipped configurations. The hot-region layout is
implemented, tested and **not** adopted: it loses to the global native index at
equal storage and loses badly on bytes at equal latency.

## Limitations

* The signed-correction representation (R167/R169) was not re-measured here; R173's
  adaptive arm (18.58 MB / 2,181 µs) is the reference for that axis, and R175 does
  not claim it composes better than measured.
* One corpus size, one machine, two warm passes per layout; logical activation only.
* The optimizer is manual (seven enumerated layouts), not a solver over the full
  cross product; the cross product is 2 sources × 3 term strategies × 4 regions ×
  4 budgets and was not exhausted.
