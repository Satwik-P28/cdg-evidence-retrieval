# R176: external methods and competitive baselines

Status: implemented, measured locally on AP 10,009. Clone provenance and licences in
`external.md`. CI matrix in `cdg-r176-external.yml`.

Parent commit `fce2b81`.

## What was done

1. Cloned and pinned five external repositories (`external.md`), read the codec
   headers that define the layouts we compare against, and recorded commit SHAs,
   licence files and the specific constants used.
2. Reimplemented the published layouts independently — Elias–Fano, SIMD-BP128
   (128-value blocks, one width per block), Roaring (array containers up to 4096
   values, then 8192-byte bitmaps) and delta-varint — and validated them against
   known-answer size formulae in `tests/test_external_codecs.py` (16 tests).
3. Applied all of them to the **same** logical postings extracted from this
   archive's own source bytes (44,833 terms, 1,789,540 document pairs, 4,070,728
   positions, corpus of 10,009 revisions).

No external code is vendored; no external system was executed. These are size
comparisons of published layouts on our data, nothing more.

## Results (bytes, AP 10,009)

### Frequency index: document ids + term frequency

Both sides need term-level metadata to find a term's list, so every external figure
below also carries our lexicon's cost (724,992 B, i.e. 16.2 B per term); the column
"payload only" shows the same figure without that shared charge.

| Encoding | Bytes with term metadata | Payload only | vs ours |
|---|---:|---:|---:|
| Elias–Fano (no skip pointers) + varint tf | 4,193,814 | 3,468,822 | −27.3% |
| SIMD-BP128 (128-value blocks) + varint tf | 4,275,134 | 3,550,142 | −28.7% |
| delta-varint + varint tf | 4,621,686 | 3,896,694 | −34.0% |
| Roaring bitmaps + varint tf | 6,400,960 | 5,675,968 | −52.4% |
| **R158 frequency index (ours, postings + lexicon)** | **3,048,885** | 2,323,893 | — |

Our frequency index is 27.3% smaller than the best uncompressed external layout on
the same postings, because it also applies value packing and Zstandard. The external
layouts are designed for *decoding speed*, which this round did not measure; the
comparison is therefore about space only and must not be read as a latency claim.

Roaring loses badly here for a structural reason: at 10,009 documents a term's list
crosses the 4096-value array threshold rarely, but the corpus-universal terms that
do cross it pay a full 8 KiB bitmap for a few thousand ids.

### Positional index: document ids + tf + positions

Every layout needs one row per term in the archive, so the comparison charges both
sides the same 24 B per term (44,833 terms = 1,075,992 B); the middle columns show
the unshared parts.

| Layout | Bytes with 24 B/term | Payload + directory only | Random access | Block activation |
|---|---:|---:|---|---|
| **R173 b512 `best`+Zstandard blocks** | **9,320,643** | 8,244,651 (payload 7,747,843 + directory 496,808) | yes | yes |
| External flat SIMD-BP128 (docid + tf + position gaps) | 9,817,431 | 8,741,439 | no | no |
| External flat delta-varint | 9,989,190 | 8,913,198 | no | no |
| R172 single Zstandard blob | 10,074,904 | 8,998,912 | no | no |

The block layout is **5.1% smaller than the best uncompressed external layout once
every term row is charged on both sides**, and it is the only one of the three that
can decode a single posting block without touching the rest of the term. Without the
shared row charge the two are 8,244,651 and 8,741,439, i.e. the same conclusion at
6% margin; the margin is modest either way and comes from Zstandard on top of value
packing, not from the blocking itself.

## What this does and does not establish

**Established.** (a) On this corpus the published integer codecs, used raw, are
larger than our compressed block layout for positions and larger than our frequency
index for docids. (b) A 6% directory surcharge is the price of block addressing, and
it still leaves the block layout ahead of an unaddressed external layout.

**Not established.** That our layout is faster than PISA/FastPFor — it was not
benchmarked against them, and SIMD-BP128 decoding is typically 5–10× faster than
Python-level block decoding. Our latency claims remain *within this system*, against
native FTS5 and our own prior rounds.

**Feature mismatch, stated plainly.** PISA, FastPFor, SIMD-BP128, Elias–Fano, Roaring
and Lucene postings have no historical retrieval, no exact source reconstruction and
no time-travel phrase semantics. RLZ compresses strings but has no index, no cutoffs
and no positions. Only SQLite FTS5 (with our sharding) is feature-matched. Any
"beat PISA" claim would be false, so none is made.

## Reusable techniques identified for our own design

1. **Elias–Fano's two-level structure** is the same idea as our block directory
   (low bits + unary high bits ≈ first-cid directory + payload offsets) and is
   measurably better than plain delta-varint when the universe is dense; a future
   round could replace the directory's delta-varint first-cids with an Elias–Fano
   sequence and save roughly half of the 496,808 directory bytes.
2. **PISA's partitioning** (Ottaviano & Venturini 2014) is the principled version of
   the block-size sweep in R173: choose boundaries by dynamic programming over
   clustering rather than a fixed 512. R173's sweep already shows the gain from
   larger blocks is small (9.32 MB at b512 versus 9.7 MB at b128 in the storage
   sweep), so expected additional saving is modest.
3. **Skip/forward pointers** (folly's `kSkipQuantum`) are what our directory already
   provides at block granularity; nothing new to import.
4. **Roaring's container switch** has no analogue worth importing here: our postings
   are per-term lists, not per-document sets.

## Limitations

* Size-only; no external binaries were built, executed or timed.
* Single corpus size, single machine.
* The Elias–Fano baseline charges no skip metadata, which favours it; the conclusion
  survives that optimism, which is why it is stated.
* The Roaring baseline charges a container directory (4 bytes per container) but no
  run containers, which favours Roaring on long runs; AP postings have few long runs,
  so the bias is small but present.
