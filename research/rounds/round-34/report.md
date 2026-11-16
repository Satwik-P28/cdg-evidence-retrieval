# Round 34: Verification Before Aggressive Optimization

**Date:** 16 November 2026. **Status:** Literature-connected hypotheses and executed synthetic optimization experiments. **No authentic held-out RAG benchmark, trained evidence predictor, semantic entailment model, or demonstrated production speedup.** This follows the verified Round 33 repository investigation.

## Executive decision

The prior focus on improving exact/approximate combinatorial evidence optimization was incomplete. **The quality of the inferred witness relation matters more than the quality of its optimizer.** A sophisticated planner can have lower *predicted* source acquisition cost while worsening *true* complete-evidence recovery if its evidence labels are unreliable. Our controlled synthetic experiment quantifies this failure. The next technical milestone must improve, validate, and calibrate evidence-facet predictions. Prefer small, transparent, verified acquisition policies over a more elaborate neural graph controller unless an independently authored evaluation demonstrates a gain.

## Survey: graph of ideas and novelty collisions

The graph links **problem -> literature insight -> CDG transfer -> failure criterion**. All publications below are independent prior art, not experiments reproduced by CDG.

1. **Multihop proof structure -> HEAR-RAG (EMNLP 2026), HyperPathsRAG (Findings EMNLP 2026) ->** preserve n-ary evidence, bridge mentions, and document identity. **Collision:** a hypergraph index and multihop path retrieval are already studied; CDG's novelty must not be described as inventing either. https://aclanthology.org/2026.emnlp-main.2210/ ; https://aclanthology.org/2026.findings-emnlp.1530/
2. **Physical source acquisition as a priced action -> When Knowledge Is Not Free (Findings EMNLP 2026) ->** include paywalled access, source-materialization, frame activation, decoder CPU, metadata reads and prompt tokens in one budget; learn when to stop. **Collision:** budget-aware evidence acquisition is established. https://aclanthology.org/2026.findings-emnlp.413/
3. **Correctness calibration versus efficient stopping -> CiteGuard (ICML 2026) ->** separate source presence, relation validity, and accepted answer; calibrate unsupported-claim risk with true labels from held-out examples. **Caveat:** exchangeability and calibrated semantic scores are required for stated guarantees. Hash receipts are not semantic entailment. https://proceedings.mlr.press/v306/jiang26f.html
4. **Coverage planning with uncertain outcomes -> Minimum Cost Adaptive Submodular Cover (Mathematics of Operations Research, 2026) ->** consider sequential source acquisition with uncertain facet coverage. **Important mathematical warning:** a standard approximation bound cannot be invoked for arbitrary correlated semantic errors, AND-dependent evidence witnesses, and overlapping frame activation costs without verifying theorem assumptions. https://pubsonline.informs.org/doi/10.1287/moor.2024.0548
5. **Physical access -> Selective Late Materialization (PVLDB 2025) ->** index document/facet/link metadata first, postpone decoding source bytes until an action is justified. **Collision:** late materialization and storage-aware query plans are established database techniques; the policy must beat them as a baseline. https://www.vldb.org/pvldb/vol18/p4616-liu.pdf
6. **Representation fidelity -> FaviComp (Findings EMNLP 2025) ->** test whether compressed *prompt* evidence preserves answer-critical facts. **Separation:** lossy prompt compression has a different objective from the lossless Zstandard frame store. A model-friendly summary is not a citable source receipt. https://aclanthology.org/2025.findings-emnlp.878/
7. **Corrupted evidence forecast -> When Should Active RAG Retrieve? (arXiv 2026) ->** report calibration of the action policy, realized retrieval budget, harm rates, threshold transfer and all controller overhead; no claimed gains from uncharged gating. https://arxiv.org/abs/2607.24010
8. **Evidence-centric evaluation -> The Bottleneck Is Retrieval, Not Reading (Findings EMNLP 2026) ->** use answer-plus-evidence and line-citation metrics, and include metadata lost during chunking. **Collision:** complete evidence retrieval and source identity are recognized challenges. https://aclanthology.org/2026.findings-emnlp.2222/
9. **Partial version updates -> online submodular recourse and copy-on-write storage ->** account for how often source changes force index/frame relocation and whether citation receipts survive. **Collision:** versioning/CAS is standard, so evaluate against incremental SQLite, Git-like deduplication and direct source-file baselines. https://research.google/pubs/the-cost-of-consistency-submodular-maximization-with-constant-recourse/
10. **Arithmetic / Millennium Problems ->** known NP-hardness of covering/grammar compression motivates approximate and parameterized search; the Riemann Hypothesis has no demonstrated direct utility in CDG's natural-language frame layout. The Round 33 prime-boundary negative control remains decisive for that narrow hypothesis. No argument about the unsolved conjectures is implied.

### Structural distinction to retain

Let `U` be a set of required facets, `C_i` an **inferred** subset that a candidate span *might* support, `T_i` its token exposure, and `F_i` its compressed frames. A planner minimizes

```
C(S) = sum(frame_cost[f] for f in union(F_i, i in S)) + lambda * sum(T_i for i in S)
```

subject to `union(C_i, i in S) = U`. But that equality covers only **predicted facets**. If actual, verified facets `V_i` differ, the planner may stop without a complete witness. The correct stop condition requires `union(V_i, i read) = U`, or calibrated refusal/abstention when support remains incomplete. Under open-world claims, even an oracle facet list `U` may be unavailable, and this formalization must be replaced by a task-conditioned proof/answer verifier. A version-bound source hash certifies byte identity relative to a snapshot, **not** truth, authorization or entailment.

## Reproducible experiment

`experiments/round-34/planner_lab.py` imports the Round 33 `selection_lab` fixture generator. Exactly 300 deterministic small synthetic problems (100 each independent-frame, shared-frame, clustered bridge) have 11 candidate spans, seven required facets, six frame resources and known artificial facets. Compare four methods: marginal-cost greedy, greedily remove redundant choices, cost-reducing local swaps of up to two selected and two unselected candidates, and exhaustive optimum. Repair is a deterministic bounded local search, **not** a theoretical approximation guarantee; computation and predicate evaluations are charged separately from physical costs.

| Planner | Mean selection cost / exact optimum | Exactly optimal out of 300 | Worst ratio |
| --- | ---: | ---: | ---: |
| Greedy | 1.07921 | 143 | 2.36082 |
| Greedy + deletion | 1.06231 | 180 | 2.36082 |
| Bounded two-out/two-in local repair | **1.00325** | **292** | 1.26943 |
| Exhaustive exact | 1.00000 | 300 | 1.00000 |

This is conditional on knowing all evidence-facet labels perfectly, a highly favorable and unrealistic assumption for RAG.

### Uncertain facet prediction: the reversal

Independently flip each candidate/facet relationship with probability `epsilon` to simulate a faulty predictor, leaving actual facets unchanged and unavailable to greedy/local repair. The selected candidates' actual coverage is used only in evaluation.

| Flip rate | Greedy: truly complete | Local repair: truly complete | Idealized observed acquisition: complete |
| --- | ---: | ---: | ---: |
| 0% | 300/300 | 300/300 | 300/300 |
| 5% | 209/300 | 199/300 | 300/300 |
| 15% | 114/300 | 99/300 | 300/300 |
| 30% | 51/300 | 36/300 | 300/300 |

`coverage_missing` indicates a predicted infeasible instance; the non-verifying policies cannot claim success in those cases. For the idealized sequential verification control, **actual facets are revealed only after a source is selected and read**; unselected sources are not queried. It can sequentially acquire more sources until the target facets are observed, including all candidates if necessary. This uses an **assumed-perfect post-read facet verifier and known complete facet inventory**, neither of which exists in CDG, and is only an upper-opportunity diagnostic, not a deployable success result. Its mean cost rises from 54.987 at 0% noise to 71.957 at 30%, with mean acquired candidates rising from 2.983 to 4.693. This demonstrates the trade-off between abstention/verification safety and acquisition cost. A real verifier will have false positives, false negatives, uncertainty and latency.

The non-verifying local search can reduce modeled cost by dropping spans that actually support needed facets. That is why maximizing planner quality against noisy proxy labels is an unsafe standalone objective.

## Research roadmap: only two candidate contributions survive

### Direction A: Verified physical evidence acquisition

1. Retrieve an initial source using ordinary BM25/FTS5 or a hybrid index. Preserve source-title/identity metadata.
2. Delay physical source-frame decoding until a bridge candidate's expected acquisition value exceeds all metadata and read costs. Baselines: always read whole source; read top two or three sentences; deterministic 2-hop title lookup.
3. Attach generation-bound raw-byte span receipts and invoke a **separately validated** relation/sufficiency verifier, not just lexical co-occurrence.
4. On incomplete or conflicting evidence, acquire another source within an explicit budget, otherwise abstain.
5. Report correct answer **and** complete annotated evidence, unsupported acceptance rate, abstention, compressed bytes, archive+index storage, per-query CPU and p50/p95 latency, plus source-update costs.

### Direction B: Lightweight plan repair under uncertainty

1. First show the 2-swap search beats deletion and greedy **after counting planner CPU**, on actual query-local candidate pools.
2. Represent candidate support as calibrated probabilities rather than fixed facet booleans, including unknown relations and contradictory sources.
3. Search with robust penalties or a conservative lower confidence bound, but do not borrow submodular or conformal guarantees without checking assumptions.
4. Reject this direction if a simple verified expand-on-failure policy matches its quality/cost frontier.

## Priorities, explicit kill conditions

- **P0:** Get the official full-context HotpotQA/MuSiQue subset into an executable end-to-end harness and verify its source hashes. The earlier real-text result is only a connected-resource analysis. Freeze train/validation/test partitions.
- **P0:** Implement inexpensive semantic-facet detection or entailment verification; test source scope, quotation, negation, stale version and deliberate contradiction. With a weak verifier, abstain rather than claiming completeness.
- **P1:** Add selective late materialization to the Round 30/32 physical store. Compare with straightforward FTS5 and title-index baselines, including index/sidecar costs.
- **P1:** Test non-oracle estimates, margin calibration and dataset shift. Performance at 15% synthetic edge corruption is not a substitute for real relation-extractor validation.
- **P2:** Compare with mature prior art on hypergraph retrieval, adaptive RAG, and accepted citation risk. Conduct ablation on source receipt, indexed bridge lookup, local repair, and late decoding separately.
- **Kill:** If verification failure dominates, optimizing source-frame selection is premature. If local repair provides no benefit after CPU overhead or is less robust than simple expansion, discard it. If a standard database/store meets physical cost at equal quality, retain the standard engine rather than adding custom complexity.

## Reproduction

```bash
python experiments/round-34/planner_lab.py --out experiments/round-34/results_reproduced.json --repetitions 100
python -m unittest discover -s experiments/round-34 -p 'test_*.py' -v
```

The implementation imports `selection_lab.py` from Round 33. Six local tests passed on 16 November 2026. These tests check reproducibility, exact solution bounds, no-regression repair, corruption handling and the idealized observation policy. `results.json` is the original local run. Do not imply a clean-room second-machine reproduction or semantic RAG evaluation.
