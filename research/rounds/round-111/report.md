# Round 111: Complete-Vocabulary and BM25 Semantics Falsification

**Date:** 2026-11-23. **Status:** local synthetic unit/fixture tests executed; original-source GitHub Actions pending until uploaded and run. Do not report original-source measurements before CI succeeds.

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

### Results and limits

No original-source measurements are asserted in this initial report. Once CI passes, commit full machine-readable original-source results along with conservative paper-ready interpretation. Results must show full vocabulary count, all postings, physical bytes per six stores, BM25 score parity, and any surprising negative findings. There is no original source text or raw query text in result JSON.

**Acceptance gate:** Pass all local tests and both original-source GitHub Actions tasks with full integer + tf roundtrip, full physical byte accounting, and independent BM25 parity. If fixed BARM fails to outperform varint or EF across full-vocabulary persisted indexes, its sampled success does not support full-index compression superiority. Even if it wins physical bytes, no native FTS5, SIMD, phrase, random-access CPU, or end-to-end RAG benefit may be claimed.

## Reproduce

See `experiments/round-111/README.md` and `.github/workflows/cdg-r111-full-bm25-index.yml`.