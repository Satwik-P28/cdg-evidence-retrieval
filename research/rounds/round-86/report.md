# CDG Round 86: Source-CAS Bytes Behind Contentless FTS5 BM25

**Date:** 18 November 2026. **Status:** five synthetic regression tests and original 5,183-document full SciFact end-to-end index/source read benchmark **passed in GitHub Actions 44266853921**. Measured results and limitations are recorded below. Existing database technology, not a new retrieval or compression algorithm.

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


## Executed original SciFact measurements (GitHub Actions 44266853921)

**[FACT]** All 5 regression tests and the actual 5,183-document/300-claim corpus benchmark passed. The dataset SHA was verified. SQLite **3.46.1** was used under equal settings (FTS5 \`unicode61\`, retained column-size metadata, 4096-byte pages, VACUUM, bm25 title5/body1 and source-only OR up to 28 terms).

**[FACT] Ranking and source byte fidelity:** **0/300** changed complete top-ten rowid rankings; gold annotated evidence retrieval Recall@1 136/188 (**.723404**), @3 156/188 (**.829787**), @5 166/188 (**.882979**) and @10 179/188 (**.952128**), equal to R83 and R84. **300/300** retrieved top-one contentless-index source IDs materialized byte-exact from SHA-bound whole-source compressed receipts; \`SELECT title,abstract\` on the contentless FTS returned \`(NULL,NULL)\`, confirming the source text is not redundantly stored inside that index.

### Retained-byte accounting

| Persistent component or architecture | Measured bytes |
| --- | ---: |
| Conventional full-content FTS5 alone (contains source text) | **14,544,896** |
| Contentless FTS5 index alone, not source readable | **4,644,864** |
| Whole-Zlib6 CAS archive including binary source manifest | **3,909,759** |
| Source document ID -> archive slot JSON mapping | **55,126** |
| **Contentless FTS5 + exact compressed CAS + mapping** | **8,609,749** |
| Redundant full-content FTS5 + CAS + mapping | **18,509,781** |

**[FACT]** The complete contentless-index/CAS system retains **5,935,147 fewer bytes**, a **40.81% space reduction** against a source-readable conventional full-content FTS5 standalone installation under the same 5,183 documents. The contentless index alone is smaller by 9,900,032 bytes, **but it cannot serve source text** and therefore is not a fair functional comparator by itself. Accounted mapping is a compact JSON doc ID list; update logs, extra in-memory structures, filesystem block layout and model weights are not included.

The original 5,183 UTF-8 source documents totaled **7,792,860 B** in R86's exact \`title + newline + abstract\` serialization.

### Index and source-read performance, measured but not end-to-end server latency

| Measurement | Full content FTS5 | Contentless FTS5 + CAS |
| --- | ---: | ---: |
| Build and VACUUM wall | 0.32376 s | 0.24049 s |
| Execute 300 original SciFact BM25 queries | 0.65707 s | 0.63840 s |
| Additional archive build | not required | 0.25710 s |
| Additional byte-verified top-one archive reads | not required | 300, **0.04210 s total** |
| Logical compressed frame activation for 300 reads | not required | **231,797 B** |

These are **single-run, warm page cache / Python in-memory** descriptive measurements, not SSD cold-read or transactional performance. Query timing differences are within benchmark variation without replications, and the contentless system must serve source bytes from the archive, not from FTS.

**[INFERENCE]** A contentless FTS index coupled to source-byte receipts has a practical 40.81% persistent-byte advantage in this **specific SciFact source corpus** versus storing all original source text in FTS5, while preserving exact lexical candidate rankings and source content. This validates a conventional **index/source compression composition**, rather than a novel compressor or guaranteed general end-to-end improvement.

**Next falsifiers:** test crash-safe updates and atomic index+archive commits, document addition/deletion, source-ID migration, p95/p99 warm/cold SSD read latency, transaction recovery, a stronger independent corpus, and end-to-end model answer quality with real retrieval sources. Do not generalize the current 5,183-text result to arbitrary datasets.

Reproduce: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44266853921 .
