# CDG Round 79: Human-Label-Blind Source Perturbations of a Trained Grounding Detector

**Date:** 18 November 2026. **Status:** five dedicated regression tests and pinned real pretrained-model run passed in GitHub Actions **44243476813**. Measured numerical findings and limitations follow. This is a detector **source-sensitivity diagnostic** with real fixed responses, not verified alternative-source factuality, source retrieval, compression or novel hallucination mitigation.

## Motivation and prior art

Round 75 found the generic SNLI/MultiNLI NLI cross-encoder's *minimum* claim entailment score nearly invariant to replacing original sources. But the mean over claims changed considerably. Is a task-specific RAGTruth-trained *span detector* sensitive to swapping evidence, and does it distinguish lexically similar substitutes from dissimilar ones?

Grounding-Aware Sensitivity by Perturbation (GASP, arXiv:2607.04223, July 2026) and counterfactual grounding and perturbation research predate this round. LettuceDetect (arXiv:2502.17125) is prior art, trained on the source benchmark. This experiment does not claim novelty in counterfactual sensitivity.

## Frozen cohort and intervention

- Same immutably sampled **141 quality-good RAGTruth QA/Summary responses** from 8 QA and 16 Summary source groups as R72/76.
- Existing pretrained LettuceDetect base ModernBERT, same immutable HF SHA **0ff0f0dd23052cf751dae374f57a539aa092e772**, CPU and package as R76.
- For each original source, select nearest and farthest **different** source *within the same task*. Rank full source content-word sets using source-to-source Jaccard similarity, lexicographically fixed ties. Do not inspect human annotation or generated answer during alternative selection. Thus 24 group-specific near/far assignments, shared across each group's responses.
- Keep response bytes and original QA question unchanged. Replace only evidence source context; reconstruct the same passage presentation used by R76. For Summary, no question is present.
- Run the identical trained detector three times per answer: authentic, nearest alternative, farthest alternative. Compare response-level warning-switch rate, character mask disagreement and differences in flagged character counts. Report average near/far source similarities and actual CPU inference time for each route.
- Use paired source-group bootstrap, not naïve per-response independence, to estimate the far-minus-near warning-switch difference.

## Predeclared interpretations and falsifiers

1. **Source invariance failure:** If near and far substitutes produce no change to the detector's warning, the model's binary outputs do not use these perturbations to discriminate evidence at the chosen threshold. This does not prove the detector ignores sources internally.
2. **Source-sensitivity positive:** Higher far-than-near disagreement would indicate **sensitivity**, not necessarily correct inference or trusted grounding. It may reflect superficial lexical distribution shifts. It also may not survive outside the 24-source comparison pool.
3. **No gold label for swapped source:** Original RAGTruth human hallucination annotations refer to original evidence, not the substituted passages. They must not be used to declare swapped predictions correct or incorrect. The only human-label confusion matrix reported is the untouched-source reference.
4. **Strong experiment boundaries:** The 24 sources are not a realistic full retrieval corpus; source identity is known from the benchmark. An unrelated source may coincidentally support an answer. No generated response is edited or reduced, and a changed predicted mask is not a mitigation result.
5. **No new source codec or calibrated guarantee:** This is a semantic perturbation round that complements but does not replace R78's exact archived-source integration.

## Acceptance conditions

- Five new synthetic regression tests pass, including true label-blind source ranking, fixed QA question, source-mask differentiation and deterministic source-group bootstraps.
- The full pinned 141/24 source sample and original model identity match R76.
- Every altered source is different from the original and within task, without using human labels or answer text.
- Three true pretrained CPU inference calls per answer are charged; code emits only aggregate counts/seconds and source revision digests, never raw third-party text or annotations.
- Report real results even if near/far sensitivity is 0 or the bootstrap interval crosses 0. No arbitrary redesign of alternate sources or selective reporting after seeing them.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-79 -p 'test_*.py' -v
    python experiments/round-79/trained_source_swap.py --out experiments/round-79/ci-results.json

CI workflow: .github/workflows/cdg-trained-source-swap.yml. The numerical real-model run succeeded at CI 44243476813; see below.


## Executed evidence: CI run 44243476813

**[FACT]** The five regression tests passed. Fixed R72/R76 sample identity, 24 source groups and **141 human-labeled original responses** were preserved. The exact pretrained detector and its original data SHA contracts were reused.

**[FACT] Source-set lexical separations:** nearest same-task alternatives had mean source Jaccard **0.049670** (min 0.024390, max 0.080997). Farthest had mean **0.010834** (min 0.004000, max 0.020964). Even the "nearest" alternatives were **lexically weak matches**, so the contrast cannot be interpreted as fine-grained semantic distance.

**[FACT]** Original-context pretrained detector reference confusion reproduced R76: TP14/FP16/FN17/TN94 over 141 responses. This is not accuracy after swapping evidence.

### Paired source-sensitivity results

| Task | Response count | Original predicted positive | Near source warning decision switches | Far source warning decision switches | Mean changed answer characters, near | Mean changed answer characters, far |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QA | 45 | 9 | **36/45 = 80.00%** | **36/45 = 80.00%** | 71.873% | 72.041% |
| Summary | 96 | 21 | **75/96 = 78.125%** | **75/96 = 78.125%** | 81.870% | 92.247% |
| **Combined** | **141** | **30** | **111/141 = 78.723%** | **111/141 = 78.723%** | **78.680%** | **85.799%** |

The paired far-minus-near **response warning switch-rate** is exactly zero for the evaluated sample and its source-group resamples, CI **[0,0]**, because each tested response's aggregate near/far switch indicator was equal across conditions according to the reported aggregate; however the aggregate alone does not distinguish each possible pairwise pattern. The bootstrap output is **[0,0]**. The rate equality should not be confused with proof that near/far masks are identical: their **character** disagreement from original answer differs substantially.

**[FACT] CPU inference time:** unchanged original contexts **143.518 seconds**, near-substituted contexts **211.988 seconds**, far-substituted contexts **96.549 seconds**, total **452.055 seconds** of model inference route wall time. The large difference means alternative source contexts have unequal lengths/chunking and *cannot* be treated as a matched compute-cost ablation. This round did not charge archive or source index storage.

### Research decision

**KEEP:** strong detector source perturbations alter output masks, and character-level diagnostics preserve distinctions that a binary response warning can obscure.

**REJECT:** the claim that far substitutes reliably improve warning correctness, that response-level switch rates are more discriminative for far than near, or that weak Jaccard distance measures a truth-changing counterfactual. The alternates have no new human support labels. Near/far evidence length is confounded with CPU cost.

**NEXT FALSIFIER:** construct *controlled, human-validated* minimal evidence edits that preserve, negate or remove individual facts while holding formatting, source length and model input budgets approximately fixed; evaluate both direction of predicted support and token-level errors against independent labels. Run on previously unseen source families before making transfer claims.

Run artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44243476813 .
