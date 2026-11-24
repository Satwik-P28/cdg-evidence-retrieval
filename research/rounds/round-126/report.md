# R126: Direct fragment phrase counts and exact first-boundary correction

**Status: PASS. Four regression tests and full pinned corpus [CI 45430698969](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45430698969).**

R125 reconstructs all active term positions to compute phrase frequency,
including common terms. For exact phrases of 1–3 canonical tokens, divide
occurrences into within-fragment and boundary-crossing starts. Assign a
crossing occurrence to the first boundary after its start; the left context
is limited to the owning fragment (last two tokens), while the right context
may span several short fragments. No double counting for multi-boundary or
overlapping repeated-token phrases. Aggregate native fragment phrase counts
through active applications. Compare a direct join, materialized fragment
match CTE with grouping, and reusable indexed boundary windows versus a
sparse exact crossing-bigram/trigram table. The window auxiliary uses the
public FTS5 xInst API and only counts matches starting before and ending
after the designated cut. Coalesce multiplicity intervals. Retain the
entire R125 min64_coalesced positional index and placements in both auxiliary
variants, charge all physical bytes. Independently check every original
version's complete bigram/trigram frequency decomposition, all persisted
boundary contexts/intervals and sampled phrase counts against native active
FTS5. Reuse R124/125 query plan and add first-prefix crossing-specific
queries. Same corpus and synthetic order, warm randomized rank-only timing,
no arbitrary FTS grammar, phrase length >3, source payload or WAL. Established
fragment reuse and boundary correction, not a novel algorithm claim.

## Results

445 articles, 2,504 revisions, 1,663,050 original normalized tokens. Every original version's complete bigram/trigram count independently decomposed into internal and crossing starts, including 79,760 crossing occurrences. Sparse representation has 36,005 coalesced intervals expanding to 79,333 positive phrase/version entries. Window representation has 11,806 unique contexts, 47,172 indexed context tokens, 12,186 intervals expanding to 26,544 context/version entries. The base is the complete R125 min64_coalesced positional index; both auxiliary representations preserve it and its placement mapping. 183 queries at each of four cutoffs (80 phrase-containing), 732 rank checks per method, 3,336 ranked hits per method, 30,147 positive native frequency pairs across unique queried phrases/terms, 101 unique-phrase/cutoff probes with crossing matches totaling 541 crossing occurrences. Zero observed score error. Four regression tests including repeated-token and multi-boundary cases passed.

| Method | Physical SQLite B | Final rank median us | Final phrase median us | Final rank p95 us |
|---|---:|---:|---:|---:|
| positions | 4255744 | 632.823 | 3519.394 | 10726.539 |
| sparse_join | 5332992 | 59.069 | 54.126 | 4734.948 |
| sparse_cte | 5332992 | 62.124 | 57.171 | 5174.781 |
| window_cte | 4939776 | 72.659 | 70.496 | 5140.188 |
| native_history | 4657152 | 48.153 | 39.695 | 780.616 |

Sparse direct join reduces median phrase latency 65.02x vs position reconstruction in this matched run and overall median 10.71x. Native historical FTS5 remains faster, including p95 780.616 us vs sparse join 4,734.948 us. Sparse adds 1,077,248 B to base (+25.31%), giving 14.52% greater physical bytes than native. Window adds 684,032 B (+16.07%), 6.07% greater than native. Materialized CTE reduces returned local SQL rows at final cutoff from 47,963 to 8,183 (82.94%) but slightly increases median and tail latency. This is returned row cardinality, not native internal posting visits or disk I/O. No claim of practical superiority. All methods use prepared active maps outside timing, warm one-runner rank-only latency, source payload excluded. The plan intentionally adds boundary queries, not a representative observed workload. Not an independent corpus, arbitrary FTS syntax, longer phrases, online update/WAL or full reproduction of published fragment indexes.

## Decision

Direct fragment-local counting with explicit first-boundary correction is a promising exact algorithmic combination; preserve it. Native FTS5 remains default because both augmented layouts are larger and slower overall, especially at p95. R127 should reuse the R123 compact ordinal interval codec for sparse boundary counts and optionally combine single-term TF and crossing-phrase entries in a shared dictionary. Compare all sidecar physical bytes, term-only and phrase latency, and exact count parity; do not double-charge or conceal auxiliary data. The next gate after layout optimization is independent version histories and online maintenance. No novelty claim for boundary indexing or fragment reuse.
