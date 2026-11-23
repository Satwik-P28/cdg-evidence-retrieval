# Round 107 | Experimental zeta-family integer coding and FTS5 posting-gap pilot

Reversible Python reference BARM-R and BARM-G (based on existing two-part dyadic Golomb coding), conventional integer-code controls, seeded **finite** power-law tests and real SQLite FTS5-derived *logical* posting lists.

**Not a test of RH or GRH.** The connection to zeta distributions is the real-valued partition function for exponents >1, not the recent RH proof. No new optimal coding theorem, replacement for SQLite's on-disk FTS5 compressor, RAG answer gain or full system storage victory is asserted.

Reproduce from repository root with Python 3.11+:

```bash
python -m pip install numpy==2.3.5 pytest==9.0.2
python -m pytest -q experiments/round-107/tests
(cd experiments/round-107 && python benchmark.py --n 12000 --out results-synthetic.json)
PYTHONPATH=experiments/round-107 python experiments/round-107/fts5_postings.py \
  --root . --pattern 'research/rounds/round-*/report.md' \
  --max-files 30 --max-docs 5000 --max-terms 3000 \
  --out experiments/round-107/results-fts5.json
```

The report-only FTS5 corpus experiment builds a **new in-memory contentless FTS5 index** over paragraphs from tracked Round reports, extracts term/doc-ID occurrence lists with `fts5vocab(instance)`, and compresses *positive document-ID gaps*. SQLite's real internal FTS5 postings are not read or rewritten; term dictionary, skip pointers, and search index implementation are not included in sizes. Source input digests are stored with output, but no report text is copied to result artifacts. This experiment tests integer-code characteristics of a real-world text index proxy, **not** a native FTS5 deployment.

`benchmark.py` also supports an optional `--audit-text`, intended for local-only proxy runs; no private supplied input text is committed. Framed block bytes are charged equally among framed codecs; the global zlib comparison is **not** random-access equivalent. Production code should retain SHA-256 source receipts because codec round trip alone cannot detect arbitrary bit corruption.

See `research/rounds/round-107/report.md` and `RESEARCH_AUDIT.md` for stronger prior-art controls that remain missing and the proposed falsification gates.