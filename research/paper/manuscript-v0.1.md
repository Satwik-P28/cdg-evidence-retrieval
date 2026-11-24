# Storage-Efficient Reproducible Evidence Retrieval in Evolving Document Collections
Draft v0.1 (2026-11-24). Internal research manuscript, not submission-ready.

## Abstract (working, deliberately limited)
Retrieval-augmented generation over evolving collections requires more
than current-document search: evidence must remain recoverable at the
version used by a historical query, and relevance scores must reflect the
declared snapshot rather than later revisions. We investigate a local
storage architecture combining compressed revision histories, atomic
source/index commitments, and exact replay of snapshot-specific lexical
rankings. Experiments on a pinned collection of processed Wikipedia
revisions expose tradeoffs between snapshot storage, bounded-anchor
deltas, native full-text indexes, and coalesced temporal postings.
Compact term-frequency layouts save space but omit positional semantics;
feature-richer alternatives recover positions and short-phrase counts at
varying storage and latency costs. The results motivate an explicit
evidence contract and cost-aware selection rather than a universal
compression or retrieval speedup. Independent chronological evaluation
and an integrated end-to-end archive experiment remain necessary.

## Introduction
Problem: historical evidence loss, stale corpus statistics, and storage
overhead in versioned retrieval. Distinguish source-byte exactness,
snapshot-ranking reproducibility, and semantic answer correctness.
Contribution candidates (subject to prior-art audit):
1. A concrete implementation and testable contract tying reconstructed
   source bytes, revision identity, snapshot statistics and ranked results.
2. Controlled cost analysis across source delta policies and temporal
   posting layouts with matched native controls.
3. Negative results documenting position/phrase parity, physical page
   costs, and selective TF tail-latency tradeoffs.
Do not claim invention of versioned indexing, BM25, deltas, WAND, hashes,
fragment reuse, or evidence receipts.

## Methods
Define immutable generation, article revision, source SHA-256, active
version at cutoff, native Unicode61 tokenizer, one-column unweighted BM25
and explicit tie ordering. Describe bounded anchor source representation,
atomic SQLite transaction and prefix commitments, exact active statistics
and reference replay. Describe native full-detail default; alternative
TF and positional layouts only as measured controls.
Threat model: trusted commitment, process-death rollback, not adversarial
storage or proof of power-loss durability. Define supported query grammar.

## Existing measured evidence (do not combine unlike experiments)
- R115: held-out subset within Versions, bounded anchor 1,286,144 B vs
  snapshot 1,982,464 B; mean decoded-byte amplification 1.499 vs 1.
- R119: atomic ledger archive 1,269,760 B vs 1,253,376 B, five process-death
  stages, 256 source reads; not physical power-loss validation.
- R120: active-statistics correctness on 445 articles / 2,504 revisions;
  naive whole-history scores/rank drift, exact active rank oracle parity.
- R123: hybrid4 TF-only 1,302,528 B vs native positional history 4,657,152 B,
  57.41 vs 117.47 us same-run median; NOT position-matched.
- R124/125: positional and short-phrase reconstruction exact but slower.
- R126: direct boundary correction reduces phrase median from 3519.39 to
  54.13 us vs position reconstruction; native 39.70 us, auxiliary storage
  larger than native.
- R127: hot4 4,947,968 B vs native 4,657,152 B; common-term median 681 vs
  1474 us, overall p95 832 vs 1604 us; worse overall median/phrase latency.
Every figure must link its source report/JSON; avoid treating repeated
queries, revisions, layouts or CI runners as independent trials.

## Required final evaluation before submission
Freeze methods and parameters; hold out genuinely chronological histories
from independent domains. Record source commits, manifests, licensing,
query generation and cutoffs. Compare full source snapshots + native FTS5,
bounded anchors + native FTS5, and selected compact controls under same
feature contract. Include physical source/index/mapping/WAL sizes, append
latency, cold/warm retrieval, exact source recovery and receipt replay,
failure injection, and uncertainty across documents/workloads/runners.
Report negative results. End-to-end RAG evidence recall is separate from
answer correctness; no hallucination claim without a labeled benchmark.
No Uno generation or learned entropy decoder result in this paper unless
actually run and justified by a scoped experiment.

## Related work to verify and cite
Temporal retrieval/Time Machine, TimIR, temporal interval indexing,
He & Suel SIGIR 2012 fragment positional index, repetitive collections
indexes, content-defined chunking and delta compression, native FTS5,
BM25/dynamic pruning, provenance/temporal database snapshot consistency.
Uno and speculative decoding are adjacent future work, not primary novelty.

## Limitations
Versions corpus processed and global interleaving synthetic; repeated
tuning makes it development data. All index-only rounds exclude source
payload; no cross-round multiplication of speedups or compression ratios.
Restricted query grammar, no claim of general FTS5 parity. Exact source
bytes and lexical ranks do not establish semantic truth.
