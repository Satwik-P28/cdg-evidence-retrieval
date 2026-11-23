# R110: Packed-bit BARM decoder microbenchmark

This round preserves R107's BARM-R wire format. It substitutes one `int.from_bytes` packed bitbuffer, a bounded complement/bit-length unary scan and fixed-width mask extraction to reduce per-bit Python overhead. All input lengths, output counts and zero padding are checked. It is a scalar Python engineering experiment, not a new codec or a Riemann Hypothesis application.

Reproduce in root:

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-110
python experiments/round-110/speed_lab.py --dataset qasper --out experiments/round-110/ci-qasper.json
python experiments/round-110/speed_lab.py --dataset scifact --out experiments/round-110/ci-scifact.json
```

Source archives remain original SHA locked. No original scientific text, QA labels or machine-specific profilers are committed. The benchmark measures repeated warm Python decode batches in a shared CI runner, not production p95 query latency, cold SSD I/O, native SIMD speed or end-to-end RAG quality.