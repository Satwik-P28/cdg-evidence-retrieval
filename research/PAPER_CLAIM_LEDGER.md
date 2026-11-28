# Paper claim ledger

Every sentence the paper is allowed to say, with the artefact that entitles it to say so, the
baseline it is measured against, and the reason a reviewer might refuse it. A claim that is not
in this table does not appear in the paper.

Status legend: **MET** — verified against committed output. **NOT MET** — measured and failed;
the failure is reported. **QUALIFIED** — true only with a stated restriction. **REFUTED** — an
earlier claim that the evidence contradicts.

## Correctness claims

| # | claim | evidence | status |
|---|---|---|---|
| C1 | Every reconstructed source is byte-identical to the original for every revision in the evaluated set. | R173–R176 `source_checks` in every arm of both corpora; R179 recomputation over all 119 arms. | MET |
| C2 | Ranking is bit-identical to native FTS5 at every cutoff. | R181 `score_error`, `tie_order_differences`, `rank_mismatches` for all 6 arms × 2 corpora: all zero. | MET |
| C3 | No query returns a false-negative candidate set. | R181 pair filters: every survivor re-verified exactly; rejection only removes candidates that provably lack a stored pair. Tests `test_rejection.py`. | MET |
| C4 | An approximate filter never determines a BM25 score. | Code path: filters produce an allow-set; only FTS5/position decoding produces scores. `test_rejection.py::test_scores_come_from_verification`. | MET |
| C5 | Corrupt filter data fails closed. | `read_varints` count check plus a test that truncation raises instead of returning a short list. | MET |

## Measurement claims

| # | claim | evidence | status |
|---|---|---|---|
| M1 | The estimated payload budget is not a physical storage budget. | R179: structural overhead is a median 19.2% and up to 71.7% of the estimated budget across 76 arms (`corrected_bytes[].structural_overhead_bytes`). | QUALIFIED — every budget in this paper is reported as measured file bytes, never as the estimate. |
| M2 | Latency numbers are logical activation, not physical I/O. | No page-fault counters are available without root; only bytes-touched counters are recorded. | QUALIFIED — stated in every report; no cold-cache claim is made. |
| M3 | Corpus arms are measured in a single shuffled per-query order, so comparisons are paired. | R181 samples per query, identical query set and order for all arms. | MET |
| M4 | Archived results from hosted CI were not read. | No `gh` CLI or token in this environment; the artifact endpoint returns 401. | QUALIFIED — all numbers in these reports are recomputed locally from committed JSON. |

## Compression claims

| # | claim | evidence | status |
|---|---|---|---|
| P1 | The best complete archive saves ≥ 25% against the matched native positional baseline. | R173 AP: `unified_b512_best_zstd` 20,631,552 bytes vs `positional` 20,684,800 bytes. | **NOT MET** — 0.26% saving. The 25% figure holds only for the index portion, because source storage dominates the archive. |
| P2 | Block-coded positional storage beats external flat codecs. | R179 `external.comparisons`: −5.68% and −7.50% against SIMDBP and delta-varint, payload+directory against payload+directory. | QUALIFIED — two comparisons, index region only, never stated as a global win. |
| P3 | A lower-byte arm dominates a faster arm. | R179 relations: 1,256 dominance and 2,237 trade-off pairs; both are reported. | **REFUTED** — trade-offs are the common case. |

## Rejection and selection claims

| # | claim | evidence | status |
|---|---|---|---|
| R1 | A query-independent adjacency filter improves held-out P95 by more than 2× at a ~5% matched storage budget. | AP 388,344 → 105,639 µs (3.7×, +4.9% bytes); CLARK 168,171 → 72,078 µs (2.3×, +4.3% bytes). | MET on both corpora |
| R2 | A workload-trained positional selection does not achieve this at the same budget. | AP 269,475 µs (1.44×) with source reads unchanged at 168,996; CLARK 159,467 µs (1.05×). | MET — this is the central comparison of R181 |
| R3 | The complete pair index is the strongest but unaffordable option. | AP P95 20,322 µs at +119.1%; CLARK 7,400 µs at +148.2%. | MET |
| R4 | 64-bit document fingerprints are useless for phrase rejection at this scale. | 0.5% of candidates rejected; CLARK arm dominated; AP advantage within noise. | MET — negative result, retained. |
| R5 | Pair selection is submodular and greedy is near-optimal. | No submodularity proof exists; `exact_gap` measures the gap only over the top 12 terms. | **NOT CLAIMED** — the paper says "greedy with a measured gap on a reduced set", never "submodular". |
| R6 | Rejection benefits transfer across corpus types. | Same structure, same budget rule, same direction on AP (news revisions, 10,009 documents) and CLARK (1,161 dated articles). | QUALIFIED — two English news corpora; no transfer of a *fitted* policy between corpora was demonstrated, and none is claimed. |

## Execution claims

| # | claim | evidence | status |
|---|---|---|---|
| E1 | The planner chooses the cheapest mode per query and never a mode it cannot execute. | `test_planner.py`: no positions without full coverage, no pair promises from an unindexed pair in a selective index, zero survivors for a missing pair in a complete index. | MET |
| E2 | Planned execution beats a fixed strategy at equal storage. | R182 `planner` vs `source` and `pairs_source` on the same archives. | see `research/rounds/round-182/report.md` for the measured outcome |
| E3 | Phrase-level joint selection beats per-term selection. | R183 `joint_coverage` vs `additive` and `independent_df`. | see `research/rounds/round-183/report.md` for the measured outcome |

## Claims that must not appear

* "25% archive savings" without the phrase "for the index region".
* "Submodular" or "greedy is optimal within (1−1/e)".
* Any cold-cache, page-fault or physical I/O statement.
* Any result from the AP-100,000 or 74,364-revision scale point; it was never re-measured.
* Any hosted-CI number that is not present in a committed local result file.
* "Zero false negatives" as a property of the whole system: it is a property of the filter,
  conditional on exact verification, and the paper says so.