# Jane Street FOCUS | CDG project brief

## Preferred project name

**CDG: Evidence-Preserving Retrieval and Versioned Compressed Storage**

Use **CDG** rather than inventing a new academic-sounding acronym expansion. Name the implementation, the constraint, and the experiment.

## Short application field (approximately 65 words)

I have been developing a retrieval and compressed-storage prototype that preserves exact source bytes and tracks evidence across immutable versions. It combines SQLite full-text search with independently compressed Zstandard frames and content-addressed source segments. In a controlled 11-generation update experiment, it retained 74.5% less storage than a full-rebuild baseline. The project taught me to separate correctness, retrieval quality, read amplification and update cost rather than optimizing a single attractive metric.

## Main project description (approximately 155 words)

I started CDG after noticing that retrieving relevant documents is not the same as retrieving enough evidence to justify an answer. I explored multihop retrieval on HotpotQA-derived questions, then built a file-backed prototype that maps indexed text to exact UTF-8 byte spans inside independently compressed Zstandard frames. The system now supports contentless SQLite FTS5 indexes, source-version hashes, generation-bound evidence receipts and content-addressed reuse of unchanged frames and search segments.

My most useful experiment followed eleven successive versions of five research reports. Incremental reuse occupied 1.17 MB versus 4.60 MB for a deliberately full-rebuild design, and median update time fell from 475.6 ms to 24.5 ms in the controlled replacement workload. The comparison is intentionally limited: a mature incremental SQLite implementation may perform just as well. Earlier tests also showed that lower compressed read traffic did not necessarily mean lower latency. I am using these results to learn how to design systems whose performance claims survive careful baselines and adversarial correctness tests.

## One-line resume entry

**CDG | Versioned Evidence Retrieval & Compressed Storage** | Independent Research Project, 2026

- Built a Python/SQLite FTS5/Zstandard prototype with byte-exact evidence receipts, immutable source generations and content-addressed search/frame reuse; measured **74.5% less retained storage and 19.4x faster median updates** against a full-rebuild baseline over 11 versions of five documents.

If space permits, a second bullet:

- Evaluated multihop evidence discovery on 100 HotpotQA-derived queries and compressed-source access; documented how bridge expansion improved complete supporting-document coverage from **33% to 46% @2**, while smaller frame reads did not reliably lower latency.

Keep the source/baseline qualifier wherever the performance metric appears. Do not turn this into a production claim or call the retrieval policy original.

## 30-second spoken explanation

I began by studying a retrieval failure: a system can find a relevant document but miss the second document needed to support an answer. I built a prototype that ties search results to exact source bytes in compressed storage. Once I added versioned evidence receipts, a new problem appeared: every small source edit forced me to rebuild and retain an entire archive. I redesigned the store around immutable per-source indexes and content-addressed frames. That reduced storage and update work against the original rebuild design, but I am now testing whether standard incremental SQLite can achieve the same thing. My focus has been on proving which optimizations are real.

## Why this is relevant to FOCUS

The connection is **technical problem-solving and learning through experiments**, not that RAG resembles a trading system. The transferable ideas are immutable state, correctness invariants, latency-versus-throughput trade-offs, data structure selection, counterexamples and challenging baselines. Jane Street does not require previous financial knowledge for FOCUS.

## Be ready to say what is not established

- The 19.4x comparison uses a deliberately rebuild-everything control on a small corpus. It is not versus optimized incremental databases.
- The HotpotQA-derived retrieval results were computed in a separate connected-data analysis, not an end-to-end execution through the compressed reader.
- Exact byte receipts establish identity within a chosen generation, not truth, authorization or independent source freshness.
- I have no peer-reviewed paper or independently verified SOTA RAG results.
- Model-assisted development/research was used. I can explain my own choices, experiments and corrections without implying all code was written unaided.

## Interview questions to rehearse

1. What is the asymptotic write amplification of full rebuilds versus per-source copy-on-write? Under what update distributions does the advantage disappear?
2. Why do SQLite index pages outweigh Zstandard payloads on a small corpus?
3. Why can smaller frame reads increase query latency?
4. What is the difference between `source_digest`, `frame_digest` and `generation_id`? Why do all matter?
5. Which metadata must change if a sentence insertion shifts later UTF-8 offsets?
6. What happens if the manifest is modified alongside the data by an attacker?
7. Why is a query-local FTS rank not comparable across independent source indexes?
8. What would an incremental SQLite WAL baseline have to include for a fair comparison?
9. When is a title mention *not* evidence of a valid semantic relationship?
10. Which result would make you remove the custom storage engine?
