# Baseline comparison

Two kinds of baseline appear here, kept strictly apart:

* **Feature-matched**: the baseline answers the same question (exact historical
  keyword/phrase ranking at a cutoff, plus exact source reconstruction). Only SQLite
  FTS5 qualifies, together with our own earlier rounds.
* **Component**: the baseline compresses the same integer data but cannot do the task.
  PISA, FastPFor, SIMD-BP128, Elias–Fano, Roaring, Lucene postings, RLZ. These are
  compared on **bytes only**, never on features or end-to-end latency.

Mixing the two would manufacture a win. No such claim is made anywhere in this
programme.

## Feature matrix

| System | Exact historical cutoff ranking | Exact source bytes back | Phrase/positions | Append revisions | Static index cost reported |
|---|---|---|---|---|---|
| **This archive (R173–R177)** | yes (oracle-checked) | yes (byte-compared) | yes (block positions) | yes (kind 1 deltas) | yes, all structures |
| SQLite FTS5, native | yes, via sharded snapshots | no (index only) | yes | yes | yes |
| PISA / FastPFor / SIMD-BP128 / Elias–Fano / Roaring | no | no | no | no | yes |
| Lucene postings | no | no | yes | yes (segments) | yes |
| RLZ (Kuruppu / Hoobin) | n/a | yes (decompress) | no | no | n/a |
| Time-travel sharding (Anand et al.) | yes | no | yes | yes | yes |

## AP NewsEdits, 10,009 revisions — feature-matched frontier

Archive bytes are the complete SQLite file with all structures charged; latency is
p95 over 640 executions of the frozen 160-query × 4-cutoff plan (warm cache, 2 vCPU).

| Configuration | Archive B | p95 µs | Bytes per revision | Source in R |
|---|---:|---:|---:|---|
| R172 frequency only | 14,082,048 | 24,267 | 1,407 | R173/R174 |
| R175 frequency only (same config, other run) | 14,090,240 | 19,353 | 1,408 | R175 |
| **R174/R175 trained selective (22 terms)** | **14,503,936** | **7,054 / 6,517** | **1,449** | R174, R175 |
| R175 `sel_unified` (postings dropped for selected terms) | 14,467,072 | 6,804 | 1,446 | R175 |
| **R174 trained selective at a 1% budget (20 terms)** | **14,221,312** | **12,684** | **1,421** | R174 |
| R174 `df-1%` (cost-aware document frequency) | 14,266,368 | 21,621 | 1,426 | R174 |
| R172 selective top-32 terms | 15,392,768 | 25,825 | 1,538 | R173 |
| R175 `sel + hot256` | 15,650,816 | 6,000 | 1,564 | R175 |
| R175 `sel + hot1024` | 17,985,536 | 5,417 | 1,797 | R175 |
| R172 adaptive signed corrections | 18,583,552 | 2,182 | 1,857 | R173 |
| R174 `df_topk k512` | 18,657,280 | 12,580 | 1,864 | R174 |
| **Native positional FTS5** | **20,684,800** | **2,775** | **2,067** | R173 |
| R173 unified b32 (positions replace postings) | 21,413,888 | 3,418 | 2,140 | R173 |
| R173 unified b512 | 20,631,552 | 7,697 | 2,062 | R173 |
| R173 duplex b128 (all terms) | 24,096,768 | 7,687 | 2,408 | R173 |
| R177 same config, 5 reps | 24,096,768 | 8,412 (median of 5) | 2,408 | R177 |
| R172 full custom positions | 23,080,960 | 39,314 | 2,306 | R173 |
| R175 `sel + hot4096` | 24,363,008 | 3,626 | 2,434 | R175 |

Reading of the frontier: frequency-only is cheapest but slow; the trained selective
point improves p95 3.4× for +3.0% bytes; the adaptive and native points are 2.5–3.2×
faster than the trained point but cost 28–43% more bytes. Nothing in the archive
beats native FTS5 on latency, and native FTS5 cannot return a source byte.

## CLARK, 1,161 revisions

| Configuration | Archive B | p95 µs | Source in R |
|---|---:|---:|---|
| Frequency only | 5,009,408 | 8,220 | R173 |
| Trained selective (17 terms) | 5,074,944 | 3,030 | R174 |
| R172 adaptive | 6,021,120 | 1,993 | R173 |
| R173 unified b64 | 7,262,208 | 1,556 | R173 |
| R173 unified b128 bp raw | 7,438,336 | 1,532 | R173 |
| R174 `cf-40%` | 7,479,296 | 1,806 | R174 |
| R177 duplex b128, 5 reps | 8,212,480 | 1,764 (median of 5) | R177 |

The CLARK frontier has the same shape as AP: +1.3% bytes for a 2.7× p95 reduction.

## Component comparison (bytes only, AP 10,009)

Equal term metadata charged on both sides; see R176 for the full derivation.

| Data | Ours | Best external | Margin |
|---|---:|---:|---:|
| Document ids + tf (frequency index) | 3,048,885 | Elias–Fano 4,193,814 | 27.3% smaller |
| Document ids + tf + positions | 9,320,643 (with 24 B/term rows) | SIMD-BP128 flat 9,817,431 | 5.1% smaller |

Both margins come from value packing plus Zstandard over established integer encodings.
Neither is a feature win, and neither is a latency claim: raw SIMD-BP128 decodes far
faster than our Python-level block decoder.

## What a reviewer should check first

1. That the frequency-only row uses the same query plan, cutoffs and oracle as every
   other row (it does: `query_plan_sha256` is identical across rounds).
2. That the trained selection saw only the training third of the plan (it did:
   `split` in `experiments/round-174/cost_selection.py`, split manifests in the JSON).
3. That "archive bytes" includes directories, lexicons, term rows and SQLite page
   slack (it does: `dbstat` sums, plus 24 B per term row where applicable).
4. That between-process variation is ~25%, so the 3.4× and 2.5× gaps are real but the
   6% size margin in the component table is a single-run figure.
