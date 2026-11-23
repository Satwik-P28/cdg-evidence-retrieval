# CDG Round 112: Complete Positional Index and Exact Phrase-Query Control

**Date:** 2026-11-23. **Status: PASS.** 21 local fixture checks passed; both original SHA-locked QASPER/SciFact runs with actual R108 codecs, original full-vocabulary FTS5 positions and BM25/phrase differentials passed [GitHub Actions run 45278147405](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45278147405). Local tests used a temporary compatibility stand-in not committed; only GitHub Actions results are the source of authentic numerical findings.

## Research question

R111 materially stored the entire QASPER/SciFact index vocabulary, exact docIDs, term frequencies, and documents lengths, reproducing SQLite's conjunctive and single-term BM25 scores on 112 original-source queries per corpus. Its BARM index bytes were 2,977,792 vs varint 3,313,664 on QASPER and 3,264,512 vs 3,551,232 on SciFact. Those stores **omitted positions**, a fundamental feature of the native FTS5 `detail=full` baseline, so their measured savings were not equivalent full-index findings.

R112 adds the missing full per-token original positions with strict position reset at each document boundary. Every external store must now decode actual ordered original phrase matches as well as term frequency and BM25. We also test whether a static short-list hybrid or in-sample size oracle can outperform any fixed codec, charging physical index pages and every stored codec tag.

## Mechanism

1. Build contentless, one-column SQLite FTS5 (`unicode61`, `detail=full`) over official original QASPER DEV paragraphs or SciFact abstracts; fetch only via existing strict upstream SHA-lock modules. Index the exact same text concatenation and row IDs in every arm.
2. Materialize the full `fts5vocab(...,'instance')` term/row-ID/offset stream. For each term store positive doc-ID gaps, per-document term frequencies, and positive position gaps, resetting the latter within each document. This is exact lossless source-token position recovery, not source-byte reconstruction.
3. Create seven external SQLite `WITHOUT ROWID` full-vocabulary indexes with identical posting/document-length schemas. Count the actual `VACUUM`ed SQLite file bytes including term lexicon, per-term mode selectors, docID/TF/position BLOBs, document lengths and page overhead. No source text copy in any compared store.
4. For BM25 queries, fetch only docIDs/TFs; for bigram phrases, fetch and decode positions and check adjacent offsets. Independently compare deterministic SHA-selected single/conjunctive BM25 top-10 scores and ordered bigram phrase rowID sets against native SQLite FTS5.
5. Preserve negative results and do not claim independent SSD I/O/CPU wins, production code supremacy, or end-to-end RAG efficacy.

## Strongest methodological connection and prior art

- **Pibiri and Venturini (2020), Techniques for Inverted Index Compression**: standard codecs and partitioning are mature; BARM's comparison against a DP Python EF reference is not a production-PEF superiority finding. https://arxiv.org/abs/1908.10598
- **Pibiri and Venturini (2020), On Optimally Partitioning Variable-Byte Codes**: even baseline varint can be greatly improved by partitioning. https://arpi.unipi.it/handle/11568/1029436
- **Positional indexing cost**: "To index or not to index: Time–space trade-offs for positional ranking functions" explicitly notes positional postings can cost 3–5 times a non-positional index. https://www.sciencedirect.com/science/article/pii/S0306437919305186
- **PISA** provides optimized compression and BlockMax WAND search infrastructure that must enter a later head-to-head test. https://pisa.readthedocs.io/en/latest/index.html
- SQLite FTS5 semantics, offset vocab, document-size details: https://www.sqlite.org/fts5.html


## Verified original-source results (GitHub Actions)

Both original SHA-locked source runs passed, including **112 BM25 single/AND queries and 32 exact bigram phrase queries per corpus** for every external codec. Original native scores and decoded external scores differed by at most 1.78e-15, with no ranking tie-order disagreements in the tested queries. Every original term and position stream was reconstructed after physical SQLite writes. **No original-source text or query terms were committed.**

| Corpus | Docs | Vocab terms | Distinct postings | Token positions | Native contentless FTS5 bytes | BARM-R external bytes | Varint external bytes | Static hybrid external bytes | In-sample oracle external bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| QASPER | 13,266 | 22,454 | 710,223 | 1,043,480 | 3,084,288 | 4,915,200 | 5,267,456 | 4,890,624 | 4,722,688 |
| SCIFACT | 5,183 | 35,936 | 633,936 | 1,167,874 | 3,379,200 | 5,701,632 | 5,959,680 | 5,693,440 | 5,423,104 |

**Result:** On QASPER, the external BARM-R positional store consumed **6.69% less physical storage than the matched-schema external varint control**, but was **59.36% larger than native FTS5**. On SciFact, corresponding values were **4.33% less than varint** yet **68.73% larger than native FTS5**. The static short-list hybrid used slightly fewer physical pages than fixed BARM on both. Even the per-term/per-plane in-sample minimum-size oracle is larger than native FTS5, so simply selecting from the tested codecs cannot close the gap.

These external indexes implement tested term-frequency BM25 and exact ordered bigram phrase membership using all original token offsets. Native FTS5 also supports more sophisticated query operators, configurable ranking, term-prefix lookups, and production search paths. The comparison therefore **favors native FTS5 in bytes** on these exact sources without proving universal cross-engine superiority; importantly, it eliminates an earlier misleading incomplete-feature comparison.

The result also highlights why reporting only docID stream compression is insufficient. Full positional storage and per-term framing/table metadata can dominate any benefit from a new integer code. The per-term oracle's selection uses original test data, so it is a lower envelope, not a trained adaptive codec that could be claimed as a new method.

**Outcome: NEGATIVE for BARM-native-index superiority; KEEP BARM only as a reference component**, and redirect novelty work to jointly optimized versioned source storage, query-conditioned activation, and calibrated evidence verification, where original CDG provenance and WAL methods provide a clearer systems distinction.

Workflow and artifacts: [GitHub Actions run 45278147405](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45278147405), `experiments/round-112/results-qasper.json` and `results-scifact.json`.

## Epistemic gates and limitations

**[FACT]** R111 full vocabulary and BM25 scores were verified as above. **[FACT]** R110's faster Python BARM decoding remained about 4 times slower than Python scalar varint in its particular sampled warm decode workload. **[FACT]** Original R112 full position reconstruction and restricted BM25/phrase correctness passed for both datasets and all seven policies. **[NEGATIVE]** Both BARM and the minimum-size oracle physical SQLite stores are larger than conventional native FTS5 on the same complete original one-column positional corpus. **[UNCERTAIN]** How this changes under production SIMD libraries, FTS5-native segment formats, phrase-heavy latency distributions, source-version updates, or different corpora. No claim of superior operational latency is justified.

### Paper-worthiness assessment

**Potential short empirical systems paper now:** The more mature and distinctive result is R101–R106: versioned lossless evidence source store Pareto frontier over physical bytes, decompressed source bytes, compressed BLOB rewrite amplification and SQLite WAL growth, with FTS5 correctness and original-source SHA receipts. The negative outcome of historical pseudo-access policy matters scientifically. R107–R112 form a **separate index-codec ablation**, not yet the best lead claim, because major prior art, runtime mismatch, and lack of complete production equivalents remain.

**Not yet justified:** Claiming a novel universally superior compressor, superior native SQLite FTS5 index, reliable reduced RAG hallucinations, or a peer-reviewed high-impact main-track result. Beyond reproducibility, a strong main-track paper needs: genuinely new method (e.g., precommitted risk-/cost-aware segment selector over true independent workloads); original corpora and real temporal traces or separate time-split sources; matched production PISA/PEF/FastPFOR baselines; independently measured end-to-end source+index+inference costs and full answer correctness; uncertainty and ablation analysis; and faithful, appropriately bounded novelty claims.

**Best next mathematical/research transfer:** Storage-tier selection as a constrained **multi-objective optimization problem** using actual storage, decode/read, mutable-WAL and query-operator frequencies, not an RH-derived transform. Develop a *simple baseline-first* policy with separate training and source-disjoint heldout data; evaluate against static paper length/size thresholds and original R106 negative historical policy. R112 isolates the crucial positional storage cost before any such policy.