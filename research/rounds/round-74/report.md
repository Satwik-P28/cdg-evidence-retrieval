# Round 74: QA-Trained NLI Calibration Fails Under Data2txt Task Shift

**Date:** 2026-11-17. **Status:** complete, all dedicated tests and model run passed, GitHub Actions **44237569884**. Code merged in PR #15. This study tests threshold transfer, not a new verifier.

## Experimental contract

- Immutable R72 generic SNLI/MultiNLI pretrained NLI model **cross-encoder/nli-deberta-v3-xsmall**, SHA **a150876415327c80daeff35ca6f68f5ed8cf5c24**, unchanged model weights, source-window selection and 384-token input cap.
- Source data from the SHA-pinned RAGTruth upstream release.
- **Calibration:** 32 SHA-selected QA *training* source groups, **190** quality-good responses. Calibrate strict non-entailment warnings on QA human-negative responses only, using fixed 10% and 25% empirical training false-positive allowances.
- **Transfer:** 16 disjoint original Data2txt *test* groups, **96** quality-good responses with **61** annotated unsupported positives, **35** human-negative responses. Test group SHA-256 **d850ee2c845c4d38a59f94a411a9410c16fa6efffed9b716567340f4bd4365a6**. Train source group SHA-256 **cfa38f284cfe810468618645e310eaa8fe008aae1654e695e5e76094f81b7bdc**.
- Neither test labels nor any model outcomes enter calibration threshold or source-window selection. This is a previously unused task inside RAGTruth, not a separate new benchmark or deployment.
- Structured Data2txt source information is serialized to JSON under the R69 source text contract; a natural-language NLI model may struggle with this representation.

## Executed human-label confusion

| Warning policy | TP / 61 | FP / 35 | FN | Test FPR | Response F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen 55%-overlap lexical | 60 | 35 | 1 | 100% | 0.76923 |
| NLI threshold 0.50, first or best-three windows | **61** | **35** | 0 | **100%** | **0.77707** |
| Top-one max risk, QA train 10% FPR allowance | 35 | 21 | 26 | 60% | 0.59829 |
| Top-one max risk, QA train 25% FPR allowance | 56 | 28 | 5 | 80% | 0.77241 |
| Top-three max risk, QA train 10% allowance | 19 | 9 | 42 | 25.71% | 0.42697 |
| Top-three max risk, QA train 25% allowance | 32 | 21 | 29 | 60% | 0.56140 |
| Top-three mean risk, QA train 10% allowance | 2 | 0 | 59 | 0% | 0.06349 |
| Top-three mean risk, QA train 25% allowance | 10 | 7 | 51 | 20% | 0.25641 |

A trivial **reject-all** policy exactly matches the frozen NLI response F1 here, **122/157 = 0.77707**, because 61/96 are labeled positive. That F1 is not an accuracy or faithfulness breakthrough: it masks false alarms on every original human-negative response.

The QA-calibrated top-three max warning at 10% *training* false-positive allowance gives **25.71%** Data2txt test FPR and only **31.15%** recall. At a 25% train allowance its test FPR reaches 60%. A 10%-allowance mean-risk warning detects only 2/61 positives. There is no reliable transferable specificity/sensitivity operating point under these controls.

## Compute and scientific limits

- **7,550** evaluated NLI pairs, **1,552,487** actual model-input tokens, **1,228.189 seconds** cumulative CPU model forward time.
- No NLI claim sentences required truncation to 128 tokens.
- Time excludes some upstream data acquisition, tokenizer overhead, model initialization, persistent model weights, source indexing and actual physical I/O. The common model passes are shared across all threshold conditions and **must not be counted as independent per-policy latencies**.
- Human RAGTruth source-faithfulness annotations are not universal objective truth; implicit_true is separately analyzed. Training-only empirical FPR targets provide no distribution-free calibration guarantee.
- This result does not imply that stronger semantic verifiers, structured field-aware reasoning, or task-trained/independently validated models have the same failure.

**Decision:** Reject the claim that generic NLI source-window risk can be calibrated on QA training responses and deployed directly on structured Data2txt at reliable false alarm rates. Preserve the negative threshold transfer. Follow-up R75 tests counterfactual source sensitivity and R76 compares a published RAGTruth-trained detector.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-74 -p 'test_*.py' -v
    python experiments/round-74/cross_task_calibration.py --out experiments/round-74/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44237569884 . Source data and original responses are downloaded transiently under their original licenses; only derived numerical results, hashes and code are in the repository.
