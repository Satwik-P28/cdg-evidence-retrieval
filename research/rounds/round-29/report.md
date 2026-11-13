# Round 29: From Actual Text Queries to Compressed Source Receipts

**Date:** 13 November 2026  
**Status:** Executed local, file-backed retrieval and compressed-frame read benchmark; six regression tests passed. Mechanically source-derived queries; no human QA judgment, learned bridge policy, version-gated live reads, independently held-out split, or cold SSD measurement.  
**Decision:** The physical retrieval loop is operational. Reject the inference that minimum read traffic implies minimum latency. Defer any new graph-controller claim until a query-conditioned, independent multihop dataset can be run on the same engine.

## Research question and relevance to previous rounds

Round 25 found that a simple observed-title bridge improved *document*-level evidence recovery on 100 HotpotQA-derived questions. Round 26 demonstrated that selective sentence access can lose supporting facts, while smaller independent frames lower a modeled raw-byte read proxy. Round 27 measured Zstandard frames on research reports, and Round 28 physically implemented `os.pread` plus SQLite-serialized source offsets, but its queries started with gold source coordinates rather than real search results.

**Round 29 removes that last coordinate oracle from the physical retrieval stage.** A query is issued to a live FTS5 index, which returns line IDs and stored original-source byte coordinates; only then does the engine locate and decode compressed frames and reconstruct exact original bytes. Source-receipt correctness is thus evaluated independently from the selected output's semantic relevance.

This is a conventional SQLite + independent-Zstd-frame system, not a new compressor. No novel relation predictor is trained or claimed. The *measured* engineering contribution of this round is integrating the full query-to-receipt path and charging FTS lookup + frame materialization in timing.

## Source files and query generation

Five previous local reports, **88,679 original bytes**, with pinned SHA-256 hashes in `results.json` and the baseline Round 28 report. Each document is indexed by line; the raw index retains source ID, source version, source hash, line ID, byte start/end and text. Search uses SQLite FTS5 `bm25(lines_fts)` with an OR query over two terms. Gold target-line coordinates are held back from the retriever and used *only to evaluate* whether the target line was among the returned results.

The 158 deterministic tasks were generated from report lines of 90–650 bytes with at least seven non-stopword tokens. Two terms were selected from the target line, with at most approximately equal allocation per file. The selection was seeded at 29026. **The task labels leak into the query-generation process**, making this diagnostic intentionally much easier than authentic QA. It cannot estimate RAG retrieval recall, hallucination, or source semantic sufficiency. It also does not assess complete multi-document witnesses; each constructed task has one gold line. The method does not secretly feed gold offsets to `FTS5` or to the frame decoder; the held-out part is coordinates, *not query formation*.

## Measured end-to-end local storage experiment

Each layout has a physical `frames.zst` file and a real SQLite database with a source table, frame table, line-coordinate table and FTS5 virtual table. 158 tasks were queried three times in shuffled order per layout, resulting in **474 query-and-read measurements** per layout. Only the top three FTS hits are materialized. Any frame reused inside one selected source line is counted once for that `read_spans` call; repeated hits across different rows are not shared through an explicit application cache. Reconstructed bytes were compared with the original files. Five candidates were returned for recall measurement, although only the top three were decoded.

| Layout | Persistent payload + SQLite B | Mean compressed payload read / query B | Full warm p50 μs | Full warm p95 μs |
|---|---:|---:|---:|---:|
| Whole-document Zstd | 272,161 | 23,369.2 | 185.4 | 271.6 |
| Fixed 512-byte frames | 291,755 | 1,372.7 | 139.0 | 221.0 |
| Line-aligned 512-byte frames | 301,449 | **825.7** | 140.1 | 244.8 |
| Fixed 2,048-byte frames | 281,795 | 3,531.6 | **126.8** | **166.1** |
| Line-aligned 2,048-byte frames | 282,433 | 2,971.4 | 127.0 | 229.0 |

For all layouts, **exact target-line retrieval is 60.76% @1, 94.30% @3 and 97.47% @5**. This is a line-identity benchmark; a different relevant line returned by FTS counts as incorrect. The identical recall is expected because each layout uses the same text, index, ranker and tie-breaking policy. The code recorded **zero source-byte reconstruction errors** across the returned top-three hits in all five layouts.

The line-aligned 512 B representation reads **39.8% fewer compressed bytes** than fixed 512 B (825.7 vs 1,372.7 B), while increasing persistent footprint by **9,694 B** (301,449 vs 291,755 B). Its measured median warm request latency is essentially tied (140.1 vs 139.0 μs); the p95 is worse (244.8 vs 221.0 μs). The fixed 2,048 B configuration reads 4.3 times as many compressed bytes as line-aligned 512 B, yet has a *lower observed warm median*. These comparisons illustrate overhead, **not statistically established performance rankings**. Layouts were benchmarked in a fixed order, with no control of OS page cache residency, CPU clocks or process noise; timings include Python and SQLite overhead. No actual disk cold-read distributions are available.

The current timing includes FTS lookup, line ID join, SQLite frame lookup, `os.pread`, libzstd decompression and byte reconstruction. It does **not** include index build time per query, model inference, cross-source link extraction, tokenization into model prompts, or a concurrency SLA. Persistent bytes include the full SQLite database and compressed frame payload, not filesystem allocation/metadata.

## Counterexamples and graph-of-hypotheses evolution

**H29-A: Search relevance does not establish evidence sufficiency.** Exact line recall is a narrower criterion than complete supporting-sentence recall. A retrieved line can be the mechanically selected gold line while failing to answer a real question. An exact source hash and offset prove identity, not truth, authority or entailment.

**H29-B: Frame granularity and runtime latency are competing objectives.** A smaller compressed payload per request may be offset by more SQLite work, more frames to decompress and Python call overhead. A useful physical objective must include measured latency, storage cost, update cost and query distribution, not just compression ratio or frame bytes. This result rejects a simplistic "read fewer bytes => faster" hypothesis.

**H29-C: Data-dependent layout is vulnerable to workload selection bias.** Lines determine both alignment and gold query generation, so aligned frames are favored. The next independently-authored workload may differ substantially. The earlier subspan control in Round 27/28 mitigates but does not eliminate this issue.

**H29-D: Source version checks remain incomplete.** Source hashes are recorded during build, but a production reader does not yet enforce expected source/epoch identity at every read. A query could find valid bytes from an obsolete archive version after a source update. A correct deployed system needs immutable per-epoch readers, transactional update/publish, version-qualified retrieval and refusal of mismatched receipts.

**H29-E: The graph controller still lacks a predictive advantage.** Nothing here compares BM25+iterative bridging, graph retrieval and a CDG joint planner at matched cost on original multihop questions. Standard FTS5 with 2,048-byte frames is already a competitive local latency baseline. Do not treat this systems integration as a novel algorithm.

## Implementation and reproducibility

The experiment is self-contained with `experiments/round-29/retrieval_bench.py` plus the vendored, unchanged Round 28 `filebacked_bench.py` baseline. Python standard library, system `libzstd` and an SQLite build with FTS5 are required. The input reports are already in earlier repository archive paths or available in the research records; their exact hashes are in the results JSON. They are not represented as HotpotQA data.

```bash
python -m unittest discover -s experiments/round-29 -p 'test_*.py' -v
python experiments/round-29/retrieval_bench.py \
  --files path/to/round19.md path/to/round20.md path/to/round21.md path/to/round22.md path/to/round27.md \
  --output experiments/round-29/results_reproduced.json
```

Six tests passed for FTS lookup, byte-range reconstruction, Unicode-safe source positions, rank invariance across frame layouts, deterministic task construction and zero-length frame-read refusal. Input and output hashes should be checked before comparing reproduced numbers; warm timing values are not expected to reproduce exactly on another host.

## Round 30 registered falsification plan

1. Fix per-query independent original HotpotQA context sources locally. Verify full corpus and gold supporting sentence identities, and **execute** both retrieval and read-cost measurements in the same environment. The previous connector-only JS evaluations must be cross-validated by the Python runner.
2. Compare FTS5 line search, FTS5 paragraph search, two-hop title-mention expansion, title-link index, a conventional iterative retriever and a proposed source-cost-aware controller. Each policy must consume its own observed outputs, not gold source coordinates. Evaluate all gold supporting facts, answer correctness and citation correctness separately.
3. Enforce immutable source-epoch receipts and conduct adversarial update/rollback tests. Charge hash/version checks and title-link sidecars. Test stale, misleading and conflicting source relationships, not just document ID collisions.
4. Run several randomized layout orders, controlled host/cold-cache experiments and repeated sampling before making a latency claim. Include end-to-end indexing, metadata and storage footprints.
5. **Kill rule:** If a basic FTS5/bridge-index + standard Zstd layout lies on the equal-or-better complete-evidence/cost frontier, do not build or publish a more elaborate hypergraph controller. Redirect the technical contribution to source receipts, verified updates or query-aware physical source packing only if those show a separately measurable gain.

**Verdict:** A query-to-byte-receipt retrieval engine now runs without an oracle coordinate input, and the measured trade-off rejects read-traffic-only optimization. Independent QA/citation and true multihop capability remain unproved.
