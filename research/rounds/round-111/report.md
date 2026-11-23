# Round 111: Complete-Vocabulary and BM25 Semantics Falsification

**Date:** 2026-11-23. **Status:** PASS. Thirty synthetic local tests and original SHA-locked complete-vocabulary QASPER/SciFact GitHub Actions matrix succeeded in [run 45260649171](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45260649171). Original-source aggregate outputs are committed as `experiments/round-111/results-qasper.json` and `results-scifact.json`.

## Hypothesis and stronger falsifier

R108's 1,950-term stratified logical sample favored BARM compression. R109 materialized actual docID-only stores and found a physical size benefit against the tested Python-codec baselines. R110 improved BARM decoder CPU cost without changing its bits, but its optimized scalar Python decoder was still about 4x slower than Python varint. All three rounds omit terms outside a hash-stratified sample and original term frequencies/actual BM25 score parity. For their full index savings to be meaningful, **complete-vocabulary materialization with true term frequencies and document lengths** must not erase the advantage.

### Immutable source and format contract

Reuse R108's existing SHA-locked original QASPER DEV paragraph reader (13,266 documents) and SciFact title/abstract corpus reader (5,183 documents). Never persist user questions, original source passages or paper bodies in Git result artifacts. Index original title + body in a single contentless FTS5 column using its tokenizer; extract every term's true per-document frequency and each document's token length directly from `fts5vocab(instance)`.

For each of six codec stores, persist the full corpus vocabulary with identical SQLite 4 KiB pages and identical `term TEXT PRIMARY KEY, df, payload` `WITHOUT ROWID` schema. Payload has a one-byte codec discriminator, four-byte gap length, independently framed compressed positive gaps and identically varint-compressed per-document term frequencies. A document-length table and original-document-count/total-tokens metadata are present and fully charged to every store. Perform SQLite `VACUUM` and compare actual physical file size, with total payload and schema/lexicon overhead reported separately. Confirm **all** encoded lists recover every original docID and tf exactly.

### Methods and prior art

- Fixed BARM-R; ordinary framed varint; R108's DP reference Elias-Fano (not production PEF); framed bitpack.
- Fixed rule hybrid: `df < 4` uses varint, otherwise BARM. Threshold is fixed before seeing this round's corpus results. It is not tuned on test data.
- In-sample minimum-byte oracle across four codecs, charging the 1-byte codec tag. This is an attainable per-list envelope, not a learned policy and not a CPU-optimal hybrid.
- Original native contentless one-column FTS5 `detail=full` provides the **BM25 ranking correctness oracle** and a contextual larger physical index. Native FTS5 includes positions, so it is not functionally matched to the experimental reduced index.

### Score and provenance correctness

Check numerical BM25 for independently SHA-selected df1, df2–3, df4–31, df32–256 and df257+ single-term queries, plus conjunctive term pairs, using SQLite FTS5's `bm25()` as the independent score reference. Assert exact selected result-document sets and per-document scores within absolute 1e-12, with tied-score order differences enumerated rather than counted as rank errors. No phrase, NEAR, semantic, vector, generated-answer, or source-byte receipt claim is established.

### Verified original-source outcomes

Both GitHub Actions jobs passed with original source SHA verification inherited from the established R108 readers. Every term's encoded docIDs and frequencies was reconstructed before size was accepted. The one-column contentless FTS5 reference was independently rebuilt for every original corpus and was never codec-substituted. Raw upstream source text was not committed.

| Full original-source workload | QASPER DEV | SciFact corpus |
| --- | ---: | ---: |
| Documents | 13,266 | 5,183 |
| Entire source vocabulary terms | 22,454 | 35,936 |
| **All distinct term/document postings** | **710,223** | **633,936** |
| Total original term occurrences / token counts | 1,043,480 | 1,167,874 |
| Native one-column contentless FTS5 bytes, **not feature-equivalent** | 3,084,288 | 3,379,200 |
| **Fixed BARM-R external SQLite bytes** | **2,977,792** | **3,264,512** |
| Fixed varint external SQLite bytes | 3,313,664 | 3,551,232 |
| R108 variable partitioned Elias-Fano reference external SQLite bytes | 3,182,592 | 3,424,256 |
| Fixed-width bitpack external SQLite bytes | 3,280,896 | 3,366,912 |
| **Predeclared hybrid (df<4 varint; else BARM-R)** | **2,969,600** | **3,256,320** |
| In-sample min-size oracle, codec selector fully charged | 2,965,504 | 3,239,936 |

Full-vocabulary fixed BARM-R saves **335,872 B (10.14%)** versus its same-schema varint control on QASPER, and **286,720 B (8.07%)** on SciFact. BARM-R also beats the R108 *reference* partitioned Elias-Fano by 204,800 B (6.43%) and 159,744 B (4.67%), respectively. These are actual physical SQLite page sizes, not sums of abstract codeword lengths. They do **not** imply any such difference versus production PEF or native SQLite FTS5.

The predeclared `df < 4` hybrid saves only another **8,192 B** versus full BARM-R in either corpus (0.28% QASPER, 0.25% SciFact), showing that the short-list overhead concern is real but modest under the complete metadata and lexicon denominator. The in-sample per-list minimum-storage oracle saves 4,096 B versus the fixed hybrid on QASPER and 16,384 B on SciFact. This is a within-implementation lower envelope, not proof of globally optimal code selection or a learned decision policy.

**Full-vocabulary frequency-aware BM25 validation:** all six stores verified **112 predeclared lexical/conjunctive queries each** against SQLite's independent FTS5 `bm25()` implementation. Maximum per-document absolute score discrepancy was **3.5528×10⁻¹⁵ QASPER** and **1.7764×10⁻¹⁵ SciFact**, with zero scored-rank tie discrepancies. Unlike R109's set-only matching, this establishes exact sampled-query BM25 score semantics within floating-point tolerance, while leaving phrase and positional semantics out of scope.

**Important negative / restricted claims:** The fixed BARM-only store is *not* the byte minimum: a simple varint-for-short-lists rule wins on both corpora. The production-native FTS5 bytes are shown only as context: native FTS5 stores positions and can perform phrase matching, unlike the comparison stores. BARM has not overcome the large Python CPU decode deficit identified in R110. Whole source-archive bytes, positional posting metadata, reader tokens, source SHA receipts, user query distribution and dynamic updates are not included here. The experiments did not measure end-to-end RAG answer quality.

This strengthens the systems evidence for **compact, feature-restricted, frequency-aware inverted lists**, but does not establish a novel compression theorem, an RH/GRH consequence or a production index performance advantage. Next decisive test: integrate token positions and phrase/NEAR semantics into a feature-equivalent original-corpus index, or benchmark optimized native PEF/StreamVByte/FastPFOR under the same reduced contract with total source+index, decode CPU and query latency in one Pareto table.

**Acceptance gate: PASSED for this limited contract.** Thirty local tests and both original-source GitHub Actions jobs passed full integer + tf roundtrip, full physical byte accounting, and independent sampled-query BM25 parity. If fixed BARM fails to outperform varint or EF across full-vocabulary persisted indexes, its sampled success does not support full-index compression superiority. Even if it wins physical bytes, no native FTS5, SIMD, phrase, random-access CPU, or end-to-end RAG benefit may be claimed.

## Reproduce

See `experiments/round-111/README.md` and `.github/workflows/cdg-r111-full-bm25-index.yml`.