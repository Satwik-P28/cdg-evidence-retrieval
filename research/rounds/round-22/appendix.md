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
