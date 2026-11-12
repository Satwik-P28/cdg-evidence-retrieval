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
