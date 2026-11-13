# Round 27: Storage Versus Source-Read Cost in Independent Zstandard Frames

**Research date:** 13 November 2026  
**Stage:** Real Zstandard compression and measured compressed-frame sizes on local CDG technical reports, with deterministic synthetic read workloads.  
**Decision:** Retain line-aware framing as a *candidate physical baseline*, not as an original compressor or a demonstrated RAG advantage. Next experiment must charge the search index and run against the authentic HotpotQA source contents with realistic request distributions.

## 1. The problem I chose to isolate

Round 25 improved complete supporting-document coverage by reading bridges. Round 26 showed that sentence selection trades source evidence preservation for modeled frame reads. However, neither established actual compressed storage or read costs on the 100-question HotpotQA sample. Before adding a complex joint evidence-layout planner, I wanted to test a simpler question: **is aligning compression frame boundaries to retrieval units sufficient to reduce decompression work, and what permanent storage cost does that incur?**

The comparison deliberately includes a lower-bound storage-oriented baseline, whole-document Zstandard, and conventional independent fixed-size frames. A line-aware layout is a crude approximation to source-aligned evidence units. None of these layouts is a novel compression algorithm. Real disk reads, NVMe queueing, page cache behavior, frame seeking, title lookup and verification are still outside this isolated test.

## 2. Data and exact experiment

Five existing CDG Markdown research reports were read as byte-for-byte local UTF-8 source files: Round 19 report, Rounds 20–22 appendices, and Round 26 report. Combined uncompressed size: **90,163 bytes**. SHA-256 digests and individual sizes are embedded in `results.json`. This is **not HotpotQA**. These documents share style and terminology, and therefore cannot stand in for multilingual, code-heavy, scientific-PDF or large web corpora.

A seeded workload (`seed=27026`) samples **250** two-span requests from source lines of at least 40 bytes. Every third query chooses a nearby second line when available; the others use a randomly sampled other line. The second workload retains the same construction but requests short interior subspans, averaging 85.7 requested raw bytes instead of the 424.0-byte average in the whole-line workload. These are synthetic query locations. They are **not inferred from independent user questions**, and alignment to line boundaries is a known advantage for the line-aware layout.

All source bytes are losslessly compressed with actual `libzstd` (Zstandard level 3) through `ctypes` and decoded to check equality. Frames are independent. The layout choices are:

- `whole`: one compressed stream per report;
- `fixed:B`: contiguous independent frames with raw capacity B bytes;
- `line_aligned:B`: greedily pack complete source lines into frames of at most B bytes, splitting a line only when it exceeds B.

Each frame has a **modeled 16-byte sidecar entry** (raw starting offset, compressed starting offset, compressed length); this sidecar was not serialized or measured. The retrieval program knows the exact source span coordinates in advance, so retrieval scores, a sentence-coordinate index, metadata lookups, query planning and frame-file seeks are not charged. Physical read traffic is measured as the sum of selected independently compressed frame payload lengths, not actual bytes transferred by an SSD. Duplicate frames within a query are only counted once per source. Each requested span is reconstructed exactly from the decompressed selected frames, including Unicode bytes.

## 3. Results: whole-line source span workload

| Layout | Compressed payload + modeled 16B/frame table | Mean compressed payload per request | Mean frames decoded | Observed median warm decode+extract (μs)* |
|---|---:|---:|---:|---:|
| Whole document | 39,412 B | 12,671 B | 1.52 | 60.3 |
| Fixed 128 B | 87,599 B | 552 B | 5.19 | 60.3 |
| Line-aligned 128 B | 92,391 B | 396 B | 4.26 | 48.0 |
| Fixed 256 B | 71,395 B | 644 B | 3.55 | 40.9 |
| Line-aligned 256 B | 74,898 B | 411 B | 2.80 | 39.0 |
| Fixed 512 B | 62,338 B | 855 B | 2.65 | 37.4 |
| **Line-aligned 512 B** | **64,722 B** | **540 B** | **2.11** | **35.5** |
| Fixed 1,024 B | 55,260 B | 1,247 B | 2.13 | 27.8 |
| Line-aligned 1,024 B | 56,624 B | 945 B | 1.85 | 26.8 |
| Fixed 2,048 B | 50,045 B | 2,002 B | 1.88 | 30.3 |
| Line-aligned 2,048 B | 50,799 B | 1,763 B | 1.75 | 30.4 |
| Fixed 4,096 B | 46,409 B | 3,457 B | 1.74 | 34.8 |
| Line-aligned 4,096 B | 46,660 B | 3,212 B | 1.69 | 34.2 |

*The timings are single-run Python-level **warm, in-memory decompression plus extraction**, excluding file I/O, search, metadata lookup, and concurrency. Do not treat differences of a few microseconds as statistically robust. The actual compressed frame payload lengths are measured, but archive tables are modeled.*

At 512 bytes, line-aware framing adds **2,384 B** to archive+table storage relative to fixed framing (64,722 vs 62,338 B), while reducing mean compressed payload fetched by **314.8 B per request** (540.0 vs 854.8 B), a **36.8% decrease**. It also activates fewer uncompressed bytes (852 vs 1,344 B). Compared to whole-document compression, every fine-grained option greatly expands stored bytes in exchange for dramatically reducing the compressed bytes needed for a targeted request.

## 4. Sensitivity: shorter subspans within lines

This control reduces direct alignment advantage by selecting interior pieces of lines rather than their entire lines. At 512 bytes, fixed framing retrieves **684.4 compressed bytes/request** on average, while line-aware framing retrieves **519.1 B/request**. At 256 bytes the values are **426.1** and **321.9 B/request**; at 1,024 bytes they are **1,105.5** and **973.9 B/request**. The line-aware gain persists in this generated workload, but decreases at larger frames. It is still not evidence of transfer to unseen natural QA questions.

## 5. The decision rule is a workload-weighted cost inequality

Suppose layout A uses persistent bytes \(S_A\), with expected compressed payload per query \(R_A\), and layout B has \(S_B, R_B\). A stylized cost is

\[
J(L)=\alpha S_L + N\,\beta\,\mathbb E[R_L(q)] + N\,\gamma\,\mathbb E[T_\mathrm{decode}(q,L)] + C_\mathrm{index}(L)+C_\mathrm{updates}(L),
\]

where \(N\) is the expected number of requests during the archive's useful lifetime and \(\alpha,\beta,\gamma\) convert storage, read traffic and CPU time into comparable costs. There is **no universal optimal frame size**. The experiment supplies two isolated inputs, \(S_L\) and an approximate \(\mathbb E[R_L]\), but does not determine the weights or full overhead.

For the 512-byte pair, the ratio \((S_\mathrm{line}-S_\mathrm{fixed})/(R_\mathrm{fixed}-R_\mathrm{line})\) is **7.6 queries**, *only if* one chooses identical cost weights per stored byte and per compressed byte retrieved, and ignores indexes, CPU, updates and latency. This is **not** a measured economic amortization threshold. SSD/storage pricing, IOPS and read amplification do not justify setting these weights equal.

A useful graph-of-thoughts connection emerges: evidence completeness has complementary AND requirements, while physical frame cost is a union over overlapping source-coordinate intervals. If the index stores query-relevant span coordinates and frame IDs, the runtime can estimate incremental frame activation, but those index entries have their own persistent and query-time cost. Optimizing activation alone is therefore incomplete.

## 6. Failure modes and algorithmic boundaries

1. **Layout leakage:** synthetic target spans are selected from lines in the source text, so line boundary knowledge helps. We include subspan sensitivity, but must eventually use real evidence spans from naturally authored queries.
2. **Storage inflation:** at 128 B, line alignment nearly doubles the archive+table size versus a 39.4-KB whole-document compression baseline.
3. **Metadata undercounting:** 16 bytes per frame is a declared hypothetical table, not a serialized index. Source IDs, ACLs, timestamps, sentence offsets, citation receipts and update logs would increase costs.
4. **Oracle coordinates:** the physical benchmark is given correct byte intervals. It says nothing about the cost of finding evidence. No human or model bridge extractor was evaluated here.
5. **No held-out generalization:** a five-report research notebook is a small convenience corpus. Results may reverse for other text distributions, long lines, HTML, short paragraphs, or code.
6. **No authenticated provenance or semantic guarantees:** byte equality establishes only lossless reconstruction. It does not prove retrieved claims, source independence, or current authority.
7. **Measurement noise:** in-memory warm decode timings depend on Python overhead, CPU scheduling and run order. Claim compression and payload sizes, not SSD latency dominance.

## 7. Practical hypothesis revisions

**H27-A (retain):** A source-unit-aware *physical layout* can lie on a better read-bytes frontier than naive fixed frames, provided requested spans align with its units. This is standard access-aware physical database/storage design, not a novelty finding.

**H27-B (downgrade):** Tiny independent frames are not a free win. They spend large amounts of compression efficiency and metadata. The useful unit depends on workload and storage constraints.

**H27-C (new experiment):** Instead of committing to line boundaries globally, measure the distribution of verified evidence span coordinates and *co-access* pairs on an independent corpus. Choose a constrained family of layouts using training queries only, then evaluate storage+I/O+accuracy on a disjoint set. A simple greedy merge or dynamic programming baseline is mandatory. No claim of a new optimum until competing storage-layout literature is audited.

**H27-D (required adversarial test):** Version update, ACL scope change and mutable source re-serialization must invalidate cached span/frame receipts; a byte hash does not substitute for source authority. Evaluate update amplification and stale-index refusal.

**H27-E (kill threshold):** A learned evidence graph planner is unnecessary unless it beats conventional BM25+link expansion plus source-aligned seekable compression on full, matched cost accounting. If no win emerges, focus the paper on a carefully measured negative result or a compact source-receipt mechanism.

## 8. Reproduction and audit

```bash
python experiments/round-27/storage_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round26.md \
  --output results_wholeline_reproduced.json
python experiments/round-27/storage_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round26.md \
  --span-style subspan --output results_subspan_reproduced.json
python -m unittest discover -s experiments/round-27 -p 'test_*.py' -v
```

Source file hashes and sizes are in each result JSON, so a different report snapshot is identifiable. The five exact sources are in earlier archives or can be supplied separately, and are **not copied into Round 27**. Seven unit tests passed after fixing two test-fixture assumptions and correcting empty-span activation. The measured results were generated in Linux with Python 3.13 and `libzstd`; `results.json` and `results_subspan.json` preserve both workloads. The scripts do not download or alter any user data.

## 9. Round 28 preregistration

**P0:** Obtain official HotpotQA paragraph and annotation bytes locally; pin checksum and freeze a disjoint train/test split. **P1:** build a genuine source-aligned frame container plus serialized offset/seek tables and a conventional query-conditioned link index, not just a modeled sidecar. **P2:** run actual cold/warm file-backed reads and decode timings on a defined host, including p50/p95 with repeated randomized order. **P3:** measure complete *annotated sentence* recall at matched prompt/index/read costs. **P4:** add version-change and stale-frame invalidation tests. **P5:** drop the custom controller if a standard line-/paragraph-framed Zstandard index achieves equal quality at lower overall cost.

**Decision:** Round 27 yields an actual compressed-byte trade-off and a reproducible physical-layer prototype, **not** an improved RAG system or a publishable new compression method.