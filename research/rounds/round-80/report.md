# CDG Round 80: Pretrained Working Verifiers Under Controlled Fact Edits

**Date:** November 18, 2026. **Status:** code, tests and pinned CPU model workflow submitted. Actual model scores **pending** and must be inserted only from a successful exact-head run. This is a controlled synthetic stress test, **not independent human ground truth, an end-to-end RAG evaluation, or a novel detector**.

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
