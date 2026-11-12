# CDG Round 5 experiments

Reproducible CPU-only research probes for compressed document-version storage, lexical change retrieval, and selective passage reconstruction.

## Requirements

- Python 3.12+ with numpy, scipy, scikit-learn
- system libzstd
- a checked-out noVNC Git history at commit `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`, default expected location `/opt/novnc`.
- Set `CDG_NOVNC_REPO` to another local path for `git_history_retrieval.create` if necessary. Other scripts containing hardcoded `/opt/novnc` are illustrative and require adjustment.
- Source scripts from Round 3 are included under `cdg_round4/prev/cdg_round3` as supporting code. Keep `cdg_round4/` and `cdg_round5/` adjacent when unpacking.

## Run key experiments

```bash
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_anchor_budget.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_merged_benchmark.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_source_storage.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_compact_metadata.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_head_to_head.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python cdg_round5/round5_seekable_sweep.py
```

Most scripts import earlier scripts which execute their own experiments on import, so you may see multiple outputs before the final JSON. All results from this run are included in `*_results.json`. Runtime and timing vary by host. No neural encoder or LLM was executed.

Read `CDG_round5_research_report_2026-11-09.md` for exact measurements, limitations, and paper links.
