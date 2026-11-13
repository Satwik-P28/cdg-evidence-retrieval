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


---

# Round 23: Bridge-Resolution Failure Injection, Version-Scope Checks, and the Cost of Knowing What to Trust

**Date:** 12 November 2026  
**Continuation:** CDG living record, Rounds 0–22  
**Status:** Controlled synthetic benchmark and deterministic regression tests executed. No independently authored multihop benchmark, trained model, semantic verification, or measured SSD system result.

## Question and decision

Recent rounds repeatedly reproduced a gap between retrieving individually relevant text and assembling an adequate evidence set. A difficult question is whether a more involved graph controller is needed at all. In Round 22, a BM25 control already retrieved 96% of constructed two-paragraph witnesses at a budget of two. Round 23 deliberately tests a different failure mode: *what if the only bridge from a question's subject to the answer is not present in the question, and two apparently valid bridges disagree about version or source scope?*

The immediate verdict is not that we have a new retrieval algorithm. The experiment indicates that inexpensive exact-ID/metadata safeguards can eliminate a class of injected false answers that naïve bridge lookup does not prevent. These safeguards are necessary only when the relevant metadata is complete, trustworthy, and correctly interpreted. Their latency, metadata-index size and correctness against adversarially forged metadata are not measured.

## Experimental design, preregisterable claims, and limitations

The bundled `experiments/round-23/cdg_round23_lab.py` constructs **600 deterministic two-hop examples**, 120 in each of five categories. Each example contains a subject-to-route anchor, a route-to-outcome document when appropriate, and 18 unrelated anchor/route pairs. The question names the subject but deliberately does not reveal its route ID. That is an *engineered lexical disconnection*, not a measurement of naturally authored compositional questions.

The three methods are:

1. **Static BM25 top-2:** retrieves two documents using a minimal independently implemented BM25; may answer only when both the exact subject anchor and its matching route document appear in those two positions.
2. **Naïve bridge lookup:** BM25 retrieves the anchor, extracts its exact route identifier, then selects the first route document with that identifier. It does not check versions, scopes or contradictory anchors.
3. **Guarded lookup:** uses the same BM25 first hop, but consults indexed identity and version metadata, rejects conflicting current anchors, picks the newest version per stable source ID, and requires that the route document match the anchor's source scope. Ambiguity or missing evidence causes abstention.

**Fairness warning:** The guarded policy is allowed to inspect all source metadata without an index/CPU charge; only source text materializations are counted. This is an optimistic proxy, not an equal-cost production comparison. All routes and outcomes are generated using the same easily parsed templates. There is no independent semantic verification and there is no trained relation predictor.

## Results

The following are exact counts from `results.json`, not statistical estimates from real workloads.

| Injected case | Static BM25 @2 correct / 120 | Naïve bridge correct / 120 | Guarded bridge correct / 120 | Why |
|---|---:|---:|---:|---|
| Unambiguous clean bridge | 0 | 120 | 120 | The answer-bearing route has no query subject tokens. |
| Two conflicting current anchors | 120 | 0 | 120 | Both static and guarded abstain; naïve picks an arbitrary route and makes a false claim. |
| Outdated version precedes current version | 0 | 0 | 120 | Guarded lookup uses source identity plus version metadata. |
| Foreign-scope route precedes authorized route | 0 | 0 | 120 | Guarded lookup requires source-scope agreement. |
| Missing second-hop document | 120 | 120 | 120 | All methods abstain; this case does not discriminate methods. |

Here, **correct** includes justified abstentions for the conflicting and missing-evidence cases. Thus these counts are *decision correctness under a fixture-specific policy*, not answer exact-match rates. For the three answerable case types (360 examples), the guarded policy returned the expected synthetic result in all 360. Static retrieval provided no answer under its forced two-document budget. On 240 unanswerable cases, guarded lookup abstained on all 240; this conclusion is specific to the generated metadata and string patterns.

The naïve policy produced **360 invalid answers** across the conflict, version and scope cases. This result is by construction: the contaminating route or older version was inserted ahead of the legitimate one. It is not an empirical error rate for production iterative retrieval.

Mean materialized uncompressed source text bytes per query for the **clean** condition: static 196 B; naïve and guarded 141 B. Under a source-read-only accounting model, the guarded policy is not more expensive than naïve lookup on the clean or version/scope cases, while reading two conflicting anchors (196 B) before abstaining. These figures omit index metadata and query computation, which are exactly where a more elaborate policy may lose its advantage.

**Bug discovered during execution:** An initial implementation checked subject identifiers with substring inclusion. `subject23026` matched `subject2302600`, making every guarded clean case appear ambiguous. Replacing substring matching with exact parsed identifier equality fixed this. The test suite now includes a regression for prefix collisions. This is a genuine implementation lesson: source identity and semantic similarity must not be conflated.

## Graph-of-thoughts branches and cross-links

### Branch A: The bridge can be lexically invisible but structurally accessible

Let a question mention subject `u`. Document `a` states `u -> v`; document `b` states `v -> y`. If `v` and `y` appear nowhere in the question, a lexical one-shot ranker has no query-derived basis to distinguish `b` from unrelated similarly formatted route documents. A second-stage exact-key lookup can retrieve it after inspecting `a`. This is established graph traversal, not new retrieval theory. The relevance of the construction is the *control*: full text need not be retrieved solely because the answer-bearing document has low query similarity.

### Branch B: Identity and authorization are not entailment

An exact route ID does not guarantee that the selected route is the right version, belongs to the same scope, is an independent corroboration, or actually supports a statement. The guard in this fixture handles version and scope **only because trusted metadata is given**. An adversary capable of forging trusted metadata defeats this model. A content hash proves byte identity relative to a known digest; it does not prove authority, authorship, or truth.

### Branch C: Acquiring information versus selecting text

Define a policy state with observed sources `O`, admissible witness hypotheses `W`, source-version constraints `V` and activated physical frames `F`. An acquisition action `a` has incremental cost

\[
C(a\mid F) = C_{\mathrm{CPU}}(a)+C_{\mathrm{metadata}}(a)+C_{\mathrm{reads}}(a\setminus F)+C_{\mathrm{decode}}(a)+C_{\mathrm{tokens}}(a).
\]

A *candidate* decision rule is to acquire evidence only if the expected reduction in decision risk exceeds a cost-weighted penalty. This is standard value-of-information reasoning. It requires **estimated** conditional probabilities, actual cost measurements and shift calibration, none of which is supplied by this round. The union operation over already activated frames is the part that connects to R19's physical layout accounting.

### Branch D: Uncertainty cannot be erased by optimization

When two distinct current anchors have equal authority and conflicting routes, selecting the shorter route, lower frame-read cost or higher BM25 score cannot turn either into verified evidence. The correct policy in the fixture is abstention. If real applications demand an answer, the system needs a distinct authority-resolution process, not merely additional extraction.

### Branch E: Connection to established physical database design

The guard resembles a version-aware join across `(subject, source_id, version, scope, route_id)`, not an exotic neural graph. The likely engineering baseline is a small keyed metadata index plus ordinary seekable source frames. Compare this *first* against a neural witness hypergraph selector. A more complex policy is justified only if it improves held-out QA/citation quality at a matched complete cost.

## Prior-art corrections and new novelty obstacle

- **IndexRAG: Index-Time Reasoning for Multi-Hop Retrieval-Augmented Generation**, Findings of IJCNLP-AACL 2026, https://aclanthology.org/2026.findings-aacl.175/ . Bridge facts materialized at indexing time with single-pass inference are already explicitly studied. Their reported HotpotQA/2WikiMultiHopQA/MuSiQue improvements cannot be compared to this synthetic lab's result.
- **Beyond Static Retrieval: Opportunities and Pitfalls of Iterative Retrieval in GraphRAG**, EMNLP 2026, https://aclanthology.org/2026.emnlp-main.1897/ . Identifies the importance of promoting bridge evidence in iterative retrieval.
- **BridgeRAG: Training-Free Bridge-Conditioned Retrieval**, arXiv April 2026, https://arxiv.org/abs/2604.03384 . Conditions second-hop retrieval on bridge information and reports controlled and benchmark evidence. Further limits novelty of our basic bridge mechanism.
- **HotpotQA**, EMNLP 2018, https://aclanthology.org/D18-1259/ . Independently authored multihop supporting-fact dataset and a necessary next baseline; **not downloaded or evaluated in this round**.

These are *prior-art candidates and baselines*, not reproduced comparisons. Round 23's metadata guards are standard distributed-systems and database concepts. The integration may be worthwhile, but a new-paper claim is not established.

## Reproduction

```bash
python experiments/round-23/cdg_round23_lab.py --output experiments/round-23/results.json
python -m unittest discover -s experiments/round-23 -p 'test_*.py' -v
```

Executed locally using Python 3 and standard library only. Six regression tests passed. Source SHA-256/UTF-8 offset sanity checks passed on a toy Unicode string, but no original-to-canonical map, authenticated citation chain, or live ACL system was implemented. Fixed random seed 23026; no dataset download.

## Next test: a dataset that can falsify the mechanism

**Round 24 P0:** Obtain and checksum the official HotpotQA distractor development split or another authentic multihop benchmark. Freeze question/doc partitions. Measure exact supporting document/sentence recall using common candidate pools. Establish BM25, hybrid, IRCoT-style iterative retrieval, IndexRAG-style bridge materialization, and simple metadata-join baselines. Compare to a frozen answerer on answer and citation correctness.

**Round 24 P1:** Add source-version snapshots, ACL scope, and conflicting source fixtures to an otherwise authentic corpus, with explicit source-authority labels. Test attacks where metadata is missing, corrupted, or fraudulent. Report precision/abstention and the rate of **unsupported answers**, not only selection success.

**Round 24 P2:** Measure real archive/index/metadata bytes, compressed frame union, source reads, decoding CPU and cold/warm p50/p95 on a benchmark host. A controller that merely moves work into metadata scans is not a storage or latency improvement.

**Kill criteria:** If a simple two-hop retrieval baseline plus version/scope join performs as well as the proposed graph controller on matched held-out quality, cost, shift and citation metrics, drop the graph controller. If metadata cannot be authenticated, avoid claiming a safe grounding guarantee. If the only success is on exact-template synthetic data, do not submit a paper arguing a generally better RAG system.


---

# Round 24: Missing Bridges in Authentic Questions, and the Limits of Title-Only Evidence Search

**Date:** 12 November 2026  
**Stage:** Real question text, *restricted label-derived title index*. Not standard HotpotQA, not QA accuracy, and not held-out full-context retrieval.  
**Decision:** Reject diversity-only retrieval as the bridge remedy. Build an actual source-reading bridge acquisition baseline before proposing a graph controller.

## 1. Why I ran this test

Round 22's constructed questions let BM25 recover both relevant paragraphs almost all the time. Round 23 made the opposite case, but used synthetic route identifiers. Neither settled what happens when real questions mention one entity but omit the intermediate entity needed to find the second document.

I chose a deliberately narrow diagnostic with authentic HotpotQA-derived questions and their supporting article titles. The point was to test whether the missing-bridge phenomenon exists before paying for a full model-based stack. I resisted adding a graph predictor because we still do not have a defensible source of inference-time edges.

## 2. Data, provenance, and leakage

Upstream: `surpradhan/rag-benchmark`, revision `c9dc6c350accb3c07629f0465e57d38756a006b0`, `data/processed/dev_questions.json` and `test_questions.json`.

| File | Git blob SHA-1 | Questions |
| --- | --- | ---: |
| `dev_questions.json` | `553bca588cda339747dbdbffd876be4d4c9ef72d` | 500 |
| `test_questions.json` | `b76819e1aaa08f7146f781184cd4f935eef5b79c` | 500 |

Both files contain `question_id`, natural-language `question`, `answer`, `supporting_titles`, `type` and `level`; they do **not** contain source paragraphs, original sentence IDs, authorized source versions, source contents, or physical frame coordinates. There are 399 bridge and 101 comparison questions in the first subset, and 404 bridge and 96 comparison questions in the second. The question IDs do not overlap.

For a consistent candidate universe, I created the **union of supporting titles from both files**, yielding 1,975 distinct titles. **This construction leaks evaluation labels into the index.** No gold titles are passed to the ranker at query time, but the corpus omits ordinary distractor documents and guarantees the target titles are included. It is an engineered closed-world upper-opportunity test, not open-domain retrieval. The upstream file labels `dev` and `test` are publication-defined and should not be mistaken for an untouched official HotpotQA test server split.

The official HotpotQA distractor dev distribution includes per-question paragraphs and sentence-level supporting-fact annotations, which are required for a genuine follow-up benchmark; see https://github.com/hotpotqa/hotpot and https://huggingface.co/datasets/hotpotqa/hotpot_qa . The benchmark dataset is CC BY-SA 4.0. The question-only derivative was inspected through the connected GitHub resource; its bytes were not redistributed in this package.

## 3. Methods

A Unicode alphanumeric tokenizer splits lowercase question/title text. Each distinct title is a pseudo-document. BM25 uses `k1=1.2`, `b=0.75`, positive IDF `ln(1+(N-df+0.5)/(df+0.5))`, title length normalization and deterministic title sorting for ties. The query is only the question text.

The comparison is **MMR** over the first 50 (or fewer) ranked title candidates, greedily choosing 10 titles using `0.75 * normalized_BM25 - 0.25 * max_Jaccard_overlap_with_selected_titles`. Its purpose is to test whether diversity can rescue omitted support titles. It is not a neural, graph, or bridge-conditioned retrieval system.

For k in 1, 2, 3, 5 and 10, record:

* `any`: at least one annotated support title appears in the selected top k.
* `complete`: every distinct annotated support title appears in top k. In these files each question has two titles, so `complete@1 = 0` by construction.

Neither is a supporting-*sentence* metric, semantic entailment metric, answer EM, citation correctness, or token/SSD latency measurement. Gold `answer` labels are unused.

**Execution audit:** All 1,000 question rows and source blob identities were inspected using the GitHub connector; the scoring and counts below were computed in an independent JavaScript evaluation over the fetched text, not by executing the Python reproducer on the full dataset in this offline container. The Python reproduction code and four local standard-library unit tests are included; the latter passed. A networked rerun of `title_probe.py` against pinned upstream bytes is required before upgrading these counts to cross-implementation reproduction.

## 4. Results

### Complete two-title retrieval

| Subset | Type | n | BM25 complete@2 | MMR complete@2 | BM25 complete@10 | MMR complete@10 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dev | Bridge | 399 | 48 (12.0%) | 46 (11.5%) | 101 | 94 |
| Dev | Comparison | 101 | 97 (96.0%) | 96 (95.0%) | 100 | 100 |
| Test | Bridge | 404 | 74 (18.3%) | 70 (17.3%) | 114 | 114 |
| Test | Comparison | 96 | 93 (96.9%) | 93 (96.9%) | 96 | 96 |
| Both | All | 1,000 | **312 (31.2%)** | **305 (30.5%)** | 411 | 404 |

### Any annotated title retrieved

| Subset | BM25 any@1 | BM25 any@2 | BM25 any@10 | MMR any@2 |
| --- | ---: | ---: | ---: | ---: |
| Dev | 408/500 | 426/500 | 443/500 | 431/500 |
| Test | 413/500 | 424/500 | 443/500 | 425/500 |

The high first-title recall and low two-title recall on bridge questions is the important asymmetry. The bridge-vs-comparison gap persists across the two nonoverlapping question files. Diversity modestly increased any-title recall at k=2 on dev (426 to 431) but reduced complete-title recall (145 to 142). A metric that reports only one relevant document can therefore hide failure to reconstruct the full witness.

### Concrete error pattern

For the authentic question "In what country does the director of Shirin in Love, live?", the annotated support-title pair is `Shirin in Love` and `Nazanin Boniadi`. The title `Shirin in Love` is discoverable directly from the query; `Nazanin Boniadi` is not named. The corpus here contains titles only, so the system has no evidence text from which to learn the director relationship. Selecting more lexically diverse titles does not create that missing relationship.

This also limits interpretation: a correct answer could sometimes be given from a single source or background knowledge. Full annotated title coverage is a structural surrogate, **not a proof that both documents are logically necessary**.

## 5. Graph-of-thoughts continuation

### A. A missing bridge is a missing observation, not a ranking defect

An unobserved entity `v` may connect `u` in the question to an answer-bearing source. If the index contains only document titles and `v` does not occur in the query, a lexical scoring policy lacks the information needed to prefer the correct `v`-title over other unrelated titles. Suppressing redundancy or increasing k can change the shortlist, but cannot create evidence about the relation `u -> v`.

This is an identifiability problem under specified observations, not a new information-theory theorem. It motivates measuring **which acquisition actions reveal new conditional information**, rather than asserting that another graph scorer is better.

### B. Bridge extraction creates a causal dependency

A candidate two-step policy is:

1. Retrieve one question-linked source and inspect its sentences.
2. Propose a bridge entity with a source-coordinate receipt.
3. Search for a second source using that bridge entity.
4. Check that the two returned passages jointly entail the question's answer, or abstain.

The act of reading source 1 changes the input to stage 2. This is ordinary iterative retrieval and established prior art. The unresolved CDG question is whether exact source-aligned partial reads and conservative acquisition policies make it cheaper *at matched complete support*.

### C. Evidence is typed by identity, sufficiency and read cost

A typed evidence receipt needs at least `(source_version, canonicalizer_version, span_ranges, retrieval_reason, relation_claim, authorization_scope)`. The relation claim remains fallible even if source bytes and span positions are exact. A hash proves identity, not entailment or independence.

Physical frames add a submodular-looking activation **cost**: reading a second nearby span can be cheap if its frame is already resident. This observation does not make evidence sufficiency submodular. Multi-span AND requirements are often complementary. The correct objective is constrained source-acquisition planning, with confidence and metadata costs included.

### D. No confidence without a real uncertainty model

Round 21 showed that assumed dependency confidence can remain high under a no-signal shift. A bridge extractor must be evaluated on unfamiliar entities, including explicit abstention and false bridge proposals. Avoid tuning confidence cutoffs on the same questions used for evaluation.

### E. The contradiction branch

A source may mention two plausible bridges, use a stale relation, or quote another document. Before accepting a cheap answer, test exact identity, source version, permission and contradiction handling. Round 23 only proves that guards work in deterministic metadata fixtures, not on real conflicting articles.

## 6. Next controlled experiment (Round 25)

**P0: Obtain original HotpotQA distractor dev records with full `context` and `supporting_facts`, verify archive checksum, and freeze a 250–1,000-question predeclared subset.** Use official contexts, not an oracle-derived pool of titles. Measure complete supporting *document and sentence* recall under identical candidate sets.

**P1: Compare** BM25 and BM25+MMR, simple two-hop BM25 with extracted bridge entities, iterative retrieval without an LLM, and a frozen model-based query decomposition baseline. Charge every intermediate retrieval and source materialization. Put strong baselines ahead of a new graph controller.

**P2: Physical cost** use independent compressed frames and seekable Zstd: total archive+index+metadata bytes, p50/p95 cold/warm access, decoder CPU and source-update invalidation. Measure token cost only if an actual frozen reader is run.

**P3: Citations and calibration** evaluate span overlap, source version, missing/contradictory evidence, false-answer rate, abstention, and answer EM/F1 separately.

**Kill criterion:** If a conventional bridge-conditioned retriever recovers complete supporting evidence at the same or lower total resource cost than the CDG joint optimizer, drop the new controller and isolate any defensible contribution to verifiable source receipt / physical layout. If no official source texts are obtained, **do not claim end-to-end performance**.

## 7. Reproduce

```bash
python experiments/round-24/fetch_upstream.py --output-dir data/round-24-upstream
python experiments/round-24/title_probe.py --data-dir data/round-24-upstream --output experiments/round-24/results_reproduced.json
python -m unittest discover -s experiments/round-24 -p 'test_*.py' -v
```

The downloader pins the upstream Git commit and verifies both Git blob SHA-1s. The report's `results.json` contains the original independent connected-resource analysis and must not be silently overwritten to imply a successful local full-data rerun.

**Prior-art collision:** Standard iterative retrieval, IRCoT, IndexRAG, BridgeRAG and graph traversal already address much of the underlying idea. CDG's novelty is still unproven.


---

# Round 25: Exact-Mention Bridge Expansion on Authentic Multi-Document Contexts

**Research date:** 12 November 2026  
**Status:** Exploratory retrieval-only analysis of 100 HotpotQA-derived questions with authentic paragraph text and annotated supporting sentences. Full-dataset results computed in the connected GitHub JavaScript analysis; seven local Python regression tests passed. The local offline environment did **not** rerun the Python reproducer on the source corpus. No held-out claim, answer-generation evaluation, cold-SSD measurement, compression advantage, or novel-algorithm claim.

## Research question

Round 24 showed that lexical title ranking on actual multihop questions often identifies the first supporting document but not the hidden bridge. This round asks whether **reading the first retrieved paragraph** and extracting references to other candidate-document titles can restore evidence completeness. This is an intentionally *simple established baseline* before constructing a graph controller or source-aligned compressed evidence index.

## Corpus provenance and limits

- Repository: `OpenSPG/KAG`, revision `fdab15b3929d2ee40dfcdd388f90233096a6afc9`.
- File: `kag/open_benchmark/hotpotqa/data/qa_train.json`, Git blob SHA-1 `7dbdf068a437f0577043667ffee3a20f0a602154`.
- **100 questions**, including **78 bridge** and **22 comparison** questions, **994 question-local candidate paragraphs**, **4,139 sentences**, and **229 annotated supporting sentences**. Every cited supporting sentence is available in the supplied per-question context.
- The sample is curated upstream; the selection process and exact relation to the official held-out dev split were not independently audited. It is **not** a randomized, pre-registered test split, and the original official archive has not been matched bytewise.
- Every question has a closed-world candidate pool that includes its gold paragraphs, as in the distractor formulation. Gold titles and sentence IDs are used **only to score** a policy, never to choose its documents. This is not the Round 24 gold-title-pool construction, but it is still closed-world rather than open-domain retrieval.
- Corpus text is not redistributed in this repository. `bridge_probe.py` can fetch the exact pinned raw file with Git-blob SHA verification on a networked machine. Attribution and upstream dataset licensing must be respected.

## Policies and cost boundary

All policies see the same query-local candidate documents. A Unicode-alphanumeric tokenizer and independently implemented positive-IDF BM25 (`k1=1.2`, `b=0.75`) score full document titles plus text. Ties use ascending title; no model training or tuning on external data occurs here.

1. **BM25**: score, rank, take top K.
2. **MMR**: greedily choose at most K using `0.75 * normalized_BM25 - 0.25 * max_document_token_Jaccard_overlap`.
3. **Exact-title bridge expansion**: take the highest-scoring document; for subsequent selections, add a fixed **2.0 BM25-score bonus** to each unselected candidate whose *canonical title* occurs as a **whole token sequence** in any already selected source paragraph. The exact title itself is candidate metadata; the mention must be observed in selected source content. This is ordinary string matching and iterative expansion, **not** natural-language relationship understanding or semantic certification.

**Cost accounting warning:** All candidate texts are scored via a prebuilt BM25-style index, but the prototype's analysis does not charge building or consulting that index or a title-mention lookup. The report's `selected_chars` counts **only the selected source paragraphs** as an output/text-exposure proxy. Lower selected characters do **not** demonstrate lower total I/O, CPU, or wall-clock latency. No physical compression was run in this round.

**Evaluation units:** `complete_docs@K` requires all distinct gold-annotated titles among K selected documents. `any_docs@K` requires at least one. To measure how far sentence filtering can undermine a successful document retrieval, `complete_sentences_topM@K` requires every annotated gold `(title, sentence ID)` to appear after selecting up to M BM25-ranked sentences *per selected document*. The latter is a cheap sentence-level lexical proxy, not a learned claim-conditioned extractor. Evidence presence is not semantic entailment or generated-answer correctness.

## Core observed results

| Policy | Complete docs @2 | @3 | @5 | Mean selected chars @2 | @5 |
|---|---:|---:|---:|---:|---:|
| BM25 | 33/100 | 46/100 | 62/100 | 1,035 | 2,781 |
| MMR | 32/100 | 47/100 | 62/100 | 1,044 | 2,810 |
| Exact-title bridge | **46/100** | **64/100** | **84/100** | 990 | 2,707 |

**Paired @2 outcomes:** both methods succeed on 31 questions, bridge expansion alone succeeds on 15, BM25 alone succeeds on 2, and neither succeeds on 52. Bridge questions gain the most: 26/78 (BM25) to 41/78 (bridge expansion) at K=2; comparison questions fall from 7/22 to 5/22. At K=5, bridge questions go from 46/78 to 64/78, and comparison from 16/22 to 20/22.

This is **13 additional complete-document cases at K=2 and 22 at K=5** in this small and selected sample. These exploratory differences are not a new algorithm claim. No hyperparameter search was performed for the 2.0 mention bonus, but the analysis and policy were constructed with access to the same upstream dataset family, so an independent held-out replication remains necessary.

### Gold sentence coverage is harder

| Policy, K | All annotated sentences present in full selected docs | All annotated sentences among top-2 BM25 sentences per selected doc |
|---|---:|---:|
| BM25, 2 | 33/100 | 26/100 |
| Bridge, 2 | 46/100 | 36/100 |
| BM25, 5 | 62/100 | 50/100 |
| Bridge, 5 | 84/100 | 69/100 |

Thus document-level success materially overstates evidence preserved by a simple sentence filter. Under the stronger `top-3 sentences per selected doc` proxy, bridge expansion reaches 43/100 at K=2 and 79/100 at K=5. Full context access remains essential for some queries, and no semantic verifier was tested.

### Observed failure examples

- **Beneficial bridge:** A question about the man who resigned before the Israeli presidential election of 2000 retrieves the election article. That paragraph mentions **Ezer Weizman**, whose title can be found and used as a second-hop key; BM25 alone ranked a different election.
- **Beneficial bridge:** A question about a film shot near Leland, North Carolina retrieves the location article, then selects **Maximum Overdrive** rather than another document matching the location name.
- **Harmful expansion:** A comparison asking whether Christopher Nolan and Sathish Kalathil are both directors already has both gold titles in BM25's top two. The mention booster instead promotes an additional film referenced in one selected document. This illustrates why expansion should not be blindly used for comparison questions or without a stopping rule.

These examples were inspected as retrieval identities; no generated answer was produced or independently checked for truth.

## Implications for the compression/RAG graph of hypotheses

**H25-A, document bridge as an information-acquisition action.** The hidden second target cannot be reliably recovered from the original query vocabulary alone; a first selected source can reveal a candidate name. This is a standard and empirically useful retrieval operation. It is not a new mathematical result.

**H25-B, source-aligned branch factor.** A full paragraph may contain several names, but only a minority are useful bridges. A future version should produce reversible span receipts for the **sentence that contains each candidate title mention**, then selectively decode adjoining physical frames. Crucially, one cannot claim these cheaper than full document reads until index, mention lookup, frame metadata, and cold-cache costs are measured.

**H25-C, conditional routing.** In this sample, unconditional mention expansion damages some comparison questions. A policy might condition expansion on expected marginal complete-witness gain, predicted question type, remaining budget, and source confidence. A learned gate must be calibrated on held-out data. A hand-labelled question-type gate would contaminate inference and is not acceptable.

**H25-D, structural coverage and semantic support are different types.** Exact title occurrence proves that a sequence of words occurs in a source, not that the source endorses the relationship. Copied quotations, negations, outdated source versions, and forged metadata can all break the intended inference. The next prototype must distinguish `mention_present`, `relation_verified`, `source_current`, and `answer_supported` rather than using a single Boolean evidence flag.

**H25-E, physical savings could disappear.** Whole selected source characters are marginally lower for the bridge policy, but it may pay extra CPU for repeated scoring/inspection, and a compressed frame layout might increase bytes read because of scattered mentions. Database inverted indexes and title-link graphs are mature competing solutions. A new CDG method must compete with precomputed document-link indexes and source-aligned compressed frames under identical complete evidence and real cost constraints.

## Prior-art collision

- Trivedi et al., **IRCoT**, ACL 2023, interleaves reasoning and retrieval: https://aclanthology.org/2023.acl-long.557/ .
- **IndexRAG**, Findings IJCNLP-AACL 2026, precomputes bridge facts during indexing: https://aclanthology.org/2026.findings-aacl.175/ .
- **BridgeRAG**, 2026, bridge-conditioned retrieval: https://arxiv.org/abs/2604.03384 .
- Other practical systems create document-mention graphs and use query-conditioned expansion; the underlying idea is **not new**.

## Reproduction

```bash
python experiments/round-25/bridge_probe.py \
  --data data/round-25/qa_train.json --download \
  --output experiments/round-25/reproduced.json
python -m unittest discover -s experiments/round-25 -p 'test_*.py' -v
```

The pinned upstream SHA-1 check prevents accidental use of a changed corpus. Results embedded in `results.json` were computed with a **separate JavaScript implementation** over the connected source file; executing the Python full-data benchmark on an offline machine remains undone. The seven Python unit tests test local function contracts only. All code is source-available; full-data cross-implementation agreement is a future gate.

## Round 26 preregistration and kill test

1. Obtain the official HotpotQA distractor dev archive and independently verify sample membership, or use a defensible held-out alternative. Freeze a split before tuning.
2. Compare current BM25, exact-title expansion, precomputed title-link graph, IRCoT-style iterative retrieval, dense/hybrid retrieval and an always-read-full-paragraph baseline on identical candidate pools.
3. Implement reversible canonical-to-original offset receipts and independently compressed source frames. Count full archive + index + title-link sidecar + metadata bytes. Measure p50/p95 cold and warm reads, decompression and actual bytes, not just output characters.
4. Evaluate answer EM/F1, source- and sentence-grounded citation precision, complete evidence recall, selective abstention and calibration under source-version drift and authority uncertainty.
5. **Kill or simplify** the proposed joint controller if plain title-link indexing plus seekable frames matches quality/cost. Do not submit a superiority paper on the basis of this round.

**Decision:** GO for the narrow source-mention/physical-frame integration benchmark. NO-GO for an end-to-end or theoretical novelty claim.


---

# Round 26: Exact Span Receipts, Selective Source Frames, and the Vanishing-I/O-Savings Problem

**Research date:** November 12, 2026  
**Continuity:** CDG Rounds 0–25; direct continuation of the HotpotQA-derived full-context Round 25 retrieval baseline.  
**Evidence status:** 100 authentic-question/paragraph records analyzed through the pinned connected GitHub source in an independent JavaScript analysis. A separate Python implementation now supports exact UTF-8 receipts and genuinely compressed independent Zstandard frames; eight *local unit tests* passed. The full 100-record data was not downloadable into the local runtime, so **the Python whole-corpus compressed-byte experiment has not been run**. All reported frame-read values below are *modeled uncompressed physical activation*, not compressed SSD measurements or claims of better RAG answers.

## 1. Why this round exists

The previous round found that exact-title bridge expansion improves complete supporting-document recall but still loses evidence when it keeps too few sentences. It would be easy to mistake shorter passages for less retrieval work. That is often false: selective byte ranges may activate most of the same physical frames as a complete source, while indexes and sidecars add their own costs. I therefore asked two narrower questions:

1. **Can we represent every chosen sentence using unambiguous, reversible UTF-8 span coordinates without claiming original JSON byte offsets?**
2. **How much of a document's source bytes would fixed-size, independently accessible physical frames activate under non-oracle evidence-selection policies?**

A third experiment tests whether preserving sentences that contain an *observed* candidate bridge title adds marginal evidence completeness beyond ordinary top-two sentence BM25.

## 2. Data and fixed policies

**Source:** `OpenSPG/KAG`, commit `fdab15b3929d2ee40dfcdd388f90233096a6afc9`, `kag/open_benchmark/hotpotqa/data/qa_train.json`, Git blob SHA-1 `7dbdf068a437f0577043667ffee3a20f0a602154`. 100 HotpotQA-derived questions, 994 question-local paragraph occurrences, 4,139 sentences, 229 gold annotated sentence IDs. The sample is **curated upstream**, contains every gold source in a question-local candidate set, and is neither an untouched official dev set nor open-domain retrieval.

As in Round 25, the ranker uses Unicode-token BM25 over title plus body with `k1=1.2`, `b=0.75`, followed by a fixed `+2.0` bonus when a candidate's full normalized title occurs inside an already selected source paragraph. This baseline is **conventional iterative title-link retrieval**, not a CDG invention. All selection is inference-time and never sees gold annotations. Gold sentence IDs are used only for evaluation.

For each selected document, four *non-oracle* materialization policies are compared:

- `full`: read all source sentences;
- `top2`: read the two highest query-BM25 scoring sentences;
- `top3`: read the three highest;
- `top2+link`: start with top two, and also preserve any earlier selected source sentence whose normalized full-token content contains the title of a later selected source. Only the sentences of **already selected documents** are eligible. This is a dependency/receipt preservation heuristic, not a source-support verifier.

At document budgets K=2,3,5, the test measures whether **all gold `(title, sentence-index)` pairs** are present, the UTF-8 bytes in chosen sentence spans, and the *union* of source frames activated. No semantic answer was generated.

## 3. Exact bytes and frame accounting

**Representation contract:** construct a new immutable body `UTF8(title + '\n' + sentence_0 + '\n' + ... + sentence_n + '\n')`. Each sentence has exact half-open byte coordinates within **that constructed source**, not the original upstream JSON. Each selected range can carry `source_content_hash`, `(start_byte,end_byte)`, `encoder_version`, and `SHA256(range_bytes)`. The source archive remains independently lossless; a location proof is not an entailment proof.

For fixed source frame size B, the modeled activation of selected span set S is the union

\[
A_B(S)=\bigcup_{[a,b)\in S}\left\{\lfloor a/B\rfloor,\ldots,\lfloor(b-1)/B\rfloor\right\}.
\]

Actual number of source-body bytes activated is

\[
R_B(S)=\sum_{j\in A_B(S)}\min(B,\; |D|-jB),
\]

where \(|D|\) is the UTF-8 byte length of the per-question document occurrence. Overlapping selections are not counted twice within a source. The archive stores separate copies of each question's candidate documents, **not** a cross-question deduplicated Wikipedia collection. That means the archive figures are not a realistic globally deduplicated RAG database.

The archive contains **572,088 raw UTF-8 body bytes** across 994 independently addressed source occurrences. Assuming 16 *modeled* metadata bytes per frame:

| Frame B | Frame count | Modeled metadata bytes | Metadata / raw source |
|---:|---:|---:|---:|
| 128 | 4,960 | 79,360 | 13.87% |
| 256 | 2,736 | 43,776 | 7.65% |
| 512 | 1,599 | 25,584 | 4.47% |
| 1,024 | 1,082 | 17,312 | 3.03% |
| 2,048 | 998 | 15,968 | 2.79% |

These are byte counts from original source text with an assumed fixed-size frame table. Frame compression ratio, codec overhead, indexes, title-link sidecars, cache metadata and filesystem allocation are **not included** in this table.

## 4. Complete evidence versus source read amplification

### Baseline: bridge expansion with five selected documents

| Sentence policy | Complete gold sentence sets / 100 | Mean chosen sentence UTF-8 bytes | Modeled read bytes @128B frames | @512B frames | @2,048B frames |
|---|---:|---:|---:|---:|---:|
| Full documents | **84** | 2,599 | 2,722 | 2,722 | 2,722 |
| Top 2 sentences | 69 | 1,386 | 1,920 | 2,451 | 2,722 |
| Top 2 + observed bridge mentions | 74 | 1,417 | 1,946 | 2,457 | 2,722 |
| Top 3 sentences | 79 | 1,855 | 2,312 | 2,628 | 2,722 |

**Source-read savings are not evidence-equivalent savings.** At 128-byte frames, `top2+link` activates 28.5% fewer modeled source bytes than full documents but loses ten complete gold evidence sets (74 versus 84). At 512-byte frames it activates just 9.7% fewer bytes, and at 2,048 bytes no modeled savings remain because most candidate paragraphs fit inside a frame. Under the 128-byte model, the bridge-preserving addition raises recall from 69 to 74 while increasing average frame activation from 1,920 to 1,946 bytes. It is an attractive *conditional incremental trade* on this small dataset, not an established Pareto advance over more sophisticated extractors.

**Other budgets:** Complete gold evidence for K=2: full 46, top2 36, top2+link 39, top3 43. At K=3: 64, 53, 56, and 60, respectively. The link-preserving addition rescued 3 complete evidence sets at K=2, 3 at K=3, and 5 at K=5, without sacrificing any earlier top-two complete case (it is a superset). This improvement is structurally guaranteed to be nonnegative for evidence *presence* because selected sentences are only added; it is not a demonstration that those extra sentences improve a frozen reader's accuracy.

### Critical failure modes

- **Frame-size collapse:** At B=2,048, this benchmark's short paragraphs cause top2, top3 and full-document policies to activate the *same* modeled physical bytes. Smaller prompts do **not** imply fewer physical reads.
- **Budget incompleteness:** The bridge document ranker itself recovers all annotated documents for only 84/100 queries at K=5. No subsequent sentence compressor can improve that without changing retrieval.
- **Partial witness failure:** Top2 + link still loses 10/84 source-complete questions. The fact that a sentence mentions the title of the next source does not ensure it contains every supporting premise.
- **Unpriced preprocessing:** BM25 scoring, sidecar mention discovery and all candidate source scanning are treated as indexed preprocessing. A system claiming less I/O must include building and querying those indexes, and should test a conventional precomputed title-mention graph.
- **Missing semantic authority:** Exact UTF-8 receipts and link mentions do not prove the cited sentence supports the answer, that a source is independent, or that its version and ACL are appropriate.

## 5. Implementation and test evidence

`experiments/round-26/frame_probe.py` is standard-library Python 3.10+ with an optional system `libzstd` via `ctypes`. It:

1. verifies the upstream Git blob before processing;
2. reproduces Round 25 title-BM25/bridge ranking and sentence policies;
3. exposes exact source byte receipts and checks independent frame roundtrip;
4. can actually compress each frame with `zstd` or `zlib`, and count *compressed frame bytes* for each selected set as well as complete archive+modeled metadata bytes;
5. writes aggregate JSON with source identity and assumptions.

The implementation is **not** the Zstandard seekable file container specification: it compresses independent frames and measures the payload, but does not serialize a canonical seekable Zstandard jump table. Compare with the maintained reference format at https://github.com/facebook/zstd/tree/dev/contrib/seekable_format .

`test_frame_probe.py` exercises eight cases: Unicode multi-byte receipts, noncontiguous frame union, exact span receipts, zlib roundtrip, real libzstd roundtrip on local test bytes, whole-token link matching, top-two selection scope, and upstream hash rejection. All **8/8** passed locally. They are unit tests, not a fresh 100-question Python benchmark. The real-data aggregate table above was computed separately in a connected-resource JavaScript analysis of the pinned upstream corpus and recorded as `results.json`. Actual corpus-compressed bytes remain **unmeasured**, despite the code now supporting their measurement when the corpus is available.

## 6. Connecting the graph of ideas

**G26-A | Acquisition and materialization are distinct.** A mention-sidecar lets the controller identify bridge names without eagerly decoding whole source bodies. The sidecar itself is a materialized view and must be charged for persistent storage, updates and lookups. This is a conventional DB pattern, not a new retrieval theorem.

**G26-B | Cost depends on activated *sets*, not sentence lengths.** Once a frame is fetched, all its co-resident sentences have near-zero *incremental frame read* cost, although additional output tokens may still be expensive. A physically aware selector should not pretend each sentence has an independent byte cost.

**G26-C | Proof identity and decision confidence diverge.** A SHA256 receipt certifies content identity only relative to verified source bytes. Entailment, source authority and answer correctness are separate fallible decisions. Source-version churn must invalidate stale link indexes and span pointers together.

**G26-D | Evidence AND-sets versus submodular frame union.** Physical activation cost is monotone and submodular as a function of selected spans (for fixed frames), while complete witness coverage can contain conjunctive dependencies with non-diminishing returns. Naive relevance-per-byte ranking can therefore miss a complete witness even when it accurately prices frames.

**G26-E | The strongest negative result is likely the simplest.** On short scientific abstracts or per-question HotpotQA contexts, ordinary 512–2,048 byte frames often cover most or all of a document. A complicated physical controller may cost more than its potential read savings. Any proposed contribution should work on genuinely larger source bodies, or be reduced to a fast metadata-driven bridge index.

## 7. Literature and novelty check

- Zstandard's standard seekable format already defines independent frames and a seek table; frame-size tuning and source range reads are not novel. https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/README.md
- **SARA** (ACL 2026) explicitly studies adaptive retrieval and context compression, preserving some exact text and compressing other evidence. https://aclanthology.org/2026.acl-long.661/
- **HLLC** (Scientific Reports, 2026) investigates indexing-stage context compression and evidence quality tradeoffs. https://www.nature.com/articles/s41598-026-65702-2
- IndexRAG and IRCoT already provide bridge-aware multihop retrieval. https://aclanthology.org/2026.findings-aacl.175/ ; https://aclanthology.org/2023.acl-long.557/

**No new coding theorem, verified end-to-end answer improvement, or non-dominated compression/retrieval frontier is demonstrated.** The source-span/frame software is a useful reproducible engineering baseline.

## 8. Round 27 registration and decision

**P0: reproduce the 100-record result in Python** using the pinned upstream file and actually compress all frames with Zstandard, including measured compressed payload bytes and a valid seekable format/metadata baseline. Do not infer codec ratios from modeled uncompressed frames. Audit sentence parsing and matching across implementations.

**P1: longer documents and a real access workload.** Evaluate full article bodies and larger-scoped cases where selecting only 5–10% of text can plausibly save physical reads. Report document length distribution, total archive+index+metadata bytes, cold/warm latencies, disk page effects, and update/rebuild cost. Compare a simple title-link index plus seekable Zstd before introducing a new joint planner.

**P2: independent quality.** Freeze model and prompts, measure answer EM/F1 and citation faithfulness, not solely structural coverage. Reserve untouched family/document splits. Include unauthorized/corrupted/contradictory source stress tests.

**Decision:** Proceed with a source-aligned system implementation, but **do not claim current physical compression superiority**. The observed frame/read-coverage frontier sharply limits any advertised advantage on short documents. A paper claim requires real compressed archive+index+I/O results and a new mechanism that beats the simple precomputed-link baseline on held-out evidence quality.


---

# Round 27: Storage Versus Source-Read Cost in Independent Zstandard Frames

**Research date:** 13 November 2026  
**Stage:** Real Zstandard compression and measured compressed-frame sizes on local CDG technical reports, with deterministic synthetic read workloads.  
**Decision:** Retain line-aware framing as a *candidate physical baseline*, not as an original compressor or a demonstrated RAG advantage. Next experiment must charge the search index and run against the authentic HotpotQA source contents with realistic request distributions.

## 1. The problem I chose to isolate

Round 25 improved complete supporting-document coverage by reading bridges. Round 26 showed that sentence selection trades source evidence preservation for modeled frame reads. However, neither established actual compressed storage or read costs on the 100-question HotpotQA sample. Before adding a complex joint evidence-layout planner, I wanted to test a simpler question: **is aligning compression frame boundaries to retrieval units sufficient to reduce decompression work, and what permanent storage cost does that incur?**

The comparison deliberately includes a lower-bound storage-oriented baseline, whole-document Zstandard, and conventional independent fixed-size frames. A line-aware layout is a crude approximation to source-aligned evidence units. None of these layouts is a novel compression algorithm. Real disk reads, NVMe queueing, page cache behavior, frame seeking, title lookup and verification are still outside this isolated test.

## 2. Data and exact experiment

Five existing CDG Markdown research reports were read as byte-for-byte local UTF-8 source files: Round 19 report, Rounds 20–22 appendices, and Round 26 report. Combined uncompressed size: **90,163 bytes**. SHA-256 digests and individual sizes are embedded in `results.json`. This is **not HotpotQA**. These documents share style and terminology, and therefore cannot stand in for multilingual, code-heavy, scientific-PDF or large web corpora.

A seeded workload (`seed=27026`) samples **250** two-span requests from source lines of at least 40 bytes. Every third query chooses a nearby second line when available; the others use a randomly sampled other line. The second workload retains the same construction but requests short interior subspans, averaging 85.7 requested raw bytes instead of the 424.0-byte average in the whole-line workload. These are synthetic query locations. They are **not inferred from independent user questions**, and alignment to line boundaries is a known advantage for the line-aware layout.

All source bytes are losslessly compressed with actual `libzstd` (Zstandard level 3) through `ctypes` and decoded to check equality. Frames are independent. The layout choices are:

- `whole`: one compressed stream per report;
- `fixed:B`: contiguous independent frames with raw capacity B bytes;
- `line_aligned:B`: greedily pack complete source lines into frames of at most B bytes, splitting a line only when it exceeds B.

Each frame has a **modeled 16-byte sidecar entry** (raw starting offset, compressed starting offset, compressed length); this sidecar was not serialized or measured. The retrieval program knows the exact source span coordinates in advance, so retrieval scores, a sentence-coordinate index, metadata lookups, query planning and frame-file seeks are not charged. Physical read traffic is measured as the sum of selected independently compressed frame payload lengths, not actual bytes transferred by an SSD. Duplicate frames within a query are only counted once per source. Each requested span is reconstructed exactly from the decompressed selected frames, including Unicode bytes.

## 3. Results: whole-line source span workload

| Layout | Compressed payload + modeled 16B/frame table | Mean compressed payload per request | Mean frames decoded | Observed median warm decode+extract (μs)* |
|---|---:|---:|---:|---:|
| Whole document | 39,412 B | 12,671 B | 1.52 | 60.3 |
| Fixed 128 B | 87,599 B | 552 B | 5.19 | 60.3 |
| Line-aligned 128 B | 92,391 B | 396 B | 4.26 | 48.0 |
| Fixed 256 B | 71,395 B | 644 B | 3.55 | 40.9 |
| Line-aligned 256 B | 74,898 B | 411 B | 2.80 | 39.0 |
| Fixed 512 B | 62,338 B | 855 B | 2.65 | 37.4 |
| **Line-aligned 512 B** | **64,722 B** | **540 B** | **2.11** | **35.5** |
| Fixed 1,024 B | 55,260 B | 1,247 B | 2.13 | 27.8 |
| Line-aligned 1,024 B | 56,624 B | 945 B | 1.85 | 26.8 |
| Fixed 2,048 B | 50,045 B | 2,002 B | 1.88 | 30.3 |
| Line-aligned 2,048 B | 50,799 B | 1,763 B | 1.75 | 30.4 |
| Fixed 4,096 B | 46,409 B | 3,457 B | 1.74 | 34.8 |
| Line-aligned 4,096 B | 46,660 B | 3,212 B | 1.69 | 34.2 |

*The timings are single-run Python-level **warm, in-memory decompression plus extraction**, excluding file I/O, search, metadata lookup, and concurrency. Do not treat differences of a few microseconds as statistically robust. The actual compressed frame payload lengths are measured, but archive tables are modeled.*

At 512 bytes, line-aware framing adds **2,384 B** to archive+table storage relative to fixed framing (64,722 vs 62,338 B), while reducing mean compressed payload fetched by **314.8 B per request** (540.0 vs 854.8 B), a **36.8% decrease**. It also activates fewer uncompressed bytes (852 vs 1,344 B). Compared to whole-document compression, every fine-grained option greatly expands stored bytes in exchange for dramatically reducing the compressed bytes needed for a targeted request.

## 4. Sensitivity: shorter subspans within lines

This control reduces direct alignment advantage by selecting interior pieces of lines rather than their entire lines. At 512 bytes, fixed framing retrieves **684.4 compressed bytes/request** on average, while line-aware framing retrieves **519.1 B/request**. At 256 bytes the values are **426.1** and **321.9 B/request**; at 1,024 bytes they are **1,105.5** and **973.9 B/request**. The line-aware gain persists in this generated workload, but decreases at larger frames. It is still not evidence of transfer to unseen natural QA questions.

## 5. The decision rule is a workload-weighted cost inequality

Suppose layout A uses persistent bytes \(S_A\), with expected compressed payload per query \(R_A\), and layout B has \(S_B, R_B\). A stylized cost is

\[
J(L)=\alpha S_L + N\,\beta\,\mathbb E[R_L(q)] + N\,\gamma\,\mathbb E[T_\mathrm{decode}(q,L)] + C_\mathrm{index}(L)+C_\mathrm{updates}(L),
\]

where \(N\) is the expected number of requests during the archive's useful lifetime and \(\alpha,\beta,\gamma\) convert storage, read traffic and CPU time into comparable costs. There is **no universal optimal frame size**. The experiment supplies two isolated inputs, \(S_L\) and an approximate \(\mathbb E[R_L]\), but does not determine the weights or full overhead.

For the 512-byte pair, the ratio \((S_\mathrm{line}-S_\mathrm{fixed})/(R_\mathrm{fixed}-R_\mathrm{line})\) is **7.6 queries**, *only if* one chooses identical cost weights per stored byte and per compressed byte retrieved, and ignores indexes, CPU, updates and latency. This is **not** a measured economic amortization threshold. SSD/storage pricing, IOPS and read amplification do not justify setting these weights equal.

A useful graph-of-thoughts connection emerges: evidence completeness has complementary AND requirements, while physical frame cost is a union over overlapping source-coordinate intervals. If the index stores query-relevant span coordinates and frame IDs, the runtime can estimate incremental frame activation, but those index entries have their own persistent and query-time cost. Optimizing activation alone is therefore incomplete.

## 6. Failure modes and algorithmic boundaries

1. **Layout leakage:** synthetic target spans are selected from lines in the source text, so line boundary knowledge helps. We include subspan sensitivity, but must eventually use real evidence spans from naturally authored queries.
2. **Storage inflation:** at 128 B, line alignment nearly doubles the archive+table size versus a 39.4-KB whole-document compression baseline.
3. **Metadata undercounting:** 16 bytes per frame is a declared hypothetical table, not a serialized index. Source IDs, ACLs, timestamps, sentence offsets, citation receipts and update logs would increase costs.
4. **Oracle coordinates:** the physical benchmark is given correct byte intervals. It says nothing about the cost of finding evidence. No human or model bridge extractor was evaluated here.
5. **No held-out generalization:** a five-report research notebook is a small convenience corpus. Results may reverse for other text distributions, long lines, HTML, short paragraphs, or code.
6. **No authenticated provenance or semantic guarantees:** byte equality establishes only lossless reconstruction. It does not prove retrieved claims, source independence, or current authority.
7. **Measurement noise:** in-memory warm decode timings depend on Python overhead, CPU scheduling and run order. Claim compression and payload sizes, not SSD latency dominance.

## 7. Practical hypothesis revisions

**H27-A (retain):** A source-unit-aware *physical layout* can lie on a better read-bytes frontier than naive fixed frames, provided requested spans align with its units. This is standard access-aware physical database/storage design, not a novelty finding.

**H27-B (downgrade):** Tiny independent frames are not a free win. They spend large amounts of compression efficiency and metadata. The useful unit depends on workload and storage constraints.

**H27-C (new experiment):** Instead of committing to line boundaries globally, measure the distribution of verified evidence span coordinates and *co-access* pairs on an independent corpus. Choose a constrained family of layouts using training queries only, then evaluate storage+I/O+accuracy on a disjoint set. A simple greedy merge or dynamic programming baseline is mandatory. No claim of a new optimum until competing storage-layout literature is audited.

**H27-D (required adversarial test):** Version update, ACL scope change and mutable source re-serialization must invalidate cached span/frame receipts; a byte hash does not substitute for source authority. Evaluate update amplification and stale-index refusal.

**H27-E (kill threshold):** A learned evidence graph planner is unnecessary unless it beats conventional BM25+link expansion plus source-aligned seekable compression on full, matched cost accounting. If no win emerges, focus the paper on a carefully measured negative result or a compact source-receipt mechanism.

## 8. Reproduction and audit

```bash
python experiments/round-27/storage_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round26.md \
  --output results_wholeline_reproduced.json
python experiments/round-27/storage_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round26.md \
  --span-style subspan --output results_subspan_reproduced.json
python -m unittest discover -s experiments/round-27 -p 'test_*.py' -v
```

Source file hashes and sizes are in each result JSON, so a different report snapshot is identifiable. The five exact sources are in earlier archives or can be supplied separately, and are **not copied into Round 27**. Seven unit tests passed after fixing two test-fixture assumptions and correcting empty-span activation. The measured results were generated in Linux with Python 3.13 and `libzstd`; `results.json` and `results_subspan.json` preserve both workloads. The scripts do not download or alter any user data.

## 9. Round 28 preregistration

**P0:** Obtain official HotpotQA paragraph and annotation bytes locally; pin checksum and freeze a disjoint train/test split. **P1:** build a genuine source-aligned frame container plus serialized offset/seek tables and a conventional query-conditioned link index, not just a modeled sidecar. **P2:** run actual cold/warm file-backed reads and decode timings on a defined host, including p50/p95 with repeated randomized order. **P3:** measure complete *annotated sentence* recall at matched prompt/index/read costs. **P4:** add version-change and stale-frame invalidation tests. **P5:** drop the custom controller if a standard line-/paragraph-framed Zstandard index achieves equal quality at lower overall cost.

**Decision:** Round 27 yields an actual compressed-byte trade-off and a reproducible physical-layer prototype, **not** an improved RAG system or a publishable new compression method.


---

# Round 28: File-Backed Zstandard Frames, Serialized Search Metadata, and the Cost of an Index

**Date:** 13 November 2026  
**Status:** Executed local systems benchmark; not HotpotQA or a RAG answer-quality comparison.  
**Decision:** Keep conventional SQLite plus seekable independent Zstandard frames as the immediate engineering baseline. Reject claims that the Round 27 read-traffic reductions already establish a speed or total-storage improvement.

## 1. Why this round matters

Round 25 established that observing an initial source can reveal a missing bridge to another source, but the result used a question-local candidate corpus and a simple non-neural link heuristic. Round 26 showed that selecting fewer sentences can discard necessary evidence, and modeled how frame size changes read amplification. Round 27 measured actual compressed frame payload lengths on technical reports, but *did not serialize or charge for the source index and frame lookup data*. The primary question of Round 28 is: **Does a physically materialized and indexed compressed-source store change the relative cost of the proposed layouts?**

### Hypothesis before the experiment

For short, line-oriented source spans, line-aligned independent compression may reduce compressed payload activated compared to fixed-byte frames. However, a complete search and frame-coordinate index may dominate the total footprint, and the layout with fewer compressed bytes per read may not have lower latency.

## 2. Executed implementation

[`experiments/round-28/filebacked_bench.py`](../../experiments/round-28/filebacked_bench.py) writes real `frames.zst` files containing concatenated independent Zstandard level-3 frames, via the system `libzstd` API. A separate durable `index.sqlite` stores:

- Source identifiers, file names, SHA-256 digests, versions, original byte lengths.
- Frame raw offsets and exclusive ends, payload offsets and lengths; indexed by source and raw coordinate.
- Line offsets, line text, and an **actual SQLite FTS5 full-text index** of those lines.

The storage layouts are whole-document streams, fixed-byte frames, and greedily packed line-aligned frames at capacities of 256, 512 and 2,048 raw bytes. Frame decoding calls `os.pread` with serialized file offsets followed by `libzstd` decompression; overlapping requested intervals activate each relevant frame only once within a query. Reconstructed span bytes are compared directly to the original file bytes. Source frames are stored in an ordinary file, not an official Zstd seekable archive format. FTS5 is queried to verify that the search index works, but **the workload supplies source-coordinate intervals without using FTS5 to choose them**. This is a deliberately isolated physical-read test with *oracle span coordinates*. The SQLite index is real and included in measured storage footprint; its relevance and query-planning performance are not evaluated.

Six local standard-library unit tests passed after repairing a real empty-span bug where a zero-length interval activated a frame. Tests cover Unicode and discontiguous byte restoration, independent-frame codec roundtrips, multiple source IDs, zero-length intervals, live SQLite FTS lookup, and stale version-hash detection.

## 3. Dataset and workloads

Five exact local research reports, 88,679 UTF-8 bytes in total. These are **not** the exact same five report snapshots from Round 27, so direct cross-round numerical differences must not be interpreted as improvements or regressions.

| Input file | Bytes | SHA-256 |
|---|---:|---|
| `CDG_Round19_Research_Report_2026-11-11(1).md` | 28,396 | `b8c805baef7dffaeaf355d31a0ccc23fd1aa83e411a4cbebcc54cae8cd414c02` |
| `cdg_round20_appendix.md` | 16,987 | `c03ad05bd18331e8553d3fe964595bdedbc1ee6a7a9c6d7e5b3a58fd9c947291` |
| `cdg_round21_appendix.md` | 16,372 | `1b310415d0a7f267cd83712b31e70d8d42b956ac44efcff8e71b90394f2f3c99` |
| `cdg_round22_appendix.md` | 14,371 | `49470dd86762c76fcad6eed1795c27da876972a7d7f3f67ed7411963fcf415ad` |
| `report.md` (Round 27) | 12,553 | `8ccbcdd68a07afc3738d4270103c4a1616a775899721ed439323ed570e722e9b` |

Two seeded synthetic workloads of **250 requests each** are generated from lines of at least 45 raw bytes: (a) requests for whole line intervals, (b) requests for short interior subspans. Every third request chooses a nearby second line in the same source if available. Seed 28026. Original span coordinates are known before retrieval; no semantic model or question decomposition is involved. Because query spans originate from lines, line alignment has a favorable sampling bias.

## 4. Measured persistent storage and file-backed compressed traffic

All persistent bytes shown are measured on local files, not modeled entries. They include SQLite's page allocation and the complete FTS5 index. They do not include directory entries, filesystem block allocation overhead or a separate index build log.

| Layout | Zstd payload B | SQLite B | Total B | Mean compressed B/query, whole-line | Mean compressed B/query, subspan |
|---|---:|---:|---:|---:|---:|
| Whole document | 38,689 | 233,472 | **272,161** | 12,509.3 | 12,358.4 |
| Fixed 256 | 64,533 | 241,664 | 306,197 | 641.7 | 387.0 |
| Line-aligned 256 | 66,381 | 262,144 | 328,525 | **428.8** | **317.7** |
| Fixed 512 | 58,283 | 233,472 | 291,755 | 833.9 | 623.2 |
| Line-aligned 512 | 59,785 | 241,664 | 301,449 | **556.8** | **510.5** |
| Fixed 2,048 | 48,323 | 233,472 | 281,795 | 1,986.3 | 1,833.2 |
| Line-aligned 2,048 | 48,961 | 233,472 | 282,433 | **1,765.3** | **1,718.3** |

All **500 requests per layout** returned the original requested bytes without mismatches. Figures include repeated compressed reads across distinct requests; an overlapping frame is not double-counted within a request. Source hashes are preserved in [`results.json`](../../experiments/round-28/results.json).

At 512 bytes, line-aware layout stores **9,694 additional bytes** while saving **277.1 compressed bytes/query** on whole-line requests (33.2%) or **112.7 bytes/query** on subspan requests (18.1%). A mathematically simple storage-to-read ratio is ~35 or ~86 requests respectively if a persistent byte and a retrieved byte receive exactly equal unit weights. **Those ratios are not actual latency or economic break-even thresholds.** SSD read amplification, OS caching, CPU cost, index build and source update frequency are not equally weighted.

The persistent SQLite index ranges from ~233 KB to ~262 KB, more than twice the 88.7 KB of source data. `dbstat` attributed large allocations to the line text table, FTS postings and line offset index. This small-corpus result illustrates *why measured index bytes cannot be omitted*. SQLite's page granularity and duplicated text in the line table are likely factors; it is not a universal ratio for large corpora.

## 5. Real file-backed timing, with a substantial qualification

These are single-run warm observations, in microseconds per request, including Python's SQLite lookups, actual `os.pread` of compressed payload from file descriptors, Zstandard decoding and interval assembly. The benchmark does **not** drop the OS page cache or control clock frequency. No real disk cold-read distribution is available.

| Layout | Whole-line p50 / p95 μs | Subspan p50 / p95 μs |
|---|---:|---:|
| Whole | 75.7 / 96.7 | 75.4 / 114.1 |
| Fixed 256 | 70.9 / 120.8 | 48.8 / 86.2 |
| Line-aligned 256 | 68.4 / 123.5 | 55.9 / 180.2 |
| Fixed 512 | **57.0 / 98.0** | **45.5 / 83.1** |
| Line-aligned 512 | 58.2 / 93.0 | 58.5 / 183.2 |
| Fixed 2,048 | 47.2 / 81.8 | 47.6 / 117.9 |
| Line-aligned 2,048 | 46.3 / 76.4 | 46.2 / 81.2 |

**Negative result:** The 512-byte line-aware layout reliably reduces compressed bytes read in this workload but does not deliver a measured warm p50 benefit. The large subspan p95 variation is especially untrustworthy without repeated randomized runs. If the practical objective is latency, read-byte reduction alone is an invalid surrogate.

Four additional archive+index rebuild runs per layout found observed construction times of ~16-21 ms whole, ~20 ms fixed 512, and ~22-25 ms line 512, on this machine and tiny workload. These are not robust update-throughput measurements.

## 6. Graph-of-thoughts branches

### H28-A: Evidence discovery and physical materialization are separate resource constraints

The source-query controller chooses spans, but the physical store decides which frames must be decoded. Finding relevant text cheaply cannot be assumed if search metadata is larger than the source payload. **Any optimization objective must include index structure and query execution**, not just compressed archive ratio or token count.

### H28-B: Frame-packing optimality is workload-dependent

A simple objective for comparing layouts is

\[
J(L)=\alpha\,S_{\mathrm{archive+index}}(L)+\beta\,\mathbb E[R_{\mathrm{compressed}}(q,L)]+\gamma\,\mathbb E[T_{\mathrm{lookup+decode}}(q,L)]+\delta\,C_{\mathrm{updates}}(L).
\]

The coefficient values depend on expected request volume, concurrency, hardware, source lifespan and service-level objectives. They are not identified by this experiment. Smaller frames reduce bytes activated but increase frame and offset metadata. A conditional physical layout might improve a workload-specific Pareto frontier, but database clustering, materialized views, conventional posting lists and seekable compression are strong established alternatives.

### H28-C: An FTS postings index can conflict with strict byte provenance

The prototype indexes decoded line text using replacement characters for invalid UTF-8. The raw source frames are still lossless, but FTS tokens are **not a reversible canonicalization**. A search hit is an approximate locator, not evidence that the answer is grounded. A future receipt must tie `(source SHA/version, byte spans, canonicalizer ID, index snapshot)` to an exact re-read and independently validate cited text. This is a correctness concern independent of compression ratio.

### H28-D: Mutability and authorization invalidate simple caching assumptions

A mutation test changes one source's content, checks that its stored SHA-256 differs, rebuilds a replacement store and verifies its new digest. This is **only a primitive stale-digest check**. Reads themselves do not yet enforce a hash/version contract, source edits currently trigger full rebuild, and there is no atomic index/payload switchover or ACL enforcement. Production correctness requires snapshot pinning and an update transaction boundary before the source receipt can be trusted.

### H28-E: We have not established any new retrieval algorithm

Bridge-link expansion remains a conventional iterative retrieval method. FTS5 and independent compressed frames are established engineering components. The first possibility worth further work is **a rigorously benchmarked joint materialization policy** that uses held-out evidence co-access statistics to choose grouping and index placement. The simpler null hypothesis is that ordinary compressed frames plus SQLite/FTS5 already sit on the appropriate frontier for this workload. This null must be tested, not dismissed.

## 7. Prior art and implementation conventions

- SQLite FTS5 external-content behavior and shadow-table overhead: https://www.sqlite.org/fts5.html . The prototype explicitly stores line text and uses an external-content FTS5 index. Source edits require correct updating of both or query behavior can be inconsistent.
- Zstandard seekable format: https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/zstd_seekable_compression_format.md . The prototype is **not** this file format; it uses SQLite offsets and independent concatenated Zstandard frames.
- Standard database clustering, compressed inverted indexes and physical data layout optimization cover much of this design space. No original-compressor or first-of-kind index claim is appropriate.

## 8. Reproduction and audit boundaries

From the repository, supply the five SHA-matched report files, then run:

```bash
python experiments/round-28/filebacked_bench.py \
  --files round19.md round20.md round21.md round22.md round27.md \
  --output round28_results_reproduced.json
python -m unittest discover -s experiments/round-28 -p 'test_*.py' -v
```

Requires Python 3.10+, libzstd shared library, and SQLite with FTS5. Tests and full physical benchmark **were executed locally** against the five reports listed here; source bytes are not bundled into the Round 28 experiment. The temporary on-disk archives are created and removed within the benchmark. The JSON output contains precise source hashes and every layout result. The benchmark uses actual persistent files but not real natural QA span locations, answer generation, a verified independent HotpotQA split, cold-cache SSD measurements, a production versioned index, or real ACLs.

## 9. Round 29 decision gates

1. Obtain a fully authenticated, local HotpotQA distractor subset with source text and annotations, and freeze disjoint development/evaluation subsets.
2. Use a real FTS5 query + a conventional title-link or two-hop metadata join to discover source and sentence coordinates at inference. No oracle spans.
3. Compare against BM25/FTS5, iterative bridge retrieval, FTS5 plus ordinary seekable compression, and any proposed co-access grouping at **matched evidence completeness**.
4. Report archive/index/source receipts, actual compressed bytes and data reads, warm and controlled cold trials, build/update cost, update consistency, per-query search time, complete annotated sentence recall and generated-answer grounding separately.
5. Refuse any novel systems or performance claim if the custom layout loses to existing indexing and seekable compression after complete accounting.

**Round 28 verdict:** We built the missing file-backed baseline and demonstrated how index footprint and query overhead affect the trade-off. **We did not beat a strong end-to-end RAG baseline, and we did not establish publication-level novelty.**


---

# Round 29: From Actual Text Queries to Compressed Source Receipts

**Date:** 13 November 2026  
**Status:** Executed local, file-backed retrieval and compressed-frame read benchmark; six regression tests passed. Mechanically source-derived queries; no human QA judgment, learned bridge policy, version-gated live reads, independently held-out split, or cold SSD measurement.  
**Decision:** The physical retrieval loop is operational. Reject the inference that minimum read traffic implies minimum latency. Defer any new graph-controller claim until a query-conditioned, independent multihop dataset can be run on the same engine.

## Research question and relevance to previous rounds

Round 25 found that a simple observed-title bridge improved *document*-level evidence recovery on 100 HotpotQA-derived questions. Round 26 demonstrated that selective sentence access can lose supporting facts, while smaller independent frames lower a modeled raw-byte read proxy. Round 27 measured Zstandard frames on research reports, and Round 28 physically implemented `os.pread` plus SQLite-serialized source offsets, but its queries started with gold source coordinates rather than real search results.

**Round 29 removes that last coordinate oracle from the physical retrieval stage.** A query is issued to a live FTS5 index, which returns line IDs and stored original-source byte coordinates; only then does the engine locate and decode compressed frames and reconstruct exact original bytes. Source-receipt correctness is thus evaluated independently from the selected output's semantic relevance.

This is a conventional SQLite + independent-Zstd-frame system, not a new compressor. No novel relation predictor is trained or claimed. The *measured* engineering contribution of this round is integrating the full query-to-receipt path and charging FTS lookup + frame materialization in timing.

## Source files and query generation

Five previous local reports, **88,679 original bytes**, with pinned SHA-256 hashes in `results.json` and the baseline Round 28 report. Each document is indexed by line; the raw index retains source ID, source version, source hash, line ID, byte start/end and text. Search uses SQLite FTS5 `bm25(lines_fts)` with an OR query over two terms. Gold target-line coordinates are held back from the retriever and used *only to evaluate* whether the target line was among the returned results.

The 158 deterministic tasks were generated from report lines of 90–650 bytes with at least seven non-stopword tokens. Two terms were selected from the target line, with at most approximately equal allocation per file. The selection was seeded at 29026. **The task labels leak into the query-generation process**, making this diagnostic intentionally much easier than authentic QA. It cannot estimate RAG retrieval recall, hallucination, or source semantic sufficiency. It also does not assess complete multi-document witnesses; each constructed task has one gold line. The method does not secretly feed gold offsets to `FTS5` or to the frame decoder; the held-out part is coordinates, *not query formation*.

## Measured end-to-end local storage experiment

Each layout has a physical `frames.zst` file and a real SQLite database with a source table, frame table, line-coordinate table and FTS5 virtual table. 158 tasks were queried three times in shuffled order per layout, resulting in **474 query-and-read measurements** per layout. Only the top three FTS hits are materialized. Any frame reused inside one selected source line is counted once for that `read_spans` call; repeated hits across different rows are not shared through an explicit application cache. Reconstructed bytes were compared with the original files. Five candidates were returned for recall measurement, although only the top three were decoded.

| Layout | Persistent payload + SQLite B | Mean compressed payload read / query B | Full warm p50 μs | Full warm p95 μs |
|---|---:|---:|---:|---:|
| Whole-document Zstd | 272,161 | 23,369.2 | 185.4 | 271.6 |
| Fixed 512-byte frames | 291,755 | 1,372.7 | 139.0 | 221.0 |
| Line-aligned 512-byte frames | 301,449 | **825.7** | 140.1 | 244.8 |
| Fixed 2,048-byte frames | 281,795 | 3,531.6 | **126.8** | **166.1** |
| Line-aligned 2,048-byte frames | 282,433 | 2,971.4 | 127.0 | 229.0 |

For all layouts, **exact target-line retrieval is 60.76% @1, 94.30% @3 and 97.47% @5**. This is a line-identity benchmark; a different relevant line returned by FTS counts as incorrect. The identical recall is expected because each layout uses the same text, index, ranker and tie-breaking policy. The code recorded **zero source-byte reconstruction errors** across the returned top-three hits in all five layouts.

The line-aligned 512 B representation reads **39.8% fewer compressed bytes** than fixed 512 B (825.7 vs 1,372.7 B), while increasing persistent footprint by **9,694 B** (301,449 vs 291,755 B). Its measured median warm request latency is essentially tied (140.1 vs 139.0 μs); the p95 is worse (244.8 vs 221.0 μs). The fixed 2,048 B configuration reads 4.3 times as many compressed bytes as line-aligned 512 B, yet has a *lower observed warm median*. These comparisons illustrate overhead, **not statistically established performance rankings**. Layouts were benchmarked in a fixed order, with no control of OS page cache residency, CPU clocks or process noise; timings include Python and SQLite overhead. No actual disk cold-read distributions are available.

The current timing includes FTS lookup, line ID join, SQLite frame lookup, `os.pread`, libzstd decompression and byte reconstruction. It does **not** include index build time per query, model inference, cross-source link extraction, tokenization into model prompts, or a concurrency SLA. Persistent bytes include the full SQLite database and compressed frame payload, not filesystem allocation/metadata.

## Counterexamples and graph-of-hypotheses evolution

**H29-A: Search relevance does not establish evidence sufficiency.** Exact line recall is a narrower criterion than complete supporting-sentence recall. A retrieved line can be the mechanically selected gold line while failing to answer a real question. An exact source hash and offset prove identity, not truth, authority or entailment.

**H29-B: Frame granularity and runtime latency are competing objectives.** A smaller compressed payload per request may be offset by more SQLite work, more frames to decompress and Python call overhead. A useful physical objective must include measured latency, storage cost, update cost and query distribution, not just compression ratio or frame bytes. This result rejects a simplistic "read fewer bytes => faster" hypothesis.

**H29-C: Data-dependent layout is vulnerable to workload selection bias.** Lines determine both alignment and gold query generation, so aligned frames are favored. The next independently-authored workload may differ substantially. The earlier subspan control in Round 27/28 mitigates but does not eliminate this issue.

**H29-D: Source version checks remain incomplete.** Source hashes are recorded during build, but a production reader does not yet enforce expected source/epoch identity at every read. A query could find valid bytes from an obsolete archive version after a source update. A correct deployed system needs immutable per-epoch readers, transactional update/publish, version-qualified retrieval and refusal of mismatched receipts.

**H29-E: The graph controller still lacks a predictive advantage.** Nothing here compares BM25+iterative bridging, graph retrieval and a CDG joint planner at matched cost on original multihop questions. Standard FTS5 with 2,048-byte frames is already a competitive local latency baseline. Do not treat this systems integration as a novel algorithm.

## Implementation and reproducibility

The experiment is self-contained with `experiments/round-29/retrieval_bench.py` plus the vendored, unchanged Round 28 `filebacked_bench.py` baseline. Python standard library, system `libzstd` and an SQLite build with FTS5 are required. The input reports are already in earlier repository archive paths or available in the research records; their exact hashes are in the results JSON. They are not represented as HotpotQA data.

```bash
python -m unittest discover -s experiments/round-29 -p 'test_*.py' -v
python experiments/round-29/retrieval_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round27.md \
  --output experiments/round-29/results_reproduced.json
```

Six tests passed for FTS lookup, byte-range reconstruction, Unicode-safe source positions, rank invariance across frame layouts, deterministic task construction and zero-length frame-read refusal. Input and output hashes should be checked before comparing reproduced numbers; warm timing values are not expected to reproduce exactly on another host.

## Round 30 registered falsification plan

1. Fix per-query independent original HotpotQA context sources locally. Verify full corpus and gold supporting sentence identities, and **execute** both retrieval and read-cost measurements in the same environment. The previous connector-only JS evaluations must be cross-validated by the Python runner.
2. Compare FTS5 line search, FTS5 paragraph search, two-hop title-mention expansion, title-link index, a conventional iterative retriever and a proposed source-cost-aware controller. Each policy must consume its own observed outputs, not gold source coordinates. Evaluate all gold supporting facts, answer correctness and citation correctness separately.
3. Enforce immutable source-epoch receipts and conduct adversarial update/rollback tests. Charge hash/version checks and title-link sidecars. Test stale, misleading and conflicting source relationships, not just document ID collisions.
4. Run several randomized layout orders, controlled host/cold-cache experiments and repeated sampling before making a latency claim. Include end-to-end indexing, metadata and storage footprints.
5. **Kill rule:** If a basic FTS5/bridge-index + standard Zstd layout lies on the equal-or-better complete-evidence/cost frontier, do not build or publish a more elaborate hypergraph controller. Redirect the technical contribution to source receipts, verified updates or query-aware physical source packing only if those show a separately measurable gain.

**Verdict:** A query-to-byte-receipt retrieval engine now runs without an oracle coordinate input, and the measured trade-off rejects read-traffic-only optimization. Independent QA/citation and true multihop capability remain unproved.


---

# Round 30: The Index Duplication Trap, Offline Bridge Links, and Honest End-to-End Accounting

**Date:** 13 November 2026  
**Status:** File-backed SQLite/Zstandard experiment executed locally; 13 Python regression tests passed. Connected-source analysis of 100 curated HotpotQA-derived questions completed in JavaScript. The two analyses have **not** been executed together on the authentic 100-question corpus in the local file-backed engine. No answer generator, independently held-out QA gain, cold-cache benchmark or novel-algorithm result.

## Executive decision

**Keep:** a compact lexical source index and independently compressed original source bytes with exact source version and byte-offset receipts. **Stop:** using the number of compressed bytes read as the sole retrieval objective and treating an uncompressed copy of all line bodies in SQLite as unavoidable. **Do not advance to a learned graph controller yet.** The practical baseline must first be a conventional SQLite FTS5 contentless index plus a versioned title-link sidecar and Zstandard frames. Each of these components has existing prior art. Any publishable contribution would have to emerge from demonstrated, independently replicated *joint* quality/cost performance, not their coexistence.

A significant correction emerged when reviewing the Round 28/29 implementation: the code stored source line text in the `lines.body` SQLite table while also storing a compressed copy of the same original file. The FTS5 external-content table indexed that line table. Total footprint therefore included both a compressed archive and a nearly complete uncompressed source replica, plus FTS postings. That makes the previous cost frontier partly an artifact of the prototype's index schema rather than a necessary price of compressed retrieval. This failure was worth finding before adding another algorithm.

## 1. Experimental branches and provenance

**Branch A: authentic multihop source-link structure.** Connected GitHub `OpenSPG/KAG` revision `fdab15b3929d2ee40dfcdd388f90233096a6afc9`, `kag/open_benchmark/hotpotqa/data/qa_train.json`, Git blob SHA-1 `7dbdf068a437f0577043667ffee3a20f0a602154`, with 100 authentic HotpotQA-derived questions. This curated upstream subset has 78 bridge and 22 comparison questions, 994 query-local document instances and original source paragraph text. The analysis extracted exact title links only from source text within a question's supplied candidates. It did not redistribute dataset bytes. It ran within the connected GitHub JavaScript environment because network access to that corpus was blocked in the local Python container. The included Python script can be run against the exact source after its pinned bytes are downloaded and verified.

**Branch B: genuine file-backed physical storage.** Five local CDG research reports, totaling **88,679 original UTF-8 bytes**, from the Round 29 benchmark, stored as actual independent Zstandard frames with real `os.pread` calls and SQLite FTS5. Eighteen hand-selected lexical queries were run in both the original *external-content* schema and a new *contentless* schema for three frame sizes. This is a tiny, topic-selected workload, not independent QA. Every returned source span was byte-for-byte checked against the original report. The benchmark reruns both schemas against the same inputs and confirms matching retrieved document and byte coordinates.

**Branch C: integrated execution prototype.** `integrated.py` accepts the pinned HotpotQA-shaped JSON array, builds per-question frame stores and SQLite indexes, retrieves documents by best line-level FTS5 BM25, and compares static FTS, dynamic title-mention expansion and a precomputed link-table expansion. It reads the selected document from the physical compressed file before using its content. Seven local integration tests use two *manually authored* fixtures. Their numerical retrieval scores are **not** HotpotQA results, and the full 100-question corpus has not been run through this Python implementation. The source file has an explicit SHA-1 gate; synthetic fixtures require `--allow-fixture`.

The 13 total local tests comprise seven integration checks and six contentless/storage checks, including Unicode byte reconstruction, empty intervals, gold-label independence of ranking, UTF-8 content, exact reconstructed lines and link-index/dynamic agreement on a toy fixture. A source SHA mismatch is refused by the loader. They do not certify end-to-end answer correctness.

## 2. Finding: avoid duplicated source bodies in FTS5

Two concrete physical schemas were compared:

- **Existing external-content schema:** `lines(line_id, source_id, raw_start, raw_end, body)` plus `lines_fts USING fts5(body, content='lines', ...)`. The `body` column retains uncompressed source text while Zstandard frames retain a separate compressed source.
- **Contentless schema:** `lines(line_id, source_id, raw_start, raw_end)` plus `lines_fts USING fts5(body, content='')`. The original bytes reside only in the compressed payload; FTS5 retains term/posting information and tokens necessary for ranking. Exact text is returned through the stored coordinate-to-frame mapping and verified with its source version hash metadata.

| Zstd frame size | External-content total bytes | Contentless total bytes | Storage reduction |
|---|---:|---:|---:|
| 256 B | 306,197 | 211,989 | 30.8% |
| 512 B | 291,755 | 197,547 | **32.3%** |
| 2,048 B | 281,795 | 187,587 | 33.4% |

All totals count **actual SQLite database file size + actual Zstandard payload file size**. These are not estimates of virtual database pages or uncompressed bytes. FTS5 material still occupies substantial storage: even with 512-byte frames, the contentless database alone occupies 139,264 bytes versus 58,283 compressed source bytes. The original source is 88,679 bytes. Thus a source compressor alone is not yet a persuasive total-system compression story.

**Correctness:** Across each of three frame-size comparisons, all 18 term queries returned the same ranked line IDs/source offsets and exact original bytes. No reconstruction mismatch was observed. The query terms were selected from the reports, so no generalized retrieval-accuracy estimate follows. At 512 bytes, the contentless and original indexes read the same mean **1,713.5 compressed payload bytes** per top-five query. The selected spans are identical; the gain comes from eliminating duplicate persistent source text, not from a better ranking algorithm or lower compressed read traffic.

**Timings are inconclusive.** The 512-byte contentless median over 18 warm queries was 182.9 μs, compared with 231.0 μs for external-content, but these observations are too small and uncontrolled for an inference of latency advantage. Build times also vary. Contentless FTS indexes introduce real update/delete and rank-feature constraints; no concurrent writers or source-update transactions were tested.

## 3. Finding: the source-link graph is small, conventional and useful

Over the 100 authentic HotpotQA-derived query-local contexts, exact whole-token matching of any candidate title inside a different candidate source produced **403 directed document-title edges**, or 4.03 per question. The source text plus titles occupied **571,094 UTF-8 bytes** under this analysis's declared concatenation scheme. A simplistic sidecar charge of 16 bytes/edge amounts to 6,448 bytes of link metadata, and title string length plus eight bytes each gives another 28,047 bytes. These are **modeled lower bounds**, not the actual storage cost of SQLite indexes, token normalization, title dictionaries, or rebuilds; they are kept separate from the file-backed storage table above.

The retrieval result matches the prior Round 25 analysis and is **not** an independent improvement: BM25 @2 recovered both supporting documents on 33/100 questions, and exact-title mention expansion on 46/100; at five documents the counts are 62 versus 84. At k=2, paired outcomes were both 31, expansion-only 15, BM25-only 2, neither 52. In 53/100 cases, the initial BM25 document contains an exact title link to at least one other gold source, but a title string occurring in a document is not automatically an asserted or semantically supporting relation. The source itself may deny, quote, cite, or describe the target.

The fundamental equal-quality control is important: when the offline title-link table encodes exactly the same edges visible to a dynamic string extractor, and both policies use identical base scores and bonus function, **they select identical documents**. Under these conditions a new graph controller cannot claim a document-retrieval advantage from having the graph in a different data structure. The distinction can only arise in amortized index-build/update expense, source bytes read before bridge selection, measured latency, or more accurate/fallible semantic edge extraction. The locally executed fixture tests verified the same selected titles between these two policies. A complete 100-question Python run is still required.

## 4. Nonlinear hypothesis graph and adversarial counterexamples

### H30.1: Query-dependent frame packing can beat fixed line alignment

Source frame selection depends on which evidence spans are jointly requested. A natural proposal is co-locating frequently co-requested span sets, analogous to weighted graph/hypergraph partitioning. But current evidence is insufficient: Round 27's line-heavy workload favored line alignment, Round 28's SQLite dominated footprint, and Round 29 found larger frames competitive on latency. A fair optimization should minimize a joint objective such as

\[
J = \lambda_{q}\,\mathbb{E}[L_q] + \lambda_{d}\,D_{\mathrm{total}} + \lambda_{u}\,\mathbb{E}[U] + \lambda_{r}\,R_{\mathrm{unsupported}}
\]

with latency \(L_q\), full storage footprint \(D_{\mathrm{total}}\), source-update cost \(U\) and unsupported-answer risk \(R_{\mathrm{unsupported}}\). The weights and conditional demand distribution are not yet estimated. The existing compression frames are per source and do not permit free cross-source packing with independent authorization/version semantics.

### H30.2: Exact link receipts may reduce unnecessary source reads

Index-time link materialization allows a second document to be ranked before the first is fully decoded. That can reduce *online* source materializations, but not without offline link construction and maintenance. In our current integrated prototype, **all selected documents are still decoded to evaluate candidate support**, so dynamic and indexed links have identical selected-document compressed bytes when their selections match. Any future claim of reduced I/O requires a separate policy that changes which source frames are materialized and a source receipt/verification contract. Precomputed links alone do not do this.

### H30.3: Index freshness is a correctness primitive

The compressed payload, source hash and FTS/link index must refer to the same immutable version. Otherwise an index built from version \(v\) can navigate into version \(v+1\) while still returning byte-valid but semantically outdated evidence. Checking a stored SHA against another stored SHA is tautological. A real freshness guarantee requires a trusted origin/version manifest and atomic publication/snapshot pinning. The existing reader reconstructs its indexed snapshot but does not enforce contemporaneous authority or authorization. This remains an unimplemented gap.

### H30.4: Contentless indexes shift work, not eliminate it

Removing stored body text is effective for *storage*, but the FTS index still contains tokens and postings. `bm25()` scoring retains a global or per-collection statistical view that must be maintained under updates. Source snippets and semantic verification must physically read the compressed payload. This makes accurate frame cost measurement more important. It also motivates evaluating `detail=column/none`, `columnsize=0`, alternative tokenization, and external token-position tables, each with explicit loss of capabilities and update complexity. These are standard FTS5 engineering options, not theoretical novelty.

### H30.5: A witness pair is an AND constraint, not a diversity score

Evidence completeness is structurally complementary: retrieving two valid supporting sources can turn an otherwise unsupported answer into a supported one. This is why Round 24's MMR baseline underperformed and Round 25's bridge expansion helped. However the existence of a link is not a proof of relation validity. The next valid predictor should estimate the probability that *all* required support is present, calibrated on held-out questions, rather than treating each link as equal evidence. If no calibrated predictor can beat simple iterative retrieval on the same sources, discard it.

## 5. Novelty audit and related methods

- **SQLite FTS5 `content=''`:** documented contentless storage. This work is an integration and measurement, not a new index design. https://www.sqlite.org/fts5.html
- **Zstandard seekable format:** independent compressed frames and a jump table are established. https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/README.md
- **IndexRAG (Findings IJCNLP-AACL 2026):** precomputes bridge facts at index time and evaluates HotpotQA, 2WikiMultiHopQA and MuSiQue. This directly rules out pitching index-time bridge links as novel. https://aclanthology.org/2026.findings-aacl.175/
- **IRCoT (ACL 2023):** interleaved retrieval and reasoning. https://aclanthology.org/2023.acl-long.557/

**Current contribution:** a disciplined source-grounded prototype and a negative control showing that correcting an ordinary database schema can dominate a proposed complex optimization on total storage. There is **no verified novel contribution or peer-reviewed result** yet.

## 6. Reproducibility

Run local physical and integration regression tests:

```bash
cd experiments/round-30
python -m unittest -v test_integrated.py test_contentless.py
python contentless_bench.py --files report1.md report2.md report3.md report4.md report5.md --output local.json --frame-size 512
```

To rerun 100 HotpotQA-derived questions locally, obtain the exact `qa_train.json` byte sequence at the pinned upstream commit (the Round 25 downloader includes a SHA-gated retrieval command) and run:

```bash
python integrated.py --data /path/to/qa_train.json --output real_corpus_reproduction.json --layout fixed --frame-size 512
```

**Not executed:** that 100-question Python run. Do not report the authored two-question smoke fixture as a real benchmark. Python FTS5 ranks documents by their best matching *line*, unlike Round 25's custom whole-document BM25, so even a faithful execution will not necessarily reproduce Round 25's 33/46 counts.

The historical `MANIFEST.json` is not yet an up-to-date complete manifest for these new commits. The current Git tree verifies submitted blobs; source lists and hashes should be regenerated before an external artifact evaluation.

## 7. Round 31 preregistered decision points

1. **P0:** make the true 100-question raw corpus locally available and execute *all* policies through the same physical store and FTS5 scoring. Split bridge and comparison cases; track complete documents and exact annotated sentence IDs; compare query-normalized I/O bytes and p50/p95. Obtain an official held-out sample before any paper-level claim.
2. **P1:** compare external-content, contentless FTS, `detail=column/none`, BM25 and title-link expansion with indexes/updates all charged. Measure per-document metadata lookup and construction, not a fixed modeled 16-byte link cost.
3. **P2:** implement immutable snapshot publication and atomic source+FTS+link-version switching; reject mismatched version receipts at read time. Test stale links, deletion, revision, ACL changes and conflicting evidence.
4. **P3:** only then test learned uncertainty gating and physical co-layout versus an ordinary contentless SQLite + seekable-Zstd + title-link baseline. If the learned controller is dominated, omit it.

**Decision:** KEEP the stripped-down, compressed-source/contentless-index baseline. **STOP** making claims based on duplicated-source index footprints. **DEFER** CDG graph-control novelty until an independently held-out complete-evidence quality/cost result exists.
