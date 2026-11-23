# CDG Round 110: Word-Buffered Exact BARM-R Decode

**Date:** 2026-11-23. **Status:** 68 local unit/synthetic tests passed; official original-source CI experiments pending. Do not claim source-level speedups until GitHub workflow artifacts are verified.

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