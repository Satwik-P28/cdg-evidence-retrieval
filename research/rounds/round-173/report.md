# R173: block-addressable positional postings

Status: implemented and measured locally on AP 10,009 and CLARK 1,161; hosted CI
matrix defined in `cdg-r173-blocked.yml` (AP 10,000, AP 100,000, CLARK).

Parent `7731bebece0afbe052ca51e4e6dfeaec0eb4f85d` (R172). Local branch
`research/round-173-r178-block-postings`. All numbers below are from one local
process per corpus, two shuffled warm passes over the frozen R158/R172 query plan
(`query_plan_sha256 c6f41c9c9b4bc59df09cbf92f79e90ea05e76ea5b19426584172d58dbcc91e2d`
for AP 10,009, 80 queries × 4 cutoffs × 2 passes = 640 executions).

## Question

R172 stored one delta-varint position list per term and decoded the whole list on
every query, so its selective policy could not reject a candidate and its
"all positions" control was slower than the native index. Can independent
fixed-size posting blocks, addressed through a compact document-range directory,
make positional decoding proportional to the *candidates* instead of the term?

## Representation

For each term the postings are split into fixed blocks of B document entries. A
block stores three separately addressable streams — document-id deltas,
per-document counts, position deltas — each encoded as one of:

* `dv` unsigned LEB128 deltas,
* `vw` byte-aligned per-block frame of reference (1–4 byte widths),
* `bp` bit-packed with a per-block bit width,
* `best` per-stream minimum of the three with a two-bit tag,

then optionally Zstandard-compressed per block (flag byte; kept only if smaller).

The per-term directory stores block first document ids, byte offsets and lengths,
delta-encoded with the same `best` stream codec. Because document ids are strictly
increasing across blocks, block *k* covers `[first_k, first_{k+1})`, so a candidate
binary-searches the directory and only the covering block is read.

Query time (`rank_blocked`) keeps R172's semantics exactly:

1. candidates come from the frequency postings (duplex) or from the rarest term's
   count streams plus block-local membership narrowing (unified);
2. for a phrase with ≥ 2 covered offsets the shifted-position intersection is the
   exact count when all offsets are covered, otherwise an upper bound that may
   reject but never accept;
3. uncovered candidates fall back to bounded source recovery, and the bound is
   asserted.

A unigram reads only the id and count streams, never positions.

`unified` archives store **no** frequency postings: the count streams are the
frequency index. `duplex` archives keep both and are charged for both.

## Native kernel

Profiling (`cProfile`, AP 10,009, unified b32) attributed 90% of phrase-query time
to `parse_block`, and inside it 26.8 s/49.2 s to stream decoding (`dec_dv`,
`dec_bp`, `dec_vw`) plus 101.4 M `list.append` calls. That is a proven computational
bottleneck, so `cdgbp.c` provides `cdg_decode_stream` (validating, 32-bit, three
codecs) and `cdg_prefix_sum`, loaded through `ctypes`; the Python decoders remain
the reference implementation and a test asserts both paths agree. With the kernel,
AP phrase p95 fell from 15,895 µs to 7,687 µs (duplex b128) — a 2.1× improvement
from ~70 lines of C. Without the kernel everything still passes (one test skips).

## Storage configuration sweep (AP 10,009, 44,833 terms, 1,789,540 doc pairs, 4,070,728 occurrences)

Exact payload + directory bytes, plus a 24 B/term row proxy; all five block sizes,
four codecs, raw and Zstandard (24 configurations, one pass):

| Block | codec | comp | position bytes | B/occurrence |
|---:|---|---|---:|---:|
| 512 | best | zstd | 9,320,643 | 2.03 |
| 256 | best | zstd | 9,494,400 | 2.07 |
| 128 | best | zstd | 9,643,104 | 2.10 |
| 512 | dv | zstd | 9,678,647 | 2.11 |
| 64 | best | zstd | 9,749,290 | 2.13 |
| 128 | bp | zstd | 9,818,675 | 2.15 |
| 128 | best | raw | 9,919,886 | 2.17 |
| 32 | best | zstd | 9,984,297 | 2.19 |
| 128 | dv | raw | 11,866,508 | 2.65 |
| 128 | vw | raw | 14,143,427 | 3.21 |

Findings: Zstandard per block always wins (b128 best: 9.92 MB raw → 9.64 MB zstd);
`best` beats `dv` by 2.8% and `bp` by 1.8%; **byte-aligned variable width loses
badly** (3.21 B/occurrence) because small position deltas pay a whole byte; larger
blocks compress better (b512 2.03 vs b32 2.20) but coarsen activation, which the
latency table shows matters more.

R172's single-blob `term_positions` table occupied 8,998,912 B for the same data,
so block addressing plus its directories costs ~3.5% storage. That is the price of
addressability and is charged in every arm below.

## End-to-end results, AP 10,009 (manifest `2788f97b…`)

| Arm | Archive bytes | index bytes | median µs | p95 µs | p99 µs | source reads | blocks read | decoded MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native positional FTS5 | 20,684,800 | — | 276.1 | 2,775.0 | 6,348.1 | 0 | 0 | 0 |
| adaptive signed (R167) | 18,583,552 | 8,085,504 | 258.1 | 2,181.5 | 4,446.3 | 0 | 0 | 0 |
| frequency (R172) | 14,082,048 | 3,784,704 | 503.0 | 24,267.3 | 107,116.4 | 7,132 | 0 | 0 |
| R172 top32 selective | 15,392,768 | 5,095,424 | 468.5 | 25,825.4 | 100,652.9 | 7,132 | 0 | 0 |
| R172 all positions | 23,080,960 | 12,783,616 | 464.8 | 39,314.2 | 69,766.0 | 0 | 0 | 0 |
| duplex b32 best zstd | 24,473,600 | 14,176,256 | 425.2 | 6,184.0 | 14,107.0 | 0 | 4,158 | 2.4 |
| duplex b128 best zstd | 24,096,768 | 13,799,424 | 421.2 | 7,687.0 | 12,419.2 | 0 | 1,802 | 4.3 |
| duplex b512 best zstd | 23,691,264 | 13,393,920 | 489.6 | 10,096.3 | 15,948.1 | 0 | 702 | 6.0 |
| **unified b16 best zstd** | 22,052,864 | 11,755,520 | 462.7 | 3,846.1 | 11,402.2 | 0 | 22,990 | 2.1 |
| **unified b32 best zstd** | 21,413,888 | 11,116,544 | 414.6 | **3,418.4** | 12,119.0 | 0 | 12,898 | 2.9 |
| unified b64 best zstd | 21,176,320 | 10,878,976 | 404.9 | 4,958.5 | 11,453.5 | 0 | 7,318 | 3.9 |
| unified b128 best zstd | 21,037,056 | 10,739,712 | 389.7 | 5,534.9 | 12,952.9 | 0 | 4,248 | 4.9 |
| unified b512 best zstd | 20,631,552 | 10,334,208 | 412.8 | 7,696.9 | 12,526.5 | 0 | 1,670 | 6.8 |
| unified b128 dv raw | 23,506,944 | 13,209,600 | 401.2 | 5,663.7 | 10,154.1 | 0 | 4,248 | 5.5 |
| unified b128 bp raw | 21,487,616 | 11,190,272 | 397.9 | 5,936.6 | 10,450.1 | 0 | 4,248 | 5.0 |

Zero score error and identical ordered rank in every arm (640 checks each, compared
with the native FTS5 oracle at four historical cutoffs).

## End-to-end results, CLARK 1,161 (manifest `1567b6c7…`)

| Arm | Archive bytes | median µs | p95 µs | p99 µs | blocks read |
|---|---:|---:|---:|---:|---:|
| native positional FTS5 | 5,992,448 | 165.8 | 2,576.7 | 3,286.7 | 0 |
| adaptive signed (R167) | 6,021,120 | 162.9 | 1,992.6 | 2,784.2 | 0 |
| frequency (R172) | 5,009,408 | 420.9 | 8,220.4 | 52,732.8 | 0 |
| R172 all positions | 7,569,408 | 309.3 | 2,223.4 | 12,233.8 | 0 |
| duplex b32 best zstd | 8,232,960 | 312.6 | 1,738.4 | 2,718.4 | 836 |
| unified b64 best zstd | 7,262,208 | 270.7 | 1,556.1 | 2,236.5 | 4,000 |
| unified b128 best zstd | 7,262,208 | 316.2 | 1,793.1 | 3,132.2 | 2,358 |
| unified b512 best zstd | 7,217,152 | 313.9 | 1,769.9 | 3,230.8 | 1,108 |
| unified b128 bp raw | 7,438,336 | 272.4 | 1,532.1 | 2,506.8 | 2,358 |

On CLARK the unified block index has the **best p95 of any exact arm** (1,532 µs,
b128 `bp` raw) against native 2,577 µs, at +24% archive bytes. On AP it does not.

## What this establishes

1. **Block addressing works as designed.** Full positional coverage stopped
   requiring whole-list decoding: source reads 7,132 → 0 while decoded bytes stayed
   at 2.1–6.8 MB of a 9.3 MB position store, and blocks read (1,670–22,990) are a
   small fraction of the 53,755 blocks stored.
2. **It repairs R172's custom positional path.** Best AP arm 3,418 µs p95 versus
   39,314 µs for R172 all-positions — an 11.5× tail improvement — and versus
   24,267 µs for the frequency arm that R172 called its system.
3. **It does not dominate native FTS5 on AP.** unified b32 is +3.5% bytes and +23%
   p95; b512 reaches byte parity (20,631,552 vs 20,684,800) but 2.8× p95. On CLARK
   the ordering reverses on p95.
4. **The unified accounting matters.** Dropping the separate frequency postings
   saves 3,059,712 B; that is what brings a fully positional archive to native
   parity at all. Duplex arms remain 3.4 MB larger.
5. **Codec ranking is decided by activation, not compression.** b512 compresses
   best and answers worst; b16 decodes least and pays block overhead. b32 is the
   AP optimum, b64–b128 the CLARK optimum.

## Negative results (retain)

* Byte-aligned variable width (`vw`) is the worst codec, 3.21 B/occurrence vs 2.10
  for `best`: sub-byte deltas dominate and fixed byte widths waste them.
* Raw (uncompressed) blocks always lose to Zstandard, even though the blocks are
  only 32–512 entries.
* Full positional materialization cannot beat the native index on AP under any
  block size or codec tested; the best it achieves is a near-tie at b512 storage
  with worse latency.
* Larger blocks help storage and hurt latency monotonically in the measured range;
  there is no configuration that is best on both.

## Limitations

* Logical byte activation only; no page-level physical I/O, cache or RSS claim.
* One machine, two warm passes, 640 rank checks per arm; the 74,364-revision cohort
  was left to CI because the AP 100,000 CI job was still running at inspection.
* Positions here cover every term. Selective coverage is R174's subject and is the
  only place block addressing can plausibly beat the native index on both axes.
* `cdg_prefix_sum` is exported but unused; stream decoding is the measured
  bottleneck, prefix sums were not.

## Commands

```
cc -O3 -Wall -Wextra -Werror -shared -fPIC experiments/round-173/cdgbp.c -o experiments/round-173/cdgbp.so
CDG_FTS_EXTENSION=$PWD/experiments/round-152/cdgfts.so PYTHONPATH=experiments/round-173 \
  python -m pytest -q experiments/round-173
CDG_BLOCK_KERNEL=off CDG_FTS_EXTENSION=... PYTHONPATH=experiments/round-173 python -m pytest -q experiments/round-173
CDG_FTS_EXTENSION=... PYTHONPATH=experiments/round-173 python research/rounds/round-173/probe.py
python experiments/round-173/blocked_positions.py --corpus ap --source external/newsedits/ap.db \
  --target 10000 --extension experiments/round-152/cdgfts.so --out experiments/round-173/ci.json
```

27 unit tests pass with the kernel; 26 pass and 1 skips without it. The probe
executes 40,000 codec round trips, 5,000 block round trips, 2,000 directory round
trips, 20,000 shifted-position checks and 23 native FTS5 phrase-oracle comparisons.
