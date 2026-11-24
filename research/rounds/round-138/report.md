# R138: integrated historical retrieval at NewsEdits scale

Status: both original-code jobs passed.

Frozen AP SQLite SHA256 and full derived manifest from R136. Deterministic ID sample prefix targets 10,000 and 100,000 (full eligible 74,364). All initial heads first, then round-robin by revision ordinal, not real wall-clock chronology. Preserve upstream IDs and version mapping in charged archive manifest; synthetic origin IDs are explicitly not Git commits. Two transactional packed arms with identical positional FTS5, ledger and provenance. Four cutoffs, up to 64 lexical probes selected only from initial snapshot DF bands. Independently rebuild native active indexes at every cutoff; issue receipts as ingestion reaches each cutoff and replay on final compacted archive. Verify identical receipt bodies across policies, exact source bytes, extractive evidence lines, logical bounds, archive sizes and descriptive timings. Current-only baseline: rerun historical queries on final native snapshot and resolve historical citations by stable article ID to current version; report article/rank drift, revision drift, exact source drift, and loss of deterministic query-matching lines. No model answers, relevance labels, chronological real news claims, or hallucination metrics. No raw article text exported. Full cohort may encounter CI resource limits; report failures rather than substitute data.

## Verified results

Both original-code jobs passed, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45501922438 (3e41b275). Full AP: 74,364 revisions, 12,841 articles, complete archive 312,521,715 -> 223,142,857 bytes (28.60% reduction), payload 149,369,811 -> 59,982,761 bytes. 168,746 exact source readbacks across both nested cohorts and both policies, 1,024 historical ranking comparisons and receipt replays per operation type, 7,632 extractive packets; zero observed BM25 score error. Full cohort: 395/1,430 historical hit occurrences lose their exact query-matching line in the latest version, 578/1,430 have changed source bytes. These are repeated query-hit occurrences, not unique documents; historical current-only comparison uses synthetic ordinal schedule and lexical probes without relevance labels. Both snapshot and compressed archive replay exactly; compression does not improve evidence correctness over version-preserving snapshots. Timings descriptive, no LLM answers, no claim of semantic hallucination reduction. Smaller cohort is nested, not independent.

| Revisions | Policy | Complete bytes | Payload bytes | Append median us | Source read median us | Mean decode | Max decode |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10009 | snapshot | 42846800 | 20175408 | 697.53 | 13.54 | 1.0000 | 1.0000 |
| 10009 | bounded_anchor | 30691764 | 8020372 | 749.07 | 23.77 | 1.6459 | 2.4826 |
| 74364 | snapshot | 312521715 | 149369811 | 785.51 | 20.63 | 1.0000 | 1.0000 |
| 74364 | bounded_anchor | 223142857 | 59982761 | 863.19 | 32.12 | 1.6428 | 2.4877 |

| Revisions | Cutoff | Article ranking changed | Hits | Changed source bytes | Missing exact query-matching line |
|---:|---:|---:|---:|---:|---:|
| 10009 | 1744 | 56/64 | 465 | 340 | 226 |
| 10009 | 4499 | 53/64 | 477 | 190 | 142 |
| 10009 | 7254 | 50/64 | 486 | 94 | 76 |
| 74364 | 12841 | 55/64 | 473 | 344 | 232 |
| 74364 | 33348 | 55/64 | 480 | 157 | 109 |
| 74364 | 53856 | 46/64 | 477 | 77 | 54 |
