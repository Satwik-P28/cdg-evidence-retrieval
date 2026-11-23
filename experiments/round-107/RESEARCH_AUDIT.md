# Research audit: November 23, 2026 CDG / RH application proposal

## Summary

The supplied 82 KB report contains technically motivated hypotheses, but many expected performance numbers and priority rankings are **forecasts** rather than observations. Its claim that the current CDG repository was inaccessible is no longer applicable: the connected GitHub tool returned `Satwik-P28/cdg-evidence-retrieval`, README, and the Round 106 report. Round 106 measures QASPER 13,266 original source paragraphs, 1,005 unchanged BM25 query rankings, nine physical archive policies and 60 synthetic revision transactions, while explicitly disclosing that its access history is pseudo-historical. This baseline is relevant to future evaluation of source access and update amplification.

The late-November RH formal verification is a mathematical milestone but does not change ordinary text entropy. Merhav's real-zeta integer coding, Lean proof retrieval as a *corpus*, and GRH-conditional deterministic primality statements are **three logically independent concepts**. Do not write as though Merhav's code was derived from the RH proof.

## Implemented pilot

- BARM-R and BARM-G are true, reversible bitstreams, not merely encoded-length estimates.
- Finite synthetic truncated discrete power-law distribution on `x in [1, 65536]`, seed 42, 12,000 integer observations per exponent.
- 80%-small/20%-large clustered mixture, seed 443, 12,000 integers.
- **Local report position gaps**, 7,405 integers extracted from repeated word occurrences in the user-provided research audit. These are **not FTS5 docID gaps** and **not QASPER/SciFact**.
- Every measured block includes a four-byte frame-size field for individually decodable random access. The global-zlib control does **not** support selective block access, so it is a distinct operating point.
- Full decoder round-trip checks executed in every synthetic/word-gap benchmark arm.
- `pytest -q`: **31 passed**, including 600 randomly generated BARM/Golomb blocks and 150 randomly generated baseline-codec blocks.

## Initial measured byte results (not publication-grade)

| Pilot workload | BARM-R bytes | Varint bytes | Elias delta bytes | Block-local zlib/varint bytes | Global zlib/varint bytes (different access contract) |
|---|---:|---:|---:|---:|---:|
| Finite zeta beta=1.001, cap=65536 | 17,908 | 20,316 | 19,624 | 21,350 | 17,788 |
| Finite zeta beta=1.01, cap=65536 | 17,832 | 20,255 | 19,506 | 21,289 | 17,697 |
| Finite zeta beta=1.1, cap=65536 | 15,718 | 18,087 | 16,410 | 19,121 | 15,201 |
| Finite zeta beta=1.5, cap=65536 | 7,674 | 13,396 | 7,899 | 11,828 | 8,278 |
| Finite zeta beta=2, cap=65536 | 4,281 | 12,617 | 4,650 | 7,890 | 4,774 |
| Finite zeta beta=3, cap=65536 | 2,727 | 12,564 | 2,934 | 4,828 | 2,184 |
| Clustered mixture (non-zeta) | 10,942 | 16,205 | 10,843 | 14,474 | 10,292 |
| Local report word-position gap proxy | 10,931 | 12,052 | 12,433 | 12,678 | 10,453 |

The literal values above were transcribed from the same run. `results.json` is the machine-readable authority if a transcription differs. These are **one seeded run** and not a performance distribution or confidence interval.

### Interpretation

- On a truncated beta=1.001 distribution, BARM-R uses approximately 11.9% fewer bytes than block-framed varint but *slightly more* than a global zlib stream; this does not validate Merhav's asymptotic redundancy theorem.
- On a true local-text proxy, BARM-R is smaller than framed varint but about 4.6% larger than a globally compressed varint stream, which lacks efficient random access.
- On clustered mixture, Elias delta slightly beats BARM-R, and global zlib beats both. This supplies a modest negative control.
- Even for favorable samples, byte savings on an isolated integer stream do **not** imply savings on whole SQLite FTS5 databases. SQLite does not expose a simple replacement for its internal posting encoding.
- Python decode timing is deliberately not reported as a throughput victory over production SIMD routines.

## Report corrections and failure modes

1. The estimate `beta_hat=1+1/(average(log x)+gamma)` comes from the leading near-critical Laurent approximation, not the exact maximum-likelihood equation; on finite-truncated data it generally is not an MLE of that truncated model. The encoder treats it solely as a heuristic.
2. Sampling the unbounded zeta distribution with beta=1.001 can produce integers outside finite 64-bit bounds. Truncating support to 65,536 changes the distribution and invalidates direct numerical comparisons to the unbounded model's entropy/redundancy theorems.
3. The standalone BARM-G implementation includes its own larger seven-byte header, so its total code size is not perfectly header-normalized against BARM-R. That is a deliberate reported implementation difference, not proof that Rice necessarily beats optimal Golomb coding.
4. Neither 10-40% compression gains over strong production IR codecs nor SIMD throughput are demonstrated by these tests. Partitioned Elias-Fano, Stream-VByte and FastPFOR are not installed here.
5. A fixed adjacency/forward-reference graph is not automatically a runnable Lean reconstruction: modules, namespaces, imports, declarations generated by elaborators, compilation caches and axioms are part of the verification contract. A syntactic regex dependency extractor is insufficient for claim-level completeness.
6. A compressed Lean dependency-closure archive can prove local byte integrity or Lean checkability, but cannot by itself prove formal **retrieval completeness** unless the full eligible declaration universe and dependency relation are authenticated or otherwise trusted.
7. Hash-based Block-Max score certificates need version-frozen corpus statistics, a faithful upper-bound derivation for the actual ranker, and an authenticated universe of all skipped blocks. A SHA manifest on a retrieved block is not a complete top-k proof.
8. The zero-RNG GRH application does not directly improve conventional SHA-256 content-addressed storage. It should not be made a main CDG paper contribution.
9. ACMSE 2027 short papers require 5-6 pages, an exact official format, double anonymity, and in-person presentation if accepted. The November 30 deadline is real; feasibility depends on a **completed study**, not on theoretical novelty promises.

## Next gates

**Gate A: authentic posting streams.** Add an actual version-locked QASPER and SciFact IR stream extraction with dictionary/corpus IDs and SHA256s; include generic posting gaps, docID gap distribution, and Zipf fit diagnostics. Save only derived aggregate metrics if redistribution rights are uncertain.

**Gate B: strong benchmarks.** Implement production-grade PEF, Stream-VByte, SIMD-BP128/FastPFOR, Zstd per block and seekable Zstd. All must have equivalent random-access/selective-decode contracts and all metadata charged. Measure millions of integers with repeated hardware runs and workload-stratified bootstrap confidence intervals.

**Gate C: CDG-Lean correctness.** Acquire a compact verified Lean subset before implementing an extractor. Verify dependency extraction against Lean-produced tracing rather than regex, and compile both original and reconstructed bundles using the same pinned Lean/Mathlib dependency lock.

**Gate D: source-and-index cost.** Replace the integer stream within a genuinely queryable index, or build a matched independent index implementation; compare total index+archive bytes, retrieval metrics, source reads, decoded bytes, update WAL, p50/p95 CPU and wall latency. Do not count hypothetical posting savings against unchanged SQLite FTS5 postings.

If BARM cannot win these gates, keep the negative result and focus on CDG's better-supported versioned evidence retrieval and proof-carrying archive research.

### Sources

- https://arxiv.org/abs/2604.00858 (Merhav's two-part integer code)
- https://arxiv.org/abs/2610.22339 (LeanGraphSearch)
- https://acmse.net/2027/papers-call/ (deadline and requirements)
- https://github.com/Satwik-P28/cdg-evidence-retrieval/blob/main/research/rounds/round-106/report.md (current source archive baseline)