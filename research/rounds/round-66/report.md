# Round 66: Source-Verifiable Retrieval to Real Answer Exact Match and F1

**Date:** 2026-11-17. **Status:** actual pretrained CPU inference completed and six regression tests passed in [GitHub Actions run 44190160696](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44190160696). This is a baseline diagnostic, not a new RAG architecture or a publication-level generalization result.

## Question

The frozen exact title-bridge retriever obtained higher complete gold-document coverage than per-question BM25 on HotpotQA distractor dev in R54. Can this improvement propagate into **actual predicted answer exact match** when a small pretrained extractive QA reader is fixed, citations are exact-source-bound, and compression is lossless?

## Pinned sources and model

- Dataset: previous R54 SHA-256-verified HotpotQA distractor dev file (61,065,698 original bytes; SHA256 e3da074df24e8369009918aa5cdbdd254dadcde4c63f7569d36afd6f2268caa8), deterministic first **64** of prior SHA-ranked 512 sample IDs. This is NOT newly untouched data; R54 already examined retriever coverage.
- Reader: **deepset/tinyroberta-squad2**, frozen commit **12b287c9df677e28b07f0a023850dba68c997dbf**, CC BY 4.0, local pretrained SQuAD2 single-paragraph extractive reader, PyTorch CPU 2.5.1+cpu, Transformers 4.46.3, two threads, deterministic seed, maximum input sequence 384 tokens. Model weights/tokenizer are not trained or adjusted on HotpotQA.
- Policy: original frozen R25 BM25, exact-title bridge, and deterministic random-document negative control at top-2 and top-5 documents.
- Evidence: full selected source paragraphs versus top-two query-relevant sentences selected by the R55 SQLite FTS5 index; source bytes reconstructed from *both* whole-Zlib and gear512 CAS archives, verified under SHA source receipts before being exposed to the model.
- Reader strategy: each source paragraph is independently answered with the pretrained SQuAD2 model. The highest-scored source answer among the chosen documents is returned; its confidence is not calibrated across documents. Answer is rejected if it cannot be located in a verbatim byte-verified source span. A blank answer is treated as abstention. Thresholds 0.0, 0.25 and 0.50 are fixed before evaluation.

All candidate source texts were already used for question-local BM25 retrieval and source index building. Repeated reader predictions were shared across policies to avoid redundant experimental CPU inference. Attribution of per-policy tokenizer input counts therefore represents the counterfactual tokens for a separately run policy, not the full work of the shared experiment.

## Observations with full selected source paragraphs, zero threshold

| Metric | BM25 top-2 | Title bridge top-2 | BM25 top-5 | Title bridge top-5 | Random top-5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Complete annotated source docs | 24 / 64 | **29 / 64** | 44 / 64 | **51 / 64** | 13 / 64 |
| Exact answer match | **9 / 64** | **9 / 64** | **11 / 64** | **11 / 64** | 7 / 64 |
| Mean token F1 | 0.16406 | 0.16406 | 0.20312 | 0.20312 | 0.12969 |
| Nonempty answers | 31 | 31 | 37 | 36 | 24 |
| Incorrect nonempty answers | 22 | 22 | 26 | 25 | 17 |
| Correct answer with all annotated sentences materialized | 6 | 8 | 10 | 10 | 4 |
| Mean counterfactual model input tokens, selected docs | 257.69 | 254.27 | 695.42 | 688.89 | 699.66 |
| Mean unique whole-Zlib compressed frame bytes, selected docs | 585.36 | 578.64 | 1567.36 | 1554.25 | 1564.25 |

**Paired source-reader answer exact match** was the same for both retrieval policies on every one of the 64 questions at top-2 and top-5 under the full-source context. The answer set overlaps completely: top-2 9 both correct, zero bridge-only or BM25-only; top-5 11 both correct, zero policy-exclusive correct answers. The same zero difference held for the top-two FTS sentence mode at all three abstention thresholds. This is a negative result for the *particular reader and document-level answer-selection mechanism*, not proof against title-linked retrieval in real multihop-generative systems.

### Resources and provenance

- **1,272 distinct model QA calls** for 64 queries across both evidence modes and all query-local candidate documents; total batched CPU inference wall time **162.34 seconds** for this shared experiment, not independent-policy latency.
- SQLite full-text sentence index **360,448 bytes**.
- Whole-source compressed archive **231,440 bytes**; gear512 compressed archive **241,070 bytes**. Both reconstruct the **same** original source content. The FTS index is larger than either source archive. Whole-Zlib remains smaller for this short-doc source regime.
- The dataset is closed-world: original candidate pools include gold paragraphs; the answer model is an off-the-shelf extractor not designed for explicit multi-hop synthesis. All model outputs are checked against exact text spans; lexical source containment does not establish semantic support or authority.

### Interpretation, falsification and prior work

1. The previously replicated **document retrieval gain does not imply an answer gain** with this reader. This is a causal bottleneck indication, not a no-effect theorem.
2. More relevant source documents can improve complete annotated evidence coverage without changing which paragraph's answer has the highest uncalibrated QA score. A reader designed to jointly reason across documents is a necessary comparator.
3. The prediction error rate among nonempty answers is substantial. No threshold has been calibrated on an untouched validation set, and a source-byte citation is **not** a truth or entailment verifier.
4. This question is already well studied: *Retrieval Granularity as Evidence Design in Small-Model RAG Question Answering: A Diagnostic HotpotQA Study* (2026, Information) evaluated a stronger Qwen3-based full-split generator with multiple granularity conditions, answer EM/F1 and retrieved supporting-fact coverage. It also highlights generation errors despite gold evidence. See https://www.mdpi.com/2673-2688/7/8/320. R66 must not be presented as novel evidence that retrieval quality and answer quality differ.
5. The main open scientific challenge for CDG remains how to jointly optimize **reversible source provenance, temporal applicability, evidence completeness, storage and inference cost** with reliable claim support, beyond what conventional retrieval-granularity studies already measure.

## Next falsifiers

- **R67:** Hold the exact reader fixed but permit one joint bounded input over multiple retrieved source paragraphs; compare with the oracle annotated gold sentence context to isolate failure to synthesize even when evidence is complete.
- Run paired answer errors and conditional abstention controls without declaring high confidence to be calibrated factual support.
- Compare an actual multihop-capable generative model, stronger retriever (including dense/hybrid) and full physical archive/index/token costs before any claim about superior RAG.

## Exact reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-66 -p 'test_*.py' -v
    python experiments/round-66/extractive_qa.py --count 64 --offset 0 --out experiments/round-66/results.json

Requires pip-pinned CPU Torch 2.5.1, Transformers 4.46.3, huggingface_hub 0.26.5 and tokenizers 0.20.3; model commit in experiments/round-66/model_lock.json. Model API identity lookup and license recorded in CI log. Experimental code/results do not redistribute the original HotpotQA source paragraphs or pretrained model weights.
