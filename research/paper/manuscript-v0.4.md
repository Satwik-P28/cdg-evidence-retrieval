# Storage-Efficient Reproducible Evidence Retrieval in Evolving Document Collections

**Manuscript v0.4 | 2026-11-24 | Internal draft. R131 sensitivity and negative results included. Not submission-ready.**

## Abstract

Retrieval systems over evolving document collections must preserve the evidence available when a query was executed, including the exact source revision and the corpus statistics used for ranking. We evaluate a local archival design that combines bounded-depth dictionary compression of document revisions, an atomic full-text index and version ledger, and replayable historical ranking receipts. The source encoding restricts delta dependencies to independent anchors and imposes explicit logical activation and decoded-byte budgets. Both the compressed and independent-snapshot controls retain identical native positional full-text indexes, source identities, historical statistics, and receipt metadata. On two independently sourced, pinned first-parent Git histories comprising 160 documents and 750 retained revisions, the bounded-anchor representation reduced complete SQLite archive storage by 43.2% and 37.0% respectively, compared with independently Zstandard-compressed snapshots. All retained revisions reconstructed byte-exactly, and 640 historical ranking comparisons per policy matched rebuilt active-snapshot native BM25 references with zero observed score error. Logical decoded-byte amplification increased to approximately 1.86x; one-hop dependencies and explicit activation bounds were respected. These findings support a measurable storage versus reconstruction tradeoff under a common retrieval contract, rather than a general compression, search-speed, or answer-accuracy claim.

## 1 Introduction

A citation to a mutable document is insufficient to reproduce the evidence observed by an earlier retrieval run. Even if the original source bytes remain available, ranking may drift because newly added documents alter the collection size, document-frequency statistics and average length. Historical retrieval therefore requires both source identity and snapshot-specific scoring. Maintaining a separate complete archive and index for each state is straightforward but potentially redundant.

We study a practical implementation that retains exact source revisions, indexes all retained versions once using native full-detail SQLite FTS5, and derives active-snapshot relevance from validity intervals and historical collection statistics. Source compression is decoupled from the retrieval scorer. This permits a feature-matched evaluation in which alternative source representations cannot obtain storage savings merely by dropping positions, ranking data, or evidence metadata.

Our contribution candidates are (i) a precise source and ranking replay contract implemented with atomic version and index maintenance; (ii) an evaluation of bounded source dependencies with all index and provenance metadata charged; and (iii) an empirical characterization of where positional and term-frequency representations change the storage/latency tradeoff. The first two are the core of this draft. We do not claim that temporal retrieval, delta compression, BM25, hash commitments, or positional indexing are new. A full prior-art differentiation and stronger delta controls are required before submission. Dataset versioning has already formalized storage versus recreation-cost optimization [6]; our proposed evaluation concerns this specific source/ranking contract, not novelty of that optimization problem.

## 2 Related work

Berberich et al. established efficient temporal full-text retrieval through temporal extensions of inverted indexes [1]. Staudinger et al. explicitly address reproducible ranked lists in evolving corpora with historical retrieval [2,3]. These are particularly close baselines for the ranking-replay objective; historical BM25 reproducibility alone is not a novelty claim. He and Suel exploit redundant fragments to compress positional indexes for versioned documents [4]; our exploratory R124–R127 controls confirm that positional parity and physical page overhead matter. Source delta compression and anchor selection are also established, including WikECD's revision-history compression and reconstruction framework [5]. Our scope is the jointly accounted source/index/receipt implementation and bounded source reconstruction policy, subject to comparison against these prior systems. We have not reproduced their full implementations or established superiority over them.

## 3 System and contract

### 3.1 Revision identity and active snapshots

Let g be an append-only generation, a a document identifier, and i its within-document ordinal. The record stores original UTF-8 bytes, byte length, SHA-256 digest, encoding type, and optional earlier source dependency. At cutoff c the active version of each document is the latest indexed generation not exceeding c. A half-open validity interval [start, end) is maintained for each revision, with NULL representing an unbounded end. The study supports additions and updates; deletions and renames are outside the tested contract. In the Git evaluation we only expose complete commit-state cutoffs; multi-file changes are ingested one file at a time, not as a single atomic Git commit.

### 3.2 Bounded source encoding

The baseline compresses each revision independently using Zstandard level 6. In the bounded policy, the source encoder evaluates at most the four most recent independently compressed revisions of the same document. Let x be a new source, F(x) its independent compressed frame, and D(x|b) a Zstandard frame with prior raw source b as a raw-content dictionary. A candidate anchor b is eligible only when:

- |b| + |x| <= 2.5|x| (decoded-source byte bound);
- |D(x|b)| <= 0.8|F(x)| (individual frame saving);
- |F(b)| + |D(x|b)| <= 1.5|F(x)| (logical activated-frame bound).

Among eligible anchors choose the smallest delta frame, breaking ties toward the newest anchor; otherwise store F(x). Anchors have depth zero, so dependencies have depth at most one. The decoder verifies source length and SHA-256 for both anchor and requested revision. These bounds cover logical payload bytes under this recovery algorithm, not SQLite page access, memory allocation, or physical I/O. The implementation and thresholds were previously developed on Versions, then frozen before R129 evaluation.

### 3.3 Historical ranking

Both policies index each revision using a single-column, contentless, full-detail native FTS5 index with the default Unicode61 tokenizer. Validity metadata identifies active rows and a ledger records per-revision token length, cumulative token count and a chained prefix commitment. A trigger updates historical active-document counts and active-token totals on each appended revision. Exact active phrase frequencies are obtained using a native FTS5 extension and interval filtering; BM25 is evaluated with active snapshot statistics rather than all retained versions. The contract is distinct, unweighted quoted phrases with AND/OR composition, top ten results and increasing generation as score tie-breaker. It is not arbitrary native FTS5 grammar or a vector retrieval method.

For cutoff c, active document count N_c, token total T_c, phrase document frequency df_c, and active document length l, use average length T_c/N_c and the native-compatible parameters k1=1.2 and b=0.75. Phrase IDF is log((N_c-df_c+0.5)/(df_c+0.5)), clamped to 1e-6 if nonpositive; sum the native-compatible term contributions and negate the score for ascending ranking. All eligible phrase counts are collected before ranking; no speculative top-k truncation.

### 3.4 Atomicity and receipts

The source frame, version identity, full-text row, Git-origin row, token ledger, validity/stats updates, and head generation are committed in a single SQLite transaction using WAL with synchronous FULL. A ranking receipt records cutoff, normalized query, scorer contract, prefix commitment, active corpus statistics, phrase DFs, ranked generation/ordinal/source digest and hexadecimal floating score. Replay reissues the query and reconstructs all hit sources, comparing the body and its digest to a separately trusted expected commitment. Git origin is audited against the pinned manifest; the receipt chain does not authenticate Git metadata. The digest is not a signature or a proof against malicious database replacement.

## 4 Evaluation

### 4.1 Datasets and protocol

R129 uses two repositories absent from previous Versions tuning: CPython library documentation at commit 60403a5409ff2c3f3b07dd2ca91a7a3e096839c7 (v3.13.0), and Bitcoin Improvement Proposal documents at commit 0d99ffd39fdaf75209c43b1f8ec3fbbc23f10814. Select the last 400 first-parent path-touch commits, take their earliest commit's first parent as the common baseline, hash-select 80 eligible baseline paths with fixed salt, and exclude paths missing from any observed snapshot. Neither selected cohort lost a path. Source bytes are recovered directly from Git blobs, verified against Git SHA-1 object identities and separately SHA-256 hashed. No normalization of source bytes is used. Commit ancestry provides the order; timestamps are recorded rather than used to reorder commits. We do not reconstruct all side-branch edits or initial document creation histories. CPython supplies 355 revisions across 80 files (66 changed), and BIPs 395 revisions across 80 files (80 changed).

For both corpora, the baseline active index determines a fixed set of 80 term/phrase and mixed AND/OR queries, reused at four commit-boundary cutoffs. Independently rebuilt native active indexes provide the rank oracle. Both policies use identical index schema and scorer, source and Git metadata, ledger, transaction settings, and query plan. Physical file sizes include the full index and metadata after VACUUM. Source payload sizes are reported separately, as are WAL file sizes before checkpoint and external receipt bytes. No source blobs are redistributed; the source pins, manifest and workload are in the artifact. CPython is PSF-licensed; BIPs contain per-document licensing declarations.

### 4.2 Integrated physical storage

| Corpus | Revisions | Raw source B | Snapshot archive B | Bounded anchor B | Reduction |
|---|---:|---:|---:|---:|---:|
| cpython | 355 | 15653966 | 9166848 | 5210112 | 43.16% |
| bips | 395 | 10814604 | 7589888 | 4780032 | 37.02% |

The complete-archive saving is smaller than the source-payload saving because full-detail positional index and replay metadata remain in both policies. Compressed source payloads fall from 4,406,056 to 745,283 bytes for CPython and 3,051,292 to 568,414 bytes for BIPs. The observed savings are not a comparison with uncompressed storage and do not rely on sacrificing positional data.

### 4.3 Retrieval and reconstruction costs

| Corpus | Policy | Append median (us) | Source read median (us) | Rank median (us) | Receipt median (us) |
|---|---|---:|---:|---:|---:|
| cpython | snapshot | 2005.95 | 144.19 | 100.07 | 1240.71 |
| cpython | bounded_anchor | 2222.06 | 157.63 | 98.47 | 1220.47 |
| bips | snapshot | 1263.40 | 72.85 | 73.22 | 1043.35 |
| bips | bounded_anchor | 1278.66 | 69.73 | 72.57 | 898.30 |

Logical decoded-byte amplification is 1.8557x for CPython and 1.8559x for BIPs; all requests satisfy the explicit bounds. Anchor reads can activate more total compressed payload than independent snapshots when every revision is requested. CPython median append and source read costs increase by approximately 10.8% and 9.3%; BIPs observed medians are similar. The rank and receipt timings are three randomized warm passes, with policies interleaved after reopen; append measurements are sequential builds, snapshot first in both jobs. Timings are single-runner descriptive observations and not evidence for a general speedup. WAL file sizes before checkpoint decrease from 58,969,592 to 54,322,232 bytes (CPython) and 63,439,792 to 59,575,232 bytes (BIPs), but these are allocated file sizes, not physical write traffic.

### 4.4 Correctness and failure tests

All 750 retained sources reconstruct byte-exactly under each policy. Each policy passes 640 native ranking comparisons (3,378 ranked hit positions) across the two corpora with zero observed score error. Receipt bodies and digests match across policies. Each corpus and policy passes 80 pinned-snapshot and 80 later-snapshot replay checks and 320 reopen checks. Five process-death stages (source, index, ledger, meta, commit) per policy per corpus test rollback or visibility of a committed state; process termination is not a power-loss experiment. External receipt exports are not in the archive sizes; they are 397,017 and 410,807 bytes per policy respectively.

### 4.5 Development controls

The earlier Versions corpus was repeatedly used for development and must not be reported as independent validation. R120 demonstrated rank drift when all-history statistics were used instead of active statistics. R123 showed large savings for term-frequency-only indexes but not position-matched functionality. R124 and R125 reconstructed positions exactly but incurred high latency. R126 reduced phrase reconstruction overhead but added storage. R127 selective TF accelerated common-term and tail latency at a small storage premium, while losing median latency; R128 speculative candidate ordering reduced full scoring but incurred excessive bound-construction cost. These are secondary ablations, not cumulative speedups and not the primary R129 system.

### 4.6 Matched stronger controls (R130)

The next evaluation reuses the exact R129 source manifests and query plans, which are verified before accepting results. Nine causal source policies share the same full positional archive and replay contract: independent snapshots, previous-revision dictionaries with maximum depths 1/2/4/8, latest literal anchors with maximum ordinal distances 4/8, a previous-only literal dictionary with the same frame/activation/decode bounds as the proposed policy, and the unchanged four-candidate bounded-anchor policy. The matched-budget previous-only arm isolates the benefit of searching older eligible anchors. We report nondominance over complete archive storage, aggregate decoded-byte amplification, worst-request decoded and activated ratios, and maximum dependency depth. Timing remains descriptive pending repeated runners. These are reused validation cohorts, not newly independent held-out tests.

Both final jobs passed on commit a327ad56d530968f7732d30b7f74a3e9b9c99476, run https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45493072346. Exact R129 manifests and query plans matched. Across nine arms, 6750 source readbacks, 5760 historical ranking comparisons, 90 process-death stage checks, zero observed rank-score error. CDG is nondominated on both corpora using the five declared objectives; it is the smallest of the tested one-hop policies. The depth-8 chains are smaller by 57,344 B (CPython) and 69,632 B (BIPs); CDG incurs 1.11%/1.48% more archive bytes but 53.93%/53.79% less aggregate decoded work. Compared to the matched-budget immediate predecessor, CDG reduces archive size by 24.29%/19.57% at higher aggregate decoded work. Compared with anchor8 the reduction is only 1.32%/1.44%. Neither general compression superiority nor timing superiority follows. The R130 cohorts are reused validation, and depth-8 may be preferable for storage-only workloads.

| Corpus | Policy | Archive B | Payload B | Mean decode ratio | Max decode ratio | Max activation ratio | Depth |
|---|---|---:|---:|---:|---:|---:|---:|
| bips | prev_budget | 5943296 | 1652336 | 1.4692 | 2.1435 | 1.2024 | 1 |
| bips | prev1 | 5943296 | 1650415 | 1.4700 | 2.2849 | 1.6256 | 1 |
| bips | snapshot | 7589888 | 3051292 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | prev8 | 4710400 | 610268 | 4.0162 | 9.4258 | 1.6898 | 8 |
| bips | prev4 | 4894720 | 771101 | 2.7875 | 5.8305 | 1.6464 | 4 |
| bips | anchor4 | 4952064 | 794612 | 1.7600 | 2.2851 | 1.6263 | 1 |
| bips | prev2 | 5365760 | 1175193 | 1.9074 | 3.1263 | 1.2519 | 2 |
| bips | anchor8 | 4849664 | 672462 | 1.8119 | 2.2992 | 1.6530 | 1 |
| bips | bounded_anchor | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| cpython | prev_budget | 6881280 | 2357525 | 1.4681 | 2.0363 | 1.0837 | 1 |
| cpython | prev1 | 6881280 | 2357525 | 1.4681 | 2.0363 | 1.0837 | 1 |
| cpython | snapshot | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | prev8 | 5152768 | 804822 | 4.0278 | 8.9986 | 1.2038 | 8 |
| cpython | prev4 | 5521408 | 1139618 | 2.7395 | 5.0647 | 1.2038 | 4 |
| cpython | anchor4 | 5586944 | 1169022 | 1.7427 | 2.0360 | 1.0961 | 1 |
| cpython | prev2 | 6123520 | 1689774 | 1.9029 | 3.0446 | 1.1059 | 2 |
| cpython | anchor8 | 5279744 | 868378 | 1.8148 | 2.0360 | 1.1523 | 1 |
| cpython | bounded_anchor | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |

### 4.7 Budget sensitivity and codec screening (R131)

Both jobs passed at 302fb912d41b1baef77d5850954346a3402b8e6b, run https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45494253552. R129 manifests and workloads matched. Across 11 integrated arms: 8250 exact source readbacks, 7040 ranking comparisons, 110 process-death checks; zero observed score error. Candidate counts 1,2,4,8 have identical deterministic metrics on both corpora; this does not prove identical choices or universal equivalence. Tight activation (1.1x) strictly dominates bounded_anchor on CPython under the five declared objectives (5,185,536 vs 5,210,112 B), but the frozen policy remains nondominated on BIPs (4,780,032 vs 4,800,512 B). Tight decode (1.75x) nearly eliminates useful deltas. Relaxed activation does not improve storage. Local choices alter future anchor availability; specific causal mechanisms require anchor tracing. Source-only xdelta3 3.0.11 has larger payloads than matched Zstd predecessor policies at depths 1/4/8 on both corpora. This is not an integrated VCDIFF archive comparison. Do not retrospectively replace the frozen policy.

| Corpus | Policy | Archive B | Payload B | Mean decoded ratio | Max decoded ratio | Max activated ratio | Depth |
|---|---|---:|---:|---:|---:|---:|---:|
| cpython | relaxed_activation | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | tight_decode | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | k2 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | k8 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | snapshot | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | anchor8 | 5279744 | 868378 | 1.8148 | 2.0360 | 1.1523 | 1 |
| cpython | k1 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | prev8 | 5152768 | 804822 | 4.0278 | 8.9986 | 1.2038 | 8 |
| cpython | tight_activation | 5185536 | 740820 | 1.8537 | 2.0360 | 1.0973 | 1 |
| cpython | relaxed_frame | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | bounded_anchor | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| bips | relaxed_activation | 4792320 | 568561 | 1.8571 | 2.2992 | 1.6530 | 1 |
| bips | tight_decode | 7565312 | 3030643 | 1.0059 | 1.5203 | 1.0862 | 1 |
| bips | k2 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | k8 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | snapshot | 7589888 | 3051292 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | anchor8 | 4849664 | 672462 | 1.8119 | 2.2992 | 1.6530 | 1 |
| bips | k1 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | prev8 | 4710400 | 610268 | 4.0162 | 9.4258 | 1.6898 | 8 |
| bips | tight_activation | 4800512 | 598762 | 1.8380 | 2.0696 | 1.0992 | 1 |
| bips | relaxed_frame | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | bounded_anchor | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |

## 5 Limitations and remaining submission gates

Two repositories with 160 sampled text files do not establish broad generalization. Baseline path sampling, observation window and repeated queries are not real usage traces or a relevance benchmark. We exclude deleted paths and new-file evolution; commits with several file edits are not ingested atomically as a whole. The rank receipt relies on a trusted commitment, declared scoring arithmetic and tokenizer. R130 compares matched preceding-revision dictionaries and bounded chains, but we have not reproduced full TimIR/WikECD systems or compared alternative delta codecs. No cold device I/O, actual device writes, power-loss durability, semantic answer correctness, or hallucination result is established. Prior-art differentiation, alternative codec controls, repeated independent runner measurements, scaling and reproducibility packaging remain necessary. No Uno generation or neural entropy decoder is claimed as a component of the paper.

## 6 Conclusion

Under the measured contract, one-hop source dictionary compression reduces complete archival storage while preserving source bytes and historical rankings. The benefit comes with higher logical reconstruction work and is workload-dependent. The main next question is whether the explicit dependency bounds offer a favorable cost frontier against stronger delta policies and larger independent histories, not whether an additional speculative algorithm can be appended to the system.

## References (working)

[1] K. Berberich, S. Bedathur, T. Neumann, G. Weikum. A Time Machine for Text Search. SIGIR 2007. https://doi.org/10.1145/1277741.1277831

[2] M. Staudinger, F. Piroi, A. Rauber. Reproducible Hybrid Time-Travel Retrieval in Evolving Corpora. 2024 preprint. https://arxiv.org/abs/2411.04051

[3] M. Staudinger et al. TimIR: Time-Traveling Through IR History. https://repositum.tuwien.at/handle/20.500.12708/224602

[4] J. He, T. Suel. Optimizing Positional Index Structures for Versioned Document Collections. SIGIR 2012. https://doi.org/10.1145/2348283.2348319

[5] Scalable Methods for Storing and Retrieving Wikipedia Revision Histories for Large-Scale Analysis. https://doi.org/10.1145/3787449 (complete author/venue metadata to verify before submission).

[6] S. Bhattacherjee et al. Principles of Dataset Versioning: Exploring the Recreation/Storage Tradeoff. https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/

## Artifact evidence

- [R131 sensitivity and codec results](../rounds/round-131/report.md)
- [R130 matched-control results](../rounds/round-130/report.md)
- [R129 protocol and report](../rounds/round-129/report.md)
- [CPython manifest and measurements](../../experiments/round-129/results-cpython.json)
- [BIPs manifest and measurements](../../experiments/round-129/results-bips.json)
- [R129 original-code CI](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45491997407)
- [v0.1 development evidence index](manuscript-v0.1.md)
