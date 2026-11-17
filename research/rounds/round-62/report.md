# Round 62: Independent Revision-History Transfer of Frozen Mixed-Source Compression

**Date:** 2026-11-17. **Status:** successful full upstream-data run and three fixture tests in GitHub Actions run 44183545536. This round tests the frozen R58 whole-Zlib/gear512 policy on **independently maintained real version histories**, not new paraphrases of the uv README. The external source bytes are retrieved transiently and are not redistributed.

## Source provenance and identity

Upstream documents are original README.md files at path-change commit SHAs, truncated at immutable repository commit cutoffs:

| Project | Cutoff HEAD Git SHA | Distinct historical README files | Total original README bytes |
| --- | --- | ---: | ---: |
| Ruff (MIT) | 9e7e7a47f1b866340c432d535c41693d6beb4621 | 12 | 235,726 |
| Transformers (Apache-2.0) | fc00b5b3c9f9306c55908bb546fa3b033a4bfb1d | 12 | 211,378 |
| Flask (BSD-3-Clause) | 49943b5a94413a530761350f04e896f76e8d620e | 7 | 10,386 |

The pinned GitHub commit endpoint supplies all candidate file-history revisions. Each available raw source file is hashed with SHA-256 and its canonical Git blob SHA-1, sorted into original chronological order, and returned as one actual source version. No-op content revisions are skipped, as are path-history events with missing historical files (HTTP 404). The experiment requested up to 12 distinct versions, **not exactly 12**. Flask genuinely provided only seven distinct surviving README versions under this query. There is no synthetic padding or mutation.

Version identities, commit dates, original content hashes and per-history aggregate digest are available in the raw R62 JSON artifact. The control input adds 0, 128 or 512 independent HotpotQA development paragraphs from a different fixed SHA-ranked question subset than R58's training mixture. All original source blobs and two deterministic 128-byte sample spans per source are reconstructed and verified.

## Frozen policies and results

Policies are unchanged since R58: all whole-Zlib6 source CAS, all content-defined gear512-Zlib6 CAS, known-cohort source grouping (uses metadata oracle), and the previously established online storage+read-cost heuristic. All include actual content-addressed compressed source payload and compressed binary manifests. Comparisons below are **online read-weighted** versus always-whole. Negative percentages are savings.

| Revision family | Additional independent paragraphs | Retained archive change | Compressed-span activation change | Online archive bytes | Always-whole archive bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ruff | 0 | -71.673% | -89.927% | 22,671 | 80,033 |
| Ruff | 128 | -46.261% | -63.475% | 65,197 | 121,322 |
| Ruff | 512 | **-20.358%** | **-31.697%** | 209,393 | 262,918 |
| Transformers | 0 | -76.361% | -91.109% | 18,699 | 79,103 |
| Transformers | 128 | -49.140% | -64.067% | 61,232 | 120,393 |
| Transformers | 512 | **-21.588%** | **-31.856%** | 205,427 | 261,985 |
| Flask | 0 | -3.771% | -43.330% | 5,742 | 5,967 |
| Flask | 128 | +2.120% | -10.998% | 48,261 | 47,259 |
| Flask | 512 | **+1.911%** | -4.886% | 192,454 | 188,846 |

The metadata-informed known-cohort control remains better on stored bytes for many mixtures. With Ruff+512 it occupied **205,555 bytes** vs online 209,393. Transformers+512: **201,585** vs online **205,427**. Flask+512: **188,613** vs online **192,454**. The online policy chooses content-defined frames for many independent paragraphs despite apparently weak source reuse, costing some per-source metadata.

## Interpretation

The favorable R58 behavior **transferred to two new authentic, highly overlapping revision families**. On short and weakly overlapping Flask README history, the policy provides less opportunity for cross-version deduplication and causes a slight archive-size penalty once mixed with many independent documents. The effect therefore depends on actual redundant byte structure and history depth, not merely the label "versioned."

The strong previously tested Git pack and Zstd controls from R60 are not directly re-executed on these new histories; neither codec nor custom CAS is claimed superior to mature backup/storage systems. Compression/dedup using content-defined gear-style frames is established prior work (FastCDC, USENIX ATC 2016; Restic's content-defined chunker). This is an engineering transfer experiment, not proof of new theoretical compression or universally optimal source routing.

## Decision and next falsifier

- **Keep** R58 as a research candidate for repeated, highly related sources.
- **Reject** applying it unconditionally to unrelated or shallow histories.
- **Require** a source-label-free gate, grouping, or online estimate, tested prospectively rather than selected after seeing the same target mixtures.
- **Measure** physical I/O, index+archive cost, update/recompression cost and real evidence query workloads before deployment claims.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-62 -p 'test_*.py' -v
    python experiments/round-62/independent_histories.py --out experiments/round-62/results.json

GitHub Actions successful run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44183545536 . Runtime source SHA verification and historical commits are recorded in the JSON artifact. Raw README contents are never committed.
