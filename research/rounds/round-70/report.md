# Round 70: Training-Only Calibration and Disjoint RAGTruth Test Confirmation

**Date:** 2026-11-17. **Status:** complete SHA-pinned RAGTruth test and five focused unit tests passed in GitHub Actions run **44215068586**. This follow-up examines source groups never used in Round 69 warning evaluation.

## Hypothesis and partition integrity

Round 69's fixed lexical detectors caught most annotated unsupported responses but falsely warned on many clean outputs. Can a source-word-novelty cutoff calibrated exclusively on **QA training source groups** reduce false alarms without losing useful unsupported-content recall?

The official QA test split has 150 distinct source IDs. Round 69 examined 128 SHA-ranked groups. Here, the **remaining 22 previously unexamined test source groups** are frozen as the confirmation set (132 total responses; 131 with quality good). The train corpus includes **4,892 quality-good QA responses**. Source IDs that appear in heldout are excluded from training if any overlap exists. Any response carrying a quality flag other than good is excluded from the train and confirmation metrics. The original test source group and its six generated responses are treated as one bootstrap sampling unit.

No heldout human labels influence threshold selection. Target empirical training false-positive rates are fixed at **5% and 10%**. Two unchanged lexical risk scores are examined: maximum fraction of content words novel in one response sentence, and fraction of response sentences exhibiting high novelty. The cutoff is chosen as the least stringent threshold producing at most the desired observed training false-positive rate. This is **not** a population-level 5%/10% guarantee. The original R69 content-overlap threshold (55% source content-word coverage) is retained as the uncalibrated reference.

## Holdout results, quality-good responses

Among **131 responses** from 22 groups, **22** contained human annotations and **109** did not.

| Warning policy | Human positives found /22 | False positives /109 | FPR | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original R69 55%-coverage warning | **20** | 51 | 46.79% | 90.91% | **0.43011** |
| Max sentence novelty, train target 5% | 0 | 0 | 0% | 0% | 0 |
| Max sentence novelty, train target 10% | 0 | 0 | 0% | 0% | 0 |
| Fraction novel sentences, train target 5% | 0 | 0 | 0% | 0% | 0 |
| Fraction novel sentences, train target 10% | 1 | 5 | 4.59% | 4.55% | 0.07143 |

The calibrated max-novelty score was saturated among many negative training examples; the data-driven training cutoff reached its maximum allowed novelty, leaving no positive warnings. This is a genuine failure of the chosen score under specificity constraints, not a successful abstention/hallucination detector.

The fraction-of-novel-sentences control with a 10% empirical training false-alarm allowance retained **one** correct warning out of 22 human positives, with **five** false alarms. It is therefore unsuitable as a meaningful semantic grounding signal on this confirmation set. The less stringent original warning retained sensitivity but still falsely rejected nearly half of otherwise clean responses.

## Group uncertainty and label nuance

Group bootstrap, 2,000 deterministic resamples across the 22 source IDs, yields for the original R69 reference:
- Human-positive recall 95% percentile interval **[0.73684, 1.0]**.
- False-positive rate interval **[0.36697, 0.57447]**.

For train-calibrated novel-sentence fraction at the 10% target:
- Recall interval **[0.0, 0.13636]**.
- False-positive rate interval **[0.00893, 0.09184]**.

After excluding original human annotation spans marked implicit_true, only **19/131** confirmation responses count as strictly unsupported positive. The train-calibrated novel-sentence fraction identifies just **1/19**. The finding is not an artifact of treating implicit-but-possibly-true statements as falsehood.

## Interpretation

**Reject the proposition that high-recall lexical grounding checks can be made operationally reliable merely by setting a lower false-positive threshold on training data.** The observed specificity-versus-sensitivity trade-off is severe. This does not prove that pretrained NLI, sentence-level attribution, domain-specific detectors or models trained on human labels would also fail.

The historical question selection and annotator labeling were independently fixed. However, the new 22 source groups belong to the same public RAGTruth QA dataset and generation systems, not to a separate live deployment. Results are descriptive with a small source-group sample; the cutoff rule is basic order statistics, not a formal conformal false-alarm guarantee.

**Next:** R71 measures a source-only information bound with the same dataset and verifies actual compressed source receipts. Stronger pretrained semantic entailment controls and independent source/response families remain needed.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-70 -p 'test_*.py' -v
    python experiments/round-70/calibrated_grounding.py --out experiments/round-70/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44215068586 . Source bytes and model-generated response text are fetched transiently under RAGTruth's upstream data terms and not redistributed.
