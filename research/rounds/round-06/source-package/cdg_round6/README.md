# CDG Round 6 reproducibility

Real source bytes: `/opt/novnc` Git HEAD **7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861**, not included in this package. The current local checkout contains unrelated untracked files, which are not used.

Requires Python 3.12+, numpy, scipy, scikit-learn and system libzstd (through previous scripts' ctypes wrapper). All scripts use Python's deterministic random seeds, synthetic access traces and actual historical source bytes. No pretrained encoder or LLM runs.

Unzip the package and make sure `cdg_round5` and `cdg_round4` directories remain next to the `round6_*.py` scripts inside this directory. With the noVNC repo at `/opt/novnc`, run:

```bash
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python round6_access_policy.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python round6_shared_cache.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python round6_fair_ram_cache.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python round6_piece_diagnostics.py
OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python round6_materialized_windows.py
```

Outputs: `round6_*results.json`. The scripts run independent benchmarks on import because they reuse the previous round's prototypes; expect occasional repeated execution. Timings fluctuate by host, CPU frequency and cache state. Details and limitations: `CDG_round6_research_report_2026-11-09.md`.
