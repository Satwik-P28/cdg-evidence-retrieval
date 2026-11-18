# CDG Round 82: Source-Window Routing Versus Full-Premise NLI

**Date:** 18 November 2026. **Status:** source-only policy code, four model-free regression tests and full pretrained-model CI submitted. Model outcomes pending exact-head run success.

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
