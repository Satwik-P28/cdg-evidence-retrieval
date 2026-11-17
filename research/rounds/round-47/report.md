# Round 47: Compact Versioned Manifests and Cold Evidence-Read Cost

**Date:** 2026-11-17. **Status:** 24 frame/manifest combinations tested in GitHub Actions run 44028907694, four regression tests passed. Same 12 authentic Astral uv README historical versions as Round 46. One closely related version history, not a representative corpus or full RAG evaluation.

## Hypothesis and experimental controls

In Round 46, gear512 retained 31,354 bytes including 15,332 bytes of verbose JSON manifests. A compressed or compact manifest can reduce retained storage without changing frame deduplication or exact byte-span reconstruction. But reconstructing metadata on a cold query adds CPU cost, which must be measured rather than assumed away.

Compare four source-frame schemes (whole source, fixed512, gear512 and gear1024) against six representations of the identical manifest content: raw JSON, Zlib-compressed JSON, binary with 32-byte digests and unsigned varints, compressed binary, dictionary-based frame IDs, and compressed dictionary IDs. Every serialized manifest includes a 32-byte integrity digest. This is a corruption check, not cryptographic source authenticity or a signature.

## Executed CI observations

| Gear512 manifest | Total archive bytes | Manifest bytes | Mean compressed bytes per sampled 256-byte span | Median warm read (microseconds) | Median cold metadata-and-span read (microseconds) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raw JSON | 31,386 | 15,364 | 539.44 | 7.952 | 82.842 |
| JSON + Zlib | 18,172 | 2,150 | 539.44 | 8.072 | 90.158 |
| Binary | 22,119 | 6,097 | 539.44 | 7.185 | 141.228 |
| Binary + Zlib | 17,769 | 1,747 | 539.44 | 8.297 | 148.274 |
| Dictionary IDs | 18,062 | 2,040 | 539.44 | 7.681 | 157.247 |
| Dictionary IDs + Zlib | 17,770 | 1,748 | 539.44 | 8.091 | 163.632 |

All representations passed exact full-version reconstruction, exact selected byte-span reconstruction, metadata roundtrip, and tamper detection tests. The cold measurement recreates the full manifest from packed bytes on every query in Python memory. It is not a disk-cache miss or SSD physical-I/O experiment. Queries differed from Round 46's seeded random sample, so direct read-traffic comparisons across rounds need a matched replay.

The **two-dimensional archive size versus mean compressed read traffic Pareto set**, excluding cold decode latency, contains:
- Fixed512 + binary-Zlib: 46,262 B retained; 447.02 B mean compressed traffic.
- Gear512 + binary-Zlib: 17,769 B retained; 539.44 B mean compressed traffic.

The gear512 binary-Zlib representation reduces size by approximately **43.4%** relative to the raw-JSON gear512 variant (the framed payloads are unchanged). However, JSON-Zlib costs only 403 additional bytes while having faster median cold manifest decoding in these small Python samples. Thus a workload choosing only the smallest archive is not necessarily optimal.

## Decision

**Keep:** content-addressed gear512 frames plus compact metadata as a candidate for small historical archives and random evidence spans. Retain both compressed binary and compressed JSON variants; do not decree a universal winner.

**Reject:** an automatic claim that a small custom archive beats Git delta packing. Round 46's aggressive Git packed-object control is still smaller for pure archive bytes on the exact same source history. Retain the Git baseline in further experiments.

**Next:** integrate FTS5 historical line-span retrieval with source-bound manifest receipts (Round 48) and account for the index footprint and manifest decoding. If FTS5 or metadata dominates, compression-only byte improvements may be irrelevant to end-to-end costs.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-47 -p 'test_*.py' -v
    python experiments/round-47/manifest_lab.py --out experiments/round-47/results.json

Detailed metrics and reproducible numerical results are in the GitHub Actions run 44028907694 artifact. No new compression theorem or RAG answer-quality improvement is claimed.
