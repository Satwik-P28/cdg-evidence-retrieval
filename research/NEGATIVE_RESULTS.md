# Negative results

Retained deliberately: each of these cost time and each is more useful to a reader
than another positive table. All numbers are AP 10,009 at 640 rank checks per
configuration unless stated, warm cache, same frozen query plan.

## N1. The R172 document-frequency selection policy is cost-ineffective

Selecting the 32 highest-document-frequency terms was the previous round's policy.
It spends 12.6% more archive bytes than frequency-only and makes p95 *worse*.

| Arm | Archive B | p95 µs |
|---|---:|---:|
| Frequency only (baseline) | 14,082,048 | 24,267 |
| R172 selective top-32 by document frequency | 15,392,768 | 25,825 |
| R174 `df_topk` k32 (fixed count) | 15,851,520 | 25,185 |
| R174 `df_topk` k128 | 16,965,632 | 21,228 |
| R174 `df_topk` k512 | 18,657,280 | 12,580 |
| R174 `df` greedy 1% budget (104 terms) | 14,266,368 | 21,621 |
| R174 `df` greedy 40% budget (12,955 terms) | 20,787,200 | 17,380 |

Cause: frequent terms are frequent in *documents*, but a phrase needs every term
present, so frequently-posted terms are rarely the ones whose positions reject
candidates. Charging cost does not fix the value model; the value model has to change.

## N2. Reduced knapsack and local search do not beat ratio-greedy

| Arm | Terms | Archive B | p95 µs |
|---|---:|---:|---:|
| `df` ratio-greedy, 5% budget | 615 | 14,970,880 | 22,527 |
| `df` reduced knapsack, 5% budget | 250 | 14,495,744 | 20,133 |
| `df` local search from the greedy start | 615 | 14,970,880 | 29,209 |
| `train_candidates` greedy, 10% (shipped) | 22 | 14,503,936 | 7,054 |
| `train_candidates` knapsack, 10% | 22 | 14,503,936 | 6,689 |
| `train_candidates` local search, 10% | 22 | 14,503,936 | 6,771 |

Knapsack finds a cheaper set than greedy for the *same bad value model* (14.50 MB vs
14.97 MB) and is still 2.9× slower than the trained policy. Local search is harmful on
the `df` model (22,527 → 29,209 µs) and neutral on the trained model (7,054 vs 6,689 /
6,771 µs, inside the 25% between-run noise). With 44,833 candidate terms and 20–30
selectable ones, the combinatorial structure is too shallow for these methods to
matter: the value model, not the optimizer, decides the outcome.

## N3. Submodularity of the selection objective is false

The rejection kernel needs `len(covered) >= 2` offsets of a phrase. One covered
offset rejects nothing, two reject everything for that phrase, three add only a
tightened intersection. Benefit is increasing but not diminishing, so ratio-greedy
has no submodular guarantee. It is used anyway, and the report says so; no
approximation ratio is claimed.

## N4. Regional (hot-set) native positional mirroring loses at every size tested

| Layout | Archive B | p95 µs |
|---|---:|---:|
| Trained selective, no hot region | 14,503,936 | 6,517 |
| + hot 256 contents | 15,650,816 | 6,000 |
| + hot 1024 contents | 17,985,536 | 5,417 |
| + hot 4096 contents | 24,363,008 | 3,626 |
| Native positional FTS5 (global, no selection) | 20,684,800 | 2,775 |

Mirroring duplicates content already present in the source frames. At 4096 contents
the layout costs 18% more than the global native index and is 31% slower. This kills
the "tier the archive by heat" idea for this corpus shape; it is not a general
refutation, and it is stated as such.

## N5. Term-level unification of selected postings is negligible at small selections

Dropping the duplicate posting row for the 22 selected terms saves 36,864 B (0.25%)
with no measurable latency change. R173 showed unification is worth 3.06 MB only when
*all* terms carry positions — and that configuration costs 21.4 MB in total and loses
on latency.

## N6. Full positional custom archives are dominated

| Arm | Archive B | p95 µs |
|---|---:|---:|
| R172 full custom positions | 23,080,960 | 39,314 |
| R173 duplex b128 (frequency + all positions) | 24,096,768 | 7,687 |
| R173 unified b512 | 20,631,552 | 7,697 |
| R173 unified b32 | 21,413,888 | 3,418 |
| Native positional FTS5 | 20,684,800 | 2,775 |

Both custom full-positional designs are worse than native FTS5 on at least one axis
and never better on both. Larger blocks help storage (b512) and hurt latency; the
crossover is real and not in our favour.

## N7. Codec choices that lost

| Codec / compression | Bytes per occurrence |
|---|---:|
| b512 `best` + Zstd (best) | 2.025 |
| b128 `best` + Zstd | 2.105 |
| b512 delta-varint, raw | 2.622 |
| b128 variable-width, raw (worst) | 3.210 |

Raw (uncompressed) blocks are 30–58% larger; per-block Zstandard is what makes the
layout competitive, at the cost of a Python-level decompression per block.

## N8. The held-out split does not discriminate policies (methodological negative)

Held-out is 12 queries × 4 cutoffs on AP. Every arm, including frequency-only,
measures p95 1.17–1.28 ms there because those queries contain 22 candidate source
reads that positions barely change. The split passes correctness but has no power to
rank configurations; only the full-plan numbers are used as evidence.

## N9. Corruption of a well-formed block is silent

`R177` found that a corrupted posting block whose bytes still parse is returned
without error: the archived format has no checksum. Two byte-pattern corruptions were
caught incidentally (`ValueError: empty block header`, `ValueError: truncated
varint`), which is luck, not a guarantee. Cost of a fix: 8 B per term = 358,664 B
(2.5% of the AP archive). Not implemented; recorded as a defect.

## N10. Non-UTF-8 input is refused, not handled

`b"alpha\xff beta"` raises `UnicodeDecodeError` at build time. Correct in the sense
that nothing is silently mangled; a limitation in the sense that a real archive with
Latin-1 legacy pages cannot be ingested at all until a policy is configured.

## N11. Between-process variance is large enough to invalidate small claims

The same frequency-only configuration measured 24,267 µs (R173/R174) and 19,353 µs
(R175) p95 on the same machine and plan — a 25% swing. Within a process, five
repetitions vary only 1.3–4.8% (R177). Any claim resting on a <25% between-run
difference is unfounded, which is why the size comparisons are described as modest
and the latency comparisons are all ≥ 2.5×.

## N12. A 2% budget is not on the frontier, and neither is anything above 10%

Across the six requested budgets the trained policy saturates: 20 and 22 terms are
selected at 5%, 10%, 20% and 40%, so those four arms are the same archive
(14,503,936 B on AP). The 1% and 2% points are distinct (20 terms) and slower
(12,650 / 11,364 µs versus 7,054–7,263 µs), and a 40% budget changes nothing. The
usable region for this selection method is therefore 1–10% of the frequency archive;
the larger budgets in the brief are dominated by the smaller ones and are reported as
such rather than as a widening frontier.
