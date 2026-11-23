# CDG Round 112: Complete Positional Index and Exact Phrase-Query Control

**Date:** 2026-11-23. **Status:** 21 local structural/fixture tests passed under a temporary compatibility stand-in for the R108 codec; **original-source experiments and authentic R108 codec tests are pending remote GitHub Actions**. The stand-in is neither committed nor used to report original-corpus measurements. Never claim verified original-corpus compression until the GitHub workflow completes.

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

## Epistemic gates and pending evidence

**[FACT]** R111 full vocabulary and BM25 scores were verified as above. **[FACT]** R110's faster Python BARM decoding remained about 4 times slower than Python scalar varint in its particular sampled warm decode workload. **[FACT]** R112 fixture tests locally pass, but they do not validate native R108 codecs or real original-source file sizes. **[UNKNOWN UNTIL CI]** Which fixed codec is smallest when *full position streams* are included; whether a simple static hybrid has any advantage; whether the original phrase-check query plan passes on QASPER and SciFact; and what the feature-consistent original SQLite file sizes are.

### Paper-worthiness assessment

**Potential short empirical systems paper now:** The more mature and distinctive result is R101–R106: versioned lossless evidence source store Pareto frontier over physical bytes, decompressed source bytes, compressed BLOB rewrite amplification and SQLite WAL growth, with FTS5 correctness and original-source SHA receipts. The negative outcome of historical pseudo-access policy matters scientifically. R107–R112 form a **separate index-codec ablation**, not yet the best lead claim, because major prior art, runtime mismatch, and lack of complete production equivalents remain.

**Not yet justified:** Claiming a novel universally superior compressor, superior native SQLite FTS5 index, reliable reduced RAG hallucinations, or a peer-reviewed high-impact main-track result. Beyond reproducibility, a strong main-track paper needs: genuinely new method (e.g., precommitted risk-/cost-aware segment selector over true independent workloads); original corpora and real temporal traces or separate time-split sources; matched production PISA/PEF/FastPFOR baselines; independently measured end-to-end source+index+inference costs and full answer correctness; uncertainty and ablation analysis; and faithful, appropriately bounded novelty claims.

**Best next mathematical/research transfer:** Storage-tier selection as a constrained **multi-objective optimization problem** using actual storage, decode/read, mutable-WAL and query-operator frequencies, not an RH-derived transform. Develop a *simple baseline-first* policy with separate training and source-disjoint heldout data; evaluate against static paper length/size thresholds and original R106 negative historical policy. R112 isolates the crucial positional storage cost before any such policy.