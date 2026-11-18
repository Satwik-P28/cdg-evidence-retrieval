# Round 72: Zero-Shot General NLI Versus Human-Labeled Grounding and Context Selection

**Executed:** 2026-11-17; fixed-revision, CPU-only GitHub Actions run **44227468594** succeeded. All five dedicated synthetic regression tests passed. This is an exploratory negative result, not novel hallucination detection or end-to-end RAG mitigation.

## Research question and third-party prior art

R69–71 demonstrated that simple lexical source overlap cannot achieve acceptable human-label recall and false-alarm rates, while a source SHA cannot determine response faithfulness. Does a **standard pretrained semantic NLI cross-encoder trained on SNLI/MultiNLI, not on RAGTruth**, solve this failure when conditioned on candidate evidence windows?

Strong prior-art context: LettuceDetect (Kovács and Recski 2025, arXiv:2502.17125) is a ModernBERT token-level hallucination detector **trained on RAGTruth**. Its RAGTruth test performance is an important in-domain comparison, but not independent validation of transfer. Other work including NLI/DeBERTa hallucination checking and RAGTruth baselines predates this experiment. The selected zero-shot NLI is a deliberately conventional **general-purpose, non-RAGTruth-trained control**, not intended to beat trained task-specific models.

## Frozen model and source provenance

- Model: **cross-encoder/nli-deberta-v3-xsmall**, pinned Hugging Face Git SHA **a150876415327c80daeff35ca6f68f5ed8cf5c24**, Apache-2.0. Training: SNLI and MultiNLI. 70.8M parameters per public model card. Three labels from the actual loaded config confirmed as 0 contradiction, 1 entailment, 2 neutral.
- Runtime: CPU PyTorch 2.5.1, Transformers 4.46.3, Hugging Face Hub 0.26.5, tokenizers 0.20.3, sentencepiece 0.2.0, numpy 1.26.4, two torch CPU threads. The model ID was resolved through the official HF API **before** running RAGTruth scoring and then locked to the full commit.
- Dataset: immutable RAGTruth Git revision **c103204b9ce28d6bbad859304bf30de72b8ed8fe**, independently verified canonical Git blob digests for both response.jsonl and source_info.jsonl as recorded in R69. Never redistribute raw source passages, original generated answers, annotations or weights.
- Fixed SHA-sorted test source-group selection: **8 QA** source groups, **16 previously unexamined Summary** source groups (not previously used in R69–71, which only examined QA); 141 records with quality==good and **760 deterministic sentence-like claims**. Source-set SHA-256 **fd43a5ef07f80a51b05f590f55867eaefa70c9d02374fef7fd54d788d9cb9d84**. Of 141 responses, 31 have an original human annotated positive span and 110 have none.

No human-label fields enter model inference, window selection or thresholds; they enter only post-prediction scoring. Sentence-level annotation masks are created from exact human span offsets; optional implicit_true labels are scored separately rather than incorrectly equated with indisputable false facts.

## Fixed evidence-window conditions

Sources are split into overlapping 150-word source windows, stride 100, maximum 96 windows/source, with source order preserved. NLI hypotheses are deterministic response sentence-like fragments, up to 128 model tokens; premise+hypothesis inputs are capped at 384 tokens via **first-sequence-only truncation**. Three source context selection rules:
1. First source window, a conventional source truncation baseline.
2. One source window chosen by source/claim content-word overlap.
3. Maximum entailment probability over the top three content-overlap windows, at roughly three inference pairs per claim before any cross-policy sharing.

Each method uses the prespecified **entailment probability >=0.50** for a nonwarning decision. Contradiction and neutral are treated as unsupported; this is a stringent policy, not a calibrated chance of hallucination. A response is flagged if any one of its sentences is flagged. Compare with the original R69 lexical content-overlap warning (source coverage <0.55). No fine-tuning or threshold selection on test human labels.

## Actual executed resource costs

- **141 quality-good responses, 760 response fragments/sentences, 2,273 distinct NLI premise/hypothesis forward pairs.**
- **426,627 total actual tokenizer input tokens**, after model padding excluded by attention masks.
- **251.993 seconds of actual CPU forward inference wall time** over all shared comparisons. Model load 2.423 seconds after weights became available. No hypothesis exceeded the 128-token truncation limit in the sample.
- Aggregate execution shares identical source/claim/window pairs across conditions; **251.993 seconds is the entire joint experiment runtime, NOT per-policy query latency or a claim that three-window verification is free**.
- The model consumed original source passages fetched from pinned RAGTruth, not yet the compressed archive reader. Neither source index/archival decode nor SSD traffic is charged in R72. This motivates the next physical-path integration test.

## Response-level human-label outcomes

| Test task | Rule | Human positive responses found | False alarms among original human-negative responses | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| QA, 45 responses (10 positive / 35 negative) | R69 lexical overlap | 9/10 | 15/35 | 0.37500 | 0.90000 | **0.52941** |
| QA | First window NLI | 10/10 | 34/35 | 0.22727 | 1.00000 | 0.37037 |
| QA | Best window NLI | 10/10 | 34/35 | 0.22727 | 1.00000 | 0.37037 |
| QA | Best of three NLI | 10/10 | 34/35 | 0.22727 | 1.00000 | 0.37037 |
| Summary, 96 responses (21 positive / 75 negative) | R69 lexical overlap | 18/21 | 33/75 | 0.35294 | 0.85714 | **0.50000** |
| Summary | First window NLI | 21/21 | 75/75 | 0.21875 | 1.00000 | 0.35897 |
| Summary | Best window NLI | 21/21 | 74/75 | 0.22105 | 1.00000 | 0.36207 |
| Summary | Best of three NLI | 21/21 | 74/75 | 0.22105 | 1.00000 | 0.36207 |
| **Combined 141** | **R69 lexical overlap** | **27/31** | **48/110** | **0.36000** | **0.87097** | **0.50943** |
| Combined 141 | First window NLI | 31/31 | 109/110 | 0.22143 | 1.00000 | 0.36257 |
| Combined 141 | One best window NLI | 31/31 | 108/110 | 0.22302 | 1.00000 | 0.36471 |
| Combined 141 | Three best windows NLI | 31/31 | 108/110 | 0.22302 | 1.00000 | 0.36471 |

**Interpretation:** The tested general NLI model is effectively a reject-almost-everything detector under a naive 0.50 entailment threshold. Its 100% human-positive recall is accompanied by **98.2–99.1% false-positive rates** across all 141 response records. The three-window condition did not improve response-level human-label precision or F1 over the single best window, while executing more NLI pairs. The lexical baseline, despite its known unreliability, delivered better F1 and fewer false alarms on both task families.

This is a **negative result for this fixed model, threshold and evidence/window mechanism**, not proof that NLI generally fails, no threshold could help, or semantically tuned/atomic claim verifiers offer no benefit. Per-sentence hallucination labels are projected onto entire sentence-like fragments, which may introduce noise; response-level any-warning aggregation makes false alarms accumulate rapidly. The multi-sentence Summarization domain exposes that risk especially strongly.

## Next falsifiers

1. Test training-only NLI confidence calibration on source-disjoint RAGTruth QA training groups, then score **a new test family such as Data2txt** with fixed thresholds, **without retuning after confirmation**. Compare response-level false positives, precision and missed human positives. A trained RAGTruth detector is an in-domain supervised control, not an independent transfer experiment.
2. Decode actual selected source windows through SHA-bound whole/gear frame receipts; verify verbatim source bytes before NLI, and account for content-addressed compressed frames, manifests, FTS/word index, tokenizer inputs and reader latency. The lexical window normalizer changes whitespace and must not itself be confused with a byte-exact source citation.
3. Examine explicit contradiction, neutral and entailment failure slices, and measure with RAGTruth human label types and strict implicit_true handling, rather than treating all unseen words as hallucinations.
4. Compare with a stronger task-specific trained detector and a calibrated NLI/claim decomposition model under the same source-group and inference-cost boundary. Keep strong prior work explicit.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-72 -p 'test_*.py' -v
    python experiments/round-72/zero_shot_nli.py --out experiments/round-72/results.json

Workflow: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44227468594 . Model and source corpora remain at their respective upstream distributors.
