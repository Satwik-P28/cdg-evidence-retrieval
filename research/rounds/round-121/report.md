# R121: Exact temporal posting coalescing under a shared scoring contract

**Status: PASS. Three unit tests and original-source [CI 45289846933](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45289846933).**

Prior art: [A Time Machine for Text Search](https://portal.fis.tum.de/en/publications/a-time-machine-for-text-search/) (2007) and [Universal Indexes for Highly Repetitive Document Collections](https://arxiv.org/abs/1604.08897) establish temporal coalescing and exploitation of revision redundancy. TimIR implementation was inspected in R120. The relational version-specific TF baseline here is a matched implementation of the broad historical term-statistics methodology, NOT a reproduction of MonetDB/Lucene TimIR, TTIX or HINT.

Extract exact native Unicode61 token counts from original historical sources. Compare normalized per-version TF records, exact consecutive equal-TF intervals, and Zstandard level-6 packed records for both representations, plus the native historical FTS5 interval-join control and separately rebuilt active-only native FTS5 oracles. All external stores are term-only, not positional. Persisted versions carry article ID, generation, ordinal, end generation, token length and source SHA; source payloads are excluded. Compare actual VACUUMed SQLite bytes and randomized warm rank-only timings. Prepared active maps and token lengths are shared outside timed calls. Verify full expansion of coalesced postings against all original token frequencies, every persisted external posting against expected records, and sampled historical counts and rankings. Four cutoffs, full pinned Versions release, term queries from the first active corpus, AND/OR pairs, common terms. No original global timestamps, new corpus, online maintenance, WAL, full archive, source-bound receipt replay, RAG outcome or novel coalescing claim.

## Measured results

445 articles, 2,504 revisions, 43,147 terms, SHA-256 source manifest `fd24e20eff865dd34567f7b94b1323cb86c3cd4046b09a7d47118547dc14f7a7`. The 754,641 original positive term/document pairs expand exactly from 316,448 coalesced intervals (58.067% fewer records). All persisted records in each external index were compared with their expected representation. Four cutoffs and 103 queries each: 412 rank comparisons per historical method, 2,446 ordered hits, zero observed score error. 21,566 positive active integer TF checks per policy across unique queried terms at the four cutoffs. Three randomized warm timing repetitions. SQLite 3.46.1.

| Policy | Physical SQLite bytes | Logical postings | Final median us | Final common-term median us |
|---|---:|---:|---:|---:|
| rel_version | 10,297,344 | 754,641 | 54.61 | 588.04 |
| rel_coalesced | 7,057,408 | 316,448 | 39.52 | 582.24 |
| packed_version | 8,433,664 | 754,641 | 52.09 | 711.39 |
| packed_coalesced | 5,353,472 | 316,448 | 38.61 | 609.03 |
| native_history | 4,657,152 | not extracted | 72.41 | 873.10 |

Compressed coalesced storage is 36.52% smaller than same-schema compressed version-specific records, but 14.95% larger than native positional FTS5 plus identical version metadata. This is an especially strong negative compression control because the external stores support fewer query features. Retain native FTS5 as default; external TF-only stores are experimental. The coalesced representation gives faster warm medians than the native historical interval-join control on this workload, but no general latency claim: active sets and lengths are prepared outside all historical timed calls; one CI runner; no cold I/O; query set constructed from first prefix; no independent corpus. The final standalone active-only native index median was 46.65 us (common-term median 304.83 us). It is not a full historical index.

## Next gate

Investigate the physical cost of 43,147 individually stored Zstandard frames and term dictionary entries. Test a matched compact layout with gap-coded unsigned integers, article-local ordinal validity, inline tiny posting lists and shared compressed blocks for rare terms, before trying interval partitioning for frequent terms. Compare against the identical TF contract and native positional FTS5; smaller TF-only indexes are not automatically superior to the richer native index. Require position parity before a full replacement. Atomic update and WAL costs remain unmeasured; this is an offline indexing benchmark, not an integrated R120/R119 archive result. Temporal coalescing is established prior art, not our algorithmic novelty.
