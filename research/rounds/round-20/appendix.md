
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
