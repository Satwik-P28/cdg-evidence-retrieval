# R118: Native FTS5 auxiliary frequency extraction

**Status: PASS. 10 tests, original-source CI [45287395133](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45287395133).**

R117 recovered integer phrase frequencies by inverting native BM25. SQLite's
public FTS5 API already exposes phrase occurrence counts (xInstCount) and
document token length (xColumnSize). Implement a C auxiliary extension on the
same SQLite connection, compare inversion, Python vocabulary positional
extraction, native counts over all generations, native counts with rowid
cutoff, and retained native prefix indexes. Same R117 cohort, four cutoffs,
two query scopes, and prefix-derived query plan with eight high-document-
frequency terms added. Five repeated warm rank-only runs, fixed random order
of requests and methods. All outputs compared to independent full-content
prefix oracle; direct frequencies checked against positions and inversion.
No early top-k truncation of historical candidates. Cutoff result cardinality
does not measure internal posting traversal or disk reads.

Also expose a scalar count function calling the same default Unicode61
tokenizer via the public FTS5 tokenizer API. Compare its lengths with actual
native indexed positions, including Unicode and embedded NUL fixtures.
This enables later transactional ledger maintenance, but R118 does not
implement it.

Reference: https://sqlite.org/fts5.html#extending_fts5 .
No new FTS5 API, temporal scoring formula, or native ranking engine claimed.

## Results

Same R117 cohort, SQLite 3.46.1, 575 revisions. 575 scalar Unicode61 token counts and 8,200 full phrase-frequency rows exactly matched native indexed positions. 72 distinct phrases; 88 queries per scope; four cutoffs, 704 rank checks per method; zero observed score error and exact ordered results for all five methods. Five repeated randomized passes, 3,520 timed rank calls per method. Native prefix indexes are separate physical controls, not shared temporal indexes.

| Cutoff | Checks | Eligible phrase match rows | Inverse median us | Positions | Native full | Native cutoff | Native prefix |
|---|---:|---:|---:|---:|---:|---:|---:|
| 143 | 176 | 1793 | 142.45 | 208.51 | 80.50 | 57.29 | 34.79 |
| 287 | 176 | 3800 | 134.80 | 186.84 | 77.72 | 64.20 | 39.38 |
| 431 | 176 | 5953 | 136.13 | 196.48 | 79.33 | 74.96 | 53.21 |
| 575 | 176 | 8200 | 140.81 | 199.05 | 80.21 | 81.86 | 67.99 |

At generation 143, cutoff native counts return 1,793 rows versus 8,200 full-index rows across the unique phrases. This measures returned SQL rows, not FTS posting traversal. Native cutoff median ranking is 1.72–2.49x faster than score inversion across these four cutoffs; high-DF first-cutoff median 277.677 us versus 1,435.850 us inversion. Retained native prefix indexes remain faster. Prefer exact native integer counts over inversion for the supported query subset; keep inversion as a control, not a novelty claim. Native counts are exposed by established SQLite APIs. Next: atomically maintained ledger, receipts bound to query/corpus statistics, and process-death tests. No assertion of device-level read savings, end-to-end RAG quality or independent-machine latency advantage.
