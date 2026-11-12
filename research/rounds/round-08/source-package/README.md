# CDG Round 8 Reproducible Experiments

The primary contribution of this package is a comparison of exact lexical-search index factorization versus **per-query reuse of shared physical chunks and evidence text**.

## Requirements

- Python >=3.10, numpy, scipy, system `libzstd`, Git
- Local public noVNC clone: `git clone https://github.com/novnc/noVNC.git /opt/novnc` or set `CDG_NOVNC_REPO=/path/to/novnc`
- The exact historical checkout used: `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`, with historical commits available. You may fetch additional history if your clone is shallow.

## Run

```bash
python run_round8.py
python round8_batch_fetch.py
python round8_diversity.py
python round8_evidence_pack.py
```

These scripts import each other and repeat earlier preparations. Each generates JSON in the current script folder. The package includes required prior source-loader and Zstandard-ctypes wrappers in `dependencies/`. It does **not** bundle the full public noVNC source history.

## Files

- `round8_results.json`: exact BM25 index-factorization experiment, cost and quality.
- `round8_batch_results.json`: warm CPU query-batched evidence reconstruction.
- `round8_diversity_results.json`: same-path candidate cap stress test.
- `round8_evidence_pack_results.json`: exact prompt text deduplication with source provenance.
- `CDG_round8_research_report_2026-11-09.md`: methodology, research graph, findings, prior art, limitations, and proposed follow-on.

No neural encoders, LLM generation, SSD access, or end-to-end RAG were evaluated.
