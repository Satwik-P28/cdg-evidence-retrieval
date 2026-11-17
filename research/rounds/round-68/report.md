# Round 68: Frozen Hold-Back Confirmation of Answer Accuracy and Evidence Truncation

**Date:** 2026-11-17. **Status:** successful two-job GitHub Actions run **44192505755**. Six Round 66 and five Round 67 regression tests passed in each job, and all four actual pretrained inference experiments completed. The holdback study used **the last 64 SHA-sorted question IDs (indices 448:512) of the fixed R54 512-question HotpotQA distractor development selection**, distinct from the first 64 used for R66/R67 development diagnostics.

## Predeclared experimental control

No changes to document policies, model architecture, model checkpoint, source code for answer EM/F1, token cap, abstention thresholds or source frame codecs were made after examining the first answer outcomes. The original frozen R25 BM25 and title-bridge retrieval rankings, random document negative control, top-2 and top-5 documents, source paragraph vs FTS-top-two evidence, and the SHA-pinned **deepset/tinyroberta-squad2** SQuAD2 pretrained reader were held fixed. Whole-Zlib and gear512 source bytes were independently verified with receipts. The joint-context oracle was deliberately label-informed and kept out of retrieval comparisons.

This is **a held-back answer-evaluation subset, not an independent new dataset**: earlier R54 document-only analysis included all 512 questions and the 2026 literature already uses HotpotQA distractor dev. These results test stability of reader effects under fixed local conditions only.

## Heldback 64-question results: complete source paragraphs, model score threshold 0

| Outcome | BM25 K=2 | Bridge K=2 | BM25 K=5 | Bridge K=5 |
| --- | ---: | ---: | ---: | ---: |
| Complete gold document sets | 26 | 27 | 44 | **55** |
| Per-source independent reader answer EM | 21 | 21 | 20 | **22** |
| Per-source answer F1 | 0.34479 | 0.34479 | 0.33542 | **0.36667** |
| Per-source answered predictions | 36 | 36 | 42 | 43 |
| Joint-context reader answer EM | 19 | 19 | 15 | **16** |
| Joint-context answer F1 | 0.35731 | 0.35731 | 0.29261 | **0.30823** |
| Complete annotated support retained inside joint 384-token context | 26 | 27 | 36 | **46** |
| Joint-context truncated source inputs | 6 | 6 | 62 | 61 |

When an oracle input contained exactly the annotated supporting sentences, the same model achieved **26/64 exact answers** (mean F1 **0.47970**) with no context overflow and all 64 cases annotated-evidence-complete. The oracle still produced 19 wrong nonempty predictions, proving it is not an accurate multihop reasoner even when source selection is perfect.

## Combined evidence from both independent answer-level partitions (n=128)

| Core measure at top 5 documents | BM25 | Frozen title bridge |
| --- | ---: | ---: |
| Complete annotated supporting document sets | **88/128** | **106/128** |
| Independent per-source reader answer EM | **31/128** | **33/128** |
| Joint 384-token reader answer EM | **22/128** | **24/128** |
| All annotated source sentences retained inside joint model context | **69/128** | **84/128** |

The two additional exact-match answers for bridge K5 versus BM25 are **bridge-only** wins with **zero BM25-only** losses under both reader approaches across both samples. A two-sided exact discordance test gives **p = 0.50** for either paired comparison (two discordant cases). At K2 with the per-source reader, answer EM is exactly equal across both conditions on all 128 questions.

The gold-support oracle achieves **49/128 exact matches** versus bridge K5 joint 24/128 and bridge K5 per-source 33/128. These are evidence-selection *diagnostics*, not calibrated reader limits or new end-to-end systems.

The joint reader's **strict tokenizer cap** is critical: at bridge K5, 119 of 128 original source contexts were truncated, so the model often never saw all the sentences that retrieval acquired. The per-document independent reader does not share that single global context cap, making its raw EM values **not token-budget-matched** to the joint reader. Readers also access all documents initially for lexical BM25 and archive/index generation, so the reported compressed frame activation cannot imply a true end-to-end I/O or latency win.

## Resource measurements

For the second 64-question partition:
- FTS5 source-sentence index **376,832 bytes**.
- Whole-Zlib source archive **243,684 bytes** versus gear512 **252,824 bytes**; the index exceeds either archive and whole remains the smaller independent-paragraph representation.
- **1,280** independently scored per-source question/document/mode candidate pairs in **171.975 sec** of shared batched CPU reader inference.
- **832** joint-context reader conditions in **187.579 sec** of batched CPU inference.
- All original source-text spans and their archive equivalents are byte-verified. Actual model weights, tokenizer, memory and full retrieval indexing costs remain outside these archive-byte counts.

In the first 64-question block, the same paired policies were tested and produced weaker per-source EM. This heterogeneity is another reason not to extrapolate a precise answer accuracy rate to other domains or model families.

## Decision and future tests

**Reject a confirmed answer-quality effect from title-bridge retrieval.** It produced a repeatable gain in gold-document availability, but +2/128 exact answers with p=0.5 is not persuasive. A larger fully held-out test and stronger reader are required.

**Retain the diagnostic insights:** evidence acquisition, *evidence actually reaching the model*, answer correctness, literal source citation, and semantic provenance are different quantities. An answer can be exactly in a source but wrong or not causally derived from it.

**Priority:** Evaluate a multihop-capable generation/reading model with a fixed total input-token budget and accepted strong retrieval baselines, then add independent human-annotated hallucination/faithfulness data such as **RAGTruth** (ACL 2024) to quantify unsupported answer acceptance. Evaluate both corroborative citation support and causal provenance against recent work, including *Cited but Unused: Parametric Provenance in Retrieval-Augmented Generation* (Nov 2026). The real scientific objective is to improve the fully costed quality/faithfulness frontier, not the component-level retrieval score alone.

## Reproduction

    python experiments/round-66/extractive_qa.py --offset 448 --count 64 --out experiments/round-66/holdback-results.json
    python experiments/round-67/joint_context_qa.py --offset 448 --count 64 --out experiments/round-67/holdback-results.json

Workflow and raw compact numerical artifacts: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44192505755 . The original HotpotQA data remain under CC BY-SA 4.0, and the pinned SQuAD2 model under CC BY 4.0; neither is redistributed.
