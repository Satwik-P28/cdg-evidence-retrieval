# R122: Compact temporal postings with article-local ordinals and shared blocks

**Status: PASS. 13 tests and original-source [CI 45291178844](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45291178844).**

R121's 58% logical coalescing still lost to richer native positional FTS5
in physical bytes. Test six layouts: global and article-local unsigned
varints, per-term adaptive raw/Zstandard frames, shared front-coded 4/16
KiB estimated-size groups, and shared 4 KiB groups with frequent terms
partitioned into 512-generation buckets (at least 128 intervals). Buckets
duplicate overlapping intervals. A single ordered SQLite WITHOUT ROWID
block directory uses predecessor lookup; no extra per-term dictionary row.
All arms retain identical source-free version/article metadata; source
payload, positions, online updates and WAL excluded. Compare R121 packed
coalesced and native historical FTS5 in the same run, plus independent
active-only native oracles. Verify every term and stored interval, every
stored temporal bucket, exact active counts for tested queries, ranks and
logical encoded/decoded bytes per query term. No cross-query decoded block
cache. Three randomized warm timing passes, prepared active sets outside
timing. All methods are established compression/indexing techniques;
this is a measured layout combination, not a novelty claim. Same corpus
and query plan as R121; no new holdout, no published system reproduction.

## Results

445 articles, 2,504 revisions, 43,147 terms and 316,448 coalesced intervals. Each of the six compact representations round-tripped all persisted intervals (1,898,688 across six arms); every stored partition was compared with the expected overlap selection, and queried active TF maps matched original source-derived maps. 412 rank checks and 2,446 ranked positions per method across four cutoffs, zero observed score error. Three randomized warm passes.

| Layout | SQLite B | Block directory rows | Final median rank us | Final common-term median us |
|---|---:|---:|---:|---:|
| global_varint | 3,911,680 | 43147 | 69.64 | 1872.53 |
| local_varint | 3,063,808 | 43147 | 59.71 | 1598.45 |
| local_adaptive | 2,420,736 | 43147 | 61.80 | 1602.12 |
| shared4k | 2,519,040 | 525 | 148.01 | 1617.18 |
| shared16k | 1,286,144 | 128 | 407.83 | 1760.70 |
| shared4k_time | 2,674,688 | 406 | 156.03 | 1034.33 |
| packed_coalesced | 5,353,472 | - | 36.46 | 501.17 |
| native_history | 4,657,152 | - | 65.23 | 727.27 |

Shared16k is 72.38% smaller than the richer native full positional index, but final median rank latency 407.828 us versus 65.227 us native and 61.802 us local_adaptive. Local_adaptive is 48.02% smaller than native and comparable on overall warm medians, but its final common-term median 1,602.117 us is more than twice native's 727.274 us. Native active-only comparator 34.491 us final overall and 259.847 us common terms, not a historical archive. No feature-equivalent superiority to positional FTS5. Local ordinal coding reduces physical bytes versus global varints by 21.68%. Adaptive raw/Zstd avoids tiny frame overhead. Shared groups remove most per-term rows, but physical size is not monotone in estimated group size. SQLite page/overflow accounting must be measured before assigning causality.

### Logical query work at final cutoff

| Layout | Activated encoded B | Decoded block B | Posting intervals examined |
|---|---:|---:|---:|
| global_varint | 262409 | 262282 | 44309 |
| local_varint | 179211 | 179084 | 44309 |
| local_adaptive | 78542 | 179084 | 44309 |
| shared4k | 246812 | 474491 | 44309 |
| shared16k | 850634 | 1635684 | 44309 |
| shared4k_time | 263443 | 461309 | 20470 |

Shared16k decodes 9.13x the logical block bytes of local_adaptive, without cross-query caching. Temporal bucket arm reduces examined intervals by 53.80% at final cutoff, but expands physical storage versus shared4k and does not reduce median rank latency. These counters are logical returned/decoded payload, not physical disk I/O. Partitions duplicate intervals and include final-corpus knowledge; no online maintenance claim.

## Decision

Retain local_adaptive and shared16k as distinct term-only Pareto candidates, not native positional replacements. Reject fixed 512-generation partitioning as a general improvement in this implementation. The next experiment should isolate SQLite page layout and front-coded scan overhead, use a native integer decoder, compare hybrid short-list direct/rare-term shared groups and bounded caching, and then test positional parity. All compression primitives and temporal coalescing are established. Same corpus and synthetic global ingestion order, no new holdout or authentic access trace; no source payload or transaction costs in this index-only study.
