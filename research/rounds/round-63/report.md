# Round 63: Frozen Source-Relatedness Gate on Independent Revision Histories

**Date:** 2026-11-17. **Status:** 18 full threshold/history/document-mixture scenarios and four unit regression tests passed under GitHub Actions run **44183545536**. This experiment tests a simple, label-blind byte-overlap gate, not a learned model or a novel algorithm.

## Hypothesis and prespecified mechanism

R58/R62 found strong reductions in related revision histories and weak or negative storage effects for shallow or unrelated sources. Could a source-observed, future-blind similarity gate prevent unhelpful gear512 framing on independent documents while retaining the gain on related histories?

For each source in original arrival order, make BLAKE2b fingerprints of overlapping 96-byte byte windows with 48-byte stride. Use an inverted index of fingerprints for all **previous** source documents only. Define the relatedness score as the largest fraction of current unique fingerprints appearing together in any prior document. Do not inspect source labels, question annotations, future contents, compressed archive outcomes or gold answers. Test three fixed minimum overlap thresholds: **0.20, 0.50, 0.80**, chosen before executing independent history experiments.

The existing R58 online read-weighted policy is otherwise untouched. For an ineligible source, the gear candidate is simply excluded from the two-option local cost comparison. We retain the ungated R58 policy, a known-cohort metadata oracle and always-whole Zlib6 controls. The source overlap index is held in Python memory; its RAM/time are not charged in the compressed archive footprint and would need accounting in a production system.

## Results, each with 512 independent documents

| History | Gate | Archive bytes | Whole-source archive bytes | Ungated adaptive bytes | Percent smaller than whole |
| --- | --- | ---: | ---: | ---: | ---: |
| Ruff (12 revs) | 0.20 | 217,780 | 262,918 | **209,393** | 17.168% |
| Ruff | 0.50 | 224,400 | 262,918 | 209,393 | 14.650% |
| Ruff | 0.80 | 236,012 | 262,918 | 209,393 | 10.234% |
| Transformers (12 revs) | 0.20 | 220,405 | 261,985 | **205,427** | 15.871% |
| Transformers | 0.50 | 233,529 | 261,985 | 205,427 | 10.862% |
| Transformers | 0.80 | 256,052 | 261,985 | 205,427 | 2.265% |
| Flask (7 revs) | 0.20 | 188,990 | **188,846** | 192,454 | -0.076% |
| Flask | 0.50 | 188,990 | 188,846 | 192,454 | -0.076% |
| Flask | 0.80 | **188,846** | **188,846** | 192,454 | 0.000% |

At the most permissive 0.20 threshold with 512 independent paragraphs, the detector estimated an average source overlap of 0.7019 for Ruff history, 0.5324 for Transformers history, 0.2069 for Flask history and only about 0.0027 for independent paragraphs. No independent paragraph was selected for gear compression by the gated policy in those cases.

This basic approach **nearly removes the small Flask penalty** but strongly suppresses useful content-defined framing early in the related Ruff and Transformers streams. In fact, gating at 0.20 expands the stored archive from 209,393 to 217,780 bytes for Ruff, and from 205,427 to 220,405 bytes for Transformers relative to the ungated online algorithm. In the Flask+512 case, gated 188,990 bytes remains marginally larger than whole-source 188,846 bytes.

The overlap-gated policy reduces logical compressed read traffic relative to always-whole in some scenarios but can lose substantial read savings relative to ungated adaptive storage when it excludes valuable gear candidates. The 0.80 gate effectively degenerates to whole-source for Flask, as intended.

## Falsification, not promotion

**Finding:** A fixed content-overlap threshold is too crude for reliable per-source framing decisions. It can identify very unrelated short documents, but cannot automatically measure future CAS reuse value or amortize the migration cost of earlier sources. It is also highly history-order-dependent because a first version has no predecessor.

**Decision:** Do **not** promote threshold-gated framing. Preserve all 18 outcomes and the failure mechanism. Reverting to whole source for low-reuse cases is still a reasonable design choice, but a prospective, direct marginal-storage/read-cost estimator or source-family-aware two-stage storage policy must be tested rather than hardcoding the current thresholds after inspecting data.

**Next concrete falsifier:** Evaluate an online two-stage source-family promotion policy, where first versions are stored whole and an arrival with demonstrated reuse may trigger lossless migration of a small prior family. Charge *all* rewrite bytes, archive metadata, cache, and cold-read cost. Compare against the simple conventional policy that waits for a second source version before enabling chunking. Do not claim an optimized general policy without an independent future history/corpus split.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-63 -p 'test_*.py' -v
    python experiments/round-63/relatedness_gate.py --out experiments/round-63/results.json

GitHub Actions run 44183545536. The source files are pinned and hashed in R62. Byte similarity is an established fingerprint/containment heuristic, not a semantic similarity, truth assessment, or guaranteed prediction of compressed reuse.
