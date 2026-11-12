# CDG Round 19: Full-Corpus Retrieval, Exact Multi-Span Evidence Reconstruction, and Source-Layout Cost Curves

**Research date:** 11 November 2026  
**Continuation:** *Compression/RAG (CDG), Living Research Master Record, Rounds 0–18*  
**Status:** Full real-text corpus analysis and pinned source-annotation alignment executed through connected GitHub resources; a local Python reproduction script and synthetic self-tests were executed. **No actual disk download, compressed-source SSD benchmark, trained neural retrieval rerun, fixed LLM generator, or verified answer-quality improvement was completed.**

## Executive research verdict

Round 19 removes the principal corpus-availability bottleneck from Rounds 14–18. A public repository contains the complete **5,183-document** BEIR-formatted SciFact corpus, with authentic scientific abstracts and paper titles. It was accessed by exact Git blob SHA-1 `93e4d620e75aac00dc2be20a8361211b408a0c84` and analyzed against the public SciFact development claims. All 182 distinct source IDs referenced by the development evidence annotations are present in this corpus.

The central new findings are:

1. **Real whole-corpus lexical search:** An independently implemented positive-IDF BM25 ranker on the 5,183 scientific abstracts retrieves an annotated gold document for **159/188** evidence-bearing claims at top three and **174/188** at top ten. Using titles plus abstracts yields **158/188** at top three and **177/188** at top ten. These are retrieval controls, not new neural QA or end-to-end CDG results.
2. **All annotated rationale texts are mechanically re-locatable:** Among 338 gold evidence quotes, **329** occur contiguously after explicit punctuation/whitespace canonicalization. The other **nine** consist of two or three separated exact fragments; they were reconstructed as ordered, discontiguous spans. All **338/338** are unambiguous under this specific corpus and matching rule. **This is a reversible text-location audit, not evidence of semantic entailment, nor validation of original source byte offsets.**
3. **Fine-grained extraction really does trade completeness for text budget:** A new lexical sentence BM25 proxy over **45,132** heuristic sentence units, applied to the same published top-three documents, fully contains an annotated rationale in **133/188** queries with five selected sentences (mean 898 canonical characters); at eight sentences, **153/188** (1,436 chars); at twelve, **163/188** (2,149 chars). A low-strength neighbor boost gives **137/188** at five sentences but drops to **150/188** at eight. No universal win.
4. **Real source positions produce a physical-granularity frontier:** On the gold-oracle shortest-rationale workload, independent 128-byte frames require only **58,178 modeled source bytes** but require **949,360 bytes of archive metadata** at 16 metadata bytes/frame. At 512-byte frames, the corresponding modeled figures are **117,324 source bytes** and **268,976 metadata bytes**. These are actual UTF-8 lengths of normalized source content and hypothetical fixed frame activations, **not compressed SSD measurements**.
5. **A joint evidence/physical cost optimizer differs from text-only selection:** At 512-byte frames and an illustrative objective `prompt_bytes + 1 × frame_read_bytes`, selecting a (gold-annotated) adequate alternative using both costs improved the objective by **2.91%** over always choosing the shortest gold quote; 17/188 selected witnesses changed. At 2,048-byte frames the improvement was **5.17%** (15 changed). The gain is small and inherently oracle-informed.

**Decision:** The best continuation is not another generic evidence-repair graph. It is an explicitly measured, **source-aligned, query-adaptive physical evidence layout** with exact, reversible span coordinates and independently verified semantics. The novel-paper claim is still **not established** because workload-aware physical layouts, passage retrieval with neighbors, budgeted evidence acquisition, and citation-preserving compression have substantial existing art.

## 1. Corpus provenance and version control

| Input | Grounded path | Git blob / official identity | What it contains |
|---|---|---|---|
| BEIR-style scientific corpus | `rinaxosman/ir_system/data/scifact/corpus.jsonl` | `93e4d620e75aac00dc2be20a8361211b408a0c84` | 5,183 documents with `_id`, `title`, and flattened abstract `text` |
| SciFact original-schema dev | `traceloop/openllmetry/packages/sample-app/data/scifact/scifact_claims.jsonl` | `280ea26476673e40194bddc957490a2e0af2865c` | 300 claims; 188 with annotated support/refute; exact source/sentence sets |
| Normalized quote mirror | `aryash45/docucheck/evals/data/public/scifact_dev.jsonl` | `3e6c34bc7c4565f91bfe27de8b918b3cd8d1a084` | 338 quotes with reference source IDs, locations, and labels |
| Published MLM abstract reranking | `thunlp/KernelGAT/scikgat/prediction/abstract_rerank_dev_mlm.jsonl` | `c76169c31e915a8f12d812be12034c00ddc1ac14` | Three ranked source IDs for every dev claim |
| Published sentence predictions | `thunlp/KernelGAT/scikgat/prediction/rationale_selection_dev_scibert_mlm.jsonl` | `e9e7e2dd52bdab4ddbb87f1cbce41d53797d2a64` | Existing sentence-ID predictions, used in R17/18 |

The corpus source is a **flattened BEIR representation** rather than the original ordered sentence-array representation distributed by the SciFact authors. A source ID and quote match does **not** establish byte-for-byte identity to the official tarball. Use the official archive when possible to verify the ingestion transform. The public Hugging Face metadata declares 5,183 SciFact corpus entries and a 3,115,079-byte official archive with SHA-256 `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`, but this official archive was not downloaded in this round. The 5,183 BEIR abstracts total approximately 7.265 MB of canonicalized UTF-8 body text, excluding JSON packaging, title fields, source metadata and full search indexes.

References: https://github.com/rinaxosman/ir_system ; https://github.com/allenai/scifact ; https://huggingface.co/datasets/allenai/scifact/blob/main/dataset_infos.json ; https://github.com/thunlp/KernelGAT .

## 2. Exact nonlinear hypothesis graph

```
G0 LOSSLESS SOURCE WORLD: immutable raw bytes -> source version ID -> content ID -> seekable physical frames
                                   |                                      |
                        canonicalization + exact coordinate map           -> incremental frame cost
                                   |
G1 QUERY WORLD: BM25 / neural rank -> candidate occurrence -> context selector -> source inspection
                       |                                         ^
                       -> score-equivalent classes (R14)       | recovery
                                                                 |
G2 EVIDENCE WORLD: claim-conditioned OR-of-AND witnesses -> exact noncontiguous span sets
                            |                         |               |
                            |                         |          headings/time/units/ACL/origin
                      proof alternatives         pointer-preserved packet
                            |                         |
G3 UPDATE WORLD: content changes -> reverse dependency invalidation -> rebind source references or abstain
                            |                                      |
G4 RUNTIME WORLD: source frame layout -> decode-once -> full internal context -> selective final tokens
                            |                                            |
                       conditional workload                         grounded generation
                            |                                            |
G5 SCIENCE WORLD: exact bytes + complete evidence + citation quality + model output + cost
```

Cross-links and the non-obvious implications:

- **Retrieval class ≠ source occurrence:** Equal BM25 features license score factoring under a fixed ranker, not the same text, source time, source independence, or entailment. The Round 14 grouped-score experiment belongs to G1, not G2.
- **Evidence is a hyperedge, not necessarily a window:** The nine discontiguous SciFact rationales require multiple exact spans from one source. A 1,467-character gap between two useful spans shows why "fetch min-to-max" can over-read even if the final quoted text is short. R15–R16 Boolean witnesses map naturally to G2, but have standard database provenance as prior art.
- **Canonicalization is not free:** Different ingestion formats can alter whitespace, Unicode punctuation, sentence IDs and character offsets. Without an explicit original-to-canonical coordinate map, a citation computed on normalized text cannot safely be presented as an exact original-byte citation. This is a *representation contract*, not a semantic proof.
- **Source frame cost is a set union:** The marginal bytes for one source span depend on which frames have already been activated in the query and in any actual shared cache. This makes shortest-text passage selection potentially suboptimal even with completely known gold witnesses.
- **Frame size is workload-conditioned:** Small frames reduce read amplification but increase metadata, seek operations, decompression calls, rebuild costs and possible compression losses. The right optimum depends on query repetition, source update churn, cache, OS and SSD implementation.
- **Information-theoretic separation:** Exact source bytes form a lossless archive; the prompt is a per-query lossy view anchored by reversible source pointers. The system may inspect more context internally but deliver fewer final tokens, if an independent source-conditioned verifier permits the extraction.
- **The privacy counter-link:** Ordered source IDs, chunk offsets and provenance may itself leak content. Source-coordinate sidecars must inherit authorization and access-lifetime controls, not be indiscriminately published.

## 3. Independent full-source lexical retrieval baseline

**Procedure:** For each of 5,183 documents, tokenize lowercased Unicode letters/digits (`[\p{L}\p{N}]+` in the connected JavaScript implementation), count term frequencies, and create a postings index. Compare standard positive-IDF BM25 with `k1=1.2, b=0.75` using (A) abstract text and (B) title concatenated with abstract. Deterministic ties are sorted by source ID. Retrieve 100 document IDs per claim, then calculate whether at least one or all known gold source IDs appear among the first k. Exclude the 112 claims with empty annotation maps from these retrieval recall denominators.

| Method | Any gold @1 | Any gold @3 | Any gold @5 | Any gold @10 | Any gold @20 | Any gold @100 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 abstract only | 130 | 159 | 166 | 174 | 177 | 182 |
| BM25 title + abstract | 133 | 158 | 167 | 177 | 181 | 181 |
| Published SciBERT-MLM reranker | 152 | 174 | n/a | n/a | n/a | n/a |

**Negative:** Title augmentation did not reliably improve top-three and did not uniformly outperform abstract-only. A few tested BM25 hyperparameter variants produced similar but non-identical results; because the same public dev labels guided the exploration, do not select and announce a best configuration as a held-out result. The independent BM25 is a competent reproducible lexical control but lacks tuning against mature Anserini/Pyserini/Block-Max WAND implementations, learned rerankers and modern hybrid models.

**Unit:** "gold source present" measures document-ID recall only. It does not measure the complete supporting sentence set, semantic support/refute, citation soundness, or generated answer.

## 4. Exact original-evidence quotation alignment

Canonicalization: collapse whitespace runs, unify several typographic dashes and apostrophes/quotation marks, preserve lexical content and ordering. For each quote: attempt contiguous substring match; otherwise split the quote into sentence-like fragments and require each fragment to occur in increasing order in the same source document. Check that each matching fragment is unambiguous in that document. This is exact after the declared transform, not fuzzy retrieval.

**Results:** 338 gold rationale instances -> 329 contiguous matches + 9 noncontiguous matches = **338/338 unique aligned rationale texts**. The nine gap cases require 19 selected fragments total (eight 2-part and one 3-part), bringing the overall number of source fragments to **348**. The largest gap between selected fragments in the source is **1,467 characters**. Neither selected fragments nor canonical text offsets should be silently converted into original source byte offsets; save an ingestion-time transform map, or verify and report canonical-source citations only.

**Pointer contract candidate:** `(raw_source_hash, source_version, canonicalizer_id, [(canonical_start_byte, canonical_end_byte),...], source_scope, ACL_id, optional_original_byte_range_map)`. The span list is exact only relative to the pinned canonicalizer and source body. The full original raw bytes remain an independent archive object; a raw source hash is distinct from the canonicalized text hash.

**Oracle prompt size:** Across 188 evidence-bearing claims, the gold annotations specify 73,984 quote characters / 74,072 UTF-8 quote bytes. Fetching every distinct gold source document for each claim would expose ~341,292 canonical body bytes. Choosing exactly one shortest *gold-known* adequate rationale per claim with explicit source-range pointers yields **39,975 prompt bytes** in the UTF-8 proxy, only 11.71% of those full gold-document bodies. This is a large *oracle* lower-bound potential for prompt selection, not a valid deployable result: no learned method has demonstrated choosing these correct spans from unseen queries. Against all three retrieved documents, the full-context prompt is even larger (~4,470 canonical characters/query), but these are not necessarily all answer-bearing sources.

## 5. Context selection proxy: incomplete witnesses remain the bottleneck

From the 5,183 original text documents, approximately 45,132 sentence-like units were derived by a simple punctuation/uppercase boundary heuristic. BM25 with positive IDF, `k1=1.2, b=0.75`, scores each sentence unit; at query time score sentences only inside the existing published SciBERT top-three retrieved sources. A selected rationale is counted complete when every heuristic sentence unit overlapping all its exact contiguous/discontinuous source fragments is in the selected set. This is mechanical quote coverage, not equivalence to official SciFact sentence-array indices or a generated answer.

| Sentence-selection policy | k=3 | k=5 | k=8 | k=12 |
|---|---:|---:|---:|---:|
| Plain sentence BM25 | 114 | 133 | 153 | 163 |
| Neighbor additive boost 0.15 | 115 | 137 | 150 | 162 |
| Neighbor additive boost 0.40 | 115 | 136 | 146 | 160 |
| Document-max-score boost 0.15 | 117 | 133 | 153 | 165 |
| Document-max-score boost 0.40 | 115 | 135 | 154 | 163 |

All counts are among 188 evidence-bearing claims with at least one structurally recovered gold rationale; the maximum top-three gold source availability is **174**, so source retrieval itself imposes a ceiling. Mean selected canonical characters for plain BM25 at k=3/5/8/12 were **539 / 898 / 1,436 / 2,149**, compared with roughly **4,470** characters for the corresponding three full abstracts. At k=5 the low-weight neighbor prior gains four complete-witness claims, but at k=8 it loses three and higher smoothing is worse. **Negative:** A neighbor/coupling rule is not a universally dominant remedy for evidence fragmentation; the new 10 November 2026 paper *Evidence Fragmentation Is a Distinct Failure Mode* directly studies such span/neighbor methods and is a novelty blocker.

There is an obvious corpus-format limitation: heuristic sentence segmentation can merge or split differently from the official SciFact sentence list. The source-span audit remains valid, but the sentence-budget experiment is a **proxy**. It must not be directly compared on a common unit with the earlier published SciBERT original-index sentence selector's 138/188 without a common segmentation, budget and tokenizer.

## 6. Query-aware physical source frames on real source coordinates

**Inputs:** All 5,183 normalized SciFact abstracts (~7,265,077 UTF-8 body bytes). Source positions use normalized canonical UTF-8 byte offsets. For each of 188 queries, select the shortest *gold-annotated* alternative rationale, reconstruct its full list of source fragments, and count the **union** of independently materialized uncompressed frame byte ranges. Compute total archive frame count and assume **16 fixed metadata bytes per frame**, with no compression/seek/runtime assumptions. Source titles, inverted/neural indexes, frame compression dictionaries, cache and update metadata are excluded. It is deliberately a physical lower-bound proxy, not a production filesystem benchmark.

| Fixed source frame B | Canonical read bytes for 188 oracle rationales | Number of archive frames | Metadata bytes | Metadata as % of archive body |
|---:|---:|---:|---:|---:|
| 128 B | 58,178 | 59,335 | 949,360 | 13.07% |
| 256 B | 80,077 | 30,986 | 495,776 | 6.82% |
| 512 B | 117,324 | 16,811 | 268,976 | 3.70% |
| 1,024 B | 178,993 | 9,666 | 154,656 | 2.13% |
| 2,048 B | 251,410 | 5,684 | 90,944 | 1.25% |
| 4,096 B | 297,484 | 5,201 | 83,216 | 1.15% |

The source's smallest gold-known rationale text is not necessarily the cheapest to retrieve. Define illustrative `J(r|q)=prompt_bytes(r) + α * unique_frame_read_bytes(r)`, per query, and choose an alternative annotated rationale minimizing J. This objective is ORACLE and has no source-verifier or decompression costs. At α=1, compared with the shortest-text rationale baseline, the gain in total J is:

| B | Queries with changed chosen rationale | Improvement in J |
|---:|---:|---:|
| 128 | 10 | 0.72% |
| 256 | 19 | 1.39% |
| 512 | 17 | 2.91% |
| 1,024 | 18 | 2.93% |
| 2,048 | 15 | 5.17% |
| 4,096 | 7 | 1.52% |

**Important negative:** The cost-aware improvement is not dramatic, and the selector has forbidden gold knowledge. The results do not justify an elaborate joint optimization controller by themselves. This dataset is not versioned, so the experiment does not demonstrate source-version delta compression or cross-version reuse.

**Storage-versus-workload sensitivity:** For a toy global cost `metadata_bytes(B)+r*read_bytes_for_the_188_query_oracle_batch(B)`, the minimal sampled B switches from 4,096 bytes at r=.1, to 1,024 at r=1, to 512 at r=3, to 256 at r=10, to 128 at r=25. These r values are repeated batches, **not measured queries per second**. Production choice additionally depends on compression ratios, warm/cold caches, seek cost, decompression overhead, independent index sizes, updates and realistic request arrival patterns. There is no single optimal chunk size.

## 7. New graph connections and hypotheses

### H19-A: Alignment-preserving source materialization (high priority)

Make source transform maps explicit: raw source bytes -> canonical searchable text -> sentence/window embeddings -> exact original-byte citation ranges. Materialization then produces `(source_version, span_list, canonicalizer_version)` rather than a plain string. Source bytes remain lossless. The storage layer must never misrepresent canonicalized offsets as raw-source offsets or a broad bounding interval as selected evidence. A first systems contribution could be that reversible spans add negligible overhead while reducing citation failures in document-reformat/version-change stress. **Novelty threat:** citations with offsets, authenticated storage and provenance-carrying retrieval already exist; the combination is not yet novel.

### H19-B: Support-aware rate-distortion with retrieval-cost activation (medium-high priority)

Use a query-specific distortion measure:

\[
D_q(S)=1-\mathbf 1\{\text{a complete, admissible supporting evidence witness is present in }S\}
\]

for mechanically annotated synthetic/structured witnesses, plus a **separate** fallible semantic verifier for natural-language sources. Minimize actual archived+index+cache bytes and expected cold frame I/O + decompression + final token costs subject to a complete-evidence recall floor. When a proof requires multiple spans, partial selection has zero structural value. This explains why generic relevance-per-byte greedy may fail and why group activation matters. **Novelty threat:** set-wise retrieval, OR-of-AND database lineage, rate-distortion and materialized-view selection are established.

### H19-C: Workload-adaptive layout under source/family shift (high priority)

The derived trade-off suggests a scheduler that learns *actual source frame access distributions* and chooses per-family seekable frame sizes, with a cap/regret budget for cold or unfamiliar source families. Retain independent BM25/ANN index. This can reuse R10's negative result about unseen families and R16's source activation model. **Novelty threat:** database workload-driven physical design and optimized seekable codecs already exist, so only measured joint performance plus a new mechanism would matter.

### H19-D: Safety and privacy of provenance (independent adversarial branch)

Precise ordered offsets and source groupings may leak original text in embedding systems; 2026 work on document-level embedding inversion shows provenance is an active privacy channel. Stable exact span receipts therefore must be authorization scoped, revocable on policy changes, and excluded from cross-user caches. This is a reason not to expose every cache key, not a reason to erase the audit trail. Threat model and baselines required.

### H19-E: Explicit separation of certificates (strict correctness invariant)

A source hash certifies identity of bytes (after verifying the hash), a deterministic ranking certificate certifies ordering for a frozen scorer and eligible corpus, an exact span record certifies only location of cited text, and a separately assessed verifier can offer an uncertain entailment judgment. **None is a proof of source independence or global truth.** Never collapse these types into one `evidence_verified=True` flag.

## 8. Frontier reading and direct novelty obstacles

- **BEAR: Budgeted Evidence Allocation for Multi-Document Reasoning** (EMNLP 2026), hierarchical coarse-to-fine evidence access with complementary recovery paths: https://aclanthology.org/2026.emnlp-main.1348/ . Direct collision with budgeted evidence allocation.
- **Evidence Fragmentation Is a Distinct Failure Mode in Chunked Retrieval** (10 November 2026), within-question causal evidence fragmentation and neighbor-coupled span selection: https://doi.org/10.3390/info17111129 . Direct collision with adjacency and multi-representation rescue.
- **From Evidence to Exact Answers** (EMNLP 2026), copy-preserving evidence compression and frozen-reader calibration: https://aclanthology.org/2026.emnlp-main.849/ . Direct collision with compressed citation-preserving prompting.
- **Efficiency vs. Verifiability** (CustomNLP4U 2026), answer preservation may obscure serious citation-grounding loss: https://aclanthology.org/2026.customnlp4u-1.19/ . Must measure source-grounded citations independently.
- **Safe and Sufficient Caching** (EMNLP Industry 2026), evidence cache validation for source currency and access permissions: https://aclanthology.org/2026.emnlp-industry.75/ . Direct collision with freshness/ACL filtering.
- **The Bottleneck Is Retrieval, Not Reading** (Findings EMNLP 2026), holistic evidence-based generation and context loss on harder multi-hop tasks: https://aclanthology.org/2026.findings-emnlp.2222/ . Benchmark must not overgeneralize SciFact single-sentence dominance.
- **S2G-RAG** (ACL 2026) https://aclanthology.org/2026.acl-long.1185/ ; **SPARE-RAG** (Information 2026) https://doi.org/10.3390/info17101052 ; **SARA** (ACL 2026) https://aclanthology.org/2026.acl-long.661/ . Evidence-gap repair and compressed mixed representations are not novel alone.
- **When Metadata Remembers** (EMNLP 2026), ordered chunk provenance as privacy leakage: https://aclanthology.org/2026.emnlp-main.582/ . Safety constraint on global caching.

**Novelties not demonstrated:** a new lossless coding theorem, a general source verifier, a semantically sound natural-language compression scheme, faster cold SSD access than seekable Zstd under matched metadata/RSS, stronger QA than frozen-reader retrieval baseline, an exact or independent source-origin audit, or a new theoretical optimization class. The robust architectural hypotheses deserve testing; paper quality requires better than prior-art integration.

## 9. Updated decision and next-round preregistration

**RETAIN:** full-corpus independent lexical baseline; source canonicalization plus reversible original-byte map contract; noncontiguous exact span representation; source-specific physical frame union accounting; query-batched exact decode only for actual overlap; alternative witness selection under cost; conservative update/ranker/ACL separation; full-source fallback for uncertain evidence; independent answer and source-grounded citation evaluation.

**REJECT/DOWNGRADE:** fixed single sentence chunk as certified evidence; shortest passage as universal lowest-cost witness; frame size optimized on storage ratio alone; raw canonicalized text offsets as original byte pointers; big oracle prompt compression as a deployable result; semantic claim support derived solely from exact text matching; neighbor boost as a universally good method; old SciFact dev as a clean final test; a stitched graph of established ideas as automatically new.

**ROUND 20 P0:** Obtain a separately hosted exact official source sentence-array corpus or validate an ingestion-time raw/canonical transform using official SciFact; assemble a genuinely held-out multihop source benchmark. Implement independent seekable Zstd plus conventional BM25/hybrid and exact dedup baselines. Frozen verifier + reader + tokenization; compare source-grounded answer/citation quality at equal actual cost.

**ROUND 20 P1:** Run physical storage and I/O on a machine with the corpus bytes downloaded. Compare 128–4096B independent seekable frames, shared CDC/delta archive, and per-family layout; record **compressed source+index+metadata+cache bytes**, p50/p95 cold reads, decompression, re-layout/update costs, and final prompt tokens. Compare simple shortest-witness/source-preserving fallback to joint source-read-aware selection under imperfect witness predictions. If the simple heuristic matches, kill the complex optimizer.

**ROUND 20 P2:** Adversarial exactness: Unicode whitespace canonicalization, repeated source fragments (must abstain on ambiguous mapping), discontiguous sentence citations, old/new source versions with shifted offsets, negation/quantifier/context changes, unauthorized source ACL crossing, copied secondary sources masquerading as independent corroboration, and unseen source families. Each case must separately report source-identity, rank, span and semantic-verifier status.

**PAPER GO/NO-GO:** Require a new, precisely specified mechanism with either a genuine theorem under stated hypotheses or a demonstrated non-dominated joint storage, latency and source-grounded QA frontier over strong prior systems on held-out real workloads. This round is **NO-GO for a final superiority claim**, but **GO for building the source/span/frame integration prototype**.

## 10. Reproducibility notes

`cdg_round19_reproduce.py` is a Python 3.10+ standard-library reproduction script that retrieves Git SHA-pinned sources on a networked machine, checks Git blob hashes, runs corpus BM25, exact fragment/ambiguity alignment, and physical frame oracle accounting. `--selftest` was executed locally and passed. Full-data results quoted above were computed in separate connected GitHub JavaScript analyses on the pinned source contents; they have **not been reproduced through the Python script in the local offline container**. A raw-to-canonical UTF-8 coordinate map and real zstd/seekable measurements remain for the next round. All source links are pinned to Git identities; raw corpus bytes are not redistributed in this package.

---

# CDG Round 20: Exact Source Receipts, Witness Complementarity, and the Adaptive Acquisition Gate

**Research date:** 11 November 2026  
**Continuation:** Round 19 above  
**Execution status:** Six local synthetic correctness checks passed; one 20,000-instance seeded synthetic witness-selection experiment executed. Recent external literature and official formats inspected. **The full SciFact corpus was not downloaded locally; no held-out QA, model run, real compressed SSD benchmark, or production improvement is claimed.**

## 20.1 Executive decision

The strongest defensible direction is **receipt-preserving, witness-conditioned retrieval and physical materialization**. It has three deliberately different layers:

1. **Identity and coordinates:** Retain immutable original bytes and record the deterministic transform to canonical text, exact multi-span original-byte intervals, original content hash, and ACL/version scope. Exact reconstruction is a *mechanical property*.
2. **Evidence structure:** Model a candidate answer as complete alternative AND-witness sets (OR over candidate witnesses). Completeness is a *structural property*, but for natural language the structure and entailment labels are themselves uncertain.
3. **Access and choice:** Acquire only frames needed for the current admissible witness, accounting for shared-frame activation, seekable decoding, prompt cost, uncertainty and fallback. Lower expected cost is an *empirical claim* requiring a deployable, non-oracle selector and comparison against simple alternatives.

**What changed from Round 19:** We now have a runnable, minimal exactness prototype and a rigorous reason *not* to treat individual span relevance as evidence quality. We do **not** have a positive new RAG benchmark result. The immediate priority is a frozen, externally evaluated evidence prediction model; optimizing source frames on gold rationale sets is otherwise secondary.

## 20.2 New nonlinear graph: edge types and their failure modes

```text
                   SOURCE BYTES (hash/version/ACL)
                       |           |          \
             raw-to-canonical map  |           +--> update and revocation log
                       |           v                        |
              unique exact spans   seekable archive          v
                       |           |                 cache/receipt invalidation
                       v           v                        |
 CLAIM --> candidate documents --> evidence span hypotheses  <---- corpus/index family shift
                     |                |       |                          |
                 ranking         AND-set    source lineage            fallback
                     |                |       |                          |
                     v                v       v                          v
              score-only IDs --> complete admissible witnesses --> materialization choice
                                       |                         |
                                fallible entailment       frame union/read/decode
                                       |                         |
                                       +---------> cited answer <+
                                                      |
                                           independent attribution
                                                      |
                                           QUALITY / COST FRONTIER
```

**New counter-links:** (a) A source hash cannot certify entailment. (b) Unique canonical substring matches do not necessarily imply unique original-byte interpretation under arbitrary Unicode transformations. (c) Multiple corroborating IDs can be copies of one origin. (d) Physical read-cost benefits can be swallowed by model verification overhead. (e) Optimizing on development gold rationale coordinates invites severe oracle leakage.

### H20-A: Byte-reversible source receipts, with transformation *refusal*

Define a receipt as:

`Receipt=(raw_sha256, raw_version, canon_alg_id, canon_sha256, ordered_raw_byte_intervals, canon_byte_intervals, ACL_scope, transform_audit_id)`.

Ingest source bytes once and retain raw bytes. A controlled canonicalizer emits a mapping from canonical characters to raw UTF-8 byte intervals. If the transform is many-to-one, the map must carry the entire consumed original interval; if a transform is context-sensitive or crosses character boundaries, the naive character-local algorithm must be replaced by a formally specified alignment algorithm or marked unsupported. Refuse duplicate/unlocatable fragments rather than guessing. Distinguish **reconstructing the actual raw interval** from claiming that the normalized display text is byte-identical to the original.

Local tested canonicalizer is intentionally restricted to Unicode whitespace-run collapse and a few one-character quote/dash substitutions. It does **not** support arbitrary NFC/NFKC, PDF layout, table extraction, OCR, tokenizer offsets, or semantically equivalent paraphrases. Its output is an integration sketch, not general document normalization.

Invariant: for an accepted receipt, each raw interval belongs to the hash-pinned raw object; no coordinate is permitted to silently point to a newer version. Authorization must be rechecked at read time. A valid hash proves identity only if the bytes are retrieved and verified against that hash. Independent citation evaluation is still mandatory.

### H20-B: Complementarity destroys naive marginal-score selection

Suppose two valid supporting witnesses are `{a,b}` and `{c,d}`. With a two-piece budget, independent relevance ranking chooses the two highest-scoring pieces. When scores are i.i.d. continuous, all six 2-subsets are equally likely, but only two are complete witnesses, so structural success probability is **2/6 = 1/3**. A controller that knows the true witness identities can pick a full pair and achieves 1. That upper bound uses **oracle structure** and cannot be presented as a deployable accuracy gain.

This simple construction shows the reason to predict *sets and dependencies*, not just individual scores. More formally, for a required conjunction `W={a,b}`, utility `U(S)=1[W⊆S]` is not submodular: the marginal contribution of `b` is zero at the empty set and one after `a` has been acquired. Conversely the physical frame activation cost `C(S)=sum_{f in union of frame sets of S} c_f` is monotone submodular for nonnegative fixed frame costs. Thus the natural objective combines **complementary evidence utility** with **shared-cost economies**, and common greedy guarantees for monotone submodular maximization do not automatically apply. This is a mathematical observation under stated definitions, not a new theorem or algorithmic novelty claim.

### H20-C: Adaptive, but never oracle, next-read policy

Maintain a distribution over candidate witnesses and per-span verifier error, rather than a single Boolean evidence flag. A policy chooses to read a new source frame, expand a context, switch source, or abstain/fallback. Its predicted benefit is the **change in expected probability of obtaining a complete admissible witness**, divided by marginal actual cost (bytes + latency + prompt + verification, with explicit units and a cost conversion). Stop only under a preregistered risk and budget criterion. Do not interpret an uncalibrated model confidence as a calibrated posterior.

Core candidate objective, to be evaluated rather than asserted optimal:

`argmax_action [E(complete admissible witness after action) - E(complete before)] / incremental measured cost`.

The baseline is much simpler: strong top-k retrieval, exact-source fallback, cheap sentence selector, and full-source expansion on uncertainty. If the adaptive policy fails to improve a **held-out Pareto frontier** over this baseline, remove it.

### H20-D: End-to-end measured break-even and fallback

A candidate implementation is beneficial only if:

`source_read_savings + prompt_savings + cache_savings > receipt/index overhead + extra seeks/decompression + verifier calls + update/ACL checks + failure recovery`.

All terms must be measured in compatible latency, dollar or byte-weighted objective units, with component-wise accounting. A hard quality constraint should additionally require non-inferior complete evidence retrieval, answer correctness and citation attribution under source/domain shift. Frame layout changes should be offline, reversible, and source-version scoped. **Source security and correctness are gating conditions, not optimization weights to trade away.**

## 20.3 Completed local experiments

Reproduction artifacts: `cdg_round20_lab.py`, `cdg_round20_results.json`. No external corpus downloads or model calls used.

| Test | Observed result | Meaning and limitation |
|---|---|---|
| UTF-8 multi-byte and whitespace/dash transform | PASS, reconstructed raw `[8,26)` byte interval | Controlled transform maps back to actual original bytes; not general Unicode normalization |
| Duplicate quote | PASS, refused 2-occurrence ambiguity | Exactness requires refusal when uniqueness fails |
| Noncontiguous spans | PASS, 2 intervals with a **1,101-byte gap** | Avoids falsely promoting the whole enclosing interval to evidence |
| Duplicate later fragment | PASS, refused ambiguous ordering | A superficially valid ordered match can still be uncertain |
| Shared-frame accounting | PASS, overlapping spans billed once | Frame activation must use set union |
| Partial AND witness | PASS, marked incomplete | A single evidence fragment cannot masquerade as a full conjunction |

**Synthetic selection test:** 20,000 independent four-piece problems, each with the two valid witness pairs `{0,1}` and `{2,3}`; independent Uniform(0,1) scores, two-piece evidence budget, deterministic seed `20261111`. Independent top-two relevance yielded **6,705/20,000 = 33.525%** complete witness coverage, close to the exact 1/3 expectation. A **structure-oracle** pair selector covered **20,000/20,000 = 100%** by definition. The experiment validates the construction and the executable test code, **not** an improvement on unseen real sources.

This negative implication matters: without a reliable witness predictor, an apparent optimization gap is entirely unearned. Gold-known witness structure is the critical missing learning problem.

## 20.4 Updated prior-art collision matrix (verified links)

| External work | Collision or baseline | Consequence |
|---|---|---|
| Wu et al., *When Knowledge Is Not Free*, Findings EMNLP 2026, https://aclanthology.org/2026.findings-emnlp.413/ | Cost-aware evidence access with budget-constrained and agentic policies | Merely making retrieval adaptive or cost-aware is **not novel** |
| *AB-RAG*, 2026, https://arxiv.org/abs/2606.29090 | Training-free adaptive stop/retrieve based on confidence | Adaptive confidence-triggered acquisition is known |
| *SPARE-RAG*, 2026, https://doi.org/10.3390/info17101052 | Explicit multi-hop set repair, verification and rollback | AND-set preservation and recovery have close direct prior art |
| Meta Zstandard seekable format, https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/zstd_seekable_compression_format.md | Independently compressed frames with seek table, 8–12-byte entries | Basic seekable framing is established and must be the primary physical baseline |
| Official SciFact data specification, https://github.com/allenai/scifact/blob/master/doc/data.md | Ordered sentence arrays and sentence-ID evidence | Need official corpus transformation verification before source-byte claims |

**Scope correction:** Several previously collected 2026 paper claims and dates in Round 19 are retained as historical research notes, not independently reproduced results in this round. For a paper's final related-work section, verify every bibliographic entry, release date, and implementation before treating it as an established collision. Do not use any publication dated after 11 November 2026 to support a claim about knowledge available this day.

## 20.5 Targeted ablations to settle the research idea

A frozen evaluation should compare these variants on genuine held-out multi-hop and scientific verification tasks, with identical source corpora, retrievers, reader, tokenization and hardware:

- **B0:** conventional BM25/hybrid and complete retrieved chunks, seekable Zstd; exact references to whole source/version.
- **B1:** B0 plus top-k sentence extraction; no dependency predictor.
- **B2:** B1 plus calibrated complete-witness prediction; force full-source fallback below a held-out threshold.
- **B3:** B2 plus exact raw-byte receipts and noncontiguous span coordinates; count attribution errors independently.
- **B4:** B3 plus joint read-aware selection under predicted witnesses; compare shortest-text and top-score selectors.
- **B5:** B4 plus workload-adaptive seekable frame layout. Include relayout/update/write amplification and drift.

Ablate witness predictor error, candidate-document recall, false entailment, source duplicates, source-version mutations, cache warming, metadata storage, index bytes and ACL revocations. No result is acceptable without numerator/denominator and confidence intervals or paired bootstrap; cite every loss from the original content to answer. Use an untouched test set selected before tuning. SciFact dev can remain an engineering regression set only.

**Decision ladder:** First prove mapping and cache/version correctness, next show a learned selector beats cheap extraction under held-out witness-completeness constraints, then measure latency and physical bytes. If B2 cannot outperform B1 on held-out data, do not add B4/B5 complexity. If B4's savings are within noise or swamped by verifier cost, reject the joint controller. If B5 fails against seekable Zstd with realistic metadata and read traces, reject workload-adaptive framing.

## 20.6 Specific papers/mechanisms worth exploring next

**Graph fork 1, predicted witness hypergraphs:** Contrast exact OR-of-AND witness representations with pairwise passage graphs, chain-of-thought-based gap inference and probabilistic set coverage. Require a predictor that identifies *missing obligations*, not merely a scalar score. Benchmark both predicted structural coverage and independent entailment errors.

**Graph fork 2, transforms and cryptographic receipts:** Evaluate raw-to-canonical coordinate maps against round-trip HTML, PDF extraction and Unicode changes. A Merkle commitment or source hash may authenticate bytes but cannot authenticate an LLM's interpretation. Investigate a small typed receipt schema that explicitly prevents category mistakes between byte identity, location and semantic support.

**Graph fork 3, layout/content interaction:** Reuse exact source spans to group frames on actual access traces, but constrain p95 fallback latency and unknown source families. Test access-conditioned layout only *after* obtaining a reliable end-to-end selector. Treat data compression ratio, total index footprint, random-read latency and rebuild/write costs as separate outcomes.

**Graph fork 4, failure-aware RAG:** Use evidence gaps to predict when the model should decline or expand retrieval, and study selective risk-coverage curves, not just average QA accuracy. Distinguish document recall, witness completion, citation precision and final answer truth. A false source citation is a first-class failure even when the final answer happens to be correct.

## 20.7 Revised research claims and next-round contract

**Established by prior Round 19:** A SciFact BEIR mirror contains 5,183 source documents; a source-quote matching audit re-located 338 annotations under a specific canonicalizer; BM25 and frame-cost proxy figures were computed in connected analyses, not reproduced locally. Those statements are inherited as reported results, not re-verified this round.

**Established this round:** The restricted source-coordinate prototype passed six tests; an oracle-witness synthetic construction shows naive independent relevance can fail on required conjunctive evidence, with observed 6,705/20,000 completions. The structural mechanism has a transparent mathematical explanation and strong prior-art proximity.

**Not established:** Genuine originality, efficient natural-language witness prediction, source-byte equivalence to the official SciFact download, real compression acceleration, no-hallucination guarantees, universal adaptive stopping, or QA/citation improvements.

**Round 21 first action:** Get the official raw SciFact archive and a separately sourced multi-hop benchmark into the same local test environment, pin SHA-256 and exact source format, then run a frozen non-oracle witness-selector comparison. Only after a positive held-out result should additional physical optimization be attempted. A journal submission asserting algorithmic superiority remains **NO-GO**.

---

# CDG Round 21: Non-Oracle Dependency Signals, Calibration Shift, and Actual Frame Compression

**Research date:** 12 November 2026  
**Continuation:** Living Research Master Record, Rounds 0–20  
**Status:** Two executable local experiments completed: a controlled *synthetic* noisy-evidence-set predictor and real libzstd independent-frame compression on the user-provided Round 19–20 report. **No held-out SciFact/HotpotQA/MuSiQue run, neural entailment predictor, frozen LLM, SSD benchmark, or demonstrated end-to-end RAG improvement.**

## 21.1 Executive finding and updated research direction

Round 20 showed that an oracle which knows complete evidence sets wins on synthetic pairs. Round 21 removes oracle pairing knowledge **at inference** in a synthetic task: evidence-pair relationships must be inferred from noisy observable features. The candidate approach only becomes useful if these structural signals remain predictive on unseen source families and their confidence is calibrated. A distribution-shift control demonstrates the danger: a model assuming strong edge signals remains highly confident even when the true signal has disappeared.

The physical archive side shows a *separate*, real measured trade-off. Compressing the 45,381-byte Round 19–20 Markdown research record into individual zstd frames yields a combined compressed-frame-plus-modeled-seek-table size from 41,311 bytes at 128-byte frames to 21,639 bytes at 8,192-byte frames. Over the controlled 250-span access workload, the corresponding mean **compressed frame payload activated per span** rises from 271.7 to 3,757.2 bytes. Those are actual libzstd payload sizes and modeled index bytes, but **not measured disk I/O or production seekable archives**.

**Research decision:** Prioritize **calibrated dependency prediction under distribution shift**, followed by a matched real-corpus comparison with standard set selection. Keep exact source receipts and physical layout as a separate systems contribution until a measured cross-layer interaction emerges.

## 21.2 Nonlinear hypothesis graph, Round 21

```text
QUERY q
  | 
  +--> independent retrieval (BM25 / dense / hybrid) -> candidate occurrences
  |                                                           |
  +--> query decomposition -> information needs                |
                               |                                |
                               v                                v
             candidate dependency predictor <--- source structure / semantics
                               | 
              predicted OR-of-AND witness hypergraph
                |                |                    |
                |                +--> confidence --> calibration / shift alarm
                |                                         |
                |                                stop / fallback / expand
                v
        admissibility and ACL gate
                |
                v
      cost-aware witness activation <--- exact-source frame union cost
                |                                |
                +--> reversible raw-byte receipts |
                |                                +--> seekable frame layout
                v
      independent semantic verifier + citation assessment
                |
                v
             frozen answer reader
                |
                v
   COMPLETE WITNESS / ANSWER / CITATION / ARCHIVE BYTES / ACTUAL IO
```

**New cross-links:**

1. **Dependency quality gates compression benefit.** A physically cheap but incorrect evidence pair has no answer-quality benefit. A joint optimizer must charge expected failure and fallback costs, not merely span bytes.
2. **Calibration controls when graph inference is worth paying for.** If edge prediction is uninformative, independent retrieval should win once inference overhead is charged. Under shift, confidence alone is insufficient without distribution-robust calibration.
3. **Source receipts and evidence support are different types.** Exact byte reconstruction verifies what was read; it does not verify that the text proves a proposition or that multiple texts are independent.
4. **Physical frame size is a system knob, not a novel compression code.** Standard seekable Zstandard already implements per-frame decompression and jump tables, including configurable boundaries. Novelty requires measured added value over its mature implementation.
5. **The model can cross source scopes only after authorization.** Shared dictionaries, caches and metadata cannot cross access boundaries by default.
6. **Training labels are permitted; inference oracles are not.** Gold rationale sets can train/evaluate the predictor but may never be supplied as answers or pair identities at evaluation time.

## 21.3 Completed experiment A: synthetic noisy witness prediction

### Task and protocol

Four candidate fragments have a hidden dependency structure chosen from the three distinct perfect matchings of four items. Each structure contains **two alternative two-fragment complete witnesses**. A two-fragment budget forces a choice. Independent ranking selects two fragments using independent, uniformly random relevance scores, yielding theoretical complete-witness chance `2 / C(4,2) = 1/3`. The competing non-oracle graph policy receives *six noisy observed edge-coherence features*. For edges that belong to the hidden matching, feature means equal `mu`; other edges have mean zero. All feature standard deviations equal one. The policy computes three likelihood scores and picks the most probable matching, then selects the higher-relevance of its two predicted witness pairs. **At inference it never receives the actual matching.**

Each condition runs 60,000 independent deterministic seeded simulations. A separate decision policy assesses graph-overhead charge `0.08` units of success utility and gates the graph policy when posterior advantage over `1/3` exceeds that charge. This charge is hypothetical, **not actual latency**. Code: `cdg_round21_lab.py`; data: `cdg_round21_results.json`.

| Observed edge signal `mu` | Independent top-two complete | Non-oracle graph complete | Gated net utility* | Graph used by gate |
|---:|---:|---:|---:|---:|
| 0.00 | 33.67% | 33.56% | 0.33668 | 0.0% |
| 0.25 | 33.43% | 44.06% | 0.37119 | 59.4% |
| 0.50 | 33.44% | 54.92% | 0.47167 | 88.4% |
| 0.75 | 33.39% | 64.88% | 0.57051 | 95.5% |
| 1.00 | 33.42% | 74.52% | 0.66597 | 98.0% |
| 1.50 | 33.23% | 88.47% | 0.80518 | 99.6% |
| 2.00 | 33.34% | 95.84% | 0.87859 | 99.9% |

\*Net utility is the mean indicator of complete synthetic evidence minus a fixed hypothetical `0.08` each time graph inference is used. It is **not an answer-quality score, a compression ratio or a measured RAG efficiency gain**.

### Explicit negative: confidence under signal shift

Freeze the classifier's assumed signal strength to `mu_model=1.0`, then change only the true signal generator. When actual `mu_true=0`, graph success becomes **33.07%**, but the model's mean reported probability of correct matching remains **66.95%** and the gate invokes graph inference **96.37%** of the time; gated net utility drops to **0.2532**, materially below the independent policy's **0.3322**. Thus even this simple dependency-conditioned controller can fail when its calibration contract breaks. At actual `mu_true=0.5`, graph success is 54.92% but reported probability is 68.92%, still substantially overconfident.

**What this experiment does and does not prove:** It proves only that under the chosen Gaussian synthetic observation model, informative non-oracle edge signals can help recover structured witness pairs and miscalibration can negate utility. It does not demonstrate that natural-language evidence produces such signals, that the features can be learned inexpensively, or that a full multi-hop system improves. The pair-only toy family is too simple to justify a novel theoretical claim.

## 21.4 Completed experiment B: real libzstd frame-size pilot

Source bytes: current Round 19–20 report Markdown, **45,381 UTF-8 bytes**. Frame payloads were actually compressed and fully decompressed through `libzstd` level 3, individually; exact full-source round-trip was asserted. A reproducible 250-span synthetic workload samples 50–349-byte source spans. Each access activates the union of all overlapping independent frames. Table charges eight modeled seek-table bytes per frame plus a fixed 17-byte table overhead, matching a minimal no-checksum table layout approximately, but **the experiment does not serialize or validate the official seekable container**.

| Uncompressed frame max | Frames | zstd payload + modeled table bytes | Fraction of original source | Mean compressed bytes activated per sampled span |
|---:|---:|---:|---:|---:|
| 128 | 355 | 41,311 | 0.9103 | 271.7 |
| 256 | 178 | 34,556 | 0.7614 | 329.4 |
| 512 | 89 | 30,666 | 0.6757 | 474.6 |
| 1,024 | 45 | 27,479 | 0.6055 | 733.1 |
| 2,048 | 23 | 24,991 | 0.5507 | 1,206.4 |
| 4,096 | 12 | 23,207 | 0.5114 | 2,174.3 |
| 8,192 | 6 | 21,639 | 0.4768 | 3,757.2 |

**Interpretation:** The basic storage/read trade-off is real in this local compression trial. However, it is already an expected property of seekable codecs, and a single report plus random spans is not representative of scientific retrieval traffic. Actual SSD bytes read, page cache amplification, codec CPU, index footprint, tail latency, multi-source layouts and update costs remain unmeasured. Code: `cdg_round21_storage.py`; outputs: `cdg_round21_storage_results.json`.

## 21.5 Formal design hypothesis: cost-adjusted, calibrated witness acquisition

For query `q`, current materialized evidence `S`, and prospective acquisition action `a`, model the **expected** value as

\[
\Delta U(a\mid q,S)=\widehat{P}(\text{adequate witness after }a\mid q,S)-\widehat{P}(\text{adequate witness now}\mid q,S)-\lambda \widehat{C}_{\text{source}}(a\mid S)-\gamma\widehat{C}_{\text{verify}}(a)-\eta\widehat{C}_{\text{tokens}}(a).
\]

The source term counts the actual **marginal set-union** of newly activated frame payloads, not the sum of passage byte lengths; corpus and cache state must be declared. A candidate is admitted only after checking permission, source version, and pointer validity. The decision policy takes the best permitted action if its lower-confidence value bound is positive. Otherwise it falls back to broader source inspection or abstains. Full-source fallback is charged in the same measured cost accounting.

**Critical mathematical caveat:** With unknown evidence sufficiency and arbitrary OR-of-AND dependencies, the completion-value function need not be submodular. Therefore classic greedy submodular guarantees cannot be assumed. A two-span witness has zero partial utility from selecting its first span and positive marginal completion utility for its second. A valid guarantee would require additional strong assumptions such as calibrated probability bounds, conditional independence, monotone coverage surrogate, bounded hyperedge size or benchmark-defined certificates. Those assumptions themselves need falsification.

### Reliability-oriented alternative

Prefer a *risk-constrained* formulation rather than trading all errors against cost:

\[
\min_{\pi}\;\mathbb{E}[C_{\text{archive}}+C_{\text{I/O}}+C_{\text{decode}}+C_{\text{tokens}}]\quad
\text{s.t.}\quad P(\text{complete, authorized source support}\mid\text{answered})\ge 1-\delta.
\]

Without held-out calibration, that constraint is an aspiration and not a certified guarantee. Monitor selective-coverage curves, calibration error per source family and worst-group behavior instead of presenting average confidence as safety.

## 21.6 Prior-art collision matrix updated on 12 November 2026

| Prior work | What it already covers | Consequence for CDG |
|---|---|---|
| **SetR**, ACL 2025, https://aclanthology.org/2025.acl-long.861/ | Explicit set-level evidence selection and query information requirements | A set selector alone is not novel. Benchmark against its published algorithm and code. |
| **SPARE-RAG**, Information 21 Oct 2026, https://doi.org/10.3390/info17101052 | Evidence repair, calibrated sufficiency checks, rollback and pruning, multi-hop benchmarks | Verification-before-pruning and missing-evidence repair are not novel alone. |
| **EAGR**, arXiv 1 Nov 2026, https://arxiv.org/abs/2611.01910 | Evidence-conditioned graph exploration with compact metadata and no explicit GraphDB | Adaptive implicit evidence graphs alone are not novel. |
| **PAR²-RAG**, arXiv Mar 2026, https://arxiv.org/abs/2603.29085 | Breadth-first high-recall anchoring plus evidence-conditioned refinement | Adaptive active retrieval and coverage-before-commitment already exist. |
| **Zstandard Seekable Format**, https://github.com/facebook/zstd/tree/dev/contrib/seekable_format | Independent compressed frames with a jump table and random-range reads | Standard seekable Zstd must be a matched physical baseline. |
| **Cited but Not Verified**, May 2026, https://arxiv.org/abs/2605.06635 | Separates citation accessibility, relevance and factual verification | A source pointer is not an entailment certificate. |

**Tentative distinctive scope, not proven novelty:** a calibrated witness-dependency policy whose decisions use **measured marginal physical source-frame cost** while maintaining reversible raw-byte source receipts under version/ACL changes. If SetR + ordinary Zstandard + simple stopping matches it on held-out real data, downgrade this as an engineering integration instead of claiming a new method.

## 21.7 Registered Round 22 experiment and kill criteria

1. **Dataset:** retrieve and SHA-pin official SciFact original sentence arrays plus a held-out multihop benchmark (MuSiQue or HotpotQA); do not reuse SciFact dev for a claimed final test. Record source-family and question separation.
2. **Candidate retrieval:** BM25, dense/hybrid, SetR or a faithful reimplementation, adjacent-span extraction, a no-graph setwise policy, full-context retrieval, and the proposed graph policy. Match candidate pools to avoid a hidden retrieval advantage.
3. **Learning:** train a pair/group coverage predictor on train only, validate confidence on dev, evaluate once on test. Include adversarial empty signal, corrupted relation labels, unseen entities/topics, and source-version shifts. Freeze models and hyperparameters.
4. **Physical baseline:** official seekable Zstd, fixed frames and optional content-defined segmentation; measure archive+index+metadata bytes, Linux cache state, actual reads, p50/p95 latency, decompression wall time, query overhead and updates. Use a real corpus and actual query-conditioned source spans.
5. **Grounding:** complete-gold-witness recall, evidence precision, separate answer EM/F1, citation factual support, copy/offset validity, unauthorized-source failures, and abstention coverage. Keep quote location separate from entailment judgment.
6. **Kill graph controller** if its quality-cost frontier is dominated by independent ranking plus simple set selection, or calibration under source shift cannot be improved reliably.
7. **Kill physical co-design claim** if simple per-document seekable Zstd with a strong retrieval policy matches compressed storage, actual I/O and answer/citation results.
8. **Paper gate:** only advance a new superior-mechanism claim if a held-out, source-grounded quality/cost Pareto improvement appears with matched strong baselines, or an actual new theorem survives independently stated assumptions.

## 21.8 Reproducibility audit

- `cdg_round21_lab.py`: seeded pure synthetic non-oracle observation model with 60,000 trials per condition and distribution-shift controls.
- `cdg_round21_results.json`: generated exact numerical results, including full input signal strengths and gates.
- `cdg_round21_storage.py`: exact local `libzstd` round-trip independent-frame compression on the attached research record.
- `cdg_round21_storage_results.json`: byte sizes and deterministic workload activation totals.
- No corpus download was possible through the local Python runtime during this round; network DNS resolution failed. Public literature links were inspected separately. **Do not conflate these two experimental populations with SciFact or real end-to-end RAG.**
# Round 22 Research Appendix: When Should CDG Refuse to Build a Dependency Graph?

**Date:** 12 November 2026  
**Continuation of:** CDG Living Research Master Record, Rounds 0–21  
**Status:** Local real-text retrieval stress test completed; independent SciFact/MuSiQue real-data end-to-end evaluation NOT completed. No claim of novel state-of-the-art result.

## 22.0 Executive decision

**Result:** On 250 mechanically constructed two-paragraph evidence tasks from 63 paragraphs in the existing research record, BM25 retrieved both required paragraphs in 240/250 queries at k=2 and 250/250 at k=3. A facet-aware coverage selector recovered 244/250 at k=2, while MMR recovered 242/250. The four incremental facet wins are an extremely narrow benefit under an artificial query distribution; at k=3, all three methods tie. This is a **negative result for unconditional graph complexity**, not a validation of CDG on natural multihop questions.

**Primary conceptual advance:** Derive *identifiability-gated acquisition*. A dependency policy may act on its dependency posterior only when the available signal distinguishes competing witness hypotheses; otherwise it should purchase a discriminating observation, use a simple retriever, or abstain. This is a proposed design principle and lower-bound insight, **not a unique new theorem**, and it overlaps Bayesian experimental design, active learning, sequential decision theory, and selective prediction.

## 22.1 Source and reproducible protocol

Input: `CDG_Living_Research_Record_Rounds_19_21_2026-11-12.md`, SHA-256 `eece022c466001babc7dd3460c62b33c0885471d6f2ab1a260c1a4c58cc61785`. Extract 63 paragraphs of length 160–1,600 characters meeting the script's deterministic prose filters. Build positive-IDF document BM25 (`k1=1.2`, `b=.75`) over lowercased three-letter-plus alphabetic terms. Seed `22026`. Create 250 two-target queries by randomly sampling three moderately rare terms from each of two target paragraphs in different locally tracked sections. Query facets retain the three-term partitions. Labels are used for evaluation only, not provided to the ranking policy.

This is **not** a real user question distribution: queries are intentionally assembled from the target answer texts, and section tracking is heuristic. The 63 paragraphs come from our own research documentation, not a separately obtained third-party evidence benchmark. Neither a QA model nor semantic citation verifier runs. Results should not be compared to SciFact performance or presented as an independent external validation.

Selection policies:

- **BM25:** descend by total query score, deterministic tie-break.
- **Facet-aware:** greedily maximize total BM25 score plus an uncalibrated additive gain from coverage of the two supplied query facets. This is not a learned dependency model and is advantaged by the artificial facet annotation supplied at query generation.
- **MMR proxy:** greedy BM25 minus a fixed lexical-Jaccard redundancy penalty; not an optimized state-of-the-art MMR benchmark.

| Budget | BM25 complete | Facet-aware complete | MMR complete |
|---|---:|---:|---:|
| 2 passages | 240/250 (96.0%) | 244/250 (97.6%) | 242/250 (96.8%) |
| 3 passages | 250/250 | 250/250 | 250/250 |
| 5 passages | 250/250 | 250/250 | 250/250 |
| 8 passages | 250/250 | 250/250 | 250/250 |

At k=2, facet-aware versus BM25 paired outcomes: 240 both succeed; 4 facet-only successes; 0 BM25-only successes; 6 both fail. Because only four pairs disagree, any claim of robust superiority is unwarranted. Each trial is not an independent real question: source paragraphs and term distributions recur. No inferential statistical conclusion or confidence interval is reported.

**Kill/retain:** Do NOT build a general graph selector for simple explicit lexical evidence: k=3 erases the margin. Retain facet coverage only as a candidate *budget-2* heuristic to test on independently authored questions, with equivalent facet extraction costs charged.

## 22.2 Formal identifiability lower bound

Consider a hidden adequate witness `W` drawn uniformly from `m` mutually exclusive candidate evidence groups. The retrieval controller observes signal `X`. If `P(X | W=w)` is identical for every `w`, then Bayes' rule gives `P(W=w | X)=1/m`. Any single-group selection policy based only on `X`, including an arbitrarily complicated graph controller, has expected success exactly `1/m` (assuming all groups have equal eligibility and one group can be acquired). Randomization and unlimited compute do not help. If the controller can acquire `k` distinct groups at equal cost, success is at most `min(k/m, 1)` under this simplified setup.

This is an elementary symmetry/no-information result, not a novel coding theorem. It explains the Round 21 zero-signal ~1/3 baseline and gives a **gate:** controller sophistication can have value only if features carry predictive information about actual witness membership or there is a more useful acquisition action available.

For nonuniform priors with indistinguishable observations, the best one-group success is `max_w P(W=w)` rather than `1/m`. With unequal costs, optimal policy depends on the precise utility and budget. Real witnesses can overlap and are often OR-of-AND hyperedges; the simplified lower bound must not be generalized without qualification.

## 22.3 A coupling gap: why evidence value is non-submodular

Let complete-witness utility be `f(S)=1` if selected set `S` contains both evidence pieces `a,b` and zero otherwise. Then `f({a})-f(∅)=0` but `f({a,b})-f({b})=1`. This violates diminishing returns and demonstrates complementarity. Marginal-gain greedy algorithms for submodular coverage cannot claim their usual approximation guarantees for this hard-completion objective.

More generally let `\mathcal W_q` contain sufficient evidence hyperedges and set `f_q(S)=1{exists W in \mathcal W_q: W ⊆ S}`. This function is monotone for fixed admissibility, but not generally submodular. Additional constraints (source diversity, temporal consistency, ACL, independent provenance) can invalidate naïve monotonicity if materialization changes the eligible universe.

**New design fork:** (A) learn a soft approximately submodular coverage surrogate to rank actions, then use a strict evidence verifier before answering; (B) solve a small candidate witness-hypergraph integer program when groups are few; (C) avoid hard witness optimization and use simple retrieval plus targeted failure recovery. No mechanism should be selected without a same-pool cost/quality comparison.

## 22.4 Nonlinear cross-branch graph

```
                         source identity / versions / ACLs
                                    |
            +-----------------------+-----------------------+
            |                                               |
      raw-byte archive                                canonical span maps
            |                                               |
    seekable Zstd / CDC                               citation receipts
            |                                               |
       activated frames <------- hyperedge witness ---- verifier/abstention
            |                          |                    ^
     cache locality                identifiability          |
            |                          |                    |
      marginal I/O cost           query ambiguity ------ active disambiguation
            |                          |                    |
            +----------- constrained decision policy -------+
                                        |
                               cold & shifted families
                                        |
                             selective-risk calibration
```

**Cross-link 1: Retrieval and information theory.** The controller's *decision-relevant information* is how much observable query/source evidence narrows the conditional distribution over adequate witnesses, not overall embedding similarity. Use held-out log-loss, conditional entropy proxies, calibration and discrimination tests to establish that graph predictions have information not already present in BM25 scores.

**Cross-link 2: Physical cost and active sensing.** If two potential actions reveal the same answer-relevant uncertainty but one shares already activated frames, its *marginal* I/O cost can be much smaller. An acquisition policy should optimize `expected decision improvement / incremental decompression + source + token cost`, conditional on ACL and version validation, rather than independent per-passage prices.

**Cross-link 3: Compression representations and exactness.** Source pointers may be represented compactly through delta-coded canonical byte offsets, but a compressed receipt cannot substitute for source identity, raw-byte revalidation, or semantic entailment. Raw source bytes and canonical byte maps belong to separate correctness layers.

**Cross-link 4: Shift and confidence.** A learned posterior is not a certified risk bound after document-family/source shift. If the shift detector is uncertain or the action-value estimates are not discriminative, default to simple retrieval/full-source fallback and charge its cost. Credible selective risk needs independent evaluation on shifted groups.

**Cross-link 5: Graph optimization and systems implementation.** A hypergraph controller is worthwhile only if end-to-end saved costs exceed graph inference, metadata maintenance, index footprint, recalibration and source-version invalidation. Prior rounds' oracle savings alone do not cover these overheads.

## 22.5 Failure probes on attached source bytes

The lab script pins the byte SHA-256 of the actual Round 21 Markdown record, creates five contiguous UTF-8 span receipts on its bytes, and checks round-trip hash correctness. A one-byte prefix insertion changes the whole-source hash and invalidates previously issued raw-byte coordinates. All three tests pass:

- `utf8_byte_roundtrip = true` for five selected spans.
- `old_version_rejected = true` for a modified source.
- `stale_offset_not_equivalent = true` for the shifted source.

These are **minimal sanity checks**, not a complete raw-to-canonical mapping implementation and not security proof. In particular the script's inputs are plain Markdown and do not include NFC/NFD normalization, repeated fragments, compressed archive frames or multi-user ACLs.

## 22.6 Important new novelty collisions (externally verified)

- **OptiSet**, Findings of EMNLP 2026, https://aclanthology.org/2026.findings-emnlp.339/ : set selection plus set-level ranking, query expansion, preference learning from set-conditional generator utility. **Blocks** claim that learning complementarity or set utility is novel by itself.
- **When Knowledge Is Not Free**, Findings of EMNLP 2026, https://aclanthology.org/2026.findings-emnlp.413/ : budgeted, cost-tiered evidence access with adaptive controller. **Blocks** general novelty for cost-aware evidence routing; physical frame union is a *different cost definition*, but that difference requires measured value.
- **Safe Adaptive Context and TACER**, GroundLM 2026, https://aclanthology.org/2026.groundlm-1.33/ : context expansion/compact routing and token efficiency with strong retrievers. **Blocks** generic dynamic context budgeting.
- **When Is Additional Retrieval Worthwhile?**, arXiv posted 27 October 2026, https://arxiv.org/abs/2610.37358 : documents an efficiency/grounded-QA gap, with no statistically established advantage on held-out evidence and provisional answer evaluation. **Reinforces** that retrieval improvements are not answer improvements.
- **SciFact official**, https://github.com/allenai/scifact : public original sentence-array dataset; public dev annotation but test labels withheld via official submission framework. Local official download was not possible because outbound DNS/network resolution failed.

**Adjusted novelty position:** Source-aligned compressed evidence hypergraph acquisition is a viable systems hypothesis, but its components have close prior art. The paper must demonstrate a *new mechanism* and a non-dominated actual compressed-storage / source access / grounded answer curve, or a properly scoped original theorem. No such result in Round 22.

## 22.7 Round 23 preregistration: benchmark that can actually kill CDG

1. Obtain original SciFact or other independently produced corpora with verified dataset SHA/checksums, plus MuSiQue/HotpotQA-style multihop questions. Use public labels on train/dev only. Do not treat public SciFact test as labeled; obtain evaluator access or another labeled held-out split.
2. Generate candidate pools **once** with standard retrieval, then run matched top-k BM25, MMR, SetR/OptiSet-style set selection, facet-aware coverage, simple verifier-based repair, and a proposed witness-hypergraph selector. Charge any query decomposition and neural verification compute.
3. Hold out source families/entities and corrupted relation signals; report discrimination/calibration of learned dependencies separately from complete witness recall.
4. Evaluate native ground-truth source and sentence sets, query answer EM/F1, citation factual support, exact pointer validity, abstention, and access-control violations. Metrics must not collapse one into another.
5. Materialize full **source**, index and frame metadata on a benchmark host and use actual seekable Zstd and cold/warm trace protocols. Include compressed archive bytes, p50/p95, decode CPU, read bytes, updates, cache invalidation, and metadata. Compare with plain seekable Zstd and fixed frame sizes.
6. **Stop/kill:** if BM25+simple verifier or SetR+seekable Zstd dominates the graph controller on the held-out quality-cost frontier, archive the graph idea. If uncertainty calibration fails under shift, restrict to safe fallback rather than claim a calibrated acquisition policy.

## 22.8 Outputs and limitations

- `cdg_round22_lab.py`: deterministic retrieval and byte receipt sanity test.
- `cdg_round22_results.json`: exact aggregate metrics, paired k=2 contingency counts and local SHA-256.
- The results are not from an independently held-out real-world QA benchmark, nor a neural predictor, nor a compressed SSD layout test. The experiment is deliberately designed to falsify overbroad claims from earlier rounds.
