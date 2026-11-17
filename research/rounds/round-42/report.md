# Round 42: Empirical Component Recombination and Fairer Historical SQLite Controls

**Date:** 2026-11-17. **Status:** executed local Python/SQLite/zlib experiments on five genuine internal reports with replicated-source scale controls, **32 full four-way multi-generation scenarios**, two different edit types, four update fractions, two fixed seeds, **four passing differential regression tests**, reproducible code/results. **Not authentic user-query RAG, not a measured SSD benchmark, and not a novelty claim.** This round directly tests whether CDG's custom immutable source shards justify their storage/query/update costs against conventional incrementally updated SQLite.

## 1. Hypothesis and four architectures

Every architecture must retain all five generations (initial + four updates), allow byte-for-byte old/current document reconstruction, and agree on the returned source-name multiset for the same five source-derived FTS queries (`evidence`, `compression`, `retrieval`, `source`, `algorithm`). Query result order and BM25 scoring are deliberately not compared; the global index and shard fanout have different ranking semantics.

- **A: Global+copy (global):** global SQLite FTS5 table updated with DELETE/INSERT for changed sources; a full global SQLite backup and fresh zlib-compressed copy of every source on every generation. This is a simple historical-snapshot baseline, not optimized.
- **B: Global+CAS (delta):** same global live index with append-aware FTS5 posting updates, backed-up global SQLite FTS5 per generation, and SHA256-addressed zlib payloads with small source-version maps. Snapshot index copy still costs space and time.
- **C: Shard+CAS (shards):** individual source-version FTS5 indexes, SHA256-addressed zlib source payloads, small immutable generation maps. Query fans out to all source indexes and incurs database-open overhead. No current global index.
- **D: Hybrid live-global + historic shards (hybrid):** keep one global FTS5 current index, plus immutable source-version shard indexes and CAS payloads for historical generations. Avoids full global historic index copies but duplicates current indexing maintenance. **This is a combined design, not evidence of original invention.** Historic search through source shards is possible architecturally but only current search and historical exact readback are benchmarked.

For all architectures the test checks source reconstruction for every current document after each update, source-name FTS match parity after each update, and every original document from generation 0 at the end. Every query benchmark contains only five locally derived search keywords, on warm OS cache.

## 2. Workloads and measurement

The **five original inputs** are existing internal CDG round 24–28 reports (not independent evaluation); total initial text bytes **63869**. The 20-source setting duplicates these five authentic reports into 20 distinct source identities to expose identity safety and scaling behavior. It does **not** constitute 20 independent sources or a representative corpus.

Workloads: append a short provenance update to 1/5/16/20 sources for the 20-source 5%/20%/80%/100% conditions; or replace one ASCII byte inside an early source token while preserving its byte length. For 5 sources the 5% and 20% conditions both change exactly one source because of rounding. Each setting runs **four updates and two deterministic RNG seeds** (11,23), with one warm timed run per seed. The update operation includes writes, SQLite commits and backups/manifest publication, but does not include fsync durability, external caches, garbage collection, arbitrary concurrency, or query overhead. Archive bytes include index files, compressed payloads, and manifests. Each design uses zlib compression, **not** Round 32's original Zstandard/framed-byte implementation, specifically to isolate architecture; it must not be compared directly to its benchmark numbers.

Run in Python 3.13.5, SQLite 3.46.1, Linux x86_64. Short timing samples and Python-layer overhead preclude credible statistical significance claims.

## 3. Observations

Table cells order **A / B / C / D** for **update median ms**, **retained storage MB** and **warm query median μs**. Each row reports median of two per-seed medians (4 updates per seed). Bytes are decimal MB.

| Edits | Sources | Fraction changed | Update ms A/B/C/D | Stored MB A/B/C/D | Query μs A/B/C/D |
|---|---:|---:|---|---|---|
| append | 5 | 5% | 8.2 / 4.4 / 4.9 / 6.6 | 1.59 / 1.01 / 0.58 / 0.74 | 60 / 46 / 890 / 47 |
| append | 5 | 20% | 8.0 / 4.4 / 4.9 / 6.2 | 1.59 / 1.01 / 0.58 / 0.74 | 57 / 45 / 876 / 41 |
| append | 5 | 80% | 11.1 / 6.4 / 18.7 / 19.8 | 2.28 / 1.08 / 1.37 / 1.53 | 51 / 42 / 840 / 50 |
| append | 5 | 100% | 11.9 / 6.7 / 22.4 / 23.2 | 2.39 / 1.10 / 1.64 / 1.80 | 58 / 51 / 866 / 45 |
| append | 20 | 5% | 18.0 / 5.8 / 5.5 / 7.1 | 4.72 / 3.26 / 1.48 / 2.01 | 140 / 135 / 3177 / 128 |
| append | 20 | 20% | 20.3 / 7.1 / 17.6 / 19.7 | 5.49 / 3.31 / 2.23 / 2.77 | 159 / 149 / 3215 / 129 |
| append | 20 | 80% | 36.5 / 10.5 / 68.2 / 71.5 | 7.25 / 3.44 / 5.23 / 5.77 | 166 / 147 / 3540 / 138 |
| append | 20 | 100% | 42.6 / 8.3 / 81.3 / 85.0 | 7.45 / 3.37 / 6.11 / 6.66 | 163 / 126 / 3447 / 135 |
| replace | 5 | 5% | 8.8 / 5.7 / 5.7 / 8.1 | 1.53 / 1.28 / 0.52 / 0.75 | 52 / 46 / 836 / 47 |
| replace | 5 | 20% | 8.0 / 5.6 / 5.1 / 7.3 | 1.53 / 1.28 / 0.52 / 0.75 | 53 / 43 / 817 / 46 |
| replace | 5 | 80% | 10.5 / 9.9 / 17.8 / 22.8 | 2.25 / 2.14 / 1.09 / 1.52 | 42 / 40 / 845 / 39 |
| replace | 5 | 100% | 11.5 / 11.1 / 22.0 / 28.3 | 2.35 / 2.28 / 1.28 / 1.71 | 47 / 43 / 794 / 45 |
| replace | 20 | 5% | 16.3 / 6.4 / 5.1 / 8.7 | 4.72 / 3.85 / 1.41 / 2.11 | 148 / 141 / 3360 / 128 |
| replace | 20 | 20% | 20.4 / 11.0 / 17.5 / 23.6 | 5.55 / 4.72 / 1.98 / 2.80 | 135 / 153 / 3454 / 144 |
| replace | 20 | 80% | 36.9 / 31.5 / 67.9 / 94.5 | 7.31 / 6.85 / 4.14 / 5.48 | 125 / 140 / 3473 / 140 |
| replace | 20 | 100% | 40.3 / 33.2 / 78.9 / 106.7 | 7.46 / 6.75 / 4.77 / 6.11 | 133 / 134 / 3142 / 137 |

### Where recombination actually helped

**Small edit, 20 source IDs (5% changed, append):** C has the least retained bytes, ~1.48 MB, and D is about 2.01 MB, versus B at 3.26 MB. D's global current query is **~128 μs versus C's ~3,177 μs**, about 25x in this small warm local sample. However, D's median update time is ~7.1 ms against C's ~5.5 ms and B's ~5.8 ms. This is a **space/query Pareto trade-off**, not unconditional dominance.

**Large edit, 20 IDs (80% changed, append):** B updates in ~10.5 ms and retains 3.44 MB while D takes ~71.5 ms and retains 5.77 MB. B wins both write cost and retained bytes in this scenario, with similar current-query cost. **Kill blanket claims that sharded history is always preferable.**

**Large edit, 20 IDs (100% changed, replacement):** C retains ~4.77 MB and D ~6.11 MB, while B retains ~6.75 MB. B updates in ~33.2 ms, C ~78.9 ms, D ~106.7 ms. Choosing D as a default imposes a large unnecessary update cost for this workload.

**Current query scan:** C's per-source SQLite fanout is consistently much slower than A/B/D because it opens one connection per source. That latency is partly a Python/SQLite implementation artifact rather than a fundamental bound, but must be charged until a better index is implemented.

## 4. Failures uncovered and repaired in experimental code

**F42-A, source identity aliasing:** The first C implementation addressed per-source FTS5 index files by 8SHA256(source bytes) only while indexing the source name inside SQLite. When distinct names held identical bytes (the 20-source scenario), it reused an index containing another source's name and failed FTS parity. **Fix:** index identity is now SHA256(name || NUL || SHA256(source bytes)); compressed payload can still deduplicate by SHA256(bytes) alone. Add a differential test with two distinct source names sharing identical bytes. An untrusted tenant scope and policy must also be included in any cross-tenant storage identity; this prototype is single-tenant only.

**F42-B, renamed/deleted documents:** Initial update logic never removed names absent from subsequent manifests/current FTS, leaving phantom matches. **Fix:** explicitly invalidate removed source names in all four architectures while retaining old generation data. Test rename `old` to `new` and verify no current phantom plus exact old generation readback.

**F42-C, content modification outside append-only assumption:** B's fast path detects appended lines and falls back to replacing the affected document's global postings for middle-line edits. The replacement workload shows the cost of that fallback. Test removal of a historical search term and addition of a new term in the same source.

**F42-D, reader resource leak:** Shard fanout initially relied on `with sqlite3.connect()` to close connections, but the context manager only controls transactions. **Fix:** explicit `finally: close()`, and rerun tests with `ResourceWarning` treated as an error.

## 5. Scientific implications

The attempted merged architecture **does not dominate** the strong conventional global+CAS control. Instead, it identifies a measurable Pareto frontier where workload edit rate, query rate and historical retention determine the best design. This is meaningful engineering knowledge, but no new lossless compressor, no query-answer improvement, and no general RAG reliability result.

The next candidate is **adaptive index-layout selection**, not a default universal architecture. Given measured workload parameters (update frequency, fraction of sources modified, query count, retention horizon), a policy can decide between B and D, potentially with a cheap conversion path. Its savings need to be measured net of migration cost, prediction errors, planner time and retained indexes. It is likely a conventional database physical-design problem. We should compare against FTS5 optimized incremental row updates, SQLite backups/changesets and established versioned file stores.

## 6. Reproducibility and prerequisites

Requires only Python 3.10+ SQLite FTS5 and standard-library zlib. The five CDG report source files are **bundled under `experiments/round-42/inputs/`**, with exact SHA256 hashes in `source_hashes.json`. The 20-source corpus creates distinct source identifiers for repeated copies of these five source texts, not new independent documents. Because the benchmark is small and dependent on host state, reproducible counts and invariants matter more than matching the exact timing numbers.

```bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-42 -p 'test_*.py' -v
python experiments/round-42/lab.py --out experiments/round-42/recomputed.json
```

## 7. Promotion gates

- **GO:** source-scoped index identity; exact current and old-generation byte reconstruction; deletion/rename and mid-document mutation tests.
- **HOLD:** no workload-trained policy and no held-out real history / full read-write cost accounting; weak query set and Python implementation artifacts.
- **REJECT:** claim that custom shards are superior to conventional global incremental FTS5 or that the combined design itself constitutes a new compression algorithm.

Next round should run indexed-incremental SQLite with proper FTS5 row IDs, realistic edit/replacement workloads, and an adaptive policy selected on a training workload then evaluated on held-out corpus histories. Only if that beats fixed B and D at equal query correctness is there a substantive CDG-specific improvement.
