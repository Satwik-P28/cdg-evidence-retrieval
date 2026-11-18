# Round 75: Counterfactual Evidence-Source Substitution Reveals Weak Whole-Response NLI Source Sensitivity

**Date:** 2026-11-17. **Status:** actual model run and four regression tests completed successfully, GitHub Actions **44238131728**, all 11 exact-head compatibility workflows green. Code merged in PR #16.

## Question and controlled source-swap intervention

Round 74 found generic NLI largely rejects structured Data2txt answers under a fixed non-entailment threshold. Could this be because the pretrained verifier has poor *response-conditioned source sensitivity*, rather than the answers truly being universally unsupported?

Freeze the model, response strings, R74 original SHA-selected **16** Data2txt source groups and **96** quality-good generated RAGTruth responses. For each original Data2txt source ID, select the **most lexically similar distinct Data2txt source**, using Jaccard similarity of words extracted recursively from original JSON leaf values. Ties resolve deterministically. This is a deliberately hard negative *source identity*, but the replacement evidence is **not human-labeled and may still support generic claims**.

Evaluate the same generated response unchanged on (a) its actual original structured source and (b) the closest alternative's original structured source, with the exact immutable R72 **cross-encoder/nli-deberta-v3-xsmall** pretrained NLI model and lexical source-window selection. No annotation or human label enters the substitute choice or model inference. Human label strata are used only for post-hoc descriptive analysis.

A response's NLI entailment confidence is aggregated in two distinct ways:
- **Minimum over its claim-like sentence fragments** of each fragment's best top-three lexical source-window entailment confidence, i.e. the weakest claim dominates.
- **Mean over its claim-like sentence fragments**, potentially revealing source sensitivity masked by a single low score.

The distinction matters for false-alarm behavior and selective rejection. This is not a multi-hop semantic correctness proof or a general causal inference result.

## Real paired results

- **Source groups:** 16; matched original/substitute source overlap mean leaf-value Jaccard **0.19348**.
- **Responses:** 96, 61 with original human-annotated unsupported spans and 35 with none.
- **Frozen NLI model pairs evaluated:** **5,527**, **1,495,269** model-input tokens, **1,609.643 seconds** cumulative CPU forward inference (shared across both source conditions).
- All 96 original answers, source IDs and annotation labels remained identical; only the substituted source evidence changed.

| Measure, original source minus swapped source | All 96 | Human clean 35 | Human unsupported 61 |
| --- | ---: | ---: | ---: |
| Response preference: original source | 54/96 | 20/35 | 34/61 |
| Response preference: swapped source | 42/96 | 15/35 | 27/61 |
| Mean difference in response weakest-claim entailment | **+0.00023** | -0.00073 | +0.00078 |
| Mean difference in per-claim average entailment | **+0.12649** | +0.11878 | +0.13092 |
| Mean original weakest-claim entailment | 0.00796 | 0.00704 | 0.00849 |
| Mean swapped weakest-claim entailment | 0.00774 | 0.00777 | 0.00772 |

The paired source-group bootstrap 95% percentile interval for the all-96 **weakest-claim score difference** was **[-0.00589, +0.00629]**, encompassing zero. Human-clean stratum [-0.00653, +0.00485], human-unsupported [-0.00597, +0.00746], also include zero. So we do not establish a meaningful positive shift in worst-claim confidence.

The larger **+0.12649 average-per-claim score shift** indicates the model may assign better aggregate entailment to some actual evidence, but the bottleneck remains the minimum across claims. We did not predefine or test a calibrated response acceptance rule based on the mean, so **do not convert that shift into a claimed detector gain**.

## Interpretation and limits

This is a **falsification-oriented source sensitivity diagnostic**. It challenges the assumption that a low minimum NLI entailment score proves the answer is unsupported: a difficult or unrecognized sentence can cause both real and substituted evidence to be scored near zero. Source-swap models can still rate the actual evidence differently at the individual-claim level.

Critical limits:
- The substitute source is lexically similar and distinct, **not an independently verified false evidence source**. Some generic output statements may remain supported under both.
- Actual source is not assured to entail every part of generated answer, since **61/96 original responses have human-labeled unsupported content**. Source preference is not ground-truth model accuracy.
- A 16-group within-dataset sample is small; the model and source serialization are specific to Data2txt. RAGTruth QA and Summary are not tested in this same source swap.
- R72's sentence segmentation and source lexical retrieval can omit relevant atomic facts; no semantic claim decomposition, temporal source authority, independent counterfactual labels or citation causality.
- Model CPU forward time excludes actual cold SSD I/O and optional source FTS/archives, separately studied in R73.
- None of the response strings were generated, modified or corrected by CDG.

**Decision:** Reject a claim that the current *minimum per claim NLI score* is a reliable source-faithfulness verifier or calibrated selective warning signal. Keep the counterfactual-source test as a structural falsifier and investigate input-aware atomic-claim verification, model uncertainty and stronger trained priors under human-label and total-cost controls.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-75 -p 'test_*.py' -v
    python experiments/round-75/source_swap.py --out experiments/round-75/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44238131728 . Original RAGTruth source/response text is never redistributed.
