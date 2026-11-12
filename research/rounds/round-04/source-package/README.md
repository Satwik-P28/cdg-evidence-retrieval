# CDG Round 4: Reproducibility

This package contains the local experimental code and the prior Round 3 code required to reproduce the new Round 4 tests. `round4_bounds.py` and related scripts are **not a pretrained neural retriever or an LLM RAG benchmark**. They build 96-dimensional TruncatedSVD representations from TF-IDF on public noVNC source-history versions and query them using human-written Git commit subjects. The other two tests generate synthetic clustered vectors.

## Inputs / setup

- Linux with Python 3.11+ (`numpy`, `scipy`, `scikit-learn`), system `libzstd` available (the old experiment uses a `ctypes` wrapper).
- Public noVNC Git history checked out at `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`.
- By default source code reads `/opt/novnc`. Override with environment variable `CDG_NOVNC_REPO`.
- Set `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1` for comparable CPU timing behavior.

## Commands

```bash
export CDG_NOVNC_REPO=/path/to/noVNC
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python round4_bounds.py
python round4_scaling.py
python round4_adaptive.py
```

## Outputs

- `round4_bounds_results.json`: real-revision SVD proxy, bound-guided exact top-k, compact residual comparisons, CPU timings.
- `round4_scaling_results.json`: controlled vector-family similarity microbenchmark (250, 5k, 50k).
- `round4_adaptive_results.json`: 10-query pilot choice and 60 held-out query measurements.
- `round4_proxy_vectors.npz`: cached projected vectors and commit queries for independent analysis.
- `CDG_round4_research_report_2026-11-09.md`: interpretation, close prior art, and research direction.

## Scientific limitations

- The noVNC task is not an independently judged RAG benchmark. A commit subject and its changed source revision are a noisy proxy for relevance.
- The embeddings are **linear SVD representations**, not learned pretrained semantic encoders.
- Group search is slower on small real data and on synthetic high-dispersion vector families.
- GPU/SSD, cold-cache, production ANN, real RAG generation, actual LLM token costs, and alternative retrievers (including FAISS, Qdrant, PLAID, MV-IVF) were not benchmarked.
- The reported byte sizes for shared residuals are a simple encoding, not an optimized product-quantization implementation. The serialized zlib figures refer to the vector data, not entire index structures or the encoder model.
- The pilot policy adds a setup cost, excluded from per-query figures.
- Reranking assumes the full-precision vector is available on demand; cost of reading it is not measured.
- Score-bound certificates are valid only for exact top-k under the explicitly defined normalized dot-product model, not general evidence completeness or generated-answer correctness.

For an additional independent check, run `python round4_validation.py` after `round4_bounds.py`. The generated file `round4_validation_results.json` verifies exact score-level top-k behavior under float tolerance, including tied-result cases.
