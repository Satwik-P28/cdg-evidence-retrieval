# CDG Round 110: Word-Buffered Exact BARM-R Decode

**Date:** 2026-11-23. **Status:** PASS. 68 local input/compatibility tests and full original SHA-locked QASPER/SciFact runs passed in GitHub Actions [45250427687](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45250427687). Both full numerical JSON artifacts are saved in `experiments/round-110/results-qasper.json` and `results-scifact.json`.

## Why this is the next real question

R108 demonstrated BARM's reference bitstream is compact on SHA-locked QASPER and SciFact FTS5 logical postings; R109 measured an actually materialized per-term seekable SQLite docID-only posting store. BARM physically used fewer bytes, but the reference decoder had roughly 1.8–2.1× slower warm median Python+SQLite lookup than basic varint, with substantially worse tail time in the one observed run.

R110 retains *exactly the same* R107 `barm_r` encoder and on-disk bytes. It replaces only the decoding algorithm:

- A single Python integer represents the packed bitstream rather than calling `.bit()` for each individual unary or offset bit.
- Unary quotients are located by bit length of the complemented unread prefix, then the cursor advances over all ones and the terminating zero in a bounded operation.
- Fixed-width Rice remainders and dyadic offsets are extracted with one mask and shift each.
- Independent framing, block-length caps, output count, scale range, zero padding and truncation checks remain enforced.

The result is not a novel integer code, not a proof of new compression theory, and not a test of RH. This is ordinary decoder engineering with potential time/space Pareto consequences for CDG.

## Frozen original-source and benchmark contract

- Pull R108's **same** SHA-locked original QASPER DEV and SciFact corpus streams, same 1,950-term five-band stratified selection, same 144,717 and 116,186 logical posting entries respectively. Assert R108 byte-length identity, selected term count and posting count.
- For all selected terms, decode every BARM block byte-identically with legacy R107 and R110 fast decoder, and compare with original positive docID gaps. Varint, scalar StreamVByte-format and partitioned Elias-Fano reference decoders also must reconstruct every list.
- Run seven warm batches per method and corpus, changing method order with independent deterministic seeds. Each timed batch decodes all selected lists and accounts for every value. Record all seven times, median CPU wall time and ratios.
- These are Python, warm-runner, one-machine descriptive timings. No cache flushing, CPU pinning, process isolation, C/SIMD comparison, physical SSD reads, or confidence intervals from independent runner repeats. Do not extrapolate a native-production latency improvement.

## Actual original-source results

Every selected logical posting list decoded to the same original values across both decoder versions and ordinary reference formats; BARM encoded bytes were **130,129** QASPER and **110,142** SciFact in both versions, precisely reproducing R108 byte totals.

| Method | QASPER warm median batch decode (144,717 postings) | SciFact warm median batch decode (116,186 postings) |
| --- | ---: | ---: |
| R107 legacy bit-at-a-time BARM-R | 224.845 ms | 185.804 ms |
| **R110 word-buffered BARM-R** | **105.996 ms** | **86.951 ms** |
| Variable-partition EF Python reference | 80.897 ms | 64.454 ms |
| Scalar StreamVByte-format Python control | 49.580 ms | 40.505 ms |
| Scalar varint Python control | 26.271 ms | 20.702 ms |

Observed warm median decoder speedup for the unchanged BARM bytes: **2.121× QASPER** and **2.137× SciFact**. This is a repeated, method-order-randomized CPU-runner **Python scalar comparison**, not optimized native or SIMD throughput and not a speedup guaranteed on other hardware.

The optimized BARM remains **4.03× QASPER** and **4.20× SciFact slower than scalar Python varint** on the sampled decoding workload. This is a material failure against the simplest decoding-speed control. A general "BARM is now faster" claim is unjustified. Benchmark results also depend on source term frequency and independent framing.

**Decision:** Promote the fast decoder only as the default experimental BARM reader, not as a production retrieval codec. The current storage/CPU frontier motivates optimized native implementations, explicit seek offsets, and a true total source+index+query Pareto study. Do not claim a new RH implication or end-to-end RAG efficiency from this result.

## Decision

If R110 improves the warm reference decoder without changing any bytes or exact outputs, it becomes the preferred BARM *experimental reader*. We still must compare actual native optimized alternatives and full source+index overhead before a production decision.

## Reproduction

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-110
python experiments/round-110/speed_lab.py --dataset qasper --out experiments/round-110/ci-qasper.json
python experiments/round-110/speed_lab.py --dataset scifact --out experiments/round-110/ci-scifact.json
```

GitHub workflow `.github/workflows/cdg-r110-barm-fast-decode.yml`.