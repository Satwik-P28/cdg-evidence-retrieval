# CDG Round 108: Authentic Original-Corpus FTS5 Gap Coding with Stronger Reference Controls

**Date:** 2026-11-23. **Status:** PASS. 97 local tests and complete original-source QASPER/SciFact SHA-locked experiments succeeded in GitHub Actions run [45248301874](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45248301874). This round measures compressed *logical* posting lists, not an integrated physical index. Original aggregate machine-readable results are stored in `experiments/round-108/results-qasper.json` and `results-scifact.json`.

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

## Measured exact source outcomes (GitHub Actions)

| Original source, stable-hash df-stratified term sample | QASPER DEV | SciFact corpus |
| --- | ---: | ---: |
| Original source documents indexed | 13,266 | 5,183 |
| Source documents/papers | 281 papers | 5,183 abstracts |
| Sampled terms (350 df1, 400 df2–3, 650 df4–31, 350 df32–127, 200 df>=128) | 1,950 | 1,950 |
| Logical posting entries | 144,717 | 116,186 |
| Conventional contentless FTS5 SQLite bytes, **not codec-substituted** | 4,505,600 | 4,644,864 |
| **BARM-R (all framing charged)** | **130,129** | **110,142** |
| BARM-G | 144,405 | 122,954 |
| Variable partitioned EF reference | 150,961 | 116,932 |
| Framed bitpack | 170,875 | 120,054 |
| Framed zlib9(varints) | 180,304 | 142,540 |
| Framed varint | 187,580 | 149,854 |
| Scalar StreamVByte-format control | 217,772 | 174,920 |

BARM-R is 30.63% and 26.50% smaller than framed varint on the *sampled logical streams*, and 13.80% and 5.81% smaller than this experimental partitioned-EF reference on QASPER and SciFact respectively. The latter is **not** a production PEF benchmark. At document frequency 1, however, BARM-R requires 4,455 vs 4,196 B (QASPER) and 4,266 vs 4,192 B (SciFact) against the ordinary framed varint baseline; short-list overhead is not free.

At df 32–127 on SciFact, BARM-R uses 28,101 B versus EF 27,285 B, and at df 4–31 it uses 16,815 B versus block bitpack 16,495 B. Thus BARM does **not** dominate every corpus or frequency regime. Across both samples, higher-df terms dominate logical posting entry counts; the stratified mixture is not a statistically representative distribution of all index terms or bytes. No source text or labels were emitted.

**Scientific decision:** Maintain BARM as a candidate for a physical external index integration experiment, not as an established superior codec. The more challenging next control is an actual byte-accounted posting store that supports random term lookups and compares with optimized C/C++ StreamVByte/FastPFOR and Partitioned Elias-Fano libraries. Whole-system FTS5/archival and query performance are unmeasured here.

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