# Round 58: Online Compression Policies on Mixed Version Histories and Independent Documents

**Date:** 2026-11-17. **Status:** 1,288 authentic source documents in three input orders, 15 policy/order scenarios, four dedicated regression/corruption tests passed in GitHub Actions run 44165816726. This is an established-codec/archive policy experiment, not a new compression theorem or full RAG benchmark.

## Cross-round hypothesis

R46–47 found content-defined 512-byte framing effective for highly related historical README revisions, while R55 found whole-document Zlib smaller for independent short HotpotQA paragraphs. Can an online algorithm choose between those *existing* representations without being told the source domain or relying on a gold answer?

Mix 12 authentic pinned Astral uv README revisions and 1,276 independent source paragraphs from the first 128 SHA-locked HotpotQA distractor development questions. There are fewer than 10 candidate paragraphs in some examples; the exact source count is not padded. All bytes are real input text and every source and selected 128-byte span is verified against the original.

## Compared policies

- All whole-document Zlib, per-source SHA-256 content addressing.
- All gear512 content-defined frames, with cross-source frame reuse.
- Known-cohort control: gear512 for historically related versions, whole for independent paragraphs. This uses externally known source group metadata and is not a learned policy.
- Online minimum-incremental-storage heuristic, comparing candidate new compressed CAS payload bytes plus a fixed approximate 12 bytes per manifest frame and 35 bytes per source.
- Online read-weighted heuristic: the same incremental cost plus half the estimated compressed activation cost for one centered 128-byte source span. Selection uses source bytes and existing CAS contents only, not source labels or gold QA outcomes.

All policies use the same 32-byte content digest, exact frame manifests compressed with binary/Zlib, source readback and content validation. The three input sequences are revisions-first, independent-documents-first, and interleaved. Sampled random byte spans are keyed by SHA-256 of content rather than source position to avoid order-dependent read-query confounding.

## CI results

Representative results for history-first ordering, archive bytes inclusive of compressed payloads and complete serialized manifests:

| Policy | Archive bytes | Mean compressed bytes per 128 B sampled span | Whole document choices | Gear512 choices |
| --- | ---: | ---: | ---: | ---: |
| Always whole | 511,165 | 360.953 | 1,288 | 0 |
| Always gear512 | 521,958 | **303.630** | 0 | 1,288 |
| Known source cohort | **480,807** | 329.595 | 1,276 | 12 |
| Online storage-only | 511,165 | 360.953 | 1,288 | 0 |
| Online storage + read cost | **487,779** | **324.169** | 1,231 | 57 |

Across the other two input orders the online read-weighted footprint was 487,744 and 487,832 bytes respectively. Its measured mean traffic remained 324.169 bytes with matched content-keyed sample positions. Known-cohort totals ranged 480,799–480,827 bytes. Minor archive-size variations arise from the order of manifest metadata before compression.

The online read-weighted policy is about **4.6% smaller** than always-whole and activates about **10.2% fewer compressed bytes** for the specified random-span probe. It is not universally superior: always-gear has lower measured read traffic; known-cohort routing has smaller storage; overall system index, CPU, cache, physical disk traffic and QA answer quality are not included.

Storage-only greedy never selects gear512 because the approximate per-frame metadata charge erases the locally estimated CAS advantage, despite global shared-history gear512 compression being beneficial. This demonstrates why strictly local greedy objectives can miss collective deduplication opportunities.

## Interpretation

This is a concrete example of **joint storage/read-cost archive selection** working better than storage-only selection across a heterogeneous source mixture. The method is classical greedy cost minimization over existing lossless codecs and source CAS. The observed improvement is a measured architecture option, **not novel algorithmic state-of-the-art** or proof of compression of arbitrary datasets. The known-cohort metadata control shows a simpler operator-specified regime could outperform the online heuristic on archive bytes.

The mix comprises just one README revision history and one HotpotQA short-document sample. An adversarial mixture, varied source update stream, real historical evidence query distribution, robust Zstd and Git pack controls, and actual SSD/cache accounting are required before promoting this into a production default.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-58 -p 'test_*.py' -v
    python experiments/round-58/mixed_archive.py --out experiments/round-58/results.json

CI execution: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44165816726 . Input sources remain upstream licensed and downloaded transiently. SHA-256 digests here establish local byte consistency, not source factual authority.
