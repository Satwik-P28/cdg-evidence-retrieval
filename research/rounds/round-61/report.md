# Round 61: Frozen Online Compression Policy Under Source-Mixture Shift

**Date:** 2026-11-17. **Status:** passed two dedicated regression tests and 12 complete mixture configurations in GitHub Actions run **44167751697**. Source bytes reconstruct exactly, including 128-byte sampled spans. Uses the policy from R58 **without retuning**, and a distinct set of 128 SHA-locked HotpotQA dev question IDs from the final quarter of the R54 sample.

## Objective and evidence boundary

R58 found a mixed whole-Zlib/content-defined frame policy favorable against always-whole on 12 authentic uv README revisions + 1,276 short HotpotQA paragraphs. R60 demonstrated stronger codec and Git controls but not generalization across source ratios. R61 tests **mixture sensitivity**: 0, 3, 6, or 12 pinned README revisions combined with 96, 384 or 1,024 independent short source paragraphs. The input source paragraphs come from R54's final 128 dev examples, not the first 128 used in R58.

The policies use the exact conventional R58 source CAS and binary-Zlib manifests: always-whole, always-gear512, known-cohort, greedy storage-only, and frozen online read-weighted. No gold labels or annotations enter compression selection. For each source, check complete lossless readback and two deterministic SHA-content-keyed 128-byte spans.

## Results for online read-weighted versus always-whole Zlib6

Negative percentages are savings in the named metric. Positive archive percentages mean the adaptive policy is **larger**.

| History sources / independent sources | Archive size delta | Logical compressed read traffic delta |
| --- | ---: | ---: |
| 0 / 96 | +1.381% | -2.261% |
| 0 / 384 | +0.796% | -1.173% |
| 0 / 1,024 | +1.571% | -2.699% |
| 3 / 96 | +0.858% | -18.115% |
| 3 / 384 | +0.677% | -6.337% |
| 3 / 1,024 | +1.503% | -4.623% |
| 6 / 96 | -14.837% | -33.411% |
| 6 / 384 | -5.059% | -13.080% |
| 6 / 1,024 | -0.823% | -7.399% |
| 12 / 96 | -36.040% | -48.248% |
| 12 / 384 | -15.897% | -22.875% |
| 12 / 1,024 | -5.790% | -12.070% |

**Interpretation:** A source relatedness threshold visibly matters. The frozen policy activated less logical compressed frame traffic in all 12 scenarios, but yielded a smaller retained archive only in 6 of 12, and all six required six or twelve related revisions. A mixed policy cannot be advertised as a free win for unrelated single-use documents.

These observations involve one particular revision history and one question-local source family, and the history prefixes were selected in their original chronological ordering. The apparent threshold at six revisions is **not** a general switching rule, statistical breakpoint, or proof of predictable corpus redundancy. Relative proportions, edit distribution, framing overhead, and future queries can change the result.

## Decisions

- **Reject:** an unconditional adaptive archive default for arbitrary text.
- **Keep experimentally:** online storage+read-aware routing for source groups with meaningful repeated/revised content, while using plain whole-source compression elsewhere.
- **Avoid retrofitted threshold optimization:** no revised coefficients were tuned on this 12-case matrix; that would invalidate its use as a frozen-policy check.
- **Next falsification:** genuine unrelated version histories, independent domains, source family detection without source label or history oracle, stronger Git pack/Zstandard controls at matched archive contract and measured physical access costs.

## Exact reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-61 -p 'test_*.py' -v
    python experiments/round-61/mix_shift.py --out experiments/round-61/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44167751697 . R60's strong Zstandard and Git pack baselines were also executed successfully in the same job before R61.

**Limits:** The held-back source IDs belong to the same publicly used HotpotQA development dataset and were also used for the earlier R59 allocation check. They are unexamined for R58 compression routing, but do not constitute a new independent corpus family. Compressed activation byte counts exclude FTS/embedding indexes, model/verifier tokens, hardware I/O, and transaction durability. These are established Zlib/CAS/framing techniques, not a novel compressor or end-to-end RAG validation.
