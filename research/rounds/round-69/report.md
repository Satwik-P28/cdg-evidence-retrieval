# Round 69: Source-Byte Receipts Versus Human-Annotated Hallucinations

**Date:** 2026-11-17. **Status:** Executed full official RAGTruth QA test split in [GitHub Actions run 44195886999](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44195886999); six dedicated unit tests passed. Follow-on CI adds Wilson uncertainty bounds and additional regression test. **Not a novel hallucination detector.**

## Objective and pinned data

Rounds 66–68 verified exact source bytes when presenting a citation but did not test whether the claimed answer was semantically supported. RAGTruth (Niu et al., ACL 2024; https://aclanthology.org/2024.acl-long.585/) supplies original prompts, retrieved passages, generated responses and human-annotated hallucination spans. Test how conventional lexical source matching behaves in this independent human-annotated corpus.

Source repository ParticleMedia/RAGTruth, pinned commit **c103204b9ce28d6bbad859304bf30de72b8ed8fe**. Verify downloaded dataset/response.jsonl has Git blob SHA-1 **f9ae5913fb9976684f3e13be3cd3465062db54cc**, and dataset/source_info.jsonl has Git blob SHA-1 **119277774009f110aa58596b93f9512f62594a89**. Join sources by source_id. Restrict to the official **test** split, good-quality QA responses only. No model generation or fine-tuning and no test-threshold tuning.

**Executed data:** 875 good QA test responses from 150 unique source IDs; source ID overlap with official training split **zero**. All **235** annotated word spans passed exact offset/content checks. No original third-party source passages, response text or annotation comments are committed to the CDG repository.

Source storage includes exact SHA-bound whole-Zlib and content-defined gear512 frame reconstruction receipts. The retained archives occupied **98,488 B** (whole-Zlib) and **117,721 B** (gear512), with no FTS or embedding index included. These source strings are short and mostly independent; whole-Zlib is smaller.

## Human labels and source matches

| Original annotation category | Annotated spans | Exact case-sensitive source substring matches | Casefolded token-normalized phrase matches |
| --- | ---: | ---: | ---: |
| Baseless information | 159 | 0 | 1 |
| Contradictory information | 30 | 0 | 1 |
| Implicit true (correct, absent from supplied source) | 46 | 0 | 0 |
| **Total** | **235** | **0** | **2** |

The original RAGTruth implicit_true marker indicates factually correct information not explicitly in the provided context. These 46 cases must **not** be silently categorized as factually false.

The zero exact matches of annotated erroneous fragments are a property of this sample and annotation granularity, not proof that every exact citation is true or a population-level false-support probability of zero. The script additionally reports a Wilson reference interval for the exact-match proportion and a source-clustered bootstrap percentile interval. Zero-positive bootstrap resampling is degenerate and is not a valid general population upper bound.

## Sentence-level lexical baselines

Split responses into **6,266 punctuation-delimited chunks**; 381 chunks overlap at least one non-implicit-true human error annotation. The other 5,885 chunks are **unlabeled**, NOT independently verified as true or supported. Three fixed label-blind lexical controls treat mismatch as potential hallucination:

| Lexical missing-source heuristic | Human-positive chunks flagged | Human-positive chunks missed | Unlabeled chunks flagged | Proxy precision (unlabeled treated as negative) |
| --- | ---: | ---: | ---: | ---: |
| Entire sentence absent as a casefolded source substring | 364 / 381 | 17 | 5,324 / 5,885 | 6.40% |
| Fewer than 50% of sentence token trigrams found in source | 314 / 381 | 67 | 3,203 / 5,885 | 8.93% |
| Fewer than 75% token trigrams found | 324 / 381 | 57 | 4,131 / 5,885 | 7.27% |

**Interpretation constraint:** These are *agreement with human annotations*, not truth-calibrated semantic verifier precision. An unlabeled sentence can still be false. The heuristic segmentation is not atomic-claim decomposition, and annotators typically mark only the erroneous fragment of a longer statement. Literal non-match is ubiquitous because legitimate generated answers paraphrase their sources.

Some annotated false fragments appear in the original passages after canonical normalization, illustrating that mere mention of the same words is not an entailment argument. Conversely, correct source-supported paraphrases often do not appear as exact text. This experiment does not establish the overall false acceptance rate of a semantic citation verifier.

## Falsification decision

**Reject** equating literal text mismatch with a hallucination detector and **reject** equating a SHA source receipt with semantic support or truth. Byte integrity, sentence-level entailment, factual authority, recency and whether retrieved evidence causally influenced an answer are distinct questions.

**Next test:** Compare a fixed pretrained NLI/contradiction classifier against these lexical controls on the human-annotated QA data without tuning thresholds on the test partition. Measure multi-sentence source selection, source truncation, abstention, inference cost and disagreement with the human labels. Distinguish implicit-but-true annotations from actual erroneous claims.

Prior art: RAGTruth is a recognized ACL 2024 dataset and prior work includes trained hallucination detectors. This CDG round is an auditable component stress test, not an independent new dataset or state-of-the-art classifier.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-69 -p 'test_*.py' -v
    python experiments/round-69/human_span_audit.py --out experiments/round-69/results.json

Original RAGTruth project is MIT licensed; underlying MS MARCO QA material and other base sources retain their original rights. All original data remain upstream and are downloaded transiently; only aggregate metrics and pinned hashes are published.
