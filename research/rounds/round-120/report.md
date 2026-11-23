# R120: Active-version historical BM25 and transactional validity intervals

Status: pending corpus CI.

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
