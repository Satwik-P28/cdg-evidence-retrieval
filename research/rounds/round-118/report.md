# R118: Native FTS5 auxiliary frequency extraction

Status: pending CI.

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
