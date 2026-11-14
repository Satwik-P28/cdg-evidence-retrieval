# Round 32: Versioned Source Segments, Content-Addressed Frames, and the Cost of Incremental Publication

**Date:** 14 November 2026  
**Status:** Executed local Python/SQLite FTS5/libzstd experiment, nine passing unit tests, 11 generations in each of two deterministic update regimes. Exploratory warm-cache systems comparison. **Not** HotpotQA, semantic grounding, authenticated data origin, or a novel compression method.

## Question and preceding failure

Round 31 introduced immutable generation receipts that prevent cross-generation citation reuse, but changing one line forced a full rebuild and duplicated every retained index and compressed payload. Is the full rebuild necessary to maintain this consistency contract? The simplest alternative is a content-addressed store of independent compressed frames and an immutable search-index segment for each source version. A generation then contains only references to source descriptors. This is established copy-on-write and content-addressed storage engineering, not a newly discovered compression principle.

## Exact scope and design

Inputs: the five existing CDG research reports from Rounds 24 through 28. Original source hashes are in `results.json`. Total input size is 63,869 bytes. Neither the corpus nor the mechanically selected keyword queries constitutes an independent user-question workload.

Two *architecturally matched* experimental stores were compared:

- `full`: a new generation writes a distinct FTS5 SQLite segment for **every** source plus independently compressed per-line Zstandard frames, even if a source is unchanged. The snapshot includes all source-to-frame mappings in the generation manifest. This is an **intentionally nonincremental control** using the same per-source search representation, not the optimal conventional global SQLite incremental-update baseline.
- `cas`: keeps one immutable contentless FTS5 SQLite segment per SHA-256 source version; maintains independent compressed frames keyed by SHA-256 of raw frame bytes; stores a frame map in an immutable source descriptor; and publishes only small generation manifests referencing these source descriptors. Byte-identical frames and unchanged source indexes are reused across updates.

Both policies use the same 512-byte cap and line-bounded frame partitioning. Frame SHA-256 identifies byte identity, not authority. Both stores are single-writer, local, and retain **all** published generations. Readers verify file digests when opened; a citation receipt includes `(generation, source digest, start, end)` and is refused against a different generation. An older reader remains pinned to its original snapshot.

The index is deliberately *sharded by source*. Fifteen fixed, literal, source-derived lexical terms are issued to **every** shard, with results ordered by stable source name and line ID rather than globally comparable BM25. Both stores use identical search logic and must produce identical search and source reconstruction results. That makes this a matched storage/update comparison, **not** a search-relevance study. No semantic retrieval, ANN, link-graph maintenance or question answering is tested.

### Update regimes

Start from the same five immutable source byte sequences, publish generation 0, then publish **10** additional generations, changing one rotating source per generation. `replace` modifies one ASCII letter without shifting offsets; `insert` inserts one ASCII byte and changes subsequent offsets in that source. Offsets and indexed lines are regenerated for changed sources, while other source versions are shared. In each regime each store serves 15 keyword requests and reconstructs a complete source byte-for-byte per generation. Comparison includes only safe same-generation receipts. Old receipts are rejected by new readers; historical pinned readers still reconstruct old bytes.

### Engineering failure during the round

The initial CAS representation mistakenly included a full array of frame references for all five sources in every generation manifest. Even with actual frame reuse, this created large repeated metadata. The final design stores frame arrays once per immutable source-version descriptor, and keeps generation manifests small. This is a measured design correction, not an opportunity to selectively hide a failed experiment.

## Measured results

All byte totals include the SQLite segment files, compressed Zstandard frames, source descriptors, generation manifests and `CURRENT` pointer. No garbage collection or external filesystem allocation overhead is modeled beyond actual file sizes. Latency values are from one warm local execution, not repeated randomized trials.

| Metric | Full rebuild, replace | CAS, replace | Full rebuild, insert | CAS, insert |
|---|---:|---:|---:|---:|
| Initial generation total | 419,533 B | 420,818 B | 419,533 B | 420,818 B |
| **11 retained generations** | **4,602,314 B** | **1,174,447 B** | **4,602,343 B** | **1,174,683 B** |
| Stored-byte reduction at generation 10 | reference | **74.48%** | reference | **74.48%** |
| Added bytes written during 10 updates | 4,182,781 B | 753,629 B | 4,182,810 B | 753,865 B |
| Median per-update build time | 475.6 ms | 24.5 ms | 447.3 ms | 24.1 ms |
| Median of per-generation warm median query time | 2,143 µs | 2,031 µs | 2,074 µs | 1,982 µs |

The small initial *CAS penalty* comes from content-addressed descriptor and path metadata. The reduction only emerges with retained repeated versions and changes that affect one of five sources per update. Query times are not statistically distinguishable in this one-run test; do not present them as evidence of faster querying.

The data support the narrow hypothesis that source-version reuse can sharply reduce **retained historical storage and publication rewriting** under localized edits. They do **not** show that CDG beats SQLite `UPDATE`/FTS5 incremental maintenance, an LSM database, Git packfiles, or content-defined chunk deduplication. Our full-rebuild control deliberately has poor update amplification and should be replaced by stronger baselines in Round 33.

## Correctness checks

Nine Python `unittest` cases passed:

1. Byte-exact UTF-8 reconstruction across frame boundaries and partial multibyte offsets.
2. Pinned old reader remains available after a new generation.
3. A current reader rejects stale generation receipts.
4. Identical frames across source versions share a physical Zstandard payload.
5. Failed publication before pointer replacement preserves current generation.
6. Corrupted compressed payload is rejected at reader initialization.
7. Corrupted source descriptor is rejected.
8. Full and CAS implementations yield identical FTS5 source matches.
9. Insert and same-length replace preserve expected byte-size invariants and bad offsets are refused.

**Open risks:** `CURRENT` is atomically renamed but not a complete fsync/dir durability and crash-recovery protocol; readers do not reacquire origin trust; no ACL, concurrent writers, signed manifest, reader-aware GC, per-frame authenticated provenance, or corpus-wide consistent origin snapshot. A SHA-256 manifest stored in the same writable root cannot defend against an attacker who changes both manifest and data. Content-based deduplication is an optimization, not permission to reuse material across tenants.

## Graph-of-thoughts extensions and negative branches

### H32-A: Storage reuse and evidence validity are orthogonal

The same byte frame can be referenced in two source generations without implying that the **meaning, authority, source title or access rights** are shared. Receipts still require the source digest and generation ID. Content hashes authorize reuse of bytes only after the request's source and policy constraints are checked.

### H32-B: Index update cost dominates simple frame reuse

Most saved update work is avoiding rebuilds of unchanged sources. Frame-level dedup helps within a modified source, but per-source contentless FTS indexes still need regeneration when one byte changes. An actual incremental FTS5 update and content-defined chunking may be more competitive. Separate index-posting changes from compressed-frame changes in the next trial.

### H32-C: Making metadata independently addressable is essential

A naive append-only manifest can destroy the space savings of a CAS payload. Source-descriptor deduplication is as important as frame deduplication in this experiment. Track metadata bytes independently from payload and indexes. This generalizes to citation span maps, source versions and physical storage-layout maps.

### H32-D: The primary open research hypothesis remains retrieval-specific

Nothing in this round predicts which evidence is sufficient or reduces unsupported answers. A first-class research claim requires integrating these versioned frames with authentic multi-hop retrieval and a frozen answer evaluator, then comparing complete evidence coverage and answer grounding at matched *total* online, update and storage cost. Do not confuse a working CAS engine with an improved RAG system.

## Reproduce

Requires Python 3.10+, SQLite compiled with FTS5, and system `libzstd` via `ctypes`. Inputs are **not** embedded with the report; use the five Round 24–28 source Markdown files with the SHA-256 values in `results.json` to reproduce the same figures.

```bash
python -m unittest discover -s experiments/round-32 -p 'test_*.py' -v
python experiments/round-32/benchmark.py \
  --files path/to/round24.md path/to/round25.md path/to/round26.md path/to/round27.md path/to/round28.md \
  --out experiments/round-32/results_reproduced.json
```

Measurements vary with operating system, SQLite build and filesystem cache. Do not overwrite the originally measured JSON to imply a cross-machine reproduction.

## Round 33 preregistration / kill criteria

- **Stronger conventional baselines:** one global SQLite FTS5 database using in-place incremental updates, contentless-delete FTS5, WAL/checkpoint costs, `VACUUM INTO`, and a simple Git-pack-style archival strategy. Compare under equal historical query retention requirements.
- **More realistic update shifts:** change 1%, 20%, 80% and 100% of sources; insert/delete paragraphs; modify document titles so link edges change; rename/delete source IDs; retest receipt validity and storage growth.
- **Storage details:** report payload, FTS postings, descriptors, manifests, deleted space and eventual GC separately, plus p50/p95 wall times with randomized repeated runs and an explicitly named cold-cache method.
- **Authentic retrieval:** evaluate a frozen HotpotQA distractor subset with official evidence annotations through the actual file-backed store. Include complete supporting-sentence recall and cite spans; compare FTS5-only and title-link baselines before proposing a planner.
- **Kill:** If incremental conventional SQLite achieves equal update/query/storage performance, retire custom segmented index; if frame CAS wins only under repeated near-identical versions, position it as an optional storage technique rather than a broad compression breakthrough.

**Verdict:** GO for immutable versioned source storage as an engineering baseline. Novel RAG/compression performance claim: **not established**.
