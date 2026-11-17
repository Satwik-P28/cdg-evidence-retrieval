# Round 46: Exact Versioned Compression, Delta Coding, and Partial-Read Amplification

**Date:** 2026-11-17. **Status:** executed in GitHub Actions run 44028480266. Five dedicated regression tests passed. Real-input corpus consists of 12 pinned historical Astral uv README revisions (120,601 aggregate source bytes), with 192 seeded random byte-span reads. This is one related document history, not 12 independent text sources or a RAG accuracy benchmark.

## Goal

Find lossless storage representations that permit exact historical source reconstruction while minimizing both retained archive size and compressed bytes activated by a small query span.

The experiment compares independent Zlib-compressed full versions, fixed 512/2048-byte frames, simplified gear-hash content-defined chunks (nominal averages 512 and 1024 bytes), line-aligned 512-byte groups, and prefix/suffix delta patches with full checkpoints every three or five revisions. This is a comparison of well-established algorithm families, not a novel compressor.

Each framed archive retains every version's full SHA-256 digest, each frame digest and raw length, and the complete serialized manifest. Identical frames are CAS-reused across versions. Every version and random read span is reconstructed byte-for-byte and verified. The delta archive also verifies all intermediate dependent source versions on read. No user-visible citation authenticity or source semantic truth claim follows from these hashes.

## Measured outcomes

Python 3.13, Ubuntu GitHub Actions run 44028480266; Zlib level 6, 192 randomly sampled 256-byte spans, 16 per version. Numbers are sensitive to implementation, warm cache and source edits. Archive sizes include uncompressed JSON manifests and compressed payload frames. Git control sizes are reported separately.

| Method | Retained archive bytes | Mean compressed bytes activated per span | Median compressed bytes activated | Median read (microseconds) |
| --- | ---: | ---: | ---: | ---: |
| Whole-version Zlib | 49,843 | 3,968 | 3,977 | 29.242 |
| Fixed 512 | 62,675 | 444 | 356 | 6.913 |
| Fixed 2048 | 44,680 | 1,062 | 967 | 10.197 |
| Gear 512 | 31,354 | 680 | 682.5 | 8.345 |
| Gear 1024 | 30,309 | 1,025 | 868 | 9.616 |
| Line groups ~512 | 50,317 | 439 | 384.5 | 8.868 |
| Delta checkpoint 3 | 23,981 | 4,635 | 4,114 | 43.669 |
| Delta checkpoint 5 | 19,939 | 5,391 | 4,425 | 61.343 |

Separate conventional Git control: pack plus pack index = **9,802 bytes**; all .git metadata = **42,695 bytes**. The two Git values have distinct boundaries and must not be conflated with either a fully checked-out working tree or the custom archives. Aggressive Git packfile delta compression is already highly effective on this revision history.

## Interpretation and decisions

1. **CDG storage-only superiority is NOT established.** The packed Git control is smaller than every custom Zlib archive when comparing compact pack/index bytes.
2. **Evidence-span economics differ from archive economics.** Fixed 512 frames give the lowest measured partial-read traffic and time but the largest retained custom archive (62,675 B). Delta5 gives smallest custom retained footprint but high decode amplification due to chaining through previous versions.
3. **Gear 512 is a promising measured compromise** for this single history: 31,354 B retained versus whole-Zlib 49,843 B (about 37% less) and roughly 680 B mean compressed traffic per sampled 256-byte span versus 3,968 B whole-Zlib. However the gear algorithm is a basic content-defined chunker, not a claim to FastCDC-level throughput or novelty.
4. **Manifest overhead is material.** Gear512's raw JSON manifests consume 15,332 B out of 31,354 B, nearly half the archive. A compact or compressed manifest could improve this trade-off without changing lossless frames. It must also account for cold manifest decoding, source-span indexing and integrity checks.
5. **Do not overinterpret microseconds.** Reads occur inside one Python process with hot data structures and no actual disk seek, fsync, cache eviction or production content indexing. Compressed bytes activated are logical traffic, not physical SSD reads.

## Next combinatorial test

Introduce two compact manifest representations for the gear layouts, compare their total bytes and per-query parsing/verification overhead, then re-run exact byte-span recovery. Test against real Git version pack storage and an on-demand Git blob checkout when selecting a full historical source. If the simple archive layout dominates once manifest compression is counted, prefer it over custom grammar/delta encoders.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-46 -p 'test_*.py' -v
    python experiments/round-46/version_chunks.py --out experiments/round-46/results.json

Source project and licensing: https://github.com/astral-sh/uv (MIT or Apache-2.0). Full input text and pinned Git blobs are archived from Round 38; reusing these revisions for local research does not imply independent question labels.

This result does not test a quantum algorithm, a new entropy bound, semantic entailment or end-to-end RAG QA.
