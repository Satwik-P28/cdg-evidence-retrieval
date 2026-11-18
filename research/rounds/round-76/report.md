# Round 76: Published LettuceDetect In-Domain Strong Baseline on Fixed RAGTruth QA and Summary Sources

**Date:** 2026-11-17. **Status:** dedicated experiment and six model-free tests passed GitHub Actions run **44238924730**, with previous compatibility checks passing. Implementation merged in PR #17. The purpose is to compare with a credible published, task-trained verifier rather than another weak lexical or generic NLI heuristic.

## Strong relevant prior art and exact model

- Published LettuceDetect (Kovács and Recski, 2025), https://arxiv.org/abs/2502.17125 ; official code https://github.com/KRLabsOrg/LettuceDetect .
- Pretrained **KRLabsOrg/lettucedect-base-modernbert-en-v1**, MIT license, immutable Hugging Face SHA **0ff0f0dd23052cf751dae374f57a539aa092e772**; public package **lettucedetect 0.2.3**.
- **149,606,402** model parameters; CPU PyTorch 2.6.0 and pinned Transformers runtime, 2 CPU threads. Source-plus-response context cap **2,048 tokens**.
- Crucial distinction: **this model is already fine-tuned on RAGTruth's original training split**. The evaluation is an in-domain test-set comparison of published prior art, **not** independent out-of-distribution validation or a new CDG model.

## Source and label contract

Use the precise immutable Round 72 QA+Summary source set: source-ID SHA256 **fd43a5ef07f80a51b05f590f55867eaefa70c9d02374fef7fd54d788d9cb9d84**, 8 QA groups + 16 Summary groups, total **141** quality-good model responses. QA had 45 responses with 10 human-labeled unsupported; Summary had 96 responses with 21 positive. Original RAGTruth file revision and blobs are pinned as in R69.

The library was given source passages and task question. QA numbered passages were split; long Summary input was split into 150-word source chunks, then the library could internally chunk to respect the 2,048-token budget. The model returned answer-relative predicted character spans, audited against the original exact answer text and offsets. Human labels enter scoring *after* model prediction, never source selection or inference.

### Actual response-level human-label results

| Task | TP | FP | FN | TN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| QA (45 responses) | 6 | 3 | 4 | 32 | 0.66667 | 0.60000 | **0.63158** |
| Summary (96 responses) | 8 | 13 | 13 | 62 | 0.38095 | 0.38095 | **0.38095** |
| **Combined 141** | **14** | **16** | **17** | **94** | **0.46667** | **0.45161** | **0.45902** |

The response false-positive rate is 16/110 = **14.55%**, while false negatives are 17/31 positive human-annotated responses. Both errors are consequential.

### Human character-level span detection

| Task | TP characters | FP characters | FN characters | Human span F1 |
| --- | ---: | ---: | ---: | ---: |
| QA | 807 | 693 | 918 | 0.50047 |
| Summary | 290 | 620 | 987 | 0.26520 |
| **Combined** | **1,097** | **1,313** | **1,905** | **0.40540** |

These character-level metrics differ substantially from example-level metrics. A response may be correctly flagged while most annotated hallucinated text is missed.

## Cost and interpretation

Total measured inference wall time over the entire 141-response shared CPU run was **179.992 seconds**; model load after snapshot resolution took **4.308 seconds**. Model weights, the full source archive/FTS and physical I/O are not included in that inference value. Package construction initially failed with an unsupported batch_size constructor field passed through to HF model; this integration mismatch was fixed before the successful locked run and documented in CI.

Round 72's *generic SNLI/MultiNLI* NLI model on the same selected source/answer pairs had combined human response F1 **0.36471** under top-three source windows. Round 72's simple lexical source-overlap warning achieved **0.50943**, exceeding this LettuceDetect execution's **0.45902**. **These three figures are NOT apples-to-apples superiority rankings**: source prompt formatting, training data, context budget (384 vs 2,048 tokens), model parameter count and inference method differ. In particular this local 141-response subset, package version and source construction must not be used to invalidate the original LettuceDetect paper's much larger published benchmark. Round 77 specifically tests input-prompt sensitivity before making further comparisons.

## Research decision

Keep this strong published supervised detector as an **essential prior-art control**, not a CDG innovation. Its notable success on QA and weaker Summary results show that response-conditioned verification can help compared with uncalibrated generic NLI yet still suffer significant miss and false-alarm rates in a task-dependent manner.

Do **not** claim reduction in hallucinations, semantic proof, citation causality, generalization to unseen generation systems, or a unique high-performance verifier. Neither this pass nor the lexical checks generate or modify a single answer. There remains no fully cost-accounted end-to-end RAG Pareto improvement.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-76 -p 'test_*.py' -v
    python experiments/round-76/lettuce_reference.py --out experiments/round-76/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44238924730 . Published code and weights retain their original authorship and MIT license. Human labels and source texts are read transiently and never redistributed.
