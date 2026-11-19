# CDG Round 100: Per-Document Codec Selection versus Uniform Brotli5

**Date:** 18 November 2026 local late evening. **Status:** nine lossless codec-choice regression tests and full source-locked SciFact/QASPER seven-policy ablation PASSED in [GitHub Actions 44459692297](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44459692297).

## Research hypothesis

Round 99 tested six existing source codecs on the same original FTS5 source index and found **Brotli quality 5** had the smallest **whole-source+index SQLite file** on both SciFact and QASPER. Could assigning a codec to each individual source document, optionally preferring faster codecs unless Brotli saves a fixed number of bytes, outperform the best global single-codec reference **after physical SQLite page rounding and metadata**?

Seven fixed deterministic policies were evaluated on each of two original SHA-locked corpora, with **all FTS5 postings and original source bytes unchanged**. Policies consult only unlabelled source content and the compressed source length, never training or development claims/labels:
- Entire source store zlib6, zstd3 or **Brotli5**.
- Choose smallest compressed payload among zlib6/zstd3/Brotli5 for **each source**.
- Prefer zstd3 unless Brotli5 saves at least 64 or 128 source bytes.
- Prefer zlib6 unless Brotli5 saves at least 64 source bytes.

Every SQLite archive has an explicit per-row codec identity column and identical source+FTS schema, so no mixed-format system receives hidden metadata free of charge. Candidate-compression encoding effort is accounted for using a common measured original-data pass for each codec, summed for the candidates required by that policy. This is an **encoding-cost estimate** for a real ingestion system, not a separately timed end-to-end ingest for every policy.

## Full original SciFact evidence archive

Source SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`; 5,183 original SciFact source docs; fixed 300 top-one source read probes repeated 3 times per codec.

| Source policy | Total persisted source+index bytes | Source BLOB bytes | Source codec mix | Candidate encode calls | Encode pass seconds |
| --- | ---: | ---: | --- | ---: | ---: |
| all zlib6 | 9,277,440 | 3,719,813 | 5,183 zlib | 5,183 | 0.20015 |
| all zstd3 | 9,457,664 | 3,868,503 | 5,183 zstd | 5,183 | 0.09588 |
| **all Brotli5** | **8,949,760** | 3,442,528 | **5,183 Brotli** | **5,183** | **0.34160** |
| Per-source min of 3 | **8,949,760** | 3,442,406 | 5,168 Brotli + 15 zlib | 15,549 | 0.63762 |
| zstd unless Brotli saves 64 B | 9,011,200 | 3,506,806 | 3,931 Brotli + 1,252 zstd | 10,366 | 0.43747 |
| zstd unless Brotli saves 128 B | 9,392,128 | 3,824,751 | 288 Brotli + 4,895 zstd | 10,366 | 0.43747 |
| zlib unless Brotli saves 64 B | 9,121,792 | 3,601,108 | 1,455 Brotli + 3,728 zlib | 10,366 | 0.54175 |

**[FACT]** Per-source min saves only **122 compressed BLOB bytes** across 5,183 docs versus all Brotli5. SQLite page rounding absorbs the difference: **zero additional physical source+index file bytes saved**, despite requiring 3× codec candidate encodes and a larger measured total candidate encode pass cost. No source-reader semantic or FTS ranking changes result.

## Independent QASPER paragraph source archive

Original QASPER dev member SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`; 13,266 original source paragraphs; 990 fixed top-one source probes, each repeated three times.

| Source policy | Total persisted source+index bytes | Source BLOB bytes | Source codec mix | Candidate encode calls | Encode pass seconds |
| --- | ---: | ---: | --- | ---: | ---: |
| all zlib6 | 9,900,032 | 3,897,576 | 13,266 zlib | 13,266 | 0.24600 |
| all zstd3 | 10,088,448 | 4,054,850 | 13,266 zstd | 13,266 | 0.13962 |
| **all Brotli5** | **9,490,432** | 3,495,332 | **13,266 Brotli** | **13,266** | **0.45069** |
| Per-source min of 3 | **9,486,336** | 3,495,129 | 13,174 Brotli + 73 zlib + 19 zstd | 39,798 | 0.83631 |
| zstd unless Brotli saves 64 B | 9,842,688 | 3,830,380 | 2,757 Brotli + 10,509 zstd | 26,532 | 0.59031 |
| zstd unless Brotli saves 128 B | 10,084,352 | 4,047,814 | 48 Brotli + 13,218 zstd | 26,532 | 0.59031 |
| zlib unless Brotli saves 64 B | 9,842,688 | 3,838,967 | 760 Brotli + 12,506 zlib | 26,532 | 0.69669 |

**[FACT]** Per-source min saves only **203 compressed source BLOB bytes**, which translate into **4,096 persisted database bytes** (one SQLite page) on QASPER, despite 3× codec candidate encodes and nearly 2× measured candidate codec encode seconds compared with uniform Brotli5. This is not a useful total-storage breakthrough.

## Original source identity, metadata and warm cost

Every original source across both corpora is fully SHA-verified against its upstream canonical bytes under every policy, with SQLite core integrity and global FTS statistics unchanged. Each static source codec outcome contains original identity, exact output bytes and explicit source codec, so there is no silent lossy reconstructor.

This one runner's warm reading timings are noisy and differ from Round 99. Do **not** promote a policy based on sub-millisecond latency differences, which are measured serially without cold-cache or background-load control. No concurrent updates, power-loss recovery of mixed codec transactions, real memory peak or background rebuild costs are evaluated here.

## Decision

**KEEP:** uniformly encoded Brotli level 5 as the current **static source archive** baseline for original SciFact and QASPER; continue using SHA-verified original source bytes and exact FTS posting data. The existing R90 update and recovery APIs still assume zlib6 and have NOT been upgraded to use mixed codecs; avoid any production claim until a new versioned source representation and corresponding crash tests exist.

**REJECT:** per-document min of tested standard codecs as a priority optimization. It adds substantial ingestion complexity and estimated encoding work for effectively no physical storage gain. Higher-level compression decisions such as *shared dictionary across related sources*, *lossless grouped paragraph blocks with original boundary receipts*, or *relevance-aware retention under joint byte and context token budgets* are more promising than per-row choosing among these three compressors, but they are untested hypotheses.

**NOT SHOWN:** any novel compression mathematical method, semantic grounding improvement, generated answer hallucination reduction, target-machine throughput result, or independent new benchmark beyond the two published source corpora.

## Reproduction

\`\`\`bash
python -m pip install zstandard==0.23.0 Brotli==1.1.0
python -W error::ResourceWarning -m unittest discover -s experiments/round-100 -p 'test_*.py' -v
python experiments/round-100/adaptive_codec.py --out experiments/round-100/ci-results.json
\`\`\`

Code \`experiments/round-100/adaptive_codec.py\`, tests \`experiments/round-100/test_adaptive_codec.py\`, workflow \`.github/workflows/cdg-r100-adaptive-codecs.yml\`. Full verified CI and aggregate results artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44459692297 .
