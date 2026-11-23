# R111 | Complete-vocabulary BM25-compatible external posting archive

**Question:** Do R108–R110's sampled docID-only BARM savings persist across **every term** from the original scientific corpora when term frequencies, document lengths, a term lexicon, mode tags, and physical SQLite pages are all charged, while verifying BM25 term / conjunction ranking against native SQLite FTS5?

The new `full_bm25_store.py` uses the original SHA-locked QASPER DEV and SciFact readers from R108. It builds a conventional one-column FTS5 index, extracts exact per-term/per-document frequencies with `fts5vocab(instance)`, then materializes six independent SQLite stores over **the same complete original vocabulary**, not the former 1,950-term stratified subsample.

Each store has the same physical SQL schema, including `postings(term,df,payload)` in a `WITHOUT ROWID` table, document length table, metadata, positive-gap encoding, and separately charged varint-encoded per-term frequencies. All codecs get the same five-byte list envelope (mode tag plus encoded-gap length). Compared methods: BARM-R, varint, DP reference partitioned Elias-Fano, fixed bitpack, a predeclared `df<4 ? varint : BARM` hybrid, and an in-sample per-list minimum-size oracle that charges its codec tag. The oracle is **not a learned policy**.

The query checks include SHA-selected terms from df=1, df=2–3, df=4–31, df=32–256 and df>256, plus conjunctions. Every retrieved candidate and BM25 score is compared with an independently generated native FTS5 `bm25()` result, with reported numerical tolerance and rank-tie disagreements.

Run from repository root:

```bash
python -m pip install pytest==9.0.2
python -m pytest -q experiments/round-111/tests
python experiments/round-111/full_bm25_store.py --dataset scifact --out experiments/round-111/ci-scifact.json
python experiments/round-111/full_bm25_store.py --dataset qasper --out experiments/round-111/ci-qasper.json
```

GitHub workflow `.github/workflows/cdg-r111-full-bm25-index.yml` runs the real original-source experiments, checks source SHAs with the preexisting R83/R96 readers and saves aggregate JSON. Full original articles/paragraphs are never committed.

**Scope:** This is a full-vocabulary, term-frequency-aware **conjunctive BM25 external index**, still not a feature-equivalent native FTS5 replacement. It does not retain token positions and therefore cannot reproduce phrase/NEAR queries. Its source archive is separately accounted for in R103–R106, not included here; do not divide index-only sizes by complete source+index bytes. The FTS5 native size has more features and is shown only as context. Codecs are Python reference implementations without matched native SIMD controls. Results are not RAG answer improvements, a novel information-theoretic codec, or applications of RH.

If the full-vocabulary BARM advantage disappears from short-list header overhead or shared TF/page metadata, demote BARM rather than selectively reporting R108/109's favorable sampled results. Further work should require a feature-matched query/phrase contract and end-to-end total-cost test.