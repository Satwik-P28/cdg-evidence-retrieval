# Bounded Source Reconstruction and Reproducible Retrieval in Versioned Document Archives

ACMSE 2027 full paper | anonymous working draft | 2026-11-28

**Draft status:** content-first rewrite of manuscript v0.33. Not yet in the mandatory conference LaTeX template, not page-checked, not ready to submit. Primary evidence R148/R151/R153/R159/R160; R136/R140/R143/R147 support controls and limitations. All numerical claims below require author review against raw results and references before submission.

## Abstract

Reproducing a search over an evolving document collection requires both the exact historical source bytes and the collection statistics at the original retrieval cutoff. Maintaining independent snapshots is straightforward but can duplicate source frames and index entries. We evaluate a transactional archive that combines causal source-delta admission under explicit decoded-byte and compressed-frame activation budgets, exact-content positional-index sharing, and generation-bound ranking receipts. In a feature-matched factorial experiment over 74,364 derived NewsEdits revisions, the complete archive decreases from 245.41 MB for deduplicated snapshots with revision indexing to 157.26 MB for marginal frame-cost selection with content-quotient indexing (35.92% less). Relative to the stronger quotient-snapshot control, the reduction is 13.95%. All tested source readbacks, historical rankings, and receipt commitments agree. The measured maximum logical decoded amplification is 2.488 and compressed-frame activation does not exceed 1.5 times the independently compressed revision size. Experiments on four real Git documentation histories show reductions of 28.12% to 42.15% against the snapshot/revision control. An efficient matched ranking baseline shows no inherent retrieval speed advantage. We characterize the storage and reconstruction trade-off rather than proposing a new compression codec or temporal ranking primitive.

## 1 Introduction

A citation or search result over a mutable document collection is not, by itself, reproducible evidence. A document may subsequently change, and even unchanged documents may receive different lexical relevance scores as the population of active documents changes. Retaining the latest text alone does not permit faithful replay. Retaining every independent snapshot or index row restores historical access but can impose avoidable storage costs when sources are repeated or incrementally revised.

The research question is whether a local archive can reduce complete retained storage while preserving three properties simultaneously: exact source recovery, native-compatible historical ranking, and verifiable binding between the selected source and a previously committed retrieval result. The archive additionally constrains logical reconstruction work per source request. Depth alone does not bound this work because a short revision may depend on a much larger earlier revision.

Our contributions are (1) an evaluated causal source representation policy that selects literal or one-hop dictionary-coded frames under two explicit logical byte budgets; (2) an exact-content quotient positional index integrated with historical revision multiplicities and transactional receipt commitments; and (3) a factorial complete-archive evaluation on derived news and real Git ancestry, including efficient ranking controls, process-death tests and process-level I/O observations. Each component has established precedents; the contribution is the joint systems evaluation under a stated contract.

## 2 Related work

Temporal full-text retrieval and historical ranking are established [1,2]. TimIR reproduces historical sparse rankings by retaining versioned statistics; we do not claim that historical BM25 replay is novel. He and Suel study redundant positional fragments in versioned collections [3]. Dataset versioning has formalized storage versus recreation-cost trade-offs [4], and Git packfiles provide practical depth-limited delta compression [5]. The comparison here is narrower: the same source/index/provenance contract is retained while source encoding and exact-content index sharing are varied independently. Prior systems are relevant controls, not complete-system comparisons. R140 reproduces a pinned TimIR scoring component, not its whole service.

## 3 Archive design and correctness contract

### 3.1 Version identity and snapshot ranking

An append-only generation g identifies an update to document a. Each retained revision has original UTF-8 bytes, length, SHA-256 digest and a validity interval [start,end). At cutoff c, one revision per active document contributes to collection size and token total. An exact-source content identifier is shared by byte-identical revisions only after verifying content equality; separate revision identities, validity intervals and origin metadata remain.

For a quoted phrase p, retrieve exact phrase counts from full-detail positional FTS5, expand each matching content to its active revision identities, and calculate BM25 using the active population. For a cutoff c, N_c is the number of active documents, T_c their total normalized token count, and df_c the active document frequency of p. Average length is T_c/N_c. Use k1=1.2, b=0.75 and FTS5-compatible IDF flooring; sum contributions for distinct quoted phrases composed with AND or OR. Preserve overlap counts, score tie-breaking and top-ten ordering. This is a limited lexical query contract, not arbitrary FTS5 syntax, dense retrieval or generated-answer evaluation.

Quotient correctness follows from exact byte equality under a fixed deterministic tokenizer: each shared content has identical phrase frequencies and normalized length, while the multiplicity expansion restores the active revision population. In particular, document frequency counts active revision identities, not distinct contents. Changing the active set therefore changes statistics even if indexed content is unchanged.

### 3.2 Bounded source encoding

For new revision bytes x, let F(x) be an independent Zstandard frame. For an eligible earlier literal anchor b of the same document, let D(x|b) be a Zstandard frame using b as a raw-content dictionary. Examine up to four recent independently stored anchors. Admit a candidate only if:

* |b| + |x| <= 2.5 |x|;
* |D(x|b)| <= 0.8 |F(x)|;
* |F(b)| + |D(x|b)| <= 1.5 |F(x)|.

Select by marginal encoded-frame cost, crediting verified reuse and charging catalog overhead, then apply deterministic tie-breaking. If no candidate qualifies or reduces marginal cost, retain an independent frame. A selected delta never depends on another delta.

Under these assumptions, the decoder materializes at most one literal parent and the requested revision. The two admission inequalities directly bound the logical decoded-source bytes and activated compressed-frame bytes of that operation. These are not bounds on physical page reads, allocator memory, or CPU time. Check length and SHA-256 on recovery.

### 3.3 Transactions and receipts

A SQLite transaction couples frame references, source revision identity, index rows, validity statistics and provenance commitments. The receipt includes cutoff, normalized query, scoring contract, active population statistics, document frequencies, ordered results, source digests and scores; the v2 commitment binds the designated origin metadata. Verification relies on a separately trusted expected commitment. Hashing does not establish publisher identity or defend against an adversary who can replace all trusted commitments. Process-death tests assess atomic visibility and orphan recovery, not hardware power-loss durability. The implementation is local single-writer experimental software.

## 4 Evaluation

### 4.1 Protocol and controls

R159 crosses source encoding (deduplicated snapshots versus marginal bounded recipes) with positional indexing (one row per revision versus exact-content quotient). All four arms use the same source retention, transaction/provenance schema, native ranking semantics and receipt contract. R153 supplies the efficient revision-scoring control, avoiding an earlier ledger-scan confound. The 74,364 derived AP NewsEdits revisions and the nested 10,009-revision cohort are not independent samples; global ingestion order is synthetic. R160 repeats the integrated comparison on four pinned first-parent Git histories, with selected paths retained across observed states and cutoffs at actual commits. Report complete apparent archive bytes after finalization, including metadata and sidecar, separately from logical reconstruction and process I/O. Warm and reopen/advised timings are descriptive.

### 4.2 Complete archive size

| Source encoding | Revision indexing, B | Quotient indexing, B |
|---|---:|---:|
| Deduplicated snapshots | 245,412,623 | 182,743,823 |
| Marginal bounded recipes | 219,925,031 | 157,256,231 |

The combined reduction is 35.92%. Holding quotient indexing fixed, the source encoding reduction is 13.95%; holding marginal encoding fixed, index sharing reduces size by approximately 28.50%. The separate factors matter: comparing only the combined configuration with the revision-index baseline conflates two distinct benefits. R151's original bounded-anchor revision archive (220,334,630 B) is a further matched control, not the snapshot baseline.

| Real history | Snapshot/revision, B | Marginal/quotient, B |
|---|---:|---:|
| CPython documentation | 8,601,555 | 4,975,688 |
| Bitcoin BIPs | 7,033,959 | 4,611,175 |
| Git documentation | 8,440,385 | 5,242,971 |
| Kubernetes documentation | 2,912,939 | 2,094,000 |

Quotient indexing is not universally beneficial relative to marginal/revision alone: on three of these histories its extra metadata raises complete size. This is an important observed boundary on the method rather than a reason to suppress the control.

### 4.3 Reconstruction, ranking and provenance

Across the two nested AP cohorts and four arms, R159 reports 337,492 exact source checks, 2,048 rank checks and 512 verified receipt replays. R160 reports 7,180 source checks, 5,120 native rank checks, 1,280 receipts and 7,757 Git-tree path checks. These are counts of checks, not independent samples or distinct unique revisions. The logical reconstruction bounds pass; R151 observed maxima 2.487654 decoded and 1.5 activated relative to their respective denominators. Report zero observed ranking discrepancies only within the evaluated query contract.

### 4.4 Performance and negative controls

R153's efficient revision and quotient rank-receipt paths have median latencies 1.103 and 1.128 ms respectively. The large apparent improvement against a prior legacy revision scorer was confounded by a full ledger scan. We do not assert a ranking acceleration due to index sharing. R159's reopen/advised process-accounted measurements find lower summed rank read_bytes in the combined arm but slightly higher source read_bytes, and slower median advised ranking (34.364 vs 25.028 ms). These measurements are not guaranteed cold or physical device-sector counts. Depth-only source controls, finalized Git packs and pinned TimIR scoring reproduction illuminate different trade-offs and must be described with their feature mismatches. Additional index-subsystem exploration is outside the integrated paper's measured claims.

## 5 Limitations

The news ingestion schedule is synthetic. Technical histories are selected first-parent path-touch cohorts with no tested path deletion or rename; a multi-file commit is not a single atomic ingestion transaction. Results are limited to supported UTF-8 source text and lexical BM25 semantics. Source fidelity does not imply factual truth, entailment, reduced hallucination, or better LLM answers. The measured archive is not a production distributed system. Existing algorithms cover key mechanisms, and complete external systems have not been reproduced feature-for-feature. Timing varies with environment, and independent human reproduction has not yet occurred.

## 6 Conclusion

Under an explicit source-recovery and historical ranking contract, combining bounded marginal source compression and exact-content index sharing reduces complete storage relative to matched snapshots. The factorial comparison and four real Git histories expose when the representation is beneficial and when metadata erodes its gains. The result supports a reproducible storage design point, not a universally faster index or a new compression primitive.

## References to verify and format

1. Berberich et al., A Time Machine for Text Search, SIGIR 2007. https://doi.org/10.1145/1277741.1277831
2. Staudinger, Piroi, Rauber, Reproducible Hybrid Time-Travel Retrieval in Evolving Corpora, 2024. https://arxiv.org/abs/2411.04051
3. He and Suel, Optimizing Positional Index Structures for Versioned Document Collections, SIGIR 2012. https://doi.org/10.1145/2348283.2348319
4. Bhattacherjee et al., Principles of Dataset Versioning: Exploring the Recreation/Storage Tradeoff. https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/
5. Git pack-objects documentation. https://git-scm.com/docs/git-pack-objects

## Author review before submission (not manuscript text)

Expand methods with exact receipt schema, precise marginal cost/tie rule from R151 source, frozen manifests/cutoffs, test protocol, baseline detail and related-work verification. Convert into conference template, add architecture and factorial/reconstruction figures, cite source datasets, tokenizer, codec, SQLite and native extension. Verify R160 reductions and R153 timing context. Include truthful ACM AI-research-use disclosure in methods: AI tools materially assisted design, coding, experiments, analysis, review and drafting; describe actual tools, human verification, any remaining limits, no AI authors. Remove identifying repository links and author details from anonymous version; consult chairs about distinct simultaneous poster and paper.
