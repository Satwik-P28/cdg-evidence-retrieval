# R127: Compact crossing-phrase intervals and selective term-frequency dispatch

Status: pending original-source CI.

R126 eliminates most positional reconstruction cost by splitting exact
phrase occurrences into within-fragment counts and first-boundary counts,
but both auxiliary representations exceed native FTS5 in physical bytes.
Reuse the R122/R123 local-ordinal gap-coded interval format, front-coded
shared blocks and native selected-list decoder for crossing phrases.
Test 4/16 KiB grouping, a cardinality-selected hot-term layer (>=128
coalesced intervals), and a complete TF layer. Every layout retains the
entire R125 min64_coalesced positional index and applications; auxiliary
dictionary, dispatch membership and all SQLite bytes charged. Single-term
requests use compact counts when present according to the declared policy;
phrases use native fragment-local counts plus compact crossing counts.
Exact historical source-derived positions, TF and crossing records audited;
every persisted sidecar interval compared; sampled full phrase counts and
rankings compared to independently rebuilt native active FTS5. Same R126
query plan and corpus; compare sparse direct join and native controls in
same run. No new corpus, arbitrary grammar, online WAL, source payload,
physical device I/O, or novel codec claim.
