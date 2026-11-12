# CDG Round 10 reproducibility package

This package contains measured experiments on **real noVNC version histories**, but the question-answer tasks are **synthetic combinations** of real commit messages. There is no pretrained encoder or LLM answer evaluation.

## Requirements

- Python 3.12 or newer
- numpy, scipy, scikit-learn
- system libzstd
- local Git checkout of `https://github.com/novnc/noVNC` at commit `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`

## Steps

```bash
python -m pip install numpy scipy scikit-learn
export CDG_NOVNC_REPO=/path/to/noVNC
export OPENBLAS_NUM_THREADS=1
python round10_strong_retrieval.py
python round10_chunk_granularity.py
python round10_mixed_layout.py
```

The scripts overwrite their matching `*_results.json` files with fresh results. Timing results are hardware-dependent, while source reconstruction should remain exact. The physical chunk store is an experimental in-memory representation, not a production archive format.

## Scope

The compressed source bytes include unique compressed chunk payloads, compact manifests, and compressed static chunk catalogs. The physical evidence payload is the union of compressed chunks intersecting selected passages. No SSD I/O, tokenizer inference, neural retrieval, index updates, or source-attribution judgments are included. See `CDG_round10_research_report_2026-11-09.md` for prior art and interpretation.
