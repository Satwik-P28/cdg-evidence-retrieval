# CDG Round 7 replication bundle

This bundle contains source code and JSON results from span-aware compressed retrieval experiments conducted November 9, 2026. It makes **no** claim about real neural RAG acceleration.

## Source corpus

A local public noVNC Git checkout at commit `7fcf9dcfe0cc5b14e3841a4429dc091a6ffca861`. 250 genuine source revisions selected by Round 3/5/6 scripts. Source bytes are not bundled.

## Setup

1. Extract `CDG_round6_research_package_2026-11-09.zip` from the `inputs` directory here, so `cdg_round6/` exists next to the Round 7 scripts.
2. Clone a local copy of noVNC and check out the pinned commit, if necessary. Set `CDG_NOVNC_REPO` to its path (default in original scripts: `/opt/novnc`).
3. Install dependencies: Python 3.12+ with `numpy`, `scipy`, and `scikit-learn`; `libzstd` available to ctypes.
4. Execute `python round7_span_coalescing.py`, then `python round7_base_decode_cache.py`, then `python round7_frame_accounting.py`.

Each script tests byte-exact source reconstruction before measuring warm CPU query latency. Request traces are synthetic. Results are not expected to reproduce microsecond-for-microsecond on other machines.

## Files

- `round7_span_coalescing.py`: sweep bridge thresholds and test one-, five-, 20- and 40-line reads.
- `round7_base_decode_cache.py`: compare decoding repeated shared base frames vs per-request memoization.
- `round7_frame_accounting.py`: instrument redundant frame decoding and piece counts.
- `round7_span_results.json`, `round7_span_stress.json`, `round7_cache_results.json`, `round7_frame_accounting_results.json`: experiment outcomes.
- `CDG_round7_research_report_2026-11-09.md`: interpretation, uncertainty and primary-source literature.
- `inputs/CDG_round6_research_package_2026-11-09.zip`: original Round 6 inputs and scripts.
