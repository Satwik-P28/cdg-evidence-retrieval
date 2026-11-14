# Round 31: Immutable evidence snapshots

This directory extends the Round 30 FTS5/Zstandard file-backed engine with a **single-writer, version-pinned local publication protocol**. It is an experimental research artifact, not a secured document service.

- `snapshot_store.py`: builds a complete new generation, creates a manifest bound to exact source digests, publishes the `CURRENT` pointer, and serves pinned byte-range receipts.
- `test_snapshot_store.py`: ten local regression tests covering old/new readers, stale receipts, corrupt files, failure before publication, and UTF-8 readbacks.
- `benchmark.py`: real disk use and warm query/update costs for a small collection of existing CDG reports. Does not modify originals.
- `results.json`: one local measured run; Python/SQLite timing is not portable.
- `contentless_bench.py` and `filebacked_bench.py`: local dependencies copied from the previously committed experimental source with original Round 28/30 attribution.
- [Research analysis](../../research/rounds/round-31/report.md): findings, prior art, limitations, and Round 32 kill criteria.

```bash
python -m unittest -v test_snapshot_store.py
python snapshot_store.py --root /tmp/cdg-snapshots publish /path/to/reportA.md /path/to/reportB.md
python snapshot_store.py --root /tmp/cdg-snapshots search evidence --topk 5
```

The `CURRENT` pointer is not an authenticated source-of-truth. A consistent snapshot can still be old; SHA-256 fingerprints are not signatures. No concurrent writer exclusion, cross-host durability, crash-recovery testing, garbage collection, or permission enforcement is implemented.