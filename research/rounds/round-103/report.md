# CDG Round 103: Out-of-Article Trained Dictionary × Source Block Storage-Access Frontier

**Date:** 19 November 2026. **Status:** PASS, eleven source and dictionary integrity, cross-paper boundary, tamper and Pareto regression tests plus official full QASPER train/dev archive benchmark verified in [GitHub Actions 44470893755](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44470893755).

## Question

R101 found that grouping original related QASPER paragraphs under Brotli5 saved substantial static storage, at the cost of decompression-byte read amplification. R102 found that a Zstandard dictionary trained **only on distinct QASPER TRAIN articles** improved compression on independently encoded QASPER DEV paragraphs, without read amplification.

Would **composing these two existing methods** move the physical source+index storage versus original-source access-cost Pareto frontier, rather than merely add algorithmic complexity? Which compositions are demonstrably dominated?

This is not novel compression mathematics, a new search algorithm, or answer-level hallucination mitigation. The question is systems co-design and verified tradeoffs.

## Frozen corpus and methods

- Original QASPER v0.3 official source train SHA256 \`9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4\`; dev SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`.
- **888** original train papers, **281** development papers, zero overlapping paper IDs. A single dictionary trained on **4,096 source-only TRAIN paragraphs**, selected by predeclared hashed original source IDs. **64 KiB** stored source dictionary, source annotation/QA labels and DEV texts excluded from training.
- Full QASPER development data: **13,266** original source paragraphs, **1,005** original questions, with **888** questions containing at least one exact human-annotated text evidence paragraph. All original UTF-8 paragraph receipts verified byte-exact against upstream, all FTS5 search postings unchanged.
- Source groups never cross original paper IDs; six group choices: 1/2/4/8/16 paragraphs or entire paper. Three codec choices with **identical grouped block+offset SHA receipt table schemas:** Brotli5; Zstd level 3 + original TRAIN dictionary; Zstd level 9 + original TRAIN dictionary. This yields **18** full source+index grouped archives, plus strong **three per-paragraph references** independently re-evaluated with uniform Brotli5 and dictionary-backed zstd3/9.
- Original FTS5 BM25 title5/body1 source posting data, source identity and all 1,005 top-ten rankings unchanged. All SQLite file-byte comparisons include source offsets, block IDs, source SHA digests, block SHA digests, dictionary metadata and **actual stored dictionary BLOB bytes**. No external uncharged dictionary.
- Access: 990 original QASPER questions return at least one source; grouped archives use a block cache only **within the same question**, not between questions, for top-one and top-ten source requests. Decoded-byte amplification counts total original uncompressed bytes actually inflated from blocks relative to requested original paragraph bytes. It is **not physical compressed SSD I/O**.

## Strong individually compressed source references

| Source record codec | Physical SQLite source+index bytes | Top-one decoded-byte amplification |
| --- | ---: | ---: |
| Independent Brotli5 | 9,506,816 | 1.000× |
| Independent zstd3 with 64 KiB train-only dictionary | 8,798,208 | 1.000× |
| **Independent zstd9 with 64 KiB train-only dictionary** | **8,687,616** | **1.000×** |

These reference archives include a different **individual source metadata schema** than the grouped block+receipt archive, but both charge all actual metadata and dictionary bytes. They are valid complete implementation comparisons, not an identical-schema isolated codec control. The same grouped-schema comparisons below isolate the codec.

## Eighteen original source block variants, physical bytes and source amplification

Source-group sizes are fixed before measurement. Read amplification is independent of codec *for identical block composition* because every codec produces the same original uncompressed block bytes.

| QASPER original paragraph block size | Brotli5 archive B | zstd3/dict archive B | zstd9/dict archive B | Top1 decoded-byte amplification | Top10 decoded-byte amplification |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 10,268,672 | 9,588,736 | **9,478,144** | 1.000× | 1.000× |
| 2 | 9,515,008 | 8,941,568 | **8,773,632** | 1.981× | 1.528× |
| 4 | 9,117,696 | 8,679,424 | **8,474,624** | 3.911× | 2.223× |
| 8 | 9,154,560 | 8,712,192 | **8,454,144** | 7.355× | 2.966× |
| 16 | 8,994,816 | 8,863,744 | **8,593,408** | 13.596× | 3.601× |
| Whole original paper | 8,003,584 | 8,024,064 | **7,811,072** | 40.069× | 4.231× |

**[FACT]** zstd9 with a single independently trained dictionary had the smallest physical source+index SQLite archive of the three codecs at all six tested original paragraph group sizes. Group-of-4 zstd9/dict saved **212,992 B** beyond the strong independently decodable zstd9 dictionary archive, but required **3.91×** decompressed original source bytes for top-one retrieval. The all-paper zstd9/dict archive saved **876,544 B** beyond independently compressed zstd9/dict, but required **40.07×** top-one source byte inflation.

**[FACT]** Composing methods does not monotonically improve performance: zstd9-dict group **16** is **139,264 B larger** than group **8**, and has strictly worse decoded-byte amplification at both top1 and top10. It is therefore **dominated** by the group-of-8 design in a deterministic cost space of (physical static SQLite bytes, top1 decoded-byte amplification). Increasing group size without considering metadata and internal compressor behavior is not justified.

**[FACT]** Whole-paper **zstd3/dict** was **20,480 B larger** than whole-paper Brotli5 on this original source set; Zstd is not automatically smaller on every grouped compression workload despite being superior for each document's own independently trained dictionary mode.

## Measured non-dominated physical-storage / top1-amplification candidates

The Pareto test uses only exact persisted SQLite bytes and exact decoded-byte amplification, *not* approximate latency or generated answer quality. Across these 21 experiments the strict non-dominated points were:

| Implementation | Total database bytes | Top1 source byte amplification | Top10 source byte amplification |
| --- | ---: | ---: | ---: |
| Individual zstd9/dict | **8,687,616** | **1.000×** | 1.000× |
| 4 paragraph zstd9/dict | **8,474,624** | 3.911× | 2.223× |
| 8 paragraph zstd9/dict | **8,454,144** | 7.355× | 2.966× |
| Whole paper zstd9/dict | **7,811,072** | 40.069× | 4.231× |

No group=2 or group=16 variant remained nondominated once the **strong individual zstd9/dict** and other group-size references were included. This is a useful negative result because grouping a few paragraphs can add more metadata/decompression than the bytes it saves.

Warm top-one original source query-probe walls for the grouped zstd9/dict arms in this single CI runner were approximately **0.0256 s** group1, **0.0268 s** group2, **0.0292 s** group4, **0.0330 s** group8, **0.0396 s** group16, and **0.0635 s** whole-paper, on the same 990 queries. These values are descriptive, sequential and cache-dependent, *not statistically defensible latency ratios or cold SSD physical reads*. Independent source arms were compared on decoded bytes rather than matched identical stopwatch paths to avoid overclaiming.

## Structural and provenance protections

Eleven regression tests cover independent-article dictionary training, exact original source SHA readback, charged dictionary bytes, unknown codec rejection, bad source receipt offset, corrupt dictionary, wrong-paper block receipt, corrupt block digest, query-local cache, unchanged original gold evidence and BM25 ranks on small fixture, and train/dev article ID overlap rejection.

The grouped archive is a static reconstruction. This round does **not** prove atomic updates, recovery after power loss, old-text FTS5 deletion correctness on repeated source revisions, memory-constrained Brotli pre-inflate, or safe network filesystem use. These are separate risks that must be addressed before a production-quality implementation.

## Scientific interpretation and next falsification

**KEEP:** the explicit joint source+index physical-byte / independently decoded-source amplification frontier. It couples retrieval access patterns to compression granularity, document/article boundary provenance and shared-dictionary compression. These components are standard prior art, so any new research claim must establish a novel allocation algorithm, stronger baseline comparison, or deployment result beyond this composition.

**NEXT:** (1) implement atomically updated versioned grouped block receipts with exact original FTS old-text deletion and SHA verification, including process-kill recovery and WAL snapshot consistency; (2) optimize chunk boundaries by source byte size and estimated query access patterns rather than fixed paragraph count; (3) evaluate the archived source frontier under a real fixed-cost context/compute budget and generated-answer annotations.

## Reproduction

\`\`\`bash
python -m pip install Brotli==1.1.0 zstandard==0.23.0
python -W error::ResourceWarning -m unittest discover -s experiments/round-103 -p 'test_*.py' -v
python experiments/round-103/joint_group_dictionary.py --out experiments/round-103/ci-results.json
\`\`\`

Code \`experiments/round-103/joint_group_dictionary.py\`, eleven tests \`experiments/round-103/test_joint_group_dictionary.py\`, workflow \`.github/workflows/cdg-r103-joint-source-frontier.yml\`. Verified exact-head source SHA, original retrieval parity and complete aggregate results in https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44470893755 .
