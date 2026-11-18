# CDG Round 81: Source-Clause Order, Reverse Negation and Supervision Directionality

**Date:** 18 November 2026. **Status:** four paired-model regression tests and pinned pretrained CPU ablation passed in GitHub Actions **44247354832**. A follow-up exact-head run includes a predeclared R80-oracle diagnostic FactCG cutoff and is separately checked. All source texts, claims and labels are synthetic fixture-defined, not independent human labels. This is a model invariance falsification test, not a new model or demonstrated RAG improvement.

## Why this experiment follows R80

R80 scored 120 synthetic supported/contradicted/unknown cases. Published MiniCheck did relatively well overall (balanced accuracy .90), but in supervisory relation **7/10 supported examples were rejected**; generic SNLI/MultiNLI NLI rejected **all 10** supported relation claims. The R80 supporting source included an affirmative supervisory statement followed by a denial of the opposite direction.

Hypothesis: some support verifiers are sensitive to **surface polarity, extra context and clause position**, even when the underlying relation remains entailed. Prior art includes MiniCheck (Tang et al., EMNLP 2024), FactCG (Lei et al., NAACL 2025), and the previously pinned LettuceDetect model. This test is not claimed as first detection of model context sensitivity.

## Fixed intervention design

10 source-group entity substitutions, **same supervision claim within each group**, ten surface variants each, 100 total inputs, with source byte SHA receipts from the R80 whole/gear compressed readers. Model weights and thresholds are identical to R80. Source ID is from the fixture, not retrieval.

- Six logically supporting conditions: (1) exact source claim, (2) active supervisor paraphrase, (3) passive supervisor paraphrase, (4) active support plus a neutral extra sentence, (5) active support followed by explicit denial of the opposite-direction relation, (6) the same two sentences in reverse order.
- Two explicit contradictions: the other entity supervises the first and the claim is denied, or direct negation of the claim.
- Two unknowns: only the reverse-direction denial without affirmative support, or an unrelated organization chart statement with the supervision relation unspecified.

**Crucial contract:** Denying \`B supervises A\` does not prove or disprove \`A supervises B\`. Therefore a document that ONLY denies the reverse direction is **unknown**, while a document that also explicitly affirms \`A supervises B\` is supported, regardless of sentence order.

All published checkpoints are exactly as R80. MiniCheck and FactCG are independently reproduced for one short source chunk with official input formats. NLI and LettuceDetect reuse R72/R76 checkpoint paths. All base cutoffs 0.50. R80's post-hoc FactCG label-oracle cutoff **0.10503259** is separately frozen as a nondeployable exploratory transfer check; R81 labels do not enter its selection, but entity names and templates overlap R80.

## Initial measured acceptance counts

The six logically **supported** conditions below are each evaluated on all ten entity groups, with no change to claim text:

| Supporting context surface | MiniCheck | General NLI | FactCG | LettuceDetect |
| --- | ---: | ---: | ---: | ---: |
| Exact \`A supervises B\` | 10/10 | 10/10 | **0/10** | 7/10 |
| Active source \`A is supervisor of B\` | 10/10 | 10/10 | 9/10 | 5/10 |
| Passive source \`B is supervised by A\` | 10/10 | 10/10 | 6/10 | 3/10 |
| Active + unrelated neutral sentence | 10/10 | **1/10** | 10/10 | 7/10 |
| Active + reversed-direction denial **after** | 10/10 | **0/10** | **0/10** | 9/10 |
| Reversed-direction denial **before** + active | 10/10 | **0/10** | **9/10** | 4/10 |

**[FACT]** MiniCheck accepted all 60 supported context variants. It still incorrectly accepted 3/10 of the **reverse-supervision** contradiction sources, so this is not error-free counterfactual verification.

**[FACT]** NLI's 10->1 drop from the active statement to active-plus-neutral context means a **second unrelated sentence alone** strongly changed its support predictions. This prevents assigning all of the 10->0 reversed-negative failure to negation logic.

**[FACT]** FactCG's 0/10 versus 9/10 under **reordering the same two sentences** provides a direct source-order sensitivity demonstration at threshold 0.50 for these ten fictional claims. The model may represent soft class scores differently, and this does not prove internal logical reasoning failed as a unique cause.

**[FACT]** LettuceDetect gave mixed 3-9/10 support acceptance across syntactic variants and accepted two contradictory reverse-supervision and two unrelated unknown statements. Span detection on a claim used as an answer, with no question field, is not necessarily its trained task.

### Synthetic contradiction/unknown controls

| Unsupportive context | MiniCheck accepted | NLI accepted | FactCG accepted | LettuceDetect accepted |
| --- | ---: | ---: | ---: | ---: |
| Explicit reverse supervisor + denial of claimed direction | **3/10** | 0 | 0 | **2/10** |
| Direct denial of claimed direction | 0 | 0 | 0 | 0 |
| Reverse-direction denial *only*, target direction unspecified | 0 | 0 | 0 | 0 |
| Unrelated records, supervisory link unspecified | 0 | 0 | 0 | **2/10** |

The lexical baseline accepted **all 100** variants and is not a semantic grounder. Its apparent sensitivity is zero.

### Model cost on initial R81 run

NLI: **2.140 s** CPU, 3,553 actual model-input tokens. MiniCheck: **20.858 s** CPU, 3,553 tokens. LettuceDetect: **8.366 s** CPU for the 100 predictions; direct input-token counts are not comparable to the other models. FactCG: **26.690 s** CPU, 6,203 input tokens because the official instruction format is longer. Models were run sequentially, without matching parameter count, training or input budgets.

## Implications and follow-ups

**Keep:** invariance tests using semantically equivalent statement order, reverse-direction negation and neutral sentence additions, split by the actual labeled target proposition. Such tests can uncover pitfalls hidden by aggregate RAGTruth F1.

**Reject:** treating a single fixed entailment probability as a guarantee of compositional truth; treating a second sentence as harmless in all models; claiming a detector ensemble eliminates errors at no cost.

**Open:** Is FactCG's source-order effect merely a shift across its 0.5 decision boundary or a genuine inversion of soft support ranks? The R80-fitted 0.10503259 threshold is a *diagnostic*, not a valid final model. The separate prospective R81 surface check is necessary; its success would still not imply out-of-domain transfer.

**No semantic improvement has been implemented:** This round isolates pre-existing model behaviors. Any new routing, atomic-claim decomposition or source-order-invariant method must be evaluated on an independent labeled benchmark, with group uncertainty and full reader/model costs.

### Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-81 -p 'test_*.py' -v
    python experiments/round-81/relation_ablation.py --out experiments/round-81/ci-results.json

Workflow: \`.github/workflows/cdg-r81-directionality.yml\`. Initial validated run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44247354832 .
