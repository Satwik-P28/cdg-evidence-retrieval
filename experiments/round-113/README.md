# Round 113 | Independent-paper source-only cost-aware layout planner

This is a static *research falsification* of the R106 finding that pseudo-historical access does not dominate paper-length heuristics. The planner never inspects DEV question text, evidence labels, generated answers or the artificial revision stream when choosing source layouts. It does inspect DEV article source bytes, necessary to build its compressed archive. The training corpus is QASPER TRAIN with different article IDs from QASPER DEV, and only supplies the 64 KiB trained Zstd dictionary.

## Algorithm and prior art

The candidate layouts are R106's per-paragraph individual Zstd9, groups-of-4, and whole-paper blocks. The planner scores their known *source-only* per-paper compressed bytes plus a deliberately imperfect row-overhead proxy, uniform-per-paragraph read bytes, and uniform-per-paragraph compressed BLOB rewrite cost. A deterministic multiple-choice knapsack chooses a layout for each paper under a **proxy** byte budget. It is not novel, does not meet a hard physical SQLite budget, does not schedule migrations, and offers no guarantees against workload drift. See [OREO (ICDE 2024)](https://arxiv.org/abs/2405.04984), [RocksDB BlobDB](https://github.com/facebook/rocksdb/wiki/BlobDB) and [RocksDB 2026 partitioned blob direct write](https://rocksdb.org/blog/2026/06/20/blob-direct-write-partitioned-blob-files.html).

Initial seven source-layout arms: all-paper, all-group4, all-individual, length-budget 35%, stable-hash-budget 35%, balanced source-cost planner 35% and 65%. **Four additional arms were introduced after seeing the first seven-arm results and are explicitly exploratory**: prior R106 paper-length 50/25 and hash 50/25, and source-only planner 25% and 30% proxy budgets. The same estimated budget fraction is used for controls at 35%. **All** arms materialize the original source+FTS5 SQLite schema, shared TRAIN-only Zstd dictionary, source SHA receipts and original index. Each verifies 13,266 originals, unchanged QASPER BM25 rankings, held-out original-question top1/top10 source read costs, 24 artificial source edits, exact source after edits, FTS5 parity and SQLite WAL page growth. The 65% planner should not be interpreted as a matched-size improvement against 35% controls.

Original QASPER questions are independent of this planner's article and compression based selection. These are not chronologically recorded human access events. The artificial edits are not genuine revision logs. Earlier CDG rounds already examined the QASPER DEV corpus, so treat this as **exploratory iteration**, not a novel blind test against the broader project.

## Reproduce

```bash
python -m pip install pytest==9.0.2 Brotli==1.1.0 zstandard==0.23.0
python -m pytest -q experiments/round-113/tests
python experiments/round-113/archive_planner.py --out experiments/round-113/ci-results.json --edits 24
```

See `research/rounds/round-113/report.md` and the workflow `.github/workflows/cdg-r113-layout-planner.yml`. The source tar is verified by existing R96 SHA locks; original QASPER text is not copied to the repo or workflow artifacts.