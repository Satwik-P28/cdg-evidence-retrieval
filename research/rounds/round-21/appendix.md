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
