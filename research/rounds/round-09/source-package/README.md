# CDG Round 9 reproducibility

This archive measures a 250-version real Git corpus and 75 synthetic, two-intent held-out retrieval tasks. It does **not** benchmark a neural RAG system.

Use a local noVNC checkout at `/opt/novnc` pinned to commit `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`; data input is not redistributed.

Python 3.10+, NumPy, SciPy, and system libzstd are required. From the extracted directory:

```
python round9_packing.py
python round9_multi_intent.py
python round9_passage_costs.py
python round9_passage_rerank.py
```

The four scripts write JSON with all relevant methods, measured sizes, and limitations. The `dependencies` directory and `run_round8.py` are copies from Round 8. All method comparisons are source-revision proxies, not measured production RAG answer accuracy or cold disk performance.

See `CDG_round9_research_report_2026-11-09.md` for results, prior art, and next tests.
