# ACMSE results section (draft)

Proposed title: **Which positional representation earns its bytes? Cost-based
selective materialisation for exact historical retrieval with byte-exact
reconstruction**

Positioning: measurement/systems paper. No new data structure, no asymptotic claim.

## Research questions

* **RQ1** Does cost-based, workload-trained selective materialisation of positions
  strictly improve the storage–latency frontier of an exact historical retrieval
  system?
* **RQ2** Do block-addressable posting lists pay for their directory when applied to
  *positions* rather than document ids?
* **RQ3** Does tiering the archive by "heat" (a native positional mirror over the most
  serviced contents) pay?
* **RQ4** How do established integer encodings compare, size-wise, on the same
  postings?
* **RQ5** Does the system stay exact under adversarial data and queries?

## Setup

AP NewsEdits (10,009 revisions; 44,833 terms; 1,789,540 document–term pairs;
4,070,728 positions) and CLARK (1,161 revisions). Archive = one SQLite file with all
structures charged via `dbstat`; source layer = RLZ-style bounded marginal frames;
ranking = BM25 with k1 = 1.2, b = 0.75 at a historical cutoff; every ranking compared
with native FTS5 on the same snapshot and every reconstructed revision compared byte
for byte. 640 executions of a frozen 160-query × 4-cutoff plan per configuration,
warm cache, 2 vCPU.

## RQ1: cost-based selection (AP, 10,009 revisions)

| Configuration | Archive MB | p95 ms | 
|---|---:|---:|
| Frequency postings only | 14.08 | 24.27 |
| Trained selective, 1% budget (20 terms) | 14.22 | 12.68 |
| **Trained selective, 10% budget (22 terms)** | **14.50** | **7.05** |
| Cost-aware document frequency, 1% (104 terms) | 14.27 | 21.62 |
| Document-frequency top-512 | 18.66 | 12.58 |
| Document-frequency 40% budget (12,955 terms) | 20.79 | 17.38 |
| Adaptive signed corrections (R167/R169) | 18.58 | 2.18 |
| Native positional FTS5 | 20.68 | 2.78 |

Answer: **yes, strictly.** +3.0% storage buys a 3.4× p95 reduction at the 10% budget,
and +1.0% storage already buys 1.9×. Every statistics-only policy either wastes
storage or fails to reduce latency; the best of them (cost-aware document frequency)
is 3.1× slower than the trained point at comparable size.

CLARK shows the same shape: 5.01 MB / 8.22 ms (frequency) → 5.07 MB / 3.06 ms
(trained, 2.7×) → 7.26 MB / 1.56 ms (unified b64) → 7.44 MB / 1.53 ms (native-free
point). Two independent runs of the trained arm gave 3,258 and 3,059 µs on CLARK and
7,054 and 7,126 µs on AP, so the effect is stable while individual arms vary.

## RQ2: block-addressable positions

| Layout | Bytes with 24 B/term rows | Random access |
|---|---:|---|
| b512 `best` + Zstd blocks + directory (ours) | 9,320,643 | yes |
| flat SIMD-BP128 of the same data | 9,817,431 | no |
| flat delta-varint | 9,989,190 | no |
| R172 single Zstd blob | 10,074,904 | no |

Answer: **yes, narrowly** — 5.1% smaller with every term row charged on both sides,
and it is the only layout that can decode one block without touching the rest of the
term. The margin comes from Zstandard on top of value packing, not from blocking
itself: payload alone is 7,747,843 B, and the directory adds 496,808 B (6.4%).

Block size trade-off on the same data (positions only, payload + directory):
b32 2.63 → b128 2.10 → b256 2.07 → b512 2.03 bytes per occurrence, with p95 rising
from 3.4 ms (unified b32) to 7.7 ms (unified b512). Larger blocks buy storage and
lose latency.

## RQ3: heat-based tiering

| Layout | Archive MB | p95 ms |
|---|---:|---:|
| Trained selective, no mirror | 14.50 | 6.52 |
| + native mirror of top 256 contents | 15.65 | 6.00 |
| + top 1024 | 17.99 | 5.42 |
| + top 4096 | 24.36 | 3.63 |
| Native positional FTS5 (global) | 20.68 | 2.78 |

Answer: **no.** Mirroring duplicates content already in the source frames. At 4096
contents the layout is 18% larger and 31% slower than simply indexing everything
natively. At 256 contents it buys 0.5 ms for 1.15 MB. The service-cost distribution is
smooth: there is no hot/cold cliff to exploit.

## RQ4: external encodings (bytes only, equal term metadata)

| Data | Ours | Best external | Margin |
|---|---:|---:|---:|
| docids + tf | 3,048,885 | Elias–Fano 4,193,814 | 27.3% smaller |
| docids + tf + positions | 9,320,643 | SIMD-BP128 flat 9,817,431 | 5.1% smaller |

Answer: our structures are smaller than the published layouts used raw, but the
published layouts decode far faster (SIMD-BP128 is a vectorised C kernel; ours is
Python over Zstandard frames). **No latency comparison against them is claimed.**

## RQ5: exactness under adversarial input

261 oracle-checked rankings across seven synthetic suites (empty documents,
duplicates, NFC/NFD and case folding, 20,000-token insertion followed by collapse to
four tokens, 500-fold phrase repetition, unrelated revisions, cutoff boundaries at
1/2/n−1/n) — all exact, all sources byte-identical. Non-UTF-8 input is refused at
build time. Corrupted block bodies and directories are detected incidentally; a
corruption that still parses would be returned silently, because the format has no
checksum (fix cost: 8 B/term = 358,664 B on AP).

## Best Pareto-optimal configurations

| Purpose | Configuration | Archive | p95 |
|---|---|---:|---:|
| Cheapest exact archive | frequency only | 14.08 MB | 24.27 ms |
| Cheapest point with real latency | trained selective 1% | 14.22 MB | 12.68 ms |
| **Recommended** | trained selective 10% | 14.50 MB | 7.05 ms |
| Positions replace postings (unified b32) | R173 unified b32 | 21.41 MB | 3.42 ms |
| Fastest with exact reconstruction | adaptive signed corrections | 18.58 MB | 2.18 ms |

Note: "cheapest point with real latency" everywhere in this table is *within this
system*; native FTS5 alone (20.68 MB / 2.78 ms) is faster than every configuration
that carries a reconstructible source, and cannot return a source byte.

## Threats to validity

1. **Two corpora, one size each.** AP at 10,009 revisions and CLARK at 1,161. AP at
   74,364 exists only as a CI run whose artifact could not be downloaded.
2. **Between-run variance up to 25%** for the same configuration on this machine;
   within-run CV 1.3–4.8%. All headline effects are ≥ 2.5×; the 5.1% size margin is
   a single-run figure and should be replicated.
3. **Warm cache only**, logical byte activation, no physical I/O instrumentation.
4. **The query workload is the source of the value model.** The trained policy is
   fitted on a hash-separated third of the frozen plan; with a different workload the
   selected terms would differ. This is a property of any workload-trained index and
   is reported, not hidden.
5. **BM25 coefficients are fixed** (k1 = 1.2, b = 0.75); coefficient sensitivity was
   verified on the formula but not plumbed through the system.
6. **Python-level decoding.** Absolute latencies are not competitive with
   C implementations; only relative comparisons within the system are meaningful.
7. **The source layer is held constant.** R173–R177 optimise the index, not the
   source recipe; conclusions are conditional on the R149 marginal recipe.

## What the paper should claim, in one paragraph

For versioned text archives that must return exact historical rankings *and* exact
historical bytes, the choice that matters is which terms carry positions, and that
choice should be made against measured marginal bytes and an explicit
candidate-rejection model rather than against document frequency. On two corpora this
converts a 3% storage increment into a 3.4× latency improvement and dominates both the
frequency-only archive and every statistics-only selection policy tested; block
addressing makes the resulting positional layer addressable at a 6% directory
surcharge; and neither full positional indices nor heat-tiered native mirrors pay for
themselves in this setting.
