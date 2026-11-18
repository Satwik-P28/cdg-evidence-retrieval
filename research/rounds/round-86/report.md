# CDG Round 86: Source-CAS Bytes Behind Contentless FTS5 BM25

**Date:** 18 November 2026. **Status:** an executable SQLite FTS5 contentless-versus-contentful benchmark and five synthetic regression tests were submitted; **full SciFact numbers pending successful exact-head CI**. Existing database technology, not a new retrieval or compression algorithm.

## Research question

Round 83 reproduced stronger conventional SQLite FTS5/BM25 SciFact retrieval than original TF-IDF on the exact 5,183-document scientific corpus. Round 84's train-only title/term grid selected that same strong FTS5 title5/abstract1 28-word query policy. Meanwhile the proposed CDG archival subsystem stores original source bytes losslessly with SHA-bound receipts, but normal contentful FTS5 stores the **source text again** in its FTS content shadow tables.

Can we retain **exactly the same retrieval ranking** and semantic input bytes while removing duplicate source storage, by using the documented SQLite FTS5 contentless mode and serving original bytes from the already-existing compressed SHA archive?

This architectural composition is already known in information retrieval, database indexing, content-addressed storage and SQLite FTS5. The potential benefit is workload-specific **retained storage accounting**, not first-of-kind algorithm novelty.

Official SQLite behavior: https://www.sqlite.org/fts5.html (section 4.4.1: contentless table, \`content=''\`; attempting to read content columns returns SQL NULL). We intentionally preserve default FTS5 column-size metadata, rather than disable \`columnsize\`, so BM25 length normalization has the same information as the ordinary table.

## Pre-registered controlled comparison

- Original SciFact AI2 release archive SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\` and 5,183 original scientific abstracts; all 300 dev claims for rankings; 188 with annotated gold source documents for Recall@1/3/5/10.
- **Control:** SQLite \`CREATE VIRTUAL TABLE sources USING fts5(title,abstract,tokenize='unicode61')\`, identical original field values, title boost 5, abstract 1, OR of first 28 query terms, deterministic \`rowid\` tie-break.
- **Intervention:** exactly the same index data, tokenization, document IDs, row insert order and query, but \`CREATE VIRTUAL TABLE ... USING fts5(title,abstract,tokenize='unicode61',content='')\`. No source text stored inside SQLite. Original UTF-8 title + newline + abstract materialized from R48 \`VersionedReader\` whole-Zlib6 SHA receipts on selected index rowids.
- Both persistent SQLite DBs get same page size and \`VACUUM\`. Account for retained DB bytes, **whole-source archive bytes including its manifest**, source ID-to-slot mapping bytes, query wall time and reader warm-memory receipt time. Compare contentful-index-alone versus contentless-plus-source-archive, as well as redundant contentful-plus-archive.
- Assert **byte-exact** source text readback for every top-one source retrieved with contentless FTS5. Check that \`SELECT title,abstract\` on contentless returns \`NULL,NULL\` and control returns original content.
- Require complete **top-ten doc rowid rankings identical on every dev claim**, not just the same average recall. Record exact source-identification, retrieval and compressed-read cost. Compare with R83 (strong conventional baseline) without pretending that a weak TF-IDF baseline is the sole rival.

## Promotion criteria and invalid claims

1. Five synthetic tests pass, including rank-invariance, contentless source omission, exact Unicode source bytes, source-label independence and source retrieval receipts.
2. Original SciFact tarball immutable SHA and 5,183 source count lock; 300 dev claims and 188 gold annotated docs.
3. Zero changed full top-ten rankings between the two SQLite variants; otherwise do not promote a quality-invariance claim.
4. If \`contentless_fts_bytes + whole_zlib_CAS_bytes + ID_mapping_bytes\` is smaller than \`full_fts_bytes\`, this is a real persistent-byte saving against that specific **contentful full-text baseline**, at the additional requirement of a separately maintained source archive and its transactional synchronization. The base FTS index can itself serve original text without the CAS, so including both would be redundant and should be costed separately.
5. Any wins on warm Python source-reader timing or bulk setup are **not SSD cold latency**, p95 serving, durable concurrent updates, crash consistency, or lower model inference cost.
6. No claim that source byte receipt proves factual support or that compressed source selection improves RAG answer hallucinations. End-to-end generation quality is not tested.
7. A useful outcome can be **negative**: if the small source corpus's contentless index and archive are larger or no faster, preserve the result and prefer conventional contentful storage.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-86 -p 'test_*.py' -v
    python experiments/round-86/contentless_cas.py --out experiments/round-86/ci-results.json

Workflow \`.github/workflows/cdg-r86-contentless-cas.yml\`. Data remains upstream. Only derived aggregate cost, hash, rank-equality and recall are stored as CI artifacts.
