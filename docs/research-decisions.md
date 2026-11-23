# Research decisions, 12 November 2026

## Keep

**Exact source-coordinate representation.** Evidence should carry source version, canonicalizer identifier, ordered spans, access scope, and where verified an explicit map to original raw bytes. Supports noncontiguous fragments without pretending that a min-max bounding range is the actual evidence.

**Set-level evidence requirements.** Some answers require multiple complementary facts. Evaluate complete support, not only top-k relevance.

**Conditional complexity.** Ordinary retrieval works well when discriminative query terms exist. Extra graph reasoning should only be used when the predicted benefit exceeds retrieval and computational costs.

**Read-cost accounting.** Marginal frame activation is a union-cost problem across candidate witnesses and already-activated frames. Measure it on compressed archives, not just in a byte-count model.

## Reject or downgrade

- Passage similarity as a correctness certificate.
- Exact quote alignment as entailment verification.
- Oracle witness cost improvements as deployable gains.
- One universally optimal frame size or neighbor boost.
- Synthetic high success rates as evidence of real-world superiority.
- Dependency prediction without calibration and out-of-distribution stress.
- Complexity that cannot beat BM25 or simple evidence expansion at matched budgets.

## Open hypotheses

- Learn query-conditioned dependencies from source structure and cross-document relationships without leakage of annotated gold sets.
- Gate graph reasoning by whether available observations distinguish plausible evidence sets.
- Jointly choose complete witnesses and physical frame activations, preserving exact provenance receipts.
- Recover gracefully from version changes and ACL invalidation without stale pointers.

## Next milestones

1. Independently authored multihop QA benchmark with held-out source families and exact evidence annotations.
2. Frozen tokenizer and reader; equal-cost baselines including hybrid ranker and set-selection.
3. True seekable Zstd and content-defined framing, storage index accounting and p50/p95 cold/warm retrieval.
4. Calibrated confidence and abstention; report support/citation/answer quality separately.
5. Ablations: no dependency model; no gating; no physical cost; no exact coordinate map.


---

# Research decision update, 19 November 2026 (Rounds 83–105)

## Evidence gates that passed

**Source integrity and differential indexing.** Original SciFact and original QASPER corpora are SHA-locked and the relevant sources are preserved exactly. Under matched documents, conventional source-readable and compressed-source contentless FTS5 give identical top-10 rankings. In dynamic data, ordinary contentless FTS5 special prior-text deletion, coupled in the same transaction with source block and paragraph receipt offsets, preserves original global BM25 index statistics. R104 checked 120 synthetic source revisions on 13,266 original QASPER records and 1,005 source queries, ten subprocess SIGKILL cases and WAL snapshot coherence.

**Human evidence retrieval under genuinely binding source+index bytes.** R95 SciFact, 6 MiB: preselected compressed Recall@10 155/188 vs strong preselected conventional 136/188; 8 MiB: 170/188 vs mean conventional 144.67/188. Both representations had to discard source documents. R98 independently replicated the direction on QASPER 888 human paragraph-evidence questions, but all question paper identities were provided, not open-domain retrieved. This tests **evidence availability**, NOT generated answer correctness or novel BM25.

**Strong individually decoded source representation.** R99 and R100 found uniform Brotli5 beat choosing a different standard codec per paragraph with an inconsequential physical gain for the per-paragraph oracle: zero on SciFact and one 4 KiB SQLite page on QASPER. R102 then demonstrated a stronger *existing prior-art* representation: a 64 KiB Zstandard dictionary learned from original QASPER TRAIN paragraphs only, independently applied to original article-disjoint DEV paragraphs. Zstd9/dictionary total source+FTS SQLite 8,687,616 B vs same-schema per-source Brotli5 9,506,816 B, **8.62% lower**; source SHA and 1,005 retrieval rankings unchanged. Dictionary bytes and metadata were charged inside the database.

## Joint source-block / access / update frontier

R101 and R103 showed grouping neighboring original paragraphs from the same paper and retaining exact source offsets/hashes can reduce idle persisted bytes, at the expense of extra source bytes decompressed when retrieving only one paragraph. Four candidate nondominated QASPER source designs from R103:

| Source layout / prior-art codec | Full source+FTS database | Top1 decoded-byte inflation | Top10 decoded-byte inflation |
| --- | ---: | ---: | ---: |
| Independent Zstd9 + 64KiB TRAIN dictionary | **8,687,616 B** | **1.000x** | **1.000x** |
| Zstd9 dictionary, 4 original paragraphs per block | **8,474,624 B** | 3.911x | 2.223x |
| Zstd9 dictionary, 8 original paragraphs per block | **8,454,144 B** | 7.355x | 2.966x |
| Zstd9 dictionary, entire original paper per block | **7,811,072 B** | 40.069x | 4.231x |

The group-of-16 design is **dominated** by group-of-8 in this static byte + top1 decompression cost projection, even though it is larger. Pareto statements are specific to those measured resources and that corpus, not universal method dominance.

R105 tested **120 identical synthetic revisions on each of 17 strong archive controls**, with WAL synchronous FULL and automatic checkpointing disabled. All 17 retained 13,266 original/live source receipts, independent conventional FTS global stats and all 1,005 top-ten rankings. The independently compressed Zstd9-dictionary archive versus **whole-paper** Zstd9-dictionary block archive demonstrated:

| Resource | Independent source | Whole original paper block |
| --- | ---: | ---: |
| Initial idle source+index SQLite | **8,687,616 B** | 7,811,072 B |
| Compressed block BLOB rewritten / edited source UTF-8 bytes | **0.406x** | 14.834x |
| Warm median source revision | **0.886 ms** | 2.546 ms |
| WAL bytes accumulated over 120 edits | **9,175,272 B** | 11,787,352 B |
| Main DB + uncheckpointed WAL, approximate peak | **17.86 MB** | 19.60 MB |

The whole-paper archive's **10.09% idle saving** created a **36.5x larger compressed-payload rewrite ratio** and a higher live DB+WAL footprint in this deliberate uncheckpointed WAL workload. The ratio of compressed BLOBs written to new source bytes is not a measured flash device write amplification; WAL file growth is not SSD bus write traffic. Warm single-runner duration is descriptive only.

## Decisions

**KEEP:** Immutable low-activity source archives may favor large grouped dictionary blocks. Frequently revised or random-access evidence may favor separately decodable dictionary-compressed source units. Source ID, original SHA, per-source offset receipts, block generations and FTS5 index transactions are non-negotiable.

**REJECT or downgrade:** one universal block size; any assumption that bigger compression levels or larger blocks strictly shrink data; per-source selection among zlib6/zstd3/Brotli5 as a high-impact static optimization; use of the original human gold answers after synthetic source edits; storage-only results as evidence of lower LLM hallucination; single-GitHub-runner warm timing as a production speed guarantee.

**RESEARCH HYPOTHESIS, NOT YET PROVEN:** Choose an evidence layout conditionally on independently observed historical read and revision rates, query top-k evidence needs, document relationships and resource budgets. A hot/cold dynamic store with atomic source migrations may improve a joint cost of persistent bytes + decoded block bytes + WAL writes + retrieval/context tokens. Existing compression and FTS components alone are established prior art. To claim a new research contribution, show a new predictive allocation algorithm with independent training/testing and strong matched-budget competitors.

## Next mandatory falsifiers

1. **R106:** Learn or predeclare an allocation rule based on TRAIN-only or historical source access/revision traces, evaluate **held-out** reads/updates and physical WAL/cold-SSD costs. Contrast with both strong independent Zstd dictionary and grouped dictionary baselines; include migration cost and correct source generation.
2. **R107:** Evaluate pretrained strong FactCG/MiniCheck/other grounded factuality controls on **actual retrieved** source text, with human claim-document annotation scoping. Do not transfer a correct source's label to a different retrieved source.
3. **R108:** Generate factual natural-language answers and evaluate human-annotated claim/evidence attribution and abstention on an independent benchmark. Measure answer quality separately from evidence retrieval and compression, with at least one strong dense/hybrid retrieval control.
4. Validate title-newline/structured source serialization, memory-safe decompress bounds, physical power-loss stress, multiwriter concurrency, cross-version citation validity and reported peak RAM.

### Reproducibility and direct links

- [R101 blocks, original source amplification](../research/rounds/round-101/report.md)
- [R102 train-only shared Zstd dictionary](../research/rounds/round-102/report.md)
- [R103 joint block/dictionary Pareto](../research/rounds/round-103/report.md)
- [R104 atomic grouped source and 10 SIGKILL cases](../research/rounds/round-104/report.md)
- [R105 source rewrite and WAL live cost](../research/rounds/round-105/report.md)

Every round above has code under experiments/round-NNN, a dedicated regression suite and a verified GitHub Actions run linked in its report. No original copyrighted source paragraph text or QA answers are committed as a local dataset.


---

# Research decision update: Round 106 pseudo-history and hybrid source allocation

**Date: November 22, 2026. Exact-head source and CI report:** [Round 106](../research/rounds/round-106/report.md).

**KEEP: Real hybrid source archive.** Round 106 constructs one genuine SQLite source+FTS database that can store some complete original paragraphs independently and other original paragraphs in paper-local groups, all using a single SHA-verified Zstd9 dictionary trained only on original QASPER TRAIN source text. Each original source belongs to exactly one representation, has exact provenance and a SHA receipt, and retains the same original FTS5 postings. Atomic edit transactions update both ordinary contentless FTS5 postings and the selected source representation. All 13,266 original source paragraphs and all 1,005 original QASPER question top-ten rankings were independently verified after each of nine layouts and 60 synthetic revisions per archive.

**NEGATIVE: Sparse pseudo-historical source reads do not dominate simple original paper features.** Original QASPER DEV question IDs were SHA-split into 494 fit-history questions and 511 held-out questions, with no human evidence label exposure. At identical ratios (50% individual, 25% groups of four, 25% whole-paper), the historical source-read-count method stored 8,273,920 B and required 2.147x the requested original bytes decompressed for heldout top10. Original-paper-length allocation stored 8,429,568 B but required only 1.639x, with lower artificial-edit WAL growth. The length policy exceeded a strict 8 MiB archive cap by 40,960 B, so it is **not** an unconditional winner at that cap. Stable paper ID hashing also beat history in heldout top10 decoded bytes at matched allocation shares. Additional 50/25 controls were added after observing first heldout outcomes, thus considered exploratory rather than pre-registered.

**DATA LIMITATION:** QASPER has NO actual timestamped read or edit history. The SHA split is a reproducible transductive pseudo-history: fit and heldout queries can share papers. The 60 revisions are synthetically generated, not observed corrections. This round is not proof that a learned hot/cold layout performs better or worse in a future deployment. Count source read amplification, FTS index bytes and WAL as distinct resources, rather than exaggerating a scalar best case.

**NEXT: Strong retrieval controls, model storage, and semantic factuality.** R107 compares independently pinned public pretrained MiniLM and BGE retrieval, conventional BM25 and fixed RRF on original QASPER expert evidence under known article scope. Charge 384-d float32 embeddings, model checkpoint bytes, source+FTS index and CPU; dense evidence improvements, if any, are not a free byproduct of compression. Then evaluate actual human-annotated generated answer attribution, as the corpus storage experiments do NOT demonstrate reduced hallucination.
