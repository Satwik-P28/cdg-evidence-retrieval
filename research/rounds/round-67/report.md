# Round 67: Joint-Context Extractive Answering Versus Annotated-Evidence Oracle

**Date:** 2026-11-17. **Status:** five model-free new tests and complete pinned pretrained QA evaluation **passed** in [GitHub Actions run 44192252258](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44192252258). R66 model and HotpotQA sample fixed, no reader training or policy parameter tuning.

## Falsifiable question

R66 showed a frozen exact-title bridge could recover extra gold documents without changing answer EM when a pretrained SQuAD2 reader independently answered each paragraph and the system selected the highest-confidence answer. Would the **same fixed reader** gain from seeing concatenated retrieved evidence in one bounded context? How often does it fail even if all annotated gold support is directly supplied?

This is a stricter *reader design* diagnostic, not independent-data generalization. The model is deepset/tinyroberta-squad2 commit 12b287c9df677e28b07f0a023850dba68c997dbf (CC BY 4.0), PyTorch CPU 2.5.1+cpu, Transformers 4.46.3 and two threads.

## Methods and source verification

- Exact same first 64 SHA-selected HotpotQA distractor development questions from R66.
- Frozen R25 document selectors: ordinary BM25, exact title-bridge expansion, deterministic negative-control random; K = 2 or 5 documents.
- Source bytes reconstructed with SHA-bound receipts from both whole-Zlib and gear512 content-addressed frames; R55 FTS5 sentence offsets also verified.
- Source evidence modes: entire selected paragraphs or top-two query-relevant FTS sentences per document. **One joint question+context model input is strictly capped at 384 tokenizer tokens**, via source-character prefix truncation that cannot rewrite source facts. No gold labels influence policy ranking or context pruning.
- Gold oracle diagnostic: only the annotated supporting-fact sentences are supplied to the same model. This label-informed condition is **not a deployable retriever**, only a diagnostic upper bound on answerability given perfect evidence selection.
- Score official-style answer exact match and token F1, complete annotated supporting sentences *actually fitting inside the model input*, answered/wrong counts, truncation rates, literal source-citation integrity and mean model input tokens. Model confidence is not calibrated and token counts exclude upstream retrieval/index processing.

## Measured answer results with whole source paragraphs, score threshold 0

| Context construction | Answer EM | Mean answer F1 | Complete gold docs retrieved | All annotated gold sentences actually within input | Truncated input contexts |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25, 2 docs | 7 / 64 | 0.13643 | 24 / 64 | 24 / 64 | 4 |
| Bridge, 2 docs | **8 / 64** | **0.14815** | **29 / 64** | **29 / 64** | 4 |
| BM25, 5 docs | 7 / 64 | 0.12969 | 44 / 64 | 33 / 64 | 57 |
| Bridge, 5 docs | **8 / 64** | **0.14531** | **51 / 64** | **38 / 64** | 58 |
| Random control, 2 docs | 0 / 64 | 0.04896 | 1 / 64 | 1 / 64 | 10 |
| Random control, 5 docs | 2 / 64 | 0.04948 | 13 / 64 | 8 / 64 | 57 |
| **Gold supporting-fact sentences supplied directly** | **23 / 64** | **0.44490** | 64 / 64 by construction | 64 / 64 | 0 |

The single bridge-only correct answer at K=2 and K=5 is not meaningful evidence of a reliable EM gain (zero BM25-only, one bridge-only, paired exact discordance p=1 for these 64 questions). A strict 384-token input prevents the model from reading all selected sentences even when the chosen documents include all gold documents: for bridge K=5, document set coverage was 51, *actual in-window gold supporting-fact coverage only 38*. This distinction was missed in earlier document-only retrieval studies.

**The oracle is especially informative:** the same off-the-shelf SQuAD2 reader achieved only 23/64 exact answers even when every annotated supporting sentence was supplied without context overflow, and it generated 22 wrong nonempty oracle answers. This is a reader/synthesis failure in addition to retrieval failure. It does not establish an intrinsic ceiling for multihop-trained models or larger generative readers.

The oracle mean model input length was **111.88 tokens**, while top-five full-context BM25 and bridge each used about **379 tokens** before the 384 token cap. The real model processed **832 question/context pairs in 94.889 seconds** for all conditions combined. CPU wall time is shared batched inference, not independent-policy query latency. Both source archive layouts provided the same byte strings and therefore the same reader inputs by design; no end-to-end storage latency comparison is claimed.

## Experimental discipline and prior art

- R66 model selection and all scoring policies were frozen; this is the same previously seen dev questions, so findings are exploratory.
- Full paragraph vs separate-paragraph reader **do not use equal token budgets**: R66 can process up to 384 tokens *per document*, R67 caps the entire joint input at 384. This is a realistic cost trade-off but **not** a pure controlled test of modeling architecture.
- Answer appearing verbatim in cited source bytes is **not** proof it is supported, true or causally sourced from that document. A source content-addressed receipt is a traceability mechanism, not semantic verification.
- The 2026 paper *Retrieval Granularity as Evidence Design in Small-Model RAG Question Answering: A Diagnostic HotpotQA Study*, https://www.mdpi.com/2673-2688/7/8/320, previously analyzed full-split HotpotQA evidence granularity with a stronger Qwen3 reader and gold support. R67 is not a novel discovery of that phenomenon.
- *Cited but Unused: Parametric Provenance in Retrieval-Augmented Generation* (Nov 12, 2026, arXiv:2611.17161) provides a more precise demonstration that even semantically matching citations can be post-hoc and causally misleading. Thus a CDG source receipt must not be advertised as model provenance, groundedness, or entailment.

## Decision and next falsifier

**Reject:** interpreting R54/R66 higher supporting-document recall as automatic answer quality improvement. Better evidence packing and multihop-capable reasoning are both required, but unproven here.

**Retain:** the exact-lossless source receipts, strict reader token budget, source-content availability accounting, and explicit oracle. These are reproducible controls for future model experiments.

**Next:** Run the identical two reader architectures on a second prespecified 64-question QA holdback (Round 68), then test stronger multihop-capable generator/reader and independent hallucination annotations (e.g., RAGTruth). Include true model-token and physical indexing/storage/update costs and independent semantic support judgments.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-67 -p 'test_*.py' -v
    python experiments/round-67/joint_context_qa.py --count 64 --offset 0 --out experiments/round-67/results.json

The pinned Torch/Transformers/Hub dependencies and source SHA constraints match Round 66. The workflow uploads aggregate JSON only; no underlying Wikipedia paragraph texts or model weights are redistributed.
