# R177: adversarial and held-out evaluation

Status: implemented, executed. Synthetic suites, corruption probes, coefficient
validation and five-repetition real-corpus runs. CI matrix in
`cdg-r177-adversarial.yml`.

Parent commit `d14ba43`. Configuration under test: R173 block positions for **all**
terms, blocks of 128 postings, per-stream `best` codec, per-block Zstandard, over the
R149 bounded-marginal source archive and the R158 frequency tape (the `duplex_b128`
arm, the storage-efficient positional point).

## Synthetic suites (261 rank checks, all exact)

Every suite verifies (a) every revision reconstructs byte-exactly and (b) every
ranking matches the native FTS5 oracle at every cutoff, including cutoff boundaries
at 1, 2, n−1 and n.

| Suite | Revisions | Cutoffs | Rank checks | p95 µs |
|---|---:|---|---:|---:|
| Empty documents (half the revisions empty) | 12 | 2, 6, 12 | 45 | 87.1 |
| Duplicated contents (30 identical revisions) | 34 | 10, 30, 34 | 36 | 111.9 |
| Unicode normalisation and case folding | 6 | 3, 6 | 36 | 54.4 |
| Large insertions and deletions (90 KB growth, collapse to 4 tokens) | 5 | 1, 2, 4, 5 | 48 | 107.3 |
| Repeated phrases (500 repeats per document) | 4 | 1, 2, 3, 4 | 48 | 312.8 |
| Unrelated revisions (no shared vocabulary) | 10 | 5, 10 | 24 | 80.6 |
| Historical cutoff boundaries | 9 | 1, 2, 8, 9 | 24 | 124.7 |

Notable sub-results:

* **Unicode.** NFC and NFD spellings, `ß`, dotted capital `İ` and a zero-width space
  all produce rankings identical to native FTS5, including a query written in NFD
  matching a document stored in NFC. The system inherits FTS5's `unicode61` folding
  and does not diverge from it on these cases.
* **Duplicates.** Thirty revisions sharing one content id are ranked individually
  (one hit per revision) with the same scores as the oracle; the content-level
  deduplication does not leak into historical ranking.
* **Large edits.** A 20,000-token insertion followed by a collapse to four tokens
  leaves no stale postings: the four-token revision is the only hit for `filler` at
  the final cutoff.
* **Repeated phrases.** `alpha beta` 500× and `beta alpha` 500× in separate
  documents produce exact counts (500 each) and correct relative ordering, which is
  the case where a positions-only heuristic could over-count.

## Failure modes found

| Input | Observed behaviour | Assessment |
|---|---|---|
| Non-UTF-8 source bytes (`b"alpha\xff beta"`) | `UnicodeDecodeError` at build time | **Correct but undocumented**; the builder refuses rather than silently replacing bytes. Needs a configured policy (`strict` / `replace` / `latin-1`) before ingesting real archives. |
| Corrupted posting block body (zeros) | `ValueError: empty block header` on the first decoded block | Detected |
| Corrupted block directory (0xFF fill) | `ValueError: truncated varint` | Detected |
| Corrupted block that still parses | **silently wrong** | Not detected: there is no checksum. A truncated BLAKE2b digest per term would cost 8 B × 44,833 = 358,664 B (2.5% of the AP archive) and is *not* part of the format. |

The last row is a genuine integrity gap in the archived format, reported as such. The
detections above are incidental, not designed: they come from header and varint
validation.

## BM25 coefficients

The scorer is standard BM25 (`positive_score(tf, dl, avg, idf)`) with pinned
constants `k1 = 1.2`, `b = 0.75`. The formula was validated for non-unit coefficients
(`k1 ∈ {0, 1.2, 10}`, `b ∈ {0, 0.75, 1}`) and for `tf = 0` against an independent
double-precision implementation (9 cases, agreement < 1e-12). **The system does not
expose these constants**; changing them requires plumbing through `active_rank`,
which no round has done. This is a limitation of the evaluation, not a proof that
ranking is coefficient-invariant.

## Real corpora, five repetitions

Same configuration, same frozen query plan, five independently shuffled passes,
320 rank checks per pass.

| Corpus | Revisions | Archive B | p95 µs per repetition | median p95 | CV(p95) | median µs | CV(median) | Peak RSS |
|---|---:|---:|---|---:|---:|---|---:|---:|---:|
| AP NewsEdits | 10,009 | 24,096,768 | 8,412 / 8,436 / 8,237 / 8,006 / 8,773 | **8,412** | 3.0% | 461 / 436 / 402 / 411 / 428 | 4.8% | 140 MiB |
| CLARK | 1,161 | 8,212,480 | 1,727 / 1,783 / 1,771 / 1,732 / 1,764 | **1,764** | 1.3% | 318 / 323 / 311 / 322 / 310 | 1.7% | 59 MiB |

1,600 rank checks per corpus, zero score error.

**Uncertainty statement.** *Within* a process, repeated measurement is tight (CV
1.3–4.8%). *Between* processes the same configuration varies much more: the
frequency-only arm measured p95 19,353 µs in R175 and 24,267 µs in R173/R174 on the
same machine and plan. Differences between configurations smaller than ~25% are
therefore not evidence, and no finding in R173–R177 rests on one.

## Cold and warm cache

Dropping the page cache requires root, which this environment lacks. Repetition 1 is
the coldest measurement available and is **not** a cold-cache guarantee. All numbers
above are warm-cache. No physical I/O instrumentation exists in this environment;
`blocks_decoded` and `source_reads` are logical counters.

## Held-out corpora not obtained

CPython documentation history and BIP history were not ingested: both need a git
history download plus per-revision extraction, and the remaining budget went to
correctness. They remain the first item in the next-experiment list; the runner takes
any event list, so no new code is needed.

## Limitations

* Synthetic fixtures are tiny (4–34 revisions): they test semantics, not throughput.
* One machine; no cache control; no NUMA or CPU-frequency control.
* Corruption testing covers two byte patterns, not systematic fault injection.
* The system refuses non-UTF-8 input; a real archive with Latin-1 legacy pages would
  fail to build.
