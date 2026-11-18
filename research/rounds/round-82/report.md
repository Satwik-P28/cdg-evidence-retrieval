# CDG Round 82: Source-Window Routing Versus Full-Premise NLI

**Date:** 18 November 2026. **Status:** source-only policy code, four model-free regression tests and full pretrained-model CI submitted. Four unit tests and full published-model CI run **44249079426** passed. Measured results below. No independent validation claim.

## Research question

R81 showed an ordinary NLI pretrained model accepted 10/10 supported short supervisory statements but only 1/10 after an unrelated sentence was appended and 0/10 after an opposite-direction negative statement was appended. R80 showed NLI success on toy two-hop warehouse claims. Can sentence-wise evidence selection improve support recognition at an explicit inference cost, and does it create false acceptance or break multi-hop support?

Prior work on sentence-level factual consistency includes SummaC, AlignScore, MiniCheck and NLI decomposition. This is a falsifiable workload-specific evaluation of conventional ideas, not a novel semantic model.

## Frozen evaluation contract

- R80 source-claim SHA: **8a2ed2de012491086784f7098faa4b51042fa98d7cd53eb063ec78b33e1722c7**, 120 cases: 40 supported/40 contradicted/40 unknown.
- R81 source-claim SHA: **817033b230722ea1551c209c358570d394d3f2a3be45ac7f77fb7edd8c2334c3**, 100 cases: 60 supported/20 contradicted/20 unknown.
- Every source is read back through whole and gear512 compressed SHA-bound receipts. Original identity is oracle-supplied, not retrieved.
- Same published cross-encoder/nli-deberta-v3-xsmall model, SHA **a150876415327c80daeff35ca6f68f5ed8cf5c24**, 384-token input and threshold 0.50, no training or support-label threshold selection.
- Deterministic source-only sentence splitting. No gold labels enter window selection or inference.

## Predeclared policies

| Policy | Candidate evidence | Acceptance |
| --- | --- | --- |
| Full | Complete source document | P(entail) >=0.50 |
| Lexical single | Highest claim-word-overlap source sentence | P(entail) >=0.50 |
| Best single | Each sentence individually | Max P(entail) >=0.50 |
| Best adjacent2 | All adjacent source-sentence pairs | Max P(entail) >=0.50 |
| Single or adjacent2 | Both singles and adjacent pairs | Max P(entail) >=0.50 |
| Contradiction veto | Both singles and adjacent pairs | Max entail >=0.50 AND max contradiction <0.50 |

## Promotion and rejection

- Count supported/contradicted/unknown acceptance, with per-family and per-surface confusion, full-source baseline wrong-to-correct and correct-to-wrong transitions.
- Report actual tokenizer-input token counts, model pair counts and shared CPU forward wall time, including the cost of multiple windows.
- Per-policy pair/token counts are isolated-query logical costs. Forward time is shared across policy inputs, not a measured per-policy standalone latency.
- A maximum entailment window can falsely accept contradictory sources by omitting conflicting material. The contradiction veto can reject valid support when the source has harmless reverse-direction negations. Both are falsifiable negative controls.
- Choose no post-hoc threshold on the template labels. Any observed benefit requires independent human-labeled external testing and real retrieval.

## Limits

These are 220 related synthetic cases, not 220 independent populations. No original generated response, real BM25/FTS source lookup, cold SSD, model memory accounting, source update, semantic human adjudication or end-to-end RAG gain. Published NLI and window optimization concepts predate this study. The source-ID benchmark oracle provides no evidence of deployable retrieval quality.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-82 -p 'test_*.py' -v
    python experiments/round-82/sentence_witness.py --out experiments/round-82/ci-results.json

CI workflow: .github/workflows/cdg-r82-witness-routing.yml. Numeric results to be appended from the exact-head run only.

## Executed quantitative outcomes (CI 44249079426)

**[FACT]** 220 identical R80/R81 source-claim conditions evaluated, original sample SHA contracts preserved, all compressed source readbacks exact. R82 tested 1,330 distinct case-window model pairs, 37,197 actual unpadded model-input tokens and **37.398 s** aggregate CPU forward time for the shared suite. This aggregate time is not the latency of a single policy.

| Policy | R80 BA | R81 BA | Combined TP/FP/FN/TN | Combined BA | Logical pairs | Input tokens |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| Full | 0.81250 | 0.75833 | 61 / 10 / 39 / 110 | 0.76333 | 220 | 9,194 |
| Lexical single | 0.79375 | 0.89167 | 80 / 15 / 20 / 105 | 0.83750 | 220 | 5,416 |
| Best single | 0.79375 | **0.97500** | 90 / 15 / 10 / 105 | 0.88750 | 690 | 14,636 |
| Best adjacent pair | 0.91875 | 0.89167 | 90 / 15 / 10 / 105 | 0.88750 | 470 | 14,867 |
| Single or adjacent pair | **0.91875** | 0.96250 | **100 / 16 / 0 / 104** | **0.93333** | **1,160** | **29,503** |
| Contradiction veto | 0.53750 | 0.53333 | 7 / 0 / 93 / 120 | 0.53500 | 1,160 | 29,503 |

A single sentence scores reasonably on R81 source surface changes but misses all ten supported two-hop relation forms from R80. Adjacent pairs restore the ten misses for R80, but do not fully solve R81 reverse-direction noise. Their union recognizes **every supported synthetic statement** in these two *already inspected* fixtures, at increased false acceptance and inference work.

### Paired change matrix against full-source baseline

| Policy | Full wrong to policy correct | Full correct to policy wrong | Changed binary decisions |
| --- | ---: | ---: | ---: |
| Lexical single | 29 | 15 | 44 |
| Best single | 39 | 15 | 54 |
| Best adjacent pair | 29 | 5 | 34 |
| Single or adjacent pair | **39** | **6** | 45 |
| Contradiction veto | 11 | **55** | 66 |

**[FACT]** The union's 29.503K model input tokens vs 9.194K full-source tokens represent approximately **3.21x** model token work; 1,160 vs 220 forward pairs represent **5.27x** more classified inputs. Runtime may not scale linearly with token count because batches and sequence lengths differ. There is no measured speed improvement.

**[FACT]** Contradiction veto is strongly invalidated under these circumstances, accepting only 7/100 positives; global maximum contradiction from disconnected windows is a poor rejection criterion.

**[INFERENCE]** Small evidence windows can avoid distracting sentences for some already inspected templates. The union trades extra model work and greater false acceptance for synthetic support recall. Such a policy **cannot be promoted** before prospectively frozen independent human-document tests. Increased recall alone is not a reliability breakthrough.

**Next:** SciFact human-annotated claims plus original-scientific TF-IDF retrieval and FTS5/BM25 baseline with no test-set calibration. Separate source retrieval acquisition from claim verification, and charge storage/index/model costs. The 220 synthetic cases are closely related, not representative independent examples.

Provenance: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44249079426 .
