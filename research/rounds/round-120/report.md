# R120: Active-version historical BM25 and transactional validity intervals

**Status: PASS. Six regression tests and full pinned corpus CI [45288487639](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45288487639).**

R119 heads scope filters eligible versions but uses all-history prefix BM25
statistics. R120 implements a separate active-only scoring contract: at
generation g, each article contributes exactly its newest version at or
before g to N, token total, phrase DF and candidates. A trigger on R119
ledger insertion closes the previous interval, opens the new interval and
records active N and total tokens inside the existing transaction. Independent
audit derives expected intervals and stats from source revision mapping and
native token counts.

Compare (1) reconstructing active heads for each query, (2) a prepared head
set reused at fixed cutoff (preparation excluded from timings), (3) interval
join and persisted active stats, and (4) rebuilt native FTS5 containing only
active revisions with original row IDs. Compare against R119-style prefix
statistics as a negative control. All 445 eligible articles from the pinned
Versions repository, four cutoffs, queries selected from first active index
including frequent terms, three repeated randomized warm rank-only passes.
Every active receipt is verified against exact source bytes; first-cutoff
receipts replayed in pinned and fresh snapshots after later commits. Test
five process-death stages and independently audit validity and ledger.

Physical bytes and WAL measured against R119 atomic ledger without interval
tables; native active snapshot files also charged as simple comparison.
Not a new corpus, real wall-clock ordering, observed workload, deletes,
general query grammar, physical disk I/O, or novel temporal retrieval.
Active validity intervals, temporal BM25 and historical stats are prior art:
https://github.com/MoritzStaudinger/TimIR ;
https://openscience.ub.uni-mainz.de/items/47d63035-e20a-43af-a4a9-f4bc938d7d3c ;
https://sqlite.org/fts5.html .

## Results

445 eligible articles, 2,504 revisions, full-corpus manifest SHA-256 `fd24e20eff865dd34567f7b94b1323cb86c3cd4046b09a7d47118547dc14f7a7`. Four historical cutoffs, 88 queries each, 352 rank comparisons per candidate method and 1,874 returned ranked positions. All three replay methods matched the independently rebuilt active-only native FTS5 exactly on this runner, including scores. 88 receipts replayed identically in a pinned reader and in the fresh snapshot, 2,504 exact source reconstructions, independently audited all interval/statistics rows and source ledger, five process-death stages passed. Six unit tests passed.

| Cutoff | Active N | Active tokens | Queries | Naive rank drift | Naive score/rank drift | Scan us | Prepared us | Interval us | Native us |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 626 | 445 | 190828 | 88 | 8 | 80 | 431.51 | 90.95 | 92.05 | 40.32 |
| 1252 | 445 | 282088 | 88 | 21 | 79 | 497.32 | 112.06 | 102.77 | 44.33 |
| 1878 | 445 | 337402 | 88 | 22 | 77 | 552.59 | 136.92 | 113.73 | 54.75 |
| 2504 | 445 | 395231 | 88 | 27 | 77 | 603.55 | 149.22 | 123.10 | 59.61 |

Old R119-style active candidate filtering with all-revisions corpus statistics changes 78/352 ranked lists and 313/352 score-or-rank signatures. Active-only scoring is therefore a distinct requirement, not equivalent to the old heads scope. At final cutoff, interval native count outputs 4,764 phrase-match rows versus 24,797 all-prefix rows, summed over query phrase requests; 80.79% fewer returned SQL rows, not measured posting traversal or device I/O. Final warm median interval ranking 123.10 us versus 603.55 us repeated head reconstruction, 149.22 us cached heads and 59.61 us native active index. First cutoff cached heads is marginally faster than interval. Final high-DF query medians 1,224.11 us interval vs 3,282.93 us prepared vs 395.18 us native. Timing excludes receipt reconstruction; warm one-machine rank-only, three randomized repeats, not independent hardware evidence.

| Measured physical resource | R119 ledger | R120 intervals + active stats |
|---|---:|---:|
| Complete SQLite bytes | 10760192 | 10829824 |
| WAL bytes before checkpoint | 232079632 | 257186912 |

Extra 69,632 physical bytes (0.647%), 25,107,280 WAL bytes (10.818%). Four rebuilt active-only native index files total 4,300,800 bytes (index files only, no source archive duplication). A simple shared archive + four native active index copies occupies 15,060,992 B versus 10,829,824 B with intervals. This is not a state-of-the-art temporal-index baseline. WAL is journal file growth, not SSD writes.

## Independent synthetic check

A separate local program, `experiments/round-120/independent_active_control.py`, independently calculated active intervals, N, total tokens and integer phrase frequencies over 25 random generated histories (1,000 events). Native FTS5 was rebuilt for each of 150 cutoffs. 1,500 query comparisons, 6,650 ranked positions, exact row identities, max absolute score error 4.440892098500626e-16. This is not a run of the integrated R120 implementation. The integrated original-source CI above is separate evidence.

## Decision

Use active-only semantics where requested; retain all-history and prefix-statistics modes under explicitly different contracts. Interval tables offer a small persistent overhead and faster historical query processing than uncached head reconstruction, but write amplification and stronger cached/native baselines matter. Current source archive is append-only with synthetic global order, no deletes or genuine timestamps, and this same processed corpus was repeatedly used in R114–119. No claim of novel time travel retrieval. See [implementation-level TimIR audit](prior-art-audit.md).
