# CDG Round 101: Lossless QASPER Source Blocks with Original Paragraph Receipts

**Date:** 19 November 2026. **Status:** PASS, ten regression tests plus original SHA-pinned QASPER full source audit and end-to-end stored original-source reads in [GitHub Actions run 44469414546](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44469414546).

## Research question

Rounds 97–100 established ordinary contentless FTS5 plus per-document Brotli5 as a useful static baseline for QASPER. Source archiving may save more if neighboring paragraphs from the **same original research paper** share one compressed frame. But that could increase random-access decompression and update costs. Round 101 tests the **physical source+FTS SQLite byte savings** and **decoded-byte read amplification** for six predeclared group sizes, keeping each paragraph's original source identity, UTF-8 content, citation/receipt offsets, and original FTS5 index unchanged.

This is a block-compression and source mapping systems technique using existing SQLite and Brotli5. It is **not** a new compression algorithm or a semantic retrieval improvement.

## Frozen data and experimental isolation

- Source corpus: **13,266** original paragraphs from **281** QASPER v0.3 development papers; **1,005** original questions; **888** with one or more human evidence paragraphs exactly matched to the original source. Official original dev JSON SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`.
- All variants use **identical** ordinary contentless SQLite FTS5 postings, source rowids, document IDs, paper IDs, original indexed title/abstract, query words and paper-scoped BM25. The index is constructed once and only source storage is replaced. FTS5 \`integrity-check\` and original global statistics match for every variant.
- Strong per-paragraph reference: Round 99's **uniform Brotli quality 5**, one independent compressed source BLOB per paragraph, same original source SHA and source length. Total original source+index SQLite file **9,490,432 B**.
- Group candidates: **1, 2, 4, 8, 16 paragraphs**, or **the entire original paper**. Groups cannot cross paper IDs; no gold evidence labels or query text influence boundary selection. Bytes of section title and exact paragraph are concatenated without modification in order.
- Group SQLite schema includes a \`source_blocks\` table (block ID, paper ID, Brotli5 BLOB, SHA256, full raw byte length, paragraph count) and \`source_receipts\` (original source rowid, document ID, block ID, byte offset, original UTF-8 length, SHA256). The entire stored SQLite footprint includes this source block metadata and all unchanged FTS postings. Individual reads require a verified block and verified paragraph offset/hash/identity.
- Ten deterministic tests cover paper-boundary enforcement, complete row identity permutation, group=1, entire paper, original source receipts, corrupted compressed block, corrupted byte offsets, wrong-paper block reassignment, per-query decompression cache, and end-to-end retrieval parity.
- Two read workloads on the real QASPER ranked results:
  - **Top 1:** **990** queries return at least one source, single original paragraph per query.
  - **Top 10:** **8,856** original source requests across 1,005 questions. For grouped storage, blocks can be decoded once per *query* and reused for subsequent retrieved source paragraphs in that query. No cache across separate queries; SQLite/OS caches naturally remain warm.
- Decoder byte amplification = **sum of UTF-8 bytes from all actually decompressed source blocks** / **sum of UTF-8 bytes in requested original paragraph receipts**. This is *in-memory decompression volume*, NOT compressed SSD reads, disk page amplification, physical network traffic, or total model prompt tokens.

## Observed source+FTS storage and original source amplification

| Original paragraph group size | SQLite source+index B | Saving vs independent Brotli5 B | Source blocks | Top1 byte amplification | Top10 byte amplification |
| --- | ---: | ---: | ---: | ---: | ---: |
| Independent Brotli5 reference | **9,490,432** | 0 | 13,266 | **1.000×** | **1.000×** |
| Group of 1, with separate block/receipt metadata | 10,264,576 | **-774,144** (worse) | 13,266 | 1.000× | 1.000× |
| Group of 2 | 9,510,912 | **-20,480** (worse) | 6,706 | 1.981× | 1.528× |
| Group of 4 | 9,113,600 | **376,832** | 3,428 | 3.911× | 2.223× |
| Group of 8 | 9,150,464 | **339,968** | 1,785 | 7.355× | 2.966× |
| Group of 16 | 8,990,720 | **499,712** | 960 | 13.596× | 3.601× |
| **Whole original paper** | **7,999,488** | **1,490,944** | **281** | **40.069×** | **4.231×** |

**[FACT]** The **whole-paper** blocks gave the smallest source+index SQLite archive on this original source set: a **15.71%** byte reduction beyond uniform per-source Brotli5. At rank 1 this forces reading/decompressing an average **40.07×** the requested original source bytes, because an entire paper's evidence block must be inflated to locate a single paragraph.

**[FACT]** Size reductions are **nonmonotone**: group of 8 is slightly larger than group of 4; group of 2 is still worse than individual source storage. This shows SQLite metadata, block framing and compression interaction matter. It is invalid to claim every increase in group size strictly improves compressed bytes.

**[FACT]** A per-query block reuse policy avoids repeatedly decompressing already decoded paper blocks for top-ten evidence. Whole-paper grouping performed **990** block decompressions to serve all **8,856** top-ten original source receipts, compared with **8,856** independent Brotli5 decompressions. That is still **4.231×** the requested paragraph UTF-8 bytes because whole-paper decoding loads other paragraphs.

### Descriptive warm latency, not a cold-SSD result

| Source method | Top1 full original source-probe seconds | Top10 full probe seconds |
| --- | ---: | ---: |
| Individual Brotli5 | **0.01787** | **0.14378** |
| Group 4 | 0.03438 | 0.21340 |
| Group 8 | 0.04291 | 0.21138 |
| Group 16 | 0.05666 | 0.20559 |
| Whole-paper | **0.10520** | **0.18384** |

Top-one whole-paper receipts were about **5.9× slower** in this one warm runner when measured across query loops (0.10520 / 0.01787) while saving 1.49 million persistent bytes. Whole-paper top-ten all-evidence requests were around **1.28× slower** in this runner (0.18384 / 0.14378), benefiting from within-query reuse. Do not treat these as replicated hardware latency estimates or SSD/device-bound results.

An earlier easy mistake would be to compare per-receipt median latency across caching modes: group=paper top10 individual receipts often reuse a decompressed block and are very fast, but those medians hide the expensive first block inflation. We therefore report **whole query-probe wall time** alongside original byte amplification and block decompression count.

## Retrieval and scientific interpretation

The original index and source identities are identical across all groups. Human-annotated evidence paragraph Recall@1 stays **229/888**, and Recall@10 stays **664/888**; grouping the source does not invent better semantic evidence. All **13,266** source records were reconstructed and SHA checked, with 8,856 real retrieved source receipts per top10 workload per group.

The result establishes a **storage versus decompression-amplification Pareto tradeoff**. It suggests adaptively using small independent blocks for low-k random access and large paper blocks for broad within-paper multi-evidence retrieval, but the ideal selection and caching policy is **not proven** by this experiment. Cache size, FTS postings, metadata, write amplification, source updates and cold I/O must all enter a future joint optimization.

## Not shown

- No new compression mathematics, no generated-answer factuality, no hallucination suppression and no answer-level human judgment.
- No measured physical disk reads, cold SSD cache misses, network transfer, model context length or GPU memory.
- No true append/update, simultaneous reader/writer, transactional power-loss or re-compression cost. A paragraph edit currently forces rebuilding its entire block.
- Brotli decompression validates SHA and expected decoded length **after decoding**, not with an internal memory-limited streaming API.
- One QASPER original corpus and one code-path; results may change with document length, codec, dictionary and passage-granularity distributions.

## Next falsifiers

1. Test trained, **fully charged shared Zstandard dictionaries** at per-paragraph granularity against the strong Brotli5 single-source baseline. One global dictionary must be persisted in the same SQLite file, and training CPU cost measured. Do not train on dev gold evidence labels.
2. Test original-article block reads with **max block byte size** and varying block boundaries, not only fixed paragraph count. Compare at matched total archive size or decompression-amplification budget.
3. Add **transactional revision** and block-repair semantics, with source ID and original receipt integrity.
4. Once complete-source reconstruction is stable, use paper-grouping storage under a **binding** archive budget and independent human evidence retrieval, compared with previous strong per-paragraph Brotli5.

## Reproduction

\`\`\`bash
python -m pip install Brotli==1.1.0
python -W error::ResourceWarning -m unittest discover -s experiments/round-101 -p 'test_*.py' -v
python experiments/round-101/paper_block_brotli.py --out experiments/round-101/ci-results.json
\`\`\`

Files \`experiments/round-101/paper_block_brotli.py\`, \`experiments/round-101/test_paper_block_brotli.py\`, workflow \`.github/workflows/cdg-r101-paper-blocks.yml\`. Verified exact-head CI and aggregate JSON artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44469414546 .
