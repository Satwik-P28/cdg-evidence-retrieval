# CDG Round 80: Pretrained Working Verifiers Under Controlled Fact Edits

**Date:** November 18, 2026. **Status:** five synthetic regression tests and the full pinned MiniCheck/NLI/Lettuce model experiment passed in GitHub Actions **44246390689**; three additional FactCG replication tests and published checkpoint run passed at **44246781207**. A further FactCG calibration/input diagnostic is running separately. These are synthetic mechanisms tests. This is a controlled synthetic stress test, **not independent human ground truth, an end-to-end RAG evaluation, or a novel detector**.

## Research question and motivation

R72 general SNLI/MultiNLI NLI rejected nearly all human-negative RAGTruth outputs at the fixed 0.50 entailment threshold. R75 response minimum entailment was nearly invariant to a source swap, while R79 trained LettuceDetect changed many response warnings on unrelated evidence but had **no independent truth labels for swapped sources**.

R80 addresses the missing counterfactual support-oracle boundary. For each frozen claim, create three explicitly different source worlds: a supporting source, a direct contradictory source, and a source that omits the necessary information. This makes model behavior interpretable by a deterministic template contract, while remaining distinctly weaker than **human-labeled natural-language factuality**.

## Precedent and what is actually reproduced

- **MiniCheck** (Tang, Laban & Durrett, EMNLP 2024, https://aclanthology.org/2024.emnlp-main.499/): published training uses 21K ANLI + 14K structured synthetic examples for a DeBERTa-v3-Large binary document-claim classifier. Authors' released model **lytang/MiniCheck-DeBERTa-v3-Large** is pinned to immutable HF Git revision **05782341a53df45bf7bee868863563907e083ee0**, MIT model-card license. This experiment independently reproduces the authors' **single-document-chunk** forward: tokenize \`document + tokenizer.eos_token + claim\`, maximum 2,048 tokens, softmax class index 1 >0.50. It does not call their official Python package or reproduce their original 11-dataset benchmark.
- **LettuceDetect** (Kovács and Recski, arXiv:2502.17125, https://arxiv.org/abs/2502.17125): exact earlier R76 published ModernBERT base, SHA **0ff0f0dd23052cf751dae374f57a539aa092e772**, trained on RAGTruth. Predictions on the synthetic **claim as answer** are supported iff no unsupported character span is flagged, an intentionally different task framing than RAGTruth QA.
- **General SNLI/MultiNLI DeBERTa** (R72) is a weaker but fixed open-weight semantic control, with 384-token model input and entailment >=0.50.
- **R69 lexical content overlap** (no model) is a deliberately cheap, nonsemantic control.
- Predeclared boolean ensembles **MiniCheck AND NLI, MiniCheck AND Lettuce, MiniCheck OR NLI** test whether complementary errors trade support recall for unsupported acceptance. All component model inference costs must be charged; ensembles claim no compute savings.
- **FactCG** (Lei et al., NAACL 2025, https://aclanthology.org/2025.naacl-long.258/) specifically extends MiniCheck-like training with graph-based connected claims; it is a priority subsequent reproduction. Do not claim it has already been evaluated in R80.

## Locked fixture and interpretation contract

Ten fictional name groups, four families (operating location, first-service year, supervisory role, two-hop designated warehouse) and three states (supported, directly contradicted, unknown): **120** deterministic document-claim evaluations, **40 positives and 80 negatives**. Every matched triplet shares **identical claim text** and varies only the evidence context. The identity, template and label are SHA-256 fingerprinted.

- Supported labels derive from the fixture's explicit affirmative source.
- Contradicted labels derive from explicit contrary or negated source statements.
- Unknown means the source explicitly does not specify the targeted fact, even when it mentions the same entity, city or year.
- The source text remains in the original task context and does not consult gold labels during scoring.
- Fixed \`0.50\` published-model decision thresholds, no tuning on fixture outcomes. The 10 entity groups are *related template copies*, not 120 independent data points.
- Every source is reconstructed through whole-Zlib6 and gear512 CAS SHA-bound receipts, byte-checked, and both paths must agree. Source identity is **oracle supplied**, so the test does not measure retrieval success.

## Registered output measures

For each method: confusion TP/FP/FN/TN for **supported** as the positive class; balanced accuracy, support recall, unsupported rejection, precision/F1, and **separate** scores for contradicted and unknown evidence. Report family-specific results so that success on direct facts cannot conceal two-hop failure. Count **fully correct matched triplets** out of 40 and source length distribution.

Charge each pretrained model's actual tokenizer input tokens, CPU inference time, parameter count and frozen weight SHA. Archive retained bytes and logical compressed-byte activation are reported separately from inference; no cold SSD timing or production-size index exists. Never combine an ensemble's achieved score with only one model's cost.

## Falsifiers and promotion rules

1. If MiniCheck does not outperform generic NLI on this controlled benchmark, **reject the assumption** that prior training improves this specific intervention setting. Original paper performance is on different held-out datasets.
2. If a method accepts the contradicted or unknown evidence, report false-accept rates separately. A high aggregate F1 can hide high unknown-source acceptance.
3. If two-hop performance lags direct location/date/role, test FactCG's graph-connected training and explicit support-chain extraction next. This is an untested hypothesis until independently reproduced.
4. If an AND ensemble reduces false accepts but disproportionately rejects supported claims, do not call it better without a specified risk/coverage utility or constrained operating point.
5. If archive bytes reconstruct perfectly but models still fail, do not attribute semantic errors to compression.
6. **External validity is intentionally limited:** fictional templated sentences, short sources, explicit statement forms, no human counterfactual annotation or out-of-distribution benchmark; no efficiency-quality advantage over strong conventional RAG is established.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-80 -p 'test_*.py' -v
    python experiments/round-80/controlled_facts.py --out experiments/round-80/ci-results.json

Workflow: \`.github/workflows/cdg-r80-controlled-checkers.yml\`; CI stores only compact aggregate measurements and hashes.


## Completed measured evidence: initial 120-case model reproduction

**[FACT] Exact source identity:** 120 deterministic documents in 40 supported/contradicted/unknown trios, fixture SHA-256 \`8a2ed2de012491086784f7098faa4b51042fa98d7cd53eb063ec78b33e1722c7\`. Whole/gear archive receipts passed 240/240 and reconstructed identical bytes. For these short, mostly unrelated source records, **both layout payloads + manifests were 21,303 B**, against 23,370 UTF-8 bytes. Per-response logical compressed activation was 140.75 B for both layouts. These measurements do not reproduce prior R78 long-document storage differences, which is expected from different workloads.

### Comparative supported-versus-unsupported confusion

| Method (fixed threshold, no tuning) | TP | FP | FN | TN | Balanced accuracy | Support recall | Unsupported rejection |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniCheck-DeBERTa-v3-Large | **33** | 2 | 7 | 78 | **.9000** | .8250 | .9750 |
| Generic R72 SNLI/MultiNLI NLI | 30 | 10 | 10 | 70 | .8125 | .7500 | .8750 |
| Published LettuceDetect | 27 | 5 | 13 | 75 | .80625 | .6750 | .9375 |
| MiniCheck AND NLI | 30 | 2 | 10 | 78 | .8625 | .7500 | .9750 |
| MiniCheck AND LettuceDetect | 21 | **0** | 19 | **80** | .7625 | .5250 | 1.0000 |
| MiniCheck OR NLI | 33 | 10 | 7 | 70 | .8500 | .8250 | .8750 |
| Lexical R69 content overlap | 40 | 80 | 0 | 0 | .5000 | 1.0000 | .0000 |
| FactCG-DeBERTa (preliminary 0.50 threshold) | 0 | 0 | 40 | 80 | .5000 | .0000 | 1.0000 |

**[FACT] MiniCheck had no accepted explicit-contradiction cases (0/40), but incorrectly accepted 2/40 unknown evidence cases.** NLI also accepted no contradictions but incorrectly accepted 10/40 unknown cases. LettuceDetect incorrectly accepted 5/40 explicit contradictions but 0/40 unknown cases. Thus the three models are not interchangeable: unknown-evidence rejection, contradicted-evidence rejection and supported-evidence recall differ.

**[FACT] Cost of the individual pretrained model forward passes on this fixed 120-pair CPU run:**
- Generic NLI, 70,831,107 parameters: 5,641 tokenizer input tokens, **3.789 s**.
- MiniCheck, 435,063,810 parameters: 5,641 tokenizer input tokens, **39.970 s**.
- LettuceDetect, 149,606,402 parameters: **16.012 s** direct detector forward calls. Its encoder/tokenizer accounting is not directly equivalent to the two classification forward token counts.
- FactCG, 435,063,810 parameters: 8,791 actual prompt input tokens and **52.258 s** in its first full 120-case run (prior to separate smoke diagnostics).

The different prompt, architecture and token context budgets make these descriptive wall times, not a controlled hardware- and input-normalized architecture ranking. A boolean ensemble charges every component model.

### Failure localization by source-fact family

| Method | Location BA | Date BA | Supervisory relation BA | Two-hop warehouse BA |
| --- | ---: | ---: | ---: | ---: |
| MiniCheck | **1.00** | **.95** | .65 | **1.00** |
| NLI | **1.00** | .75 | **.50** | **1.00** |
| LettuceDetect | .95 | **.55** | **.85** | .875 |
| FactCG at 0.50 (first run) | .50 | .50 | .50 | .50 |

**[INFERENCE]** The original relation fixture includes a correct supervisory statement and a denial of the *opposite* supervision direction. MiniCheck missed 7/10 of these supported claims and generic NLI missed all 10, despite better performance on location and trivial two-hop statements. This suggests a potential directionality-plus-negation surface confound, **not demonstrated semantic incapacity**. A separate source-surface ablation is necessary before deciding which mechanism caused the failures.

**[INFERENCE]** Strict MiniCheck AND Lettuce eliminated false acceptance of these 80 negative fixtures, but its support recall fell to 21/40. It is not generally a better model and does not make free gains: both models must run.

### FactCG reproduction caution

**[FACT]** The published \`yaxili96/FactCG-DeBERTa-v3-Large\` checkpoint, SHA \`7582b255f0b45a1be2db6fff5076d0e8ea7aa072\`, returned unsupported for all 120 cases at the authors' fixed 0.50 threshold when supplied the exact original source/claim instruction format in an independent short one-chunk forward implementation. This is **a negative reproduction result on this fixture**, not evidence that the model fails its original benchmark. An additional no-retuning smoke evaluation and real-valued support-probability audit will distinguish input/model misconfiguration from calibration collapse; conclusions about why must remain open until those diagnostics complete.

### Next required experiments

1. **Round 81:** hold the supervisory claim fixed and ablate active/passive phrasing, reversed negation, neutral extra sentences and clause order, comparing the same four published checkpoints.
2. **MiniCheck and FactCG external validity:** use a frozen, independently human-annotated benchmark partition with actual documents (e.g. LLM-AggreFact), without tuning thresholds on test labels, and distinct source-group cohorts.
3. **True multi-hop:** the two-hop warehouse templates proved relatively easy to MiniCheck and generic NLI; a longer bridge-with-distractors dataset plus independently judged support chains is needed to test graph-training benefits.
4. **Costed retrieval:** source identity was supplied by the fixture; retrieval/FTS/dense models and SSD traffic are still unmeasured.

Initial action runs:
- MiniCheck/NLI/Lettuce + archive, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44246390689
- First FactCG author-template reproduction, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44246781207


## Follow-up FactCG audit: ranking works even though default cutoff fails

**[FACT] CI 44247296287 succeeded.** The same immutable 120-case SHA and released FactCG HF SHA were preserved. Added six no-training smoke cases and stored only small synthetic diagnostic probabilities, not model weights or third-party raw data. The checkpoint correctly classified common exact-supported and contradicted geography, plus the two official-style MiniCheck example propositions:

| Diagnostic claim | Expected | FactCG P(supported) |
| --- | --- | ---: |
| London is in the United Kingdom (exact supported) | 1 | .861068 |
| London is in France, contrary to source | 0 | .021002 |
| Students are preparing for an examination (source: studying for finals) | 1 | .935020 |
| Students are on vacation (source: studying for finals) | 0 | .010399 |
| Fictional Aster Initiative operating center, source says exactly Lydon | 1 | **.473906** |
| Fictional Aster operating center, source says Merton not Lydon | 0 | .021568 |

Thus an obvious smoke-test-supported statement from the invented registry falls just below the 0.50 cutoff while ordinary common-knowledge-style examples pass. This suggests threshold/domain sensitivity, **not broken model loading or reversed class IDs**.

**[FACT] Frozen 120-case probability ranking metrics:**

| Source relation | Mean P(supported) | Range |
| --- | ---: | ---: |
| Supported, 40 | **0.318728** | 0.054164 to 0.461957 |
| Explicitly contradicted, 40 | 0.035124 | 0.016622 to 0.079159 |
| Unknown, 40 | 0.048607 | 0.009649 to 0.112831 |

The ROC AUC over the 40 positive vs 80 negative *same fixture* was **0.975625**, demonstrating strong ranking separation despite **0/40** support acceptance at the published 0.50 cutoff.

**[CRITICAL LEAKAGE WARNING]** A threshold **0.10503259**, chosen by optimizing balanced accuracy on all 120 known fixture labels, would produce apparent in-sample balanced accuracy **0.93125**. This figure is **invalid as held-out accuracy, a fair model score or deployment calibration**. It is reported solely to falsify the proposition that all FactCG scores are uninformative. A separate R81 ablation will freeze this diagnostic threshold *without fitting it to R81 labels*, though R81 uses related entity names and is only a weak surface-transfer check.

**[INFERENCE]** The strong score separation and unusually low absolute probabilities suggest calibration/wording shift, not necessarily failed graph reasoning. We cannot infer whether model architecture, training, token length or artificial names caused the lower probabilities without matched targeted interventions. A fresh, independently labeled benchmark and train/calibration/test separation remain required before declaring a generalizable working configuration.

Audit: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44247296287 .
