# Round 44: FTS5 Update Strategy, Line-Diff Policy and Historical Index Retention

**Date:** 2026-11-17. **Status:** GitHub Actions passed six Round 44 regression tests and all 48 full six-configuration scenarios. CI run 44027958456. Input corpus = five internal CDG round reports, optionally replicated under 20 identities, with synthetic edits. No production scale or independent RAG QA.

## Changes versus Round 43

Round 43 established the importance of row-ID-indexed FTS5 relative to source-name scans. Round 44 separates three design decisions: FTS5 deletion method (legacy contentless FTS5, SQLite 3.43+ contentless-delete, and external-content trigger maintenance); edit alignment (SequenceMatcher, linear prefix/suffix, full posting rebuild); and historical index retention (all SQLite snapshots or rebuild historical index from archived source on demand).

Compared variants: P_sequence, P_edges, E_edges, T_edges, E_rebuild, and E_live. E_live is the same as E_edges but omits historical full-index backups. All options retain source hashes and compressed source payloads for exact old-generation readback.

## CI measurements

GitHub Actions run 44027958456 on Ubuntu/Python 3.13, 48 scenarios: four edit types (append, replace, insert, delete), 5 or 20 source IDs, edit fractions 5%/20%/80%, seeds 11/23, four updates each. The runner checks current FTS match parity and exact source bytes for every retained generation, plus generation-0 and midpoint historical queries.

| Variant | Median update (ms) | Median retained bytes | Median current search (microseconds) | Median historical search (microseconds) |
| --- | ---: | ---: | ---: | ---: |
| P_sequence (legacy delete, SequenceMatcher, all snapshots) | 4.689 | 2,083,238 | 77.422 | 305.486 |
| P_edges (legacy delete, edge diff, all snapshots) | 4.216 | 2,083,238 | 74.582 | 296.188 |
| E_edges (contentless-delete, edge diff, all snapshots) | 4.281 | 2,087,167 | 73.312 | 299.387 |
| T_edges (external content + trigger, all snapshots) | 4.428 | 2,334,975 | 91.914 | 346.858 |
| E_rebuild (contentless-delete + full posting rebuild) | 9.951 | 2,538,312 | 77.692 | 301.262 |
| E_live (contentless-delete + edge diff, current index only) | 2.885 | 438,527 | 81.989 | 7,716.753 |

E_live had the minimum update median in all 48 scenarios, largely because it omits a historical database backup per update. It is NOT faster for historical queries. Compared with E_edges, retained storage is approximately 79% smaller while on-demand historical search is roughly 26x slower in this tiny corpus.

An illustrative pooled time-only break-even of about 0.19 historical queries per update is NOT a robust workload policy threshold. Caching, prices, migrations, durability and independent histories were not tested.

P_edges modestly improves on P_sequence in median update timing and uses the same historical archive footprint. E_edges does not clearly beat P_edges. Rebuilding all postings is slower for the tested workloads. External-content triggers are ordinary SQLite prior art, not a CDG innovation.

## Decision

Keep two explicit choices. For primarily current queries with exact historical source-byte reconstruction, E_live is an attractive option in the evaluated regime but trades away fast historical search. For frequently queried old generations, retain historical snapshots with P_edges or E_edges; there is no established gain from a self-switching policy.

Before introducing an adaptive selector, charge index migration and historical backfill cost. Future fair controls should include independent version histories, realistic query/update traces, optimized SQLite snapshot handling, actual hardware read behavior and concurrency.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-44 -p 'test_*.py' -v
    python experiments/round-44/layout_lab.py --out experiments/round-44/results.json

Raw results are preserved in the GitHub Actions artifact for run 44027958456. Timing values are short warm samples, not a statistical guarantee or real SSD throughput test.

SQLite FTS5 update and contentless-delete documentation: https://www.sqlite.org/fts5.html . SQLite session extension does not capture virtual-table writes: https://www.sqlite.org/sessionintro.html . These are established mechanisms.

**Next experiment:** evaluate an independent version history, compare time-weighted read/write/storage costs, and falsify adaptive routing against fixed conventional baselines. No new compression algorithm or end-to-end RAG quality gain is claimed.
