# CDG Round 99: Six Lossless Codecs at Fixed Source and FTS5 Index, Two Human-Evidence Corpora

**Date:** 18 November 2026, late evening. **Status:** nine original-source integrity and corruption tests plus full real SciFact/QASPER codec comparison PASSED [GitHub Actions 44459146764](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44459146764). Standard existing lossless compressors only. These results neither claim a novel compression algorithm nor change retrieval BM25 or evidence truth.

## Hypothesis and held-constant variables

R95 found an advantage to storing more exactly recoverable evidence under fixed budgets, and R97–R98 showed lower relative storage saving on short QASPER paragraph units than SciFact abstracts. How much of the corpus-specific storage frontier can be improved by selecting standard compressors more carefully, at **identical original source bytes and unchanged FTS5 search postings**?

Six predeclared source-blob compressors:
- Python zlib level 6.
- Standard Zstandard (python \`zstandard==0.23.0\`) levels 3 and 9.
- Standard Brotli (\`Brotli==1.1.0\`) quality 5 and 9.
- Python LZMA/XZ preset 6.

All six variants have a **single identical SQLite schema** with the existing R90 ordinary contentless FTS5 search table, same SHA-256 original source digests, source byte lengths, rowid source identity and \`docs.codec TEXT\` metadata. A common original zlib database is copied, and only its per-document compressed BLOBs and explicit codec identity are replaced before COMMIT, VACUUM and independent SHA source verification. This isolates the codec's physical page effects from source layout and indexing. A source with an incorrect codec ID is rejected, not silently interpreted under a fallback codec.

- Full original SciFact: **5,183 abstracts**, original raw source UTF8 bytes **7,792,860**, release SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.
- Original QASPER dev: **13,266 paragraphs**, raw index source text and section titles **6,721,559 UTF8 bytes**, member SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`. Note that the QASPER plain raw *paragraph-only* bytes are 6,328,953; R99's 6,721,559 also contains section titles and source-format separators.
- Source-read test probes are fixed original BM25 top-one rowid requests: **300** SciFact claim queries and **990** QASPER paper-scoped questions returning a source, replicated three times per codec for descriptive warm CPU read checks. QASPER has 1,005 questions in total, but not all return a nonempty lexical top-one.
- Every stored source is SHA-verified against original upstream source bytes, all **5,183/5,183** SciFact and **13,266/13,266** QASPER for all six codecs, before timing. SQLite core integrity, FTS internal integrity and complete aggregate FTS statistics unchanged across codec variants.
- Decoder source byte count cap: **2,000,000 B**. The Brotli decoder cannot enforce a strict output-size cap before decompressing; it is still SHA-checked and has corpus-level original byte cap validation. This is an engineering security limitation, not evidence of actual exploitation.

## Measured total source + index SQLite bytes

These byte figures **all include the extra explicit codec metadata column**. Do NOT equate R99's zlib6 SQLite footprint (9,277,440/9,900,032 B) with the smaller R90/R97 schema without that additional column.

| Codec | SciFact SQLite bytes | Source BLOB bytes | QASPER SQLite bytes | Source BLOB bytes |
| --- | ---: | ---: | ---: | ---: |
| **zlib6** | 9,277,440 | 3,719,813 | 9,900,032 | 3,897,576 |
| **zstd3** | 9,457,664 | 3,868,503 | 10,088,448 | 4,054,850 |
| **zstd9** | 9,375,744 | 3,796,658 | 10,035,200 | 4,010,977 |
| **Brotli5** | **8,949,760** | **3,442,528** | **9,490,432** | **3,495,332** |
| Brotli9 | 8,953,856 | 3,446,900 | 9,494,528 | 3,502,157 |
| lzma6 | 9,920,512 | 4,264,836 | 11,165,696 | 5,018,600 |

**[FACT]** In both corpora the smallest physical source+FTS SQLite file is **Brotli5**. It saved another **327,680 B** (SciFact) and **409,600 B** (QASPER) versus the same-schema zlib6 baseline. As a share of the *zlib6 total database*, that's about **3.53%** and **4.14%** respectively, not a 30–40% algorithmic leap.

**[FACT]** Brotli9 was slightly larger than Brotli5 in both tests despite greater computation. LZMA6 was substantially worse than the zlib6 baseline on these many relatively short independently compressed records, likely due to per-record framing and codec overhead. Do not extrapolate to monolithic large-file compression where LZMA can perform differently.

## Descriptive encoding and warm retrieval cost

One CI runner, one measurement series each; treat all timing differences as workload-specific not statistically proven throughput improvements.

| Codec | SciFact BLOB encode sec | SciFact warm SHA read median ms | QASPER BLOB encode sec | QASPER warm SHA read median ms |
| --- | ---: | ---: | ---: | ---: |
| zlib6 | 0.14299 | 0.017457 | 0.17717 | 0.013771 |
| zstd3 | **0.07117** | 0.013871 | **0.10341** | 0.013170 |
| zstd9 | 0.15476 | **0.013731** | 0.17373 | **0.013160** |
| Brotli5 | 0.22966 | 0.016835 | 0.32236 | 0.013220 |
| Brotli9 | **6.85740** | 0.017196 | **7.60731** | 0.013541 |
| lzma6 | 1.97058 | 0.031788 | 3.31665 | 0.018718 |

Brotli5's source compression encode cost was approximately **1.61×** zlib6 for SciFact and **1.82×** for QASPER in this one warm run. This does not include total index construction or hot update throughput. Brotli9 took approximately **30×** Brotli5's encoding time for both corpora, with no storage gain. zstd3 encoded source bytes fastest but stored more physical bytes. zstd9 gave the smallest warm median within this run but the advantage is extremely small and unreplicated.

The \`read_codec\` function includes SQLite source BLOB SELECT, source decompression, output byte length enforcement, SHA-256 verification and source row identity check. This is not controlled cold SSD I/O, cache eviction, concurrent-query p99 or power-loss recovery.

## Mechanistic interpretation and decision

**KEEP as an experimental choice, not a production default without further validation:** Brotli5 for relatively static source archives when persistent bytes are the dominant cost; Zstandard for cases where encoding/decoding throughput and mutable source ingest may dominate. The optimal codec is workload-specific and should be determined on target source distribution and update frequency.

**REJECT:** any claim that bigger numeric compression level is necessarily better, that generic LZMA beats all other codecs, that the relative byte saving scales to larger monolithic documents, or that lossless source codec choice improves semantic retrieval when postings and source identity are held constant.

**Open paths:** per-document codec selection based on source bytes and predicted update/read frequency, separate short-vs-long paragraph codec gates, shared dictionary zstd to reduce per-source overhead, and block-level compression with *lossless paragraph boundaries*. Those are potential research directions, not demonstrated superior here. They must be compared against a strong Brotli5 static corpus baseline, not only zlib6.

## Reproduce

\`\`\`bash
python -m pip install zstandard==0.23.0 Brotli==1.1.0
python -W error::ResourceWarning -m unittest discover -s experiments/round-99 -p 'test_*.py' -v
python experiments/round-99/codec_frontier.py --out experiments/round-99/ci-results.json
\`\`\`

Code \`experiments/round-99/codec_frontier.py\`, tests \`experiments/round-99/test_codec_frontier.py\`, workflow \`.github/workflows/cdg-r99-codec-ablation.yml\`. Original SHA locks and aggregate full CI result artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44459146764 .
