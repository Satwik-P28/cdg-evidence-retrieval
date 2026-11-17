# Round 60: Strong Conventional Compression Controls for the Mixed-Source Archive

**Date:** 2026-11-17. **Status:** five tests and full 1,288-source benchmark passed, GitHub Actions run 44167348275. Zstandard Python 0.25.0 pinned. Inputs are identical to R58: 12 authentic uv README historical versions and 1,276 HotpotQA development paragraphs, with SHA-verified original source text.

## Falsifier

Round 58's result was favorable only relative to whole-document Zlib. A more credible archive hypothesis must confront existing high-quality codecs and the Git pack/delta format. Evaluate whole vs 512-byte content-defined frames under Zlib level 6, Zstandard levels 3 and 9, plus source-type-cohort routing and the same frozen local read-weighted routing objective under Zstandard 3. All compressed source bytes and 128-byte sampled spans are reconstituted exactly and compared with originals.

Build a conventional Git repo: commit 1,276 independent source paragraphs as files, then make 12 commits changing README.md to each pinned original revision, run git gc --aggressive, and verify all historical revisions and 24 selected independent blobs by actual git show. Git pack+idx and full .git are reported separately, with their different accounting boundaries.

## Executed numerical results

| Layout | Archive bytes (CAS + compressed manifest) | Mean logical compressed frame traffic per sampled span |
| --- | ---: | ---: |
| whole Zlib6 | 511,165 | 360.953 |
| gear512 Zlib6 | 521,958 | 303.630 |
| whole Zstd3 | 531,600 | 376.846 |
| gear512 Zstd3 | 541,348 | 316.897 |
| whole Zstd9 | 524,994 | 371.703 |
| gear512 Zstd9 | 537,094 | 313.956 |
| known-source-cohort Zstd3 | 499,961 | 344.187 |
| online read-weighted Zstd3 | 508,271 | 335.483 |

For comparison, the previously validated R58 **online read-weighted Zlib6** archived the same inputs at **487,779 B** with **324.169 B** mean compressed span traffic. R58 known-cohort Zlib6 occupied 480,807 B with 329.595 B mean traffic. Those comparisons reuse the same source-order and content-keyed span sampling scheme.

**Git:** Packed objects = **456,386 B**; .idx = **37,808 B**; total pack+index = **494,194 B**. Full .git metadata = **635,473 B**, excluding checked-out working files. Git's packed objects contain commit and tree records in addition to content blobs and make an authentically versioned repository; custom CAS+manifest does not implement Git's same history and transactional semantics. Thus **487,779 B vs 494,194 B is not proof of compression superiority**: formats and stored history semantics differ. Git is a strong real control but not a strict common logical storage contract here.

## Interpretation

- On short, mostly independent question-local paragraphs plus one related revision family, Zlib6 yielded smaller retained compressed CAS archives than Zstandard 3/9 for the tested formats. This is a **corpus-specific outcome**, not a general comparison of library quality.
- Within Zstandard 3, online mixed routing reduces archive bytes from 531,600 to 508,271 (about 4.4%) and logical span traffic from 376.846 to 335.483 (about 11%). The same conventional source layout trade-off survives changing codec, although absolute bytes are worse here.
- A cohort-aware source-type strategy achieved 499,961 bytes, smaller than Zstandard3 online read-weighted but slightly more logical read traffic. This demonstrates online routing is not universally Pareto-optimal.
- Unlike a complete full RAG system, none of these numbers charges full-text or embedding indexing, reader/model tokens, verifier, cold SSD, cache or source ingest/update policy.

## Decisions

Retain Zlib6 mixed-source layout as a **candidate for this tested corpus** and preserve Git pack and Zstandard controls. Do **not** claim state-of-the-art compression, a novel codec, an end-to-end performance win or Git semantic equivalence. A next falsifier is evaluating the frozen source-layout policy on independent source mixtures and source proportions without tuning, with downstream index and actual evidence query load.

## Reproduction

    python -m pip install zstandard==0.25.0
    python -W error::ResourceWarning -m unittest discover -s experiments/round-60 -p 'test_*.py' -v
    python experiments/round-60/strong_controls.py --out experiments/round-60/results.json

CI logs and numerical artifacts: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44167348275 . Standard Zstandard, Zlib and Git algorithms are prior art. The pinned external HotpotQA data are downloaded transiently under their original CC BY-SA 4.0 license.
