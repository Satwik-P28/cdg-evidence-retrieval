# Round 107: Zeta-Family Integer Code Pilot and Real FTS5 Logical Posting-Gap Experiment

**Date:** 2026-11-23. **Status:** local Python reference pilot executed; complete repository-wide report-FTS5 experiment is **configured for GitHub Actions, not yet validated by CI** at the time of this commit. **34 local unit tests passed** on Python 3.13.5. This is **not** a study of the Riemann Hypothesis or proof-derived text compression.

## Research question and prior-art boundary

Could a blockwise adaptation of an established two-part dyadic-scale Golomb integer code be useful for positive gaps in an inverted index or theorem-dependency graph, when the code must be reversible and its block framing charged? The main mathematical reference is Neri Merhav's *Statistical Physics of Coding for the Integers* (arXiv:2604.00858), involving the real Riemann zeta normalization at exponent >1. This does **not** depend on the critical-line RH/GRH theorems. Stream-VByte, Partitioned Elias-Fano, SIMD-BP128/FastPFOR, and modern integer codecs are prior art; none is covered by this preliminary comparison.

### Implemented experiment, before any production integration

- Reversible 128-integer BARM-R bitstream: 2-byte `r,count` header, unary Rice quotients of dyadic exponent, `r`-bit remainder plane, dyadic offsets, strict padding and length validation. BARM-G uses arbitrary-m Golomb coding with a distinct seven-byte header. Inputs are positive unsigned 64-bit values.
- Stronger *than bit-length estimates* controls: actual encoded/decoded Elias gamma, Elias delta, positive varint, fixed-width bitpack, zlib9-compressed framed varints, and zlib9-compressed whole streams. Every framed arm charges 4 bytes per block for an independent length field. Global zlib is explicitly **not** block-random-access equivalent.
- Seeded finite truncated discrete power-law samples, 12,000 values each, with beta in {1.001, 1.01, 1.1, 1.5, 2, 3} and support x in [1,65536]. These **cannot validate Merhav's unbounded-law redundancy bounds**. A deliberately non-zeta clustered-mixture negative control is included.
- A separate executable FTS5 corpus experiment builds an in-memory SQLite contentless FTS5 index over checked-in CDG round reports. Using `fts5vocab(instance)`, it extracts actual term-to-distinct-document ID posting lists, positive docID gaps, and per-method encoded lengths with lossless round-trip assertions. **These are derived logical postings, not SQLite's on-disk FTS5 segment encoding.**

## Locally executed seeded synthetic results

| Stream (12,000 integers each) | BARM-R framed B | Varint framed B | Elias delta framed B | Fixed-width framed B | Whole zlib-varint B, unequal random-access contract |
| --- | ---: | ---: | ---: | ---: | ---: |
| Truncated beta=1.001 | 17,908 | 20,316 | 19,624 | 24,658 | **17,788** |
| Truncated beta=1.01 | 17,832 | 20,255 | 19,506 | 24,658 | **17,697** |
| Truncated beta=1.1 | 15,718 | 18,087 | 16,410 | 24,626 | **15,201** |
| Truncated beta=1.5 | **7,674** | 13,396 | 7,899 | 20,750 | 8,278 |
| Truncated beta=2 | **4,281** | 12,617 | 4,650 | 11,762 | 4,774 |
| Truncated beta=3 | 2,727 | 12,564 | 2,934 | 6,514 | **2,184** |
| Clustered mixed gaps | 10,942 | 16,205 | **10,843** | 23,158 | **10,292** |

Machine-readable results: `experiments/round-107/results-synthetic.json`, generated with `python benchmark.py --n 12000`. The synthetic runs are a single deterministic draw per parameter, not independent-run uncertainty estimates. BARM-R beat framed varint on all tested cases but lost to global zlib on most; it also lost to Elias delta on clustered gaps. The latter are useful **negative controls**. BARM-G vs BARM-R is not header-normalized.

An additional local two-Markdown-file FTS5 smoke test verified the logical posting extraction code, produced 29 paragraph rows, 109 filtered terms and 486 logical term/doc postings, and had BARM-R 940 B vs framed varint 1,140 B. This is an **extremely small self-referential development fixture** and must not be advertised as an external benchmark or held-out test. A full CDG report-corpus result is deliberately left to Actions artifacts rather than invented here.

## Why not merge as a production index codec?

1. SQLite does not expose a simple swappable FTS5 posting codec. Replacing real postings would require a new index implementation or a compatible extension. This comparison does not improve native FTS5 query speed or total indexed archive bytes by itself.
2. There are no Stream-VByte, PEF, FastPFOR, ANS or random-access seek baselines yet. Python bit-by-bit decoding does not establish good decode throughput.
3. Synthetic near-critical data have **finite support**. Code size versus block empirical entropy and zeta-exponent estimates are not theory validation. The near-critical beta estimate used here is a Laurent approximation, not exact MLE on the truncated model.
4. A real query may need a small part of one posting list, while this experiment decodes full blocks. The system requires matched seek and compressed-index metadata measurements.
5. RH proof methods are unrelated to the observed integer codec gains. No evidence of better RAG retrieval, answer grounding or hallucination mitigation.

## Reproduction and mandatory next gates

From root:

```bash
python -m pip install numpy==2.3.5 pytest==9.0.2
python -m pytest -q experiments/round-107/tests
(cd experiments/round-107 && python benchmark.py --n 12000 --out results-synthetic.json)
PYTHONPATH=experiments/round-107 python experiments/round-107/fts5_postings.py \
  --root . --pattern 'research/rounds/round-*/report.md' \
  --max-files 30 --max-docs 5000 --max-terms 3000 \
  --out experiments/round-107/results-fts5.json
```

GitHub Actions workflow `.github/workflows/cdg-r107-barm-postings.yml` runs this test suite and captures the full report-corpus logical posting gap results. It is not a QASPER or SciFact real indexing experiment. Later, pin original QASPER/SciFact source IDs and SHA-256, extract corpus-real indexing streams, and compare against PEF, Stream-VByte, FastPFOR, plus a physical index + source store byte accounting with random seek and query costs. Reject or demote BARM if robust controls dominate at the same access contract.

**Scientific disposition:** EXPERIMENTAL, no publishable performance superiority established. CDG's historical-storage/access/WAL frontier from R103–R106 remains separate and intact.