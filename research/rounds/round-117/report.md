# R117: Recovering historical BM25 using native score inversion and a length ledger

**Status: PASS. Original-source CI [45286488324](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45286488324), 6 tests passed.**

R116 demonstrated rank drift despite correct historical source receipts.
Time-varying document frequency and corpus statistics are established IR
prior art, including Staudinger, Piroi and Rauber (2024),
https://arxiv.org/abs/2411.04051 . This is a constrained SQLite experiment,
not a new temporal IR model.

For a single unweighted native FTS5 phrase, s = -I * (k1+1)f/(f+A),
where A=k1*(1-b+b*dl/avgdl). With x=-s/I, recover f=x*A/(k1+1-x).
The decoder rejects non-finite, saturated and non-unique integer frequencies
under a 64-ULP forward-score validation. It is not a proof of invertibility
for arbitrary scores, very large rows or scoring variants. For explicit
AND/OR over distinct phrases, recover each phrase separately, construct exact
candidate intersection/union, and sum recomputed historical contributions.
No early top-k truncation; all matches are enumerated.

A persisted one-row-per-revision document-length/cumulative-token ledger
is built offline from actual native FTS5 positions. Historical DF comes from
restricting complete phrase hits to the ingestion prefix. Compare integer
frequencies to independently counted native positions, and rank to full
content FTS5 rebuilt on each original prefix. Compare one complete archive
plus ledger to the same archive plus three separate native contentless
positional prefix index files. Prefix-only index copies are a simple
baseline, not the state of the art; their sizes exclude duplicate
source/metadata. Timing is warm rank-only and descriptive.

Fourth disjoint 100-article sample from Versions corpus, four cutoffs,
prefix-selected lexical, exact phrase and structured AND/OR probes.
The order between articles is synthetic. Head filtering uses whole-prefix
historical stats, not a current-head-only corpus. No arbitrary FTS5 syntax,
online ledger maintenance, authenticated rank receipt, pruning, real user
trace, RAG quality, or proof of novelty. The alternative direct native
FTS5 extension API can expose phrase frequencies without inversion and
should be a future strong control.

Native formula: https://sqlite.org/fts5.html#the_bm25_function .

## Executed results

Pinned source manifest SHA-256 `fd24e20eff865dd34567f7b94b1323cb86c3cd4046b09a7d47118547dc14f7a7`. Fourth disjoint cohort: 100 articles and 575 processed revisions. Across 64 distinct native phrases, **3,929** inferred integer frequencies exactly matched independently counted token-position frequencies. Queries were selected from the first prefix; 64 single-phrase queries (terms and bigrams), eight AND and eight OR queries. Four cutoffs and two scopes resulted in **640** comparisons per replay implementation, **3,310** returned ordered result positions. Both inversion and position-count replay exactly reproduced the native full-content prefix oracle scores and order in all observed cases. The native retained prefix-index control also matched the oracle. The earlier failing CI run caught an undersized fixture query pool, corrected without altering the original-corpus query plan.

| Cutoff | Query checks | Ranked hits | Naive rank changes | Naive score/rank changes | Inversion median us | Position extraction median us | Native prefix median us |
|---|---:|---:|---:|---:|---:|---:|---:|
| 143 | 160 | 683 | 45 | 141 | 148.99 | 199.47 | 25.00 |
| 287 | 160 | 824 | 41 | 138 | 153.20 | 212.95 | 31.71 |
| 431 | 160 | 882 | 30 | 133 | 155.12 | 217.97 | 44.48 |
| 575 | 160 | 921 | 0 | 0 | 155.36 | 216.15 | 88.78 |

At the three historical cutoffs, naive filtering changes 116/480 ordered result lists and 412/480 score-or-rank signatures (all queries with nonempty results). At the final cutoff it matches by construction. Recomputed rankings avoid these discrepancies. The native comparator is fastest in all measured cases. Inversion is faster than repeated Python-side positional extraction on this runner, not necessarily faster than a tuned FTS5 extension using native xInst or xPhrase APIs. Each query enumerates all phrase matches, including later revisions, and may be expensive for large or frequent-term workloads. Timing is warm rank-only, a single runner and fixed method order; no generalized latency claim.

### Physical storage

* Final source+FTS5 archive without ledger: 2,596,864 B.
* With offline length ledger: 2,609,152 B (increment 12,288 B).
* Additional three native prefix-index files: 1,470,464 B (225,280 + 450,560 + 794,624 B).
* Shared final archive plus retained prefix index files: 4,067,328 B. Ledger reduces incremental storage by 99.164% and total storage vs this particular baseline by 35.851%.

This is a constrained empirical tradeoff, not proof of an efficient state-of-the-art temporal index. Retained independent native prefixes are a simple materialized baseline; temporal shared postings, direct FTS5 auxiliaries, compressed temporal statistics and on-demand rebuilds are stronger controls. The current ledger is built offline and is not transactionally maintained or itself authenticated. The inverse rejects ambiguous scores; finite precision, corpus/tokenizer changes, nonstandard weights, long documents, deletion, arbitrary query syntax, and adversarial data are not covered by observed parity. No claim of novel mathematical inversion, novel temporal BM25, or improved RAG accuracy. Next gates: incremental atomic ledger, exact integer counts via native FTS5 auxiliary or APSW, larger workloads with high-frequency phrases, independently reproduced temporal-index method, and generation-bound rank receipts.
