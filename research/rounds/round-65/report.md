# Round 65: Replayable Incremental Metadata Versus Full Manifest Rewrite

**Date:** 2026-11-17. **Status:** successful GitHub Actions run **44185321958**, five new unit tests passed. All original Round 64 source reconstruction and migration tests passed in the same run. This is a classical log-structured metadata design ablation, not a novel storage system.

## Question and baseline

R64's streaming prototype rewrote the entire compact source manifest after every appended source, producing 5.1–5.8 MB of encoded metadata writes over roughly 500-source ingestion streams for archives around 190–215 KB. The full-rewrite baseline is **intentionally naive**. Before rejecting migration on this number, measure a correctly replayable append-only event journal.

Round 64 now records immutable per-source append and prior-source replace events when an earlier source is re-encoded into gear512 frames. Each event stores a source index, operation and complete source frame manifest. Encode event JSON with Zlib6 and a 4-byte packet length plus truncated 16-byte SHA256 payload checksum. Replay events in order; a replace before append or a truncated/corrupt event is rejected. At checkpoint intervals 32, 128 or 512 events, encode the full current source state with the established Round 47 compact binary/Zlib manifest and retire the old journal. Also test never checkpointing.

The snapshot+journal final state must match **every source manifest** of the Round 64 source archive exactly, including all retroactive replacements. Tests check corruption, invalid index transitions, partial records and interval variants. This is simulated encoded user-space I/O, **not** a true atomic, fsync-durable database journal or crash recovery protocol.

## Results with 512 independent sources

At checkpoint interval 128:

| Source history | Full manifest rewriting, total encoded bytes written | Journal events plus checkpoint bytes written | Write reduction | Retained metadata overhead versus one full compact snapshot |
| --- | ---: | ---: | ---: | ---: |
| Ruff | 5,813,623 | 143,255 | 97.536% | +8.466% |
| Transformers | 5,807,406 | 143,679 | 97.526% | +9.047% |
| Flask | 5,128,244 | 128,396 | 97.496% | +6.021% |
| vLLM | 5,745,079 | 137,024 | 97.615% | +9.110% |
| Pydantic | 5,389,766 | 131,629 | 97.558% | +8.809% |

This reduction is **relative to rewriting the complete manifest on each append**, not relative to a tuned SQLite WAL, RocksDB/LSM, Git index or production append-only B-tree. All schemes use the same underlying content-addressed compressed payloads, with metadata represented differently.

For Ruff+512 with an interval of 128, the final journal+checkpoint metadata occupied **22,471 bytes**, versus **20,717 bytes** for a single compact full manifest. Source payloads occupied 184,955 bytes, so the complete journal+payload archive retained **207,426 bytes**, up from 205,672 bytes with a single full snapshot.

The retention/read/write trade-off is visible at other checkpoint intervals:
- **No checkpoints:** Ruff metadata written/retained 90,758 bytes, a 98.44% reduction in metadata *writes*, but 338.1% more persistent metadata versus one compact snapshot and a median cold replay about **5.13 ms**.
- **Checkpoint every 32:** metadata writes 272,697 bytes, persistent 22,471 bytes, cold replay about **1.85 ms**.
- **Checkpoint every 128:** metadata writes 143,255 bytes, persistent 22,471 bytes, cold replay about **1.86 ms**.
- **Checkpoint every 512:** metadata writes 110,933 bytes, persistent 22,471 bytes, cold replay about **1.75 ms**.

The identical final retained size for the checkpointed cases is a dataset/tail alignment outcome, not a theorem. Shorter intervals may have lower worst-case replay depth but write more snapshot bytes. Measured replay times are small, warm, sequential Python results and should not be compared directly with previously obtained FTS query microseconds.

## Conclusions and safety boundaries

**Keep as a research control:** source metadata journal plus occasional compact checkpoints greatly reduces unnecessary full-manifest encoding and rewriting while preserving exact source mappings.

**Do not promote as production:** a real system needs atomic checkpoint pointer swap, checksummed/length-delimited durable append with fsync rules, recovery semantics for torn tails, protection against hash collision and malicious corrupt content, concurrent writers, reference-count/CAS GC ordering, indexing for random manifest access, memory-budgeted cold replay, and fair actual SQLite WAL or Git pack controls.

The journal variant can occupy more space than a full compact snapshot and adds cold replay latency. The encoder and checkpoint algorithms are conventional and not a new compression method.

The next research priority should leave isolated microbenchmarks and integrate true versioned retrieval, complete annotated supporting evidence, model/verifier token costs, and a durable standard database control. Source evidence bytes being identical is not sufficient to conclude factual correctness or no hallucination.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-65 -p 'test_*.py' -v
    python experiments/round-65/manifest_journal.py --out experiments/round-65/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44185321958 . Upstream README and HotpotQA data remain under their respective original licenses and are not committed in this repository.
