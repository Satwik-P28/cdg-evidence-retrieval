# Round 48: Integrated FTS5 Historical Evidence Spans through Versioned Compressed Frames

**Date:** 2026-11-17. **Status:** GitHub Actions run 44029238811, four new integration tests passed. The 12 authentic pinned uv README revisions were indexed with SQLite FTS5, using exact UTF-8 line byte offsets and source-generation receipts. This is retrieval integration, not independent natural-language QA or semantic entailment.

## Integration and invariants

- One historical FTS5 index contains source lines across all 12 document revisions, with separate byte offset metadata per line.
- A query specifies a generation and keyword and returns up to three ranked candidate lines. Each candidate becomes a generation-bound receipt carrying the complete source SHA-256 digest, serialized manifest digest, and exact byte start/end.
- The reader verifies metadata digest and activated frame bytes before yielding original UTF-8 bytes. An old-generation receipt is refused by the default current reader unless the requested historical generation is pinned.
- The CI tests cover Unicode byte spans, old/new query membership, exact reconstruction, stale receipt refusal, altered metadata hash rejection and corrupted compressed frame rejection.

The receipt checks *local content consistency*, not true-world source authority. SQLite index and compressed-frame publication are not crash-atomic in this experimental code.

## Executed benchmark

Ten source-derived keyword queries per version: **120 queries, 276 verified source-span recoveries**. SQLite FTS5 index file occupies **196,608 bytes** independently of chosen archive representation. Median FTS lookup was approximately **33 microseconds** in this warm Python/SQLite environment.

| Archive | Archive bytes | Archive + shared FTS index bytes | Mean compressed frame bytes per span | Median warm decoded span (microseconds) | Median including cold manifest reparse (microseconds) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Whole source + JSON | 49,875 | 246,483 | 3,968.17 | 28.608 | 42.123 |
| Fixed512 + binary-Zlib | 46,262 | 242,870 | 316.74 | 10.600 | 235.591 |
| Gear512 + binary-Zlib | 17,769 | 214,377 | 547.26 | 9.654 | 155.377 |
| Gear512 + JSON-Zlib | 18,172 | 214,780 | 547.26 | 9.665 | 89.569 |
| Gear1024 + binary-Zlib | 23,825 | 220,433 | 851.52 | 9.319 | 85.428 |

Note the changed query mix relative to Rounds 46 and 47: here we retrieve actual FTS-ranked historical source lines rather than random byte spans. Byte traffic and microsecond costs are therefore not directly interchangeable across rounds.

## Research interpretation

**Storage bottleneck migrated to the index.** In Gear512 + binary-Zlib, historical FTS5 is 196.6 KB out of 214.4 KB combined storage. Archive-only improvements are attenuated: replacing the whole-source archive with compact gear framing reduces complete index+archive footprint by roughly 13%, not the more dramatic archive-only fraction.

**Cold metadata cost reverses some preferences.** Gear512 + JSON-Zlib occupies only 403 bytes more than Gear512 + binary-Zlib but decodes the full metadata faster on the measured cold-in-memory path. Depending on query distribution and metadata caching, a slightly larger representation can be preferable.

**A baseline remains.** This is a simple SQLite keyword index plus lossless frames; it does not prove a unique retrieval algorithm. The highest-value next control is historical FTS5 index density and reduced ranking metadata, while explicitly measuring capabilities such as phrase query support. This is Round 49.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-48 -p 'test_*.py' -v
    python experiments/round-48/evidence_bridge.py --out experiments/round-48/results.json

Source corpus from Round 38. Results and full logs are in GitHub Actions run 44029238811. **No production RAG answer-quality advantage, independent credibility verification, FTS5 temporal update policy, or crash-durability result is claimed.**
