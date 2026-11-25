# Storage-Efficient Reproducible Evidence Retrieval in Evolving Document Collections

**Manuscript v0.19 | 2026-11-25 | Internal draft. Integrated archive validated. Not submission-ready.**

## Abstract

Reproducing retrieval over evolving corpora requires both the original evidence bytes and historical ranking statistics. We evaluate a revision archive with explicit logical source reconstruction bounds, transactional packed storage, a positional full-text index and structured replay receipts. On four pinned technical-document histories, its transactional packed representation is within −0.19% to +1.25% of finalized depth-one Git pack storage with matched retrieval metadata; the comparison does not establish update parity. On 74,364 derived news revisions from 12,841 NewsEdits AP articles, it reduces complete archival storage from 312.5 to 223.1 MB (28.6%) relative to transactional independent snapshots, with exact tested source and historical rank replay. On the same news source-only workload, conventional depth-eight chains and one-hop anchors reach maximum logical decoded-byte ratios of 489.02 and 128.89, compared with 2.488 for the proposed policy. Thirty-six enumerated process-death cases validate commit visibility and orphan recovery, not power-loss durability. In a synthetic ordinal ingestion schedule, 395 of 1,430 historical hit occurrences lose a query-matching line when resolved against the latest version. A pinned TimIR component reproduction confirms existing historical ranking capabilities; a query-conditioned materialization ablation fails to generalize. The contribution is the integrated source and ranking replay contract and empirical cost characterization, not a novel general-purpose compression algorithm or a claim of improved generative answer accuracy.

## 1 Introduction

A citation to a mutable document is insufficient to reproduce the evidence observed by an earlier retrieval run. Even if the original source bytes remain available, ranking may drift because newly added documents alter the collection size, document-frequency statistics and average length. Historical retrieval therefore requires both source identity and snapshot-specific scoring. Maintaining a separate complete archive and index for each state is straightforward but potentially redundant.

We study a practical implementation that retains exact source revisions, indexes all retained versions once using native full-detail SQLite FTS5, and derives active-snapshot relevance from validity intervals and historical collection statistics. Source compression is decoupled from the retrieval scorer. This permits a feature-matched evaluation in which alternative source representations cannot obtain storage savings merely by dropping positions, ranking data, or evidence metadata.

Our contribution candidates are (i) a precise source and ranking replay contract implemented with atomic version and index maintenance; (ii) an evaluation of bounded source dependencies with all index and provenance metadata charged; and (iii) an empirical characterization of where positional and term-frequency representations change the storage/latency tradeoff. The first two are the core of this draft. We do not claim that temporal retrieval, delta compression, BM25, hash commitments, or positional indexing are new. The contribution is an integrated evaluation, not a claim to invent any component; a full external-system comparison remains outstanding. Dataset versioning has already formalized storage versus recreation-cost optimization [6]; our proposed evaluation concerns this specific source/ranking contract, not novelty of that optimization problem.

## 2 Related work

Berberich et al. established efficient temporal full-text retrieval through temporal extensions of inverted indexes [1]. Staudinger et al. explicitly address reproducible ranked lists in evolving corpora with historical retrieval [2,3]. These are particularly close baselines for the ranking-replay objective; historical BM25 reproducibility alone is not a novelty claim. He and Suel exploit redundant fragments to compress positional indexes for versioned documents [4]; our exploratory R124–R127 controls confirm that positional parity and physical page overhead matter. Source delta compression and anchor selection are also established, including WikECD's revision-history compression and reconstruction framework [5]. Our scope is the jointly accounted source/index/receipt implementation and bounded source reconstruction policy, subject to comparison against these prior systems. We have not reproduced their full implementations or established superiority over them.

The graph optimization work of Guo et al. [7] and Git's established pack candidate-window and depth controls [8] further preclude novelty claims about bounded dependencies or candidate search in general. TimIR already reconstructs sparse historical rankings and uses result-list hashes for verification. WikECD already selects anchors dynamically. Our comparison concerns the precise joint source/ranking contract and the measured complete-archive costs. We have not established superiority to these complete systems.

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

### 4.8 Fresh histories and independent runner replication (R132)

All six jobs passed on d7be66b25d0c7084b8d5cfe163b817238f453a70, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45496514345. Four unique corpus/window configurations; repeated large jobs must not be counted as new datasets. Frozen bounded policy is nondominated in all four measured configurations. Latest-only and original four-candidate encodings match exactly in all four configurations by ordered dependency and payload digest. Large replicates agree on manifests, workload, deterministic metrics and encoding digests for every policy. Conventional anchor8 is smaller on both Kubernetes configurations; CDG has lower worst-case activation and decode ratios, not universal storage superiority. Exclusions of missing paths and different baseline windows limit pure scaling interpretation. Two runner repetitions are descriptive, not a confidence interval.

| Corpus | Window | Retained docs | Revisions | Snapshot B | Bounded B | Saving | Depth-8 premium | Decode reduction vs prev8 | Anchor8 B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gitdocs | 400 | 80 | 221 | 3526656 | 2187264 | 37.98% | 0.00% | 44.20% | 2203648 |
| gitdocs | 800 | 160 | 667 | 9461760 | 5582848 | 41.00% | 5.09% | 53.97% | 5615616 |
| k8sdocs | 400 | 69 | 144 | 1269760 | 929792 | 26.77% | 1.79% | 40.37% | 925696 |
| k8sdocs | 800 | 141 | 378 | 3334144 | 2215936 | 33.54% | 3.84% | 50.86% | 2207744 |

| Corpus | Runner CPU | Seed | Append median us | Source read median us |
|---|---|---:|---:|---:|
| gitdocs | Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz | 133 | 1286.16 | 78.01 |
| gitdocs | AMD EPYC 7763 64-Core Processor | 132 | 1506.54 | 81.51 |
| k8sdocs | AMD EPYC 9V74 80-Core Processor | 133 | 860.81 | 39.20 |
| k8sdocs | Intel(R) Xeon(R) 6975P-C | 132 | 783.80 | 36.48 |

### 4.9 Claim audit (R133)

The explicit one-hop logical byte inequalities follow directly from eligibility and the decoder visiting only a literal parent and the requested revision. They do not bound page reads, execution time or memory, nor imply global optimality of greedy selection. See the R133 audit for proof scope and a preregistered restricted offline oracle. Both R133 jobs passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45497029658). On Git (667 revisions), greedy payload 884,795 B versus restricted offline optimum 871,706 B (1.48% less); six of 160 documents improved. On Kubernetes (378 revisions), greedy 349,176 B versus 344,556 B (1.32% less); four of 141 documents improved. These are source-only comparisons, not archive size or general optimality. The oracle verifies the frozen R132 manifest and reproduces the k1 payload totals. Further tuning of this restricted policy has little measured headroom on these two cohorts.

### 4.10 External Git pack comparison (R134)

All four original-code jobs passed on 6635c9d163c1dea640ccf1ccd4f5593032af2512 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45498911419), with 8,975 exact source readbacks, 6,400 historical rank checks and zero observed BM25 score error. Native Git packfiles at depth 1 produce smaller finalized archives than CDG in every corpus: CDG incurs a 6.4–11.5% complete-archive premium. Worst-request logical decoded ratios for CDG are 2.04–2.25x versus 3.04–12.66x for depth-1 Git. Mean logical decoded work is also lower for CDG, but the difference is modest. Git pack depth does not constrain relative reconstructed byte volume: a single large parent can exceed a small requested object by an arbitrary factor. These are empirical finalized readback comparisons, not matched incremental updates or crash semantics. Git uses offline cross-document selection and charges entry headers in activation accounting. Its compressed objects reside outside SQLite, unlike CDG, so page-layout effects contribute to total size differences. This motivates an additional layout-matched control; no pure codec or timing superiority claim.

| Corpus | Policy | Total archive B | Mean decode ratio | Max decode ratio | Max activated ratio | Depth |
|---|---|---:|---:|---:|---:|---:|
| k8sdocs | snapshot | 3334144 | 1.0000 | 1.0000 | 1.0000 | 0 |
| k8sdocs | bounded_anchor | 2215936 | 1.7797 | 2.2496 | 1.4090 | 1 |
| k8sdocs | git_pack_depth1 | 1987197 | 1.9217 | 11.2576 | 8.4506 | 1 |
| k8sdocs | git_pack_depth8 | 1937308 | 2.8807 | 30.5929 | 10.9250 | 5 |
| k8sdocs | git_pack_depth50 | 1936778 | 3.5098 | 30.5929 | 10.9250 | 7 |
| bips | snapshot | 7589888 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | bounded_anchor | 4780032 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | git_pack_depth1 | 4481814 | 1.9100 | 3.0444 | 2.5605 | 1 |
| bips | git_pack_depth8 | 4423074 | 3.0208 | 8.3150 | 2.7034 | 7 |
| bips | git_pack_depth50 | 4422008 | 3.5723 | 10.4394 | 2.7168 | 9 |
| cpython | snapshot | 9166848 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | bounded_anchor | 5210112 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | git_pack_depth1 | 4896182 | 1.9061 | 12.6649 | 9.0721 | 1 |
| cpython | git_pack_depth8 | 4807716 | 3.1593 | 8.2150 | 1.6265 | 7 |
| cpython | git_pack_depth50 | 4806305 | 3.8686 | 12.3863 | 1.6265 | 11 |
| gitdocs | snapshot | 9461760 | 1.0000 | 1.0000 | 1.0000 | 0 |
| gitdocs | bounded_anchor | 5582848 | 1.8203 | 2.1584 | 1.2603 | 1 |
| gitdocs | git_pack_depth1 | 5008193 | 1.8711 | 3.0358 | 1.9381 | 1 |
| gitdocs | git_pack_depth8 | 4932777 | 2.8900 | 8.1857 | 1.9752 | 7 |
| gitdocs | git_pack_depth50 | 4930576 | 3.2654 | 11.4523 | 1.9785 | 10 |

### 4.11 Physical layout and published WikECD (R135)

All four jobs passed on 79bd29fd747d95134e578179e71a46787a209b5e, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45499545120. 10,770 exact readbacks and 7,680 historical ranking comparisons, zero observed score error. Packed CDG is within -0.39% to +1.17% of finalized Git depth-1 total size from R134; the logical reconstruction metrics are unchanged from inline CDG. Relative to matched packed independent snapshots it reduces total bytes by 30.9–42.6%. Published WikECD 0.1.1 default artifacts occupy 24.9–57.9% more-reducible total archive bytes (CDG reduction relative to WikECD). Both tested WikECD settings produce almost entirely literal anchors; neither establishes a strong tuned WikECD frontier, and no Wikipedia-native corpus has been tested here. WikECD partition-prefix source volume is a proxy, not actual decoder byte traffic; separately measured full JSON inflation/activation must not be conflated with it. Sidecar layout does not have atomic append/crash parity.

| Corpus | Policy | Total archive B | SQLite B | Sidecar B | Mean logical decode ratio | Max activation ratio |
|---|---|---:|---:|---:|---:|---:|
| bips | snapshot | 7589888 | 7589888 | 0 | 1.0000 | 1.0000 |
| bips | bounded_anchor | 4780032 | 4780032 | 0 | 1.8559 | 1.2077 |
| bips | snapshot_sidecar | 6983452 | 3932160 | 3051292 | 1.0000 | 1.0000 |
| bips | bounded_anchor_sidecar | 4500574 | 3932160 | 568414 | 1.8559 | 1.2077 |
| bips | wiki_default | 7843814 | 3932160 | 3911654 | 1.0000 | 47.5466 |
| bips | wiki_large_budget | 7848411 | 3932160 | 3916251 | 1.0010 | 47.5468 |
| cpython | snapshot | 9166848 | 9166848 | 0 | 1.0000 | 1.0000 |
| cpython | bounded_anchor | 5210112 | 5210112 | 0 | 1.8557 | 1.1583 |
| cpython | snapshot_sidecar | 8600360 | 4194304 | 4406056 | 1.0000 | 1.0000 |
| cpython | bounded_anchor_sidecar | 4939587 | 4194304 | 745283 | 1.8557 | 1.1583 |
| cpython | wiki_default | 11719088 | 4194304 | 7524784 | 1.0000 | 53.5656 |
| cpython | wiki_large_budget | 11719636 | 4194304 | 7525332 | 1.0000 | 53.5658 |
| k8sdocs | snapshot | 3334144 | 3334144 | 0 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor | 2215936 | 2215936 | 0 | 1.7797 | 1.4090 |
| k8sdocs | snapshot_sidecar | 2864806 | 1630208 | 1234598 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor_sidecar | 1979384 | 1630208 | 349176 | 1.7797 | 1.4090 |
| k8sdocs | wiki_default | 2637350 | 1630208 | 1007142 | 1.0000 | 34.9299 |
| k8sdocs | wiki_large_budget | 2638392 | 1630208 | 1008184 | 1.0008 | 34.9305 |
| gitdocs | snapshot | 9461760 | 9461760 | 0 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor | 5582848 | 5582848 | 0 | 1.8203 | 1.2603 |
| gitdocs | snapshot_sidecar | 8358433 | 4182016 | 4176417 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor_sidecar | 5066811 | 4182016 | 884795 | 1.8203 | 1.2603 |
| gitdocs | wiki_default | 8355922 | 4182016 | 4173906 | 1.0000 | 36.6238 |
| gitdocs | wiki_large_budget | 8361662 | 4182016 | 4179646 | 1.0024 | 36.6243 |

### 4.12 Large real news revision workload (R136)

R136 completed on commit 9b06f135 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45500923265). Exhausted all 12,841 eligible AP documents, yielding 74,364 derived text revisions (target 100,000 not reached), 327,838,512 raw bytes and 446,184 exact readbacks across six policies. Source-only SQLite bytes fall from 300,437,504 to 132,505,600 (55.90% reduction) for bounded_anchor. Relative to prev8 the archive premium is 17.68% and mean logical decoded work falls 54.84%. Worst-case decoded ratios: prev8 489.02x, anchor8 128.89x, CDG 2.4877x; worst activation CDG 1.5x. Four candidates improve source SQLite size by 4.15% and payload by 4.41% against k1, reversing the small-corpus equivalence finding. This is evidence of workload sensitivity, not universal multi-anchor superiority. NewsEdits is derived sentence text; no original news byte identity, FTS index, chronological global replay, or RAG accuracy is tested. The source database and selection hashes are recorded in results.

| Policy | Source SQLite B | Payload B | Mean decode | Max decode | Max activation |
|---|---:|---:|---:|---:|---:|
| snapshot | 300437504 | 149369811 | 1.0000 | 1.0000 | 1.0000 |
| prev8 | 112594944 | 51566108 | 3.6380 | 489.0189 | 86.8889 |
| anchor8 | 148963328 | 67227462 | 1.7436 | 128.8889 | 50.5926 |
| k1 | 138244096 | 62752187 | 1.6220 | 2.4877 | 1.5000 |
| bounded_anchor | 132505600 | 59982761 | 1.6428 | 2.4877 | 1.5000 |
| tight_activation | 134160384 | 62421909 | 1.5921 | 2.3164 | 1.1000 |

### 4.13 Commit-last packed source storage (R137)

All four original-code jobs passed on 17e8c5ef, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45501430997. Across two packed arms and four cohorts: 3,590 exact source readbacks, 2,560 historical rank comparisons, 640 pinned receipt comparisons, zero observed score error, 36 enumerated process-death cases (additional duplicate unit executions not counted). All nine stages per corpus recovered with expected generation visibility and successful retry, including old pinned readers. Packed snapshot and bounded payload totals match frozen controls. Packed transactional archive adds 4,128 bytes relative to R135 finalized CDG on each corpus, remaining between -0.19% and +1.25% of finalized native depth-1 Git bytes. The comparison is storage/readback parity only, not Git update parity. Append latency includes per-frame fsync; no same-run inline timing arm. Process death is not power loss, cooperating writers only, no file creation crash or compaction guarantee.

| Corpus | Policy | Archive B | Payload B | Append median us | Read median us | Mean decode | Max decode |
|---|---|---:|---:|---:|---:|---:|---:|
| k8sdocs | snapshot | 2868934 | 1234598 | 1275.43 | 28.39 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor | 1983512 | 349176 | 1353.57 | 39.58 | 1.7797 | 2.2496 |
| gitdocs | snapshot | 8362561 | 4176417 | 2063.23 | 27.61 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor | 5070939 | 884795 | 1805.60 | 44.52 | 1.8203 | 2.1584 |
| bips | snapshot | 6987580 | 3051292 | 1545.94 | 36.51 | 1.0000 | 1.0000 |
| bips | bounded_anchor | 4504702 | 568414 | 1620.41 | 52.22 | 1.8559 | 2.0696 |
| cpython | snapshot | 8604488 | 4406056 | 2912.61 | 84.29 | 1.0000 | 1.0000 |
| cpython | bounded_anchor | 4943715 | 745283 | 3250.46 | 122.72 | 1.8557 | 2.0360 |

### 4.14 Integrated historical retrieval at news scale (R138)

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

### 4.15 Negative result: query-conditioned materialization (R139)

Both original-code jobs passed (029cabdf, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45503944736). Query-density materialization does not transfer reliably: on the full 74,364-revision cohort, at 50 bp of prefix payload (166,337 B budget), training avoided 403,380 decoded bytes, heldout avoided 5,790 of 4,999,880 bytes (0.116%); LFU saved 12,867 (0.257%), uniform saved 12,735 (0.255%). Fractional hindsight upper bound 818,703 bytes (16.37%) is not achieved or necessarily feasible as an integer allocation. At 1, 5 and 10 bp query-density saves zero heldout bytes; on nested 10,009-revision cohort it saves zero at every budget. Sparse disjoint lexical probes limit generalization; results do not establish that real access prediction is impossible. No physical rewrite or online performance claim. Exclude materialization from main contribution, retain negative result.

### 4.16 TimIR component reproduction (R140)

All three original-code jobs passed on 39110266 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45508779561). Unmodified upstream backend builds. On BIPs and Git documentation, the actual pinned TimIR DAO scoring SQL running on MonetDB 11.55.7 with Lucene 8.4.1 tokenization/norms exactly matches the ordered native Lucene result names for all 576 single-term historical comparisons, with 576 exact repeat checks; maximum common-score discrepancies 0.000587771 and 0.000800752, respectively. These are distinct scorer semantics, not directly comparable to FTS5 score errors. Upstream SHA256 SQL fingerprint is in raw results. Docker image digest sha256:a71e6e8c8402beadc51aebf944b465ee5b185c7ae4a9e6808b5d9133ee921786. This is a strong existing historical rank competitor; no claim CDG improves TimIR rank quality, size or speed. Component-level reproduction, not full-service ingestion or full matched source storage.

### 4.17 Dated labeled retrieval (R141)

R141 passed on b8f28140 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45510196315). 1,161 released source texts for 1,157 URLs (only four multiversion URLs), six distinct cutoffs, 256 deterministic cases of 1,621 eligible; 3,700 ambiguous/nonextractive cases excluded. Historical vs latest-only answer-token coverage: top-1 93/256 vs 82/256, top-5 140 vs 144, top-10 146 vs 151. Two historical-only and seven latest-only top-10 successes. Ordered document lists change on 220/256; latest-URL resolution of original hits retains 146/256 top-10 coverage. Both snapshot and CDG replay all 256 historical receipts exactly, zero observed score error, 2,322 exact source readbacks and 5,094 evidence hit occurrences across arms. Complete archive 6,583,848 -> 6,564,548 bytes (0.293% reduction). Little revision redundancy explains limited compression benefit; no claim of semantic answer accuracy or consistent relevance superiority. Actual released read timestamps, not event timestamps; extracted text, relation-derived questions with human-validated sources, lexical gold presence proxy.

### 4.18 Large-scale external pack controls (R142)

R142 both jobs passed on e3258cb7 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45511038427). Full AP has 41,282 unique source objects, 33,082 duplicate revision occurrences. Transactional CDG 223,142,857 B; coalesced CDG 215,190,054 B; coalesced snapshots 240,460,559 B; Git depth-one 214,888,975 B. Coalesced CDG premium 0.1401%, transactional CDG premium 3.84%; mean decode 1.64283 vs Git1 1.39757; maximum decode 2.48765 vs 32.58966 (92.37% lower), maximum activation 1.5 vs 19.10818. All seven arms on both nested cohorts: 590,611 exact readbacks, 3,584 ranking comparisons, zero observed score error. Coalescing is finalized read-only, not transactional. Git average logical decoding wins; no CPU or I/O superiority claim.

| Revisions | Policy | Complete B | Mean decode | Max decode | Max activation |
|---:|---|---:|---:|---:|---:|
| 74364 | snapshot | 312521715 | 1.0000 | 1.0000 | 1.0000 |
| 74364 | bounded_anchor | 223142857 | 1.6428 | 2.4877 | 1.5000 |
| 74364 | snapshot_coalesced | 240460559 | 1.0000 | 1.0000 | 1.0000 |
| 74364 | bounded_anchor_coalesced | 215190054 | 1.6428 | 2.4877 | 1.5000 |
| 74364 | git_pack_depth1 | 214888975 | 1.3976 | 32.5897 | 19.1082 |
| 74364 | git_pack_depth8 | 215040168 | 1.4361 | 22.4914 | 12.8679 |
| 74364 | git_pack_depth50 | 214965895 | 1.4584 | 44.3464 | 20.5990 |
| 10009 | snapshot | 42846800 | 1.0000 | 1.0000 | 1.0000 |
| 10009 | bounded_anchor | 30691764 | 1.6459 | 2.4826 | 1.4983 |
| 10009 | snapshot_coalesced | 33415658 | 1.0000 | 1.0000 | 1.0000 |
| 10009 | bounded_anchor_coalesced | 29820949 | 1.6459 | 2.4826 | 1.4983 |
| 10009 | git_pack_depth1 | 29657017 | 1.4379 | 14.4250 | 9.9435 |
| 10009 | git_pack_depth8 | 29566234 | 1.5139 | 30.1449 | 14.9159 |
| 10009 | git_pack_depth50 | 29557987 | 1.5352 | 38.9305 | 14.9159 |

### 4.19 Adversarial transactional validation (R143)

R143 both stress jobs passed on 24b5114b (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45511276311). 1,280 acknowledged operations across eight concurrent process-death cases, 1,290 committed source checks, 168 pinned-reader checks, 96 native rank comparisons, 12 injected failure cases. All expected commit visibility and retry conditions pass. Eight source/pointer corruption cases rejected; two origin-metadata mutations leave v1 receipt unchanged, confirming known provenance-binding gap. Python fault injection, not VFS or power-loss validation.

### 4.20 Provenance commitment repair (R144)

Corrected R144 commit 0e4ce97d passed both jobs (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45568478507). 19 unit tests per job: nine mutation cases, nine process-death stages, SQL UDF regression. Both v1/v2 arms on both nested AP cohorts: 256 historical ranking/replay checks, zero observed score error, 168,746 audited source occurrences (one complete audit per arm/cohort, repeated audits not counted). Identical compressed payloads. Full AP v2 adds 3,080,192 B (1.38%) and 5.11% median append latency in this run, but median replay rises from 45.217 to 393.885 ms (8.71x), p95 49.850 to 626.075 ms. Linear metadata-prefix scan is expensive. V2 binds manifest and origin rows against a trusted external digest; no publisher authentication or full nonhit-source verification per replay. Timings descriptive, sequential builds.

| Revisions | Receipt | Complete archive B | Append median us | Replay median us | Replay p95 us |
|---:|---|---:|---:|---:|---:|
| 74364 | v1 | 223142857 | 1093.43 | 45217.02 | 49850.16 |
| 74364 | v2 | 226223049 | 1149.30 | 393884.73 | 626075.08 |
| 10009 | v1 | 30691764 | 1028.61 | 6142.74 | 7009.25 |
| 10009 | v2 | 31109556 | 1053.82 | 47086.75 | 74877.05 |

### 4.21 Transactional encoded-frame reuse (R145, partial)

Corrected R145 commit 0028b46a: 10,009-revision job passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45691626610); full job still pending at archival. Snapshot 42,846,800 B, snapshot reuse 33,673,706 B, bounded anchor 30,691,764 B, bounded anchor reuse 30,111,765 B. Reuses 3,566 encoded frames, identical logical reconstruction metrics, 40,036 exact reads and 1,024 historical rank comparisons with zero observed score error. Catalog overhead charged. No full cohort claim.

### 4.22 Snapshot-local batch verification (R146)

Both R146 jobs passed on 911f44f3 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45691769935). Small cohort 16/64 receipt median total speedups 6.47x/5.76x; full cohort 7.50x/7.08x (6.652s to 0.887s; 16.488s to 2.329s). Full mixed metadata rows 2,790,544 to 74,364 (37.53x reduction). Single receipt unchanged/slightly slower; no asymptotic gain for single queries. All verified receipt bodies identical. Three warm randomized method-order repeats, no cross-transaction trust cache, no extra archive storage.

### 4.23 Full transactional deduplication (R145)

Both corrected R145 jobs passed on 0028b46a (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45691626610). Full AP: ordinary transactional snapshots 312,521,715 B, snapshot reuse 242,336,527 B, bounded-anchor 223,142,857 B, bounded-anchor reuse 217,258,534 B. Reuse eliminates 28,649 encoded frames and saves 5,884,323 complete archive bytes after catalog overhead (2.637%). Identical logical costs and source bytes. Across both cohorts, 337,492 exact source reads, 2,048 ranking comparisons, zero observed score error. Seventeen tests per job including 15 process-death configurations. No v2 provenance in these arms.

### 4.24 Integrated archive (R147)

Both R147 jobs passed on 0ff28386 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45692480729). Integrated archive 30,525,461 B (10,009 revisions) and 220,334,630 B (74,364 revisions). Full source payload 52,029,958 B, 45,715 distinct encoded frames, 28,649 redundant occurrences. Full maximum decoded ratio 2.4876543, activation 1.5, mean decoded ratio 1.6428339. Across nested cohorts 84,373 source reads, 512 native ranking checks, 128 batch receipt replays, 32 pinned checks; zero observed score error. Sixteen unit tests per job including new/reuse crash paths and independent provenance mutation. Full archive 29.50% smaller than original R138 transactional snapshots and 2.53% larger than finalized Git depth one, but neither comparator has v2 provenance. No feature-matched v2 snapshot comparison yet. Full 64-receipt batch 2.309s, descriptive single execution. No power-loss durability, publisher authentication or cross-run latency superiority claim.

## 5 Limitations and remaining submission gates

The largest integrated evaluation uses 74,364 derived NewsEdits AP revisions from 12,841 articles; the 10,009-revision cohort is nested and not an independent corpus. Its global ingestion order is synthetic. CLARK-News uses released source-read timestamps and relation-derived questions, but only four URLs have multiple versions. Gold-token coverage is not semantic answer correctness, and latest-only coverage can improve despite ranking drift. Technical-document cohorts exclude deleted paths; additions after cohort selection, deletion/rename semantics, and commit-wide atomic ingestion are not evaluated. Query probes are lexical and no generated-answer, vector retrieval, or hallucination benefit is established.

The R137 receipt v1 commits to source digests, rank statistics and cutoff, but not separate origin records or the corpus manifest; it requires a trusted externally retained receipt digest. Changing an origin commit ID or timestamp without changing source bytes or ranking can leave the receipt unchanged. This is a known contract limitation identified by code inspection; R143 confirms this with two explicit negative controls. Atomic origin-row storage is not cryptographic provenance authentication. R137 process-death tests are not hardware power-loss or filesystem fault tests, and assume cooperating local writers and no compaction. R143 verifies concurrent process-death and Python-layer I/O injections, not VFS faults.

Git pack parity is established only for finalized readback on four technical corpora, not equivalent transactional updates; R142 extends finalized parity to NewsEdits, with 0.14% coalesced premium and 3.84% transactional premium relative to depth-one Git. WikECD was tested at two mostly-literal settings, not a full tuned frontier. R140 reproduces actual TimIR historical-scoring SQL and native Lucene statistics, not the full deployed service or cross-engine performance parity. R139 query-aware materialization fails heldout generalization. Timing is descriptive, not cold device I/O or statistically established speed superiority. Independent human replication and artifact packaging remain outstanding.

## 6 Conclusion

Explicit byte budgets address a failure mode that depth limits alone do not bound. The integrated archive preserves tested historical source bytes and active-snapshot ranks while reducing complete storage relative to matched transactional snapshots, including 28.6% on the full derived AP corpus. Native Git and TimIR remain strong external controls; the evidence supports a systems contribution under the declared contract, not a universally superior codec or novel historical-ranking primitive. Limited redundancy in CLARK-News and negative heldout materialization results identify meaningful boundaries. R144 strengthens the provenance commitment under an externally retained digest, at substantial verification overhead; v1 results retain their original limited contract.

## References (working)

[1] K. Berberich, S. Bedathur, T. Neumann, G. Weikum. A Time Machine for Text Search. SIGIR 2007. https://doi.org/10.1145/1277741.1277831

[2] M. Staudinger, F. Piroi, A. Rauber. Reproducible Hybrid Time-Travel Retrieval in Evolving Corpora. 2024 preprint. https://arxiv.org/abs/2411.04051

[3] M. Staudinger et al. TimIR: Time-Traveling Through IR History. https://repositum.tuwien.at/handle/20.500.12708/224602

[4] J. He, T. Suel. Optimizing Positional Index Structures for Versioned Document Collections. SIGIR 2012. https://doi.org/10.1145/2348283.2348319

[5] Scalable Methods for Storing and Retrieving Wikipedia Revision Histories for Large-Scale Analysis. https://doi.org/10.1145/3787449 (complete author/venue metadata to verify before submission).

[6] S. Bhattacherjee et al. Principles of Dataset Versioning: Exploring the Recreation/Storage Tradeoff. https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/

[7] A. Guo et al. To Store or Not to Store: A Graph Theoretical Approach for Dataset Versioning. IPDPS 2024. https://arxiv.org/abs/2402.11741

[8] Git documentation. git-pack-objects. https://git-scm.com/docs/git-pack-objects

## Artifact evidence

- [R147 integrated archive](../rounds/round-147/report.md)

- [R145 frame reuse](../rounds/round-145/report.md)
- [R146 batch verification](../rounds/round-146/report.md)

- [R144 provenance-bound receipt](../rounds/round-144/report.md)

- [R142 large-scale native Git](../rounds/round-142/report.md)
- [R143 adversarial archive](../rounds/round-143/report.md)

- [R141 CLARK-News](../rounds/round-141/report.md)

- [R140 TimIR component reproduction](../rounds/round-140/report.md)

- [R139 negative materialization ablation](../rounds/round-139/report.md)

- [R138 integrated news retrieval](../rounds/round-138/report.md)

- [R137 transactional packed storage](../rounds/round-137/report.md)

- [R136 NewsEdits scale](../rounds/round-136/report.md)

- [R135 packed layout and WikECD](../rounds/round-135/report.md)

- [R134 external Git pack comparison](../rounds/round-134/report.md)

- [R133 claim and novelty audit](../rounds/round-133/report.md)

- [R132 fresh histories and replication](../rounds/round-132/report.md)
- [R131 sensitivity and codec results](../rounds/round-131/report.md)
- [R130 matched-control results](../rounds/round-130/report.md)
- [R129 protocol and report](../rounds/round-129/report.md)
- [CPython manifest and measurements](../../experiments/round-129/results-cpython.json)
- [BIPs manifest and measurements](../../experiments/round-129/results-bips.json)
- [R129 original-code CI](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45491997407)
- [v0.1 development evidence index](manuscript-v0.1.md)
