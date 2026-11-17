# Round 55: Real Multihop Supporting-Sentence Materialization Through Compressed Frames

**Date:** 2026-11-17. **Status:** executed successfully in GitHub Actions run 44162926421. Three dedicated new regression tests pass. Input is the first 128 SHA-ranked question IDs from the immutable Round 54 independent-dev sample; all support annotations in the selected 128 are structurally valid. This round combines source-indexed FTS5 sentence selection and version-bound, exact-byte compressed source receipts.

## Motivation and controlled workflow

Round 54 confirmed that a frozen exact-title bridge can improve complete supporting-document acquisition. That alone does not show RAG evidence coverage or compressed read savings. This experiment holds the source-document selection policies fixed and tests the physical evidence materialization stage.

For each of 128 questions, we index the 10 question-local candidate paragraphs as separate sources in one SQLite FTS5 sentence index. Every sentence row holds the original UTF-8 byte start/end offset, question ID, source-document ID and sentence ordinal. The full original source paragraphs are provided to the document-level BM25 selection, so neither this FTS index nor selective sentence decoding is claimed to avoid that upstream full-document scoring cost.

For document policies BM25 and the original exact-title bridge, choose K=2 and K=5 paragraphs. Compare reading whole selected original source documents with reading top two FTS5-ranked query-relevant sentences per selected document. Use original SHA-256 source digests, content-addressed compressed frames and compact version manifests. Every returned sentence span and source receipt is verified against original exact UTF-8 bytes. Gold supporting-fact annotations are used only to evaluate complete coverage, never to select rows.

Four lossless source layouts: whole-document Zlib+compressed JSON, fixed 512-byte frames+compressed binary metadata, content-defined gear 512-byte frames+compressed binary metadata, and gear512+compressed JSON metadata.

## Executed outcomes

FTS5 historical/contextual sentence index occupies **708,608 bytes** (including span-offset tables). Persisted compressed archives:

| Frame policy | Archive bytes | FTS index + archive bytes |
| --- | ---: | ---: |
| Whole source + compressed JSON | **482,158** | **1,190,766** |
| Fixed 512 B frames + binary/Zlib | 542,788 | 1,251,396 |
| Gear512 + binary/Zlib | 504,264 | 1,212,872 |
| Gear512 + JSON/Zlib | 527,512 | 1,236,120 |

Whole-document compressed source storage has the smallest total footprint. **This falsifies assuming content-defined chunking always saves bytes across independent paragraph sources**, despite its prior advantage for related revision histories. Frame manifest overhead and weak cross-document duplication matter.

Bridge K=2: complete gold document set appears in **55/128** questions; selecting top-two FTS sentences per chosen document yields complete annotated sentence coverage in **41/128**. Bridge K=5: complete documents in **107/128**, but complete annotated sentences after top-two FTS filtering in **79/128**.

For bridge K=5:

| Layout | Mean compressed bytes reading selected full documents per question | Mean compressed bytes when each top-two sentence read is counted separately | Mean compressed bytes after perfect within-query frame reuse |
| --- | ---: | ---: | ---: |
| Whole source Zlib | 1,628.79 | 3,190.62 | 1,628.79 |
| Fixed512 | 1,774.34 | 2,651.14 | 1,560.16 |
| Gear512 binary | 1,705.07 | 2,860.96 | 1,601.33 |
| Gear512 JSON | 1,705.07 | 2,860.96 | 1,601.33 |

In this exact index/query selection, top-two sentence filtering loses 28 complete-evidence questions relative to having all selected gold paragraphs, even though selected-sentence reconstruction is byte-exact. For gear512, ideal dedup within a query reduces compressed bytes accessed by only about 6% relative to reading all selected documents (1,601 versus 1,705), **not enough to justify the large evidence loss on its own**. Without shared-frame reuse, individual snippet read traffic exceeds reading complete selected documents.

Caution: These are counted compressed frame bytes and warm Python/SQLite checks, NOT measured SSD reads. The FTS5 index is charged in persistent storage, but full model tokens, cross-request cache, and actual OS I/O are not. The tiny curated subset makes generalization weak.

## Decision and next tests

1. **Do not promote** gear512 or other frames as the default for independent question-local documents; whole-Zlib is simpler, smaller and competitive on these short sources.
2. **Do not promote** naive FTS top-two sentence filtering as evidence complete. Recovery is worse even when all gold documents were selected. Better query/bridge-conditioned sentence selection or a larger sentence budget is needed.
3. **Retain** stable, exact source-byte receipt reconstruction and the explicit separation of document coverage, sentence coverage, persistent index/metadata, read amplification, and factual support.
4. **Next falsifier:** compare local BM25, source-title-link-conditioned sentence priority, FTS BM25 and randomized controls at different sentence budgets on the locked same cases, with compressed read cost matched. This is Round 56; treat any algorithm tuning after inspecting this dev subset as exploratory, not an untouched held-out test.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-55 -p 'test_*.py' -v
    python experiments/round-55/heldout_frames.py --sample-size 128 --out experiments/round-55/results.json

Raw JSON results and CI logs: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44162926421 . Upstream HotpotQA data carry CC BY-SA 4.0 and are downloaded without redistribution. No novel compressor, full model answer-quality gain or hallucination reduction is asserted.
