# Round 45: Source-Retrieval Without Gold Record IDs in TimeConflict QA

**Date:** 2026-11-17. **Status:** executed in GitHub Actions run 44028260332. Six dedicated Round 45 regression tests passed, along with 260 source-associated QA variants from 91 real-entity TimeConflict records. Dataset is taken from CheerCHuang/PRISM-Edit. This is not open-domain semantic QA, independently verified factual truth, or end-to-end LLM generation.

## Problem isolated

Round 41's temporal consistency exercise directly associated each question with the gold record row. This is not deployable retrieval. Round 45 removes gold row IDs from the actual search and selection functions. For each natural-language question, it compares SQLite FTS5 BM25 retrieval (top 1 and top 5), exact subject-substring matching, and a hybrid of both. Only after the engine predicts a source ID does the evaluator consult the dataset's gold mapping.

Every retrieved source is stored as a canonicalized JSON blob compressed with zlib and reconstructed under its SHA-256 source digest before temporal inspection. This is an integrity/consistency test, not a signature, source authority or fact-entailment verifier.

## Observed results

Both relations combined: 91 source records, 260 same-release questions, two relationships (P26 spouse and P35 head of state). All 260 questions have the subject name in the question by dataset construction.

| Retrieval and temporal decision | Correct labels / 260 | Wrong among answered | Abstained | Correct source retrieved |
| --- | ---: | ---: | ---: | ---: |
| BM25 top1 + always latest | 122 | 138 | 0 | 260 |
| BM25 top1 + point-date heuristic | 227 | 3 | 30 | 260 |
| BM25 top1 + conservative full-window validity | 133 | 0 | 127 | 260 |
| Exact subject + point date | 216 | 3 | 41 | 249 |
| Hybrid + point date | 227 | 3 | 30 | 260 |
| Hybrid + full-window | 133 | 0 | 127 | 260 |

The expected gold source is in BM25's top-five list in all 260 questions and is first for all 260. Exact-subject selection abstains on ambiguous source names and returns the gold source on 249 questions. The hybrid offers no recovery improvement over BM25 in this dataset and performs extra work.

BM25 was not trained on the dataset, but the evaluation corpus and question templates are intrinsically easy: the subject appears verbatim and there are only 91 candidate records. This is not representative open-domain retrieval. Historical answers are derived from the same structured records used by the evaluator, rather than independent textual evidence.

The strict interval policy avoids the three measured point-date errors but abstains 127/260 times. This reflects a deliberately conservative quantification assumption, not proof of a generally optimal temporal answer strategy. For 'since Month YYYY' questions, treating the month as a complete window can be overly strict and misses valid partial-month applicability.

## Novelty and negative result

**Negative:** in this small oracle-free selection experiment, ordinary BM25 fully solves candidate source identity recovery. The expected gain from exact-name reranking or adding a graph is absent. More complex retrieval should not be accepted without beating BM25 on independent held-out queries.

**Positive engineering boundary:** separate source record identity/reconstruction, temporal interval applicability, and observed answer label match. The SHA-256 check ensures source bytes match the stored digest but does not establish factual authority.

**Unresolved:** independent entailment of full source passages, cross-source claims and conflicts, broad retrieval scale, source version changes, lossless frame read amplification, accurate temporal language understanding, and robust accepted-answer risk.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-45 -p 'test_*.py' -v
    python experiments/round-45/blind_temporal.py --out experiments/round-45/results.json

Dataset: https://github.com/CheerCHuang/PRISM-Edit (MIT licensed project with third-party notices; exact subset stored in Round 41). The experiment's source text is derived from those annotations, not from independently retrieved dated news articles.

**Next falsifier:** evaluate much more ambiguous entity name retrieval, independence between dataset answers and source evidence, temporal contradiction detection, and held-out questions. Compare the simplest BM25/time-filter baseline before adding an adaptive hypergraph planner.
