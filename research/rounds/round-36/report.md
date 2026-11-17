# Round 36: Gaps at the Intersection of Adaptive Retrieval, Source Versioning, Verification, and Classical Optimization

**Date:** 2026-11-16. **Research status:** audited prior art plus six passing local unit tests and one seeded, synthetic screening/verification experiment. **Not an authentic RAG/LLM benchmark, statistical guarantee, or demonstrated novelty.** Round 35 remains on `research/round-35-classical-quantum-hybrids`; this new branch is based on it.

## 1. Narrowed problem

The main omission from Rounds 33–35 is that optimizing a predicted witness and compressing its source do not establish semantic support. Likewise, a perfectly reconstructed, generation-pinned citation can faithfully reproduce an irrelevant or false source. A reliable system must separately evaluate (1) source identity/version; (2) structural evidence completeness; (3) claim entailment; (4) costs of acquisition, verification and abstention. Each is independently falsifiable.

Formal state: a query requires unknown true facet set `U_q`, a candidate `s` exposes observed bytes `B_s` only when read, and a fallible prediction/verification function yields `\hat E_s`, `\hat V(q,S)`. Source generation is `g`. Decisions `a_t` adaptively read, inspect, requery or stop. Total cost is `C_index+C_storage+C_update+Σ_t(C_read(a_t)+C_decode(a_t)+C_verify(a_t))+C_generation`; track unsatisfied facets and unsupported accepted claims separately. The target is a **measured Pareto frontier** of supported-answer coverage, false acceptance, abstention, latency and physical cost, not a universal scalar objective.

## 2. Verified research connections and explicit remaining gaps

1. **AdaKG-RAG (Yuan, Wang & Qian, 2026)**: iterative hypothesis/verification and KG expansion; identifies high verifier latency and incomplete offline KGs as limitations. CDG's possible contribution is physical-cost-aware source acquisition plus generation-bound source citations. But adding source receipts does not solve semantic verifier reliability. https://link.springer.com/article/10.1007/s44443-026-01028-3
2. **AIR-RAG (Han et al., 2026)**: adaptive iterative retrieval rather than one-off retrieval. CDG must beat its actual query/refinement overhead, not just a one-shot BM25 strawman. https://doi.org/10.1016/j.neucom.2025.132272
3. **HEAR-RAG (2026)**: graph/hypergraph completeness and fine-grained connected evidence paths. CDG should not present hypergraphs as original. A possible differentiator is verifying exact byte spans against immutable source generations and accounting for activated compressed frames. https://aclanthology.org/2026.emnlp-main.2210/
4. **CiteGuard (Jiang, 2026)**: conformal false-discovery control of claim acceptance. CDG can add evidence-set sufficiency and generation consistency as separate constraints; simply appending a hash to a citation is not semantically meaningful. Guarantees require their stated calibration assumptions. https://proceedings.mlr.press/v306/jiang26f.html
5. **C-RAG (Kang et al., 2024)**: studies certified generation risks. Direct novelty claim for calibrated factuality would be invalid. https://proceedings.mlr.press/v235/kang24a.html
6. **Is Conformal Factuality for RAG-based LLMs Robust? (Chen et al., 2026)**: warns of output-vacuity and shift fragility, with lightweight entailment baselines. CDG must measure acceptance and retention together and add explicit shift tests. https://arxiv.org/abs/2603.16817
7. **Adaptive Retrieval without Self-Knowledge? (Moskvoretskii et al., ACL 2025)**: demands simple uncertainty-aware alternatives and full cost evaluation for retrieval gating. https://aclanthology.org/2025.acl-long.319/
8. **The Power of Adaptivity for Stochastic Submodular Cover (Ghuge, Gupta & Nagarajan, 2021)**: formal multiround adaptivity under conditions. CDG's correlated complementarity and shared frame activation may violate relevant assumptions; avoid transferring approximation guarantees without proof. https://proceedings.mlr.press/v139/ghuge21a.html
9. **FastCDC (Xia et al., 2016)**: strong classical chunk-boundary baseline. Improved immutable receipts and source-segment CAS remain engineering designs, not compression discoveries. https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia
10. **Information Bottleneck (Tishby, Pereira & Bialek, 1999)**: task-aware approximate indices can be optimized, but source-body exactness and important qualifiers must remain separately protected. https://mlanthology.org/misc/1999/tishby1999misc-information/

### Gap transfer matrix

| Gap in CDG | Established method to transplant | Gap in that method that CDG could address | Exact falsifier |
|---|---|---|---|
| Missing evidence under predicted facet errors | Verification-guided refinement; posterior checking | Materialization cost and immutable version-linked citations often omitted from comparisons | Simple verified iterative retrieval matches quality with less complete cost |
| Planner overhead and unknown stopping | Uncertainty gating; sequential testing | Confidence shifted under stale/contradictory source updates | Shifted false accepts exceed pre-registered bound |
| Few-shot graph links omit implicit relations | Dynamic graph expansion + text retrieval | Graph edge often lacks exact source-byte receipt | Added link path does not recover more true annotated supporting facts |
| Excessive verifier cost | Cheap entailment classifier or deterministic prefilter + selective expensive verification | Screening may reject true witnesses and bias accepted cohort | Quality-cost frontier dominated by always-verify or cheap-only |
| Citation text unchanged across generations | Immutable per-source receipts and content-addressed history | No general proof of semantic support or origin authority | Receipt accurate but claim false (construct counterexample) |
| Frame/metadata duplication under updates | CDC, delta/exception code, incremental FTS5 | No major advantage over strong classical updated baseline | Modern incremental SQLite + CDC dominates at same retained history |
| Combinatorial cover is locally trapped | Annealing-inspired proposals + bounded exact search | Known facet labels are unrealistic and optimization costs counted poorly | Verified total cost no better than local repair + expansion |
| Low-rank relevance representation may save metadata | Tensor trains/SVD/sketches | Rare witness facets can disappear under approximation | Recall for rare facets drops at matched indexed bytes |

## 3. A concrete counterexample

Let a source `A` at generation `g` accurately assert "Company Q announced plan X" while source `B` at the same generation retracts X. Perfect SHA-256 receipts for A and B do not determine which claim to output. If B is missing from a compressed or approximate retrieval index, even an exact byte-level source receipt is not a sufficient-witness proof. Conversely, an exact evidence graph containing both sources does not establish what is true without semantics, temporal precedence and authority. Hence a source receipt, a facet-coverage certificate and entailment/temporal conflict detection must remain separate.

## 4. Executed experiment: screening and imperfect verification

Code: `experiments/round-36/gated_verification.py`, six local tests in `test_gated_verification.py`, results in `results.json`. Pure Python 3 standard library, fixed seed 20261116. A deterministic pseudo-data generator creates 3000 calibration, 3000 in-distribution test and 3000 distribution-shifted cases; true correctness is hidden from decision policies, and inexpensive and expensive scores share correlated latent error. Calibration chooses the **smallest deep-verifier threshold** whose normal-approximation Wilson upper confidence bound on **observed false acceptance among selected calibration items** is <= 0.05 with >=40 accepted calibration examples. This is an engineering heuristic, **NOT a conformal, simultaneous-selection, FDR, or distribution-free guarantee**. Data shift changes difficulty mix, noisy score distribution and shared bias. Gates 0.35/0.50/0.65 are prespecified and never trained on test. Assumed screening cost 0.3, deep verification cost 10 per call.

At gate 0.50:

| Policy | In-distribution false acceptance | Shifted false acceptance | In-distribution true correct-accepted / all cases | Shifted true correct-accepted / all cases | Cost / case |
|---|---:|---:|---:|---:|---:|
| Accept all | 26.60% | 44.17% | 73.40% | 55.83% | 0 |
| Deep verifier all | 1.287% | 17.168% | 71.57% | 54.20% | 10.00 |
| Cheap screen then deep | 1.290% | 18.031% | 56.10% | 44.40% | 6.55 in-distribution; 6.75 shifted |
| Cheap screen alone | 9.653% | 30.837% | 56.47% | 44.63% | 0.30 |

The cheap screen reduces assumed deep-verifier expenditure **34.5%** in distribution, but it loses **15.47 percentage points** of total correct-answer coverage compared with verifying all, and its shifted false-acceptance fraction remains high. A true-recall-sensitive utility function can therefore prefer the expensive baseline. At gate 0.65 cost drops further (4.79) and in-distribution correct-answer coverage falls to 42.2%. **No general performance claim can follow.**

The false-acceptance rate is conditional on accepted outputs, unlike risk over all questions. Its denominator must be reported. The selected threshold was 0.50 in this seed; the apparent in-distribution calibration performance is not an honest proof of alpha-level risk. We did not model actual retrieval loops, citations, ensemble costs, token cost, or physical source frames in this experiment.

## 5. A next-step system contract (hypothesis, not implementation)

- **Frozen candidate pool** built by BM25 + simple source-title expansion (R25 strong baseline) on true source text. The expensive verifier receives source receipts and decoded exact source spans, never only compressed approximate features.
- **Staged inspection**: optional cheap NLI/signal gate on metadata, then full source acquisition, source-version check, entailment and conflicting-source comparison; if insufficient, choose next acquisition using marginal cost and predicted conditional evidence value.
- **Stopping**: bound unverified claims and prefer abstention under unresolved conflicts. If a statistical risk claim is made, calibrate the complete adaptive policy on held-out queries under the theorem's conditions, not its individual verifier scores, and explicitly validate non-exchangeable shifts.
- **Optimization**: first compare a plain fixed top-k verified retriever and a simple iterative one. Optional annealing or tensor coding only enters when it wins a time-matched baseline; every index, model, verifier, frame, metadata and abstention cost is reported.
- **Snapshots**: receipt must bind `(source_id, generation, SHA256, byte spans)` but this is *consistency*, not authority or truth; independently version indexes and graph edges, and test conflicting/updated sources.

## 6. Five testable future branches

1. **Real annotated multihop QA**: make HotpotQA-derived 100-question full source subset available *locally* with hashes, freeze evaluation before tuning and compare FTS5, title-link, verified expansion and physical frame-aware acquisition; stop if no true complete-evidence improvement at matched cost.
2. **Verifier calibration and shift**: replace simulated signals with a specified NLI model, calibrate one frozen adaptive decision rule, report accepted-claim risk and abstention; stop if drift breaks the bound or the usable answer fraction collapses.
3. **Conflict-aware version freshness**: construct document revisions, timestamp and authority collisions, evaluate citation consistency separately from factual support; stop if graph edge+version validation adds no supported-answer advantage.
4. **Compression and retrieval coupling**: cross index/update work with layout learning and CDC; stop if simple Zstandard + SQLite + delta dominates total footprint/read/write cost.
5. **Adaptive decision theory**: evaluate expected value of another verification call under calibrated posterior uncertainty; stop if ordinary two-stage heuristics are Pareto superior to a complex policy.

## 7. Adversarial conclusion

Most individual components are established: iterative verification, adaptive retrieval, source-hash receipts, content-addressed storage, and risk-controlled factuality. **The possible novelty is their measured interaction under shifting source versions and an end-to-end physical cost budget**, not any one component or an untested algorithmic theorem. Right now the strongest claim is a reproducible *negative synthetic result*: gating can reduce verification work but erase useful correct answers and fail under shift. Publication status: technical note and research plan, not validated IR/systems contribution.
