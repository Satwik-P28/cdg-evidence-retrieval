# Round 77: Original RAGTruth Prompts Versus Reconstructed Passage Inputs

**Date:** 2026-11-17. **Status:** original-prompt and constructed-context evaluations completed under GitHub Actions **44239778792**, with four dedicated regression tests and all preceding research suites green. A within-response preprocessing ablation on published, pretrained LettuceDetect, not a new model, claim verifier or generalization trial.

## Hypothesis and frozen setup

Round 76 applied the RAGTruth-trained LettuceDetect ModernBERT encoder to a locally reconstructed source passage list and obtained moderate human-label sensitivity. Was the local input format a substantial source of evaluation disagreement?

Freeze everything: identical immutable model snapshot **KRLabsOrg/lettucedect-base-modernbert-en-v1 SHA 0ff0f0dd23052cf751dae374f57a539aa092e772**, same **141** quality-good RAGTruth QA + Summary source-group sample previously examined in R72 and R76 (8 QA and 16 Summary groups), identical generated response strings, human labels and model thresholds. Compare:
1. R76 package-produced prompt from split source passages plus QA question using detector.predict, including internal context chunking.
2. Exact original RAGTruth generator prompt passed to detector.predict_prompt, which can have different internal context handling.

All answer-relative predicted character spans validated as exact substrings; gold labels were used only after predictions. No training, parameter tuning, or alternate result cherry-picking.

## Executed paired response-level outcomes

| Task | Input method | Human TP | Human FP | FN | TN | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| QA (45) | Reconstructed passages | 6 | 3 | 4 | 32 | .66667 | .60000 | .63158 |
| QA | Original prompt | 6 | 2 | 4 | 33 | .75000 | .60000 | .66667 |
| Summary (96) | Reconstructed passages | 8 | 13 | 13 | 62 | .38095 | .38095 | .38095 |
| Summary | Original prompt | 9 | 14 | 12 | 61 | .39130 | .42857 | .40909 |
| **Combined (141)** | Reconstructed passages | **14** | **16** | **17** | **94** | **.46667** | **.45161** | **.45902** |
| **Combined** | Original prompt | **15** | **16** | **16** | **94** | **.48387** | **.48387** | **.48387** |

Only **5/141 response decisions** changed across the two input formats. Paired human correctness: 106 both correct, 30 both wrong, **2 reconstructed-only correct**, **3 original-prompt-only correct**.

A fixed-seed **source-group bootstrap 95% percentile interval** for original-minus-reconstructed response F1 was **[-0.02297,+0.08602]**, including zero. The sample is small and already inspected for other experiments. Do **not** infer a reliable response-level F1 improvement.

QA bootstrap interval: [0,0.16162], Summary [-0.03663,0.11880]. These are descriptive clustered intervals, not cross-dataset statistical guarantees.

## Source and compute accounting

The original generator prompt had **78,376 prechunk source-prompt tokenizer tokens** aggregated over the full sample, versus **73,351** in reconstructed input. No original prompt exceeded 2,048 tokens in the measured prechunk source tokenizer counter. The actual package may tokenize with its own instructions and chunk-specific overhead; this is **not** direct model-forward input token counting. The original-prompt route accumulated **142.111 CPU wall seconds** of model inference; it cannot directly be divided against the R76 context route's 179.992 seconds without accounting for input formatting, cache, prompt construction and library internals.

This is a genuine test of input-boundary sensitivity with all answer strings and model weights unchanged, but still in-domain because the pretrained detector was trained on RAGTruth's original training partition. The original prompt may contain instructions not guaranteed to be evidence, while the reconstructed source passage pathway may automatically chunk and normalize input differently.

## Decisions and research limits

- **Keep:** exact source and answer span validation, matched source-group evaluation, paired decisions and cluster bootstrap.
- **Reject:** claims that prompt construction alone resolves the observed semantic verifier errors, proves causal attribution, or induces significant F1 improvement.
- **Continue:** stronger models, cross-task calibration, atomic claim-level evidence and actual answer acceptance risk; do not tune prompt format on this small inspected sample.

Model authorship and license remain with published LettuceDetect. RAGTruth original source, prompts and responses are downloaded transiently and not committed. No RAG answer generation or hallucination mitigation was performed.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-77 -p 'test_*.py' -v
    python experiments/round-77/prompt_framing.py --out experiments/round-77/results.json

CI https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44239778792 .
