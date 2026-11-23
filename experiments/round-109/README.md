# CDG Round 109: physically materialized seekable posting lists

This is a falsification step after R108's encouraging *logical* size results. Using exactly the same independently selected real terms and docID postings, R109 writes each experimental codec's byte stream into separate **physical SQLite databases** with identical lexicon/metadata table definitions and `WITHOUT ROWID` storage. Every decoded list is checked against both originally extracted postings and actual SQLite FTS5 term retrieval. Fixed hash-selected warm term queries and paired set AND/OR operations must also match.

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-109
python experiments/round-109/seekable_index.py --dataset qasper --out experiments/round-109/ci-qasper.json
python experiments/round-109/seekable_index.py --dataset scifact --out experiments/round-109/ci-scifact.json
```

Source tar SHA locks come from existing R83/R96 modules. Source text is never copied into output. The external index is docID-only: it lacks native FTS5 positional data, ranking metadata and phrase semantics. FTS5 file size is contextual, **not feature-equivalent**. Warm Python decoder timing is descriptive, not SSD cold latency, optimized SIMD performance, or independent hardware replication.