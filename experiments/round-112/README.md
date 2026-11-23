# R112: Full-vocabulary, position-aware inverted index falsification

This round extends R111 from exact `docID + term-frequency` postings to **every token position** required for exact bigram phrase membership, while retaining independent BM25 scoring against SQLite's native `detail=full` FTS5. It asks whether BARM-R's previous physical-store savings remain after positions, which can dominate index storage, are included.

It uses SQLite's documented `fts5vocab(docs, 'instance')` term/document/offset metadata to recover every token occurrence from the same one-column Unicode61-tokenized original source. Each compared external SQLite store persists the **same full source token vocabulary**, document-length metadata, full term frequency data, increasing doc IDs, and ordered token positions; identical table schemas and physical `VACUUM`ed SQLite page sizes are charged. All original source bytes remain upstream, not in committed outputs.

**Seven compared policies:** fixed BARM-R, varint, partitioned Elias-Fano Python reference, bitpack, zlib(varints) framed reference, a seventh fixed short-list hybrid (varint if fewer than 4 docs; varint for <32 positions), and a per-term/per-plane measured size oracle. All are Python reference codecs, not native SIMD libraries. The oracle is not a deployable train-fitted predictor. The docID and position streams are **separate SQLite BLOB columns**, so ordinary BM25 queries decode only docIDs and frequencies; exact phrase queries explicitly decode both position streams. This is a separate decode contract, not a proven cold SSD read reduction or native FTS5 implementation.

Tests include exact reconstruction of every original term and all its positions after SQLite persistence, SHA-deterministic BM25 term/conjunctive queries checked against native FTS5 `bm25()`, exact ordered bigram phrase result identity, broken/invalid gap guards, physical SQLite page accounting, and immutable QASPER/SciFact archive provenance from existing R83/R96 source fetchers.

## Reproduce

```bash
python -m pip install pytest==9.0.2
PYTHONPATH=experiments/round-112 python -m pytest -q experiments/round-112/tests
python experiments/round-112/positional_store.py --dataset qasper --out experiments/round-112/ci-qasper.json
python experiments/round-112/positional_store.py --dataset scifact --out experiments/round-112/ci-scifact.json
```

The original-source benchmark downloads source archives only with pre-existing SHA locks and commits **aggregate metrics**. The accompanying GitHub Actions workflow runs full source experiments on GitHub-hosted runners with results stored in CI artifacts. Do not report original-source size or efficacy figures until Actions succeed.

### Scientific limits

- This external SQLite index reproduces observed full token-position semantics for tested BM25 AND/single-term and ordered-bigram phrase operators, but does not implement the complete native FTS5 query language, snippet/highlighting APIs, index update logic, column policies or optimized search/skip algorithms.
- Full-vocabulary does not mean full-text *source copies* are charged: compared external indexes exclude original document bytes just as contentless FTS5 does. End-to-end archive+index bytes must be measured separately for publication.
- Native FTS5 is an existing production comparator with different encoding/architecture, not a matched codec swap. Original source FTS5 physical size is context, not an identical-engine speed baseline.
- Plain Python codecs are not the optimized SIMD FastPFOR, PISA, or production Partitioned Elias-Fano. No statistically controlled query throughput measured.
- This is a storage/index systems experiment, unrelated to the location of zeta zeros or consequences of RH/GRH.

See `research/rounds/round-112/report.md` for the outcome and paper-worthiness decision.