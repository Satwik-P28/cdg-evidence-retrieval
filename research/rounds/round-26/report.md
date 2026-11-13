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
