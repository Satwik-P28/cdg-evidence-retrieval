# CDG Round 108: Authentic Original-Corpus FTS5 Gap Coding with Stronger Reference Controls

**Date:** 2026-11-23. **Status:** experimental code locally tested; official QASPER/SciFact results are pending GitHub Actions execution. The first code check is 97 local unit/fixture tests passing. The initial version of this report intentionally contains no original-corpus numerical claims.

## Research question

Round 107's checked-in Markdown proxy showed experimental BARM-R 44,662 bytes vs. 53,279 framed varint bytes over 35,387 logical posting entries, not original SciFact/QASPER source postings and not native SQLite index-byte compression. Does this BARM finding persist on **original, SHA-locked, independently sourced** scientific corpora when compared with stronger conventional codecs and when short-list overhead is accounted for?

## Immutable sources and trusted boundaries

- Official QASPER v0.3 train/dev tar from R96, SHA-256 `a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a`, source document extraction via R96 original paragraphs. Original DEV member SHA is independently recorded in output. Expected 13,266 paragraphs (R106).
- Official SciFact archived corpus from R83, tar SHA-256 `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be`, corpus JSONL SHA-256 `b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62` (lock enforced by R83 fetcher). The `latest` upstream path is mutable: source mismatch causes failure, never silent data substitution.
- No labels, claims, retrieval rankings, or generated answers are used to select terms or tune codecs.
- Actual original corpus text is never committed into the repository or emitted as workflow artifacts.

## Experimental method

Build a **conventional contentless SQLite FTS5** index from the original SciFact document title/abstract or original QASPER paragraph heading/body. Extract genuine `fts5vocab('instance')` term-to-row-ID logical posting sets, deduplicating term instances per document. For each term, delta-code strictly increasing original row IDs. Sample terms by SHA256-minimal rank within five predeclared document-frequency strata: df1 (350), df2–3 (400), df4–31 (650), df32–127 (350), df>=128 (200). This is a **stratified reproducible subsample**, not a full-postings or representatively weighted whole-index measurement.

The same independently decodable per-list gap values are fed to:

1. BARM-R and BARM-G from the existing R107 reference implementation, with 128-value blocks.
2. Ordinary varint and fixed-width bitpack, both similarly framed.
3. A StreamVByte-format scalar control, using one 2-bit length selector per integer and little-endian bytes, **not optimized SIMD throughput**.
4. A variable-partition Elias-Fano prefix-sum reference whose 32/64/128/256-element candidate partitions are chosen by dynamic programming using each actual list's encoded length. This is an **in-sample partition oracle**, not the optimized production PEF implementation.
5. Independently Zlib9-compressed varint frames, retaining the same per-frame independent decode boundary.

All methods include a 4-byte list count and per-frame byte-length headers where applicable. The partitioned EF reference also counts its 7-byte per-partition header and boundary sizes. Every selected list must decode to precisely the originally extracted positive gaps before its size is counted.

## Main reporting metrics

- Physical size of **unchanged** conventional FTS5 index (to expose real whole-index denominator).
- Byte count and bits per posting for every codec over identical selected posting entries, stratified by doc frequency.
- Per-stratum number of terms, number of selected posting values, and exact list-wise winner counts including ties.
- SHA of each sampled term name set and original upstream source identity.

**Critical exclusion:** these are separately compressed logical posting streams. The codecs do **not** replace native SQLite FTS5 posting segments. A reduction in logical stream bytes is not proof of an equally smaller index, better retrieval recall, or query latency.

## Precommitted decision gate

Promote BARM for further engineering only if its byte usage is reliably competitive with the adaptive Elias-Fano and StreamVByte-format references across original corpora, including medium/high-frequency strata. Otherwise preserve BARM as a scientifically useful negative control. A production claim additionally requires native or external index integration, seek APIs, latency, Python-vs-C SIMD implementation parity, and matched total source+index storage. A favorable codec result alone does not constitute a new RH-dependent compression theorem.

## Reproduce

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-108
python experiments/round-108/authentic_postings.py --dataset qasper --out experiments/round-108/ci-qasper.json
python experiments/round-108/authentic_postings.py --dataset scifact --out experiments/round-108/ci-scifact.json
```

GitHub workflow: `.github/workflows/cdg-r108-real-postings.yml`.