# R117: Recovering historical BM25 using native score inversion and a length ledger

**Status: pending original-corpus CI.**

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
