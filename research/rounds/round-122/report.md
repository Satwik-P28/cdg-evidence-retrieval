# R122: Compact temporal postings with article-local ordinals and shared blocks

Status: pending original-corpus CI.

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
