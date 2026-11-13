# Round 30: The Index Duplication Trap, Offline Bridge Links, and Honest End-to-End Accounting

**Date:** 13 November 2026  
**Status:** File-backed SQLite/Zstandard experiment executed locally; 13 Python regression tests passed. Connected-source analysis of 100 curated HotpotQA-derived questions completed in JavaScript. The two analyses have **not** been executed together on the authentic 100-question corpus in the local file-backed engine. No answer generator, independently held-out QA gain, cold-cache benchmark or novel-algorithm result.

## Executive decision

**Keep:** a compact lexical source index and independently compressed original source bytes with exact source version and byte-offset receipts. **Stop:** using the number of compressed bytes read as the sole retrieval objective and treating an uncompressed copy of all line bodies in SQLite as unavoidable. **Do not advance to a learned graph controller yet.** The practical baseline must first be a conventional SQLite FTS5 contentless index plus a versioned title-link sidecar and Zstandard frames. Each of these components has existing prior art. Any publishable contribution would have to emerge from demonstrated, independently replicated *joint* quality/cost performance, not their coexistence.

A significant correction emerged when reviewing the Round 28/29 implementation: the code stored source line text in the `lines.body` SQLite table while also storing a compressed copy of the same original file. The FTS5 external-content table indexed that line table. Total footprint therefore included both a compressed archive and a nearly complete uncompressed source replica, plus FTS postings. That makes the previous cost frontier partly an artifact of the prototype's index schema rather than a necessary price of compressed retrieval. This failure was worth finding before adding another algorithm.

## 1. Experimental branches and provenance

**Branch A: authentic multihop source-link structure.** Connected GitHub `OpenSPG/KAG` revision `fdab15b3929d2ee40dfcdd388f90233096a6afc9`, `kag/open_benchmark/hotpotqa/data/qa_train.json`, Git blob SHA-1 `7dbdf068a437f0577043667ffee3a20f0a602154`, with 100 authentic HotpotQA-derived questions. This curated upstream subset has 78 bridge and 22 comparison questions, 994 query-local document instances and original source paragraph text. The analysis extracted exact title links only from source text within a question's supplied candidates. It did not redistribute dataset bytes. It ran within the connected GitHub JavaScript environment because network access to that corpus was blocked in the local Python container. The included Python script can be run against the exact source after its pinned bytes are downloaded and verified.

**Branch B: genuine file-backed physical storage.** Five local CDG research reports, totaling **88,679 original UTF-8 bytes**, from the Round 29 benchmark, stored as actual independent Zstandard frames with real `os.pread` calls and SQLite FTS5. Eighteen hand-selected lexical queries were run in both the original *external-content* schema and a new *contentless* schema for three frame sizes. This is a tiny, topic-selected workload, not independent QA. Every returned source span was byte-for-byte checked against the original report. The benchmark reruns both schemas against the same inputs and confirms matching retrieved document and byte coordinates.

**Branch C: integrated execution prototype.** `integrated.py` accepts the pinned HotpotQA-shaped JSON array, builds per-question frame stores and SQLite indexes, retrieves documents by best line-level FTS5 BM25, and compares static FTS, dynamic title-mention expansion and a precomputed link-table expansion. It reads the selected document from the physical compressed file before using its content. Seven local integration tests use two *manually authored* fixtures. Their numerical retrieval scores are **not** HotpotQA results, and the full 100-question corpus has not been run through this Python implementation. The source file has an explicit SHA-1 gate; synthetic fixtures require `--allow-fixture`.

The 13 total local tests comprise seven integration checks and six contentless/storage checks, including Unicode byte reconstruction, empty intervals, gold-label independence of ranking, UTF-8 content, exact reconstructed lines and link-index/dynamic agreement on a toy fixture. A source SHA mismatch is refused by the loader. They do not certify end-to-end answer correctness.

## 2. Finding: avoid duplicated source bodies in FTS5

Two concrete physical schemas were compared:

- **Existing external-content schema:** `lines(line_id, source_id, raw_start, raw_end, body)` plus `lines_fts USING fts5(body, content='lines', ...)`. The `body` column retains uncompressed source text while Zstandard frames retain a separate compressed source.
- **Contentless schema:** `lines(line_id, source_id, raw_start, raw_end)` plus `lines_fts USING fts5(body, content='')`. The original bytes reside only in the compressed payload; FTS5 retains term/posting information and tokens necessary for ranking. Exact text is returned through the stored coordinate-to-frame mapping and verified with its source version hash metadata.

| Zstd frame size | External-content total bytes | Contentless total bytes | Storage reduction |
|---|---:|---:|---:|
| 256 B | 306,197 | 211,989 | 30.8% |
| 512 B | 291,755 | 197,547 | **32.3%** |
| 2,048 B | 281,795 | 187,587 | 33.4% |

All totals count **actual SQLite database file size + actual Zstandard payload file size**. These are not estimates of virtual database pages or uncompressed bytes. FTS5 material still occupies substantial storage: even with 512-byte frames, the contentless database alone occupies 139,264 bytes versus 58,283 compressed source bytes. The original source is 88,679 bytes. Thus a source compressor alone is not yet a persuasive total-system compression story.

**Correctness:** Across each of three frame-size comparisons, all 18 term queries returned the same ranked line IDs/source offsets and exact original bytes. No reconstruction mismatch was observed. The query terms were selected from the reports, so no generalized retrieval-accuracy estimate follows. At 512 bytes, the contentless and original indexes read the same mean **1,713.5 compressed payload bytes** per top-five query. The selected spans are identical; the gain comes from eliminating duplicate persistent source text, not from a better ranking algorithm or lower compressed read traffic.

**Timings are inconclusive.** The 512-byte contentless median over 18 warm queries was 182.9 μs, compared with 231.0 μs for external-content, but these observations are too small and uncontrolled for an inference of latency advantage. Build times also vary. Contentless FTS indexes introduce real update/delete and rank-feature constraints; no concurrent writers or source-update transactions were tested.

## 3. Finding: the source-link graph is small, conventional and useful

Over the 100 authentic HotpotQA-derived query-local contexts, exact whole-token matching of any candidate title inside a different candidate source produced **403 directed document-title edges**, or 4.03 per question. The source text plus titles occupied **571,094 UTF-8 bytes** under this analysis's declared concatenation scheme. A simplistic sidecar charge of 16 bytes/edge amounts to 6,448 bytes of link metadata, and title string length plus eight bytes each gives another 28,047 bytes. These are **modeled lower bounds**, not the actual storage cost of SQLite indexes, token normalization, title dictionaries, or rebuilds; they are kept separate from the file-backed storage table above.

The retrieval result matches the prior Round 25 analysis and is **not** an independent improvement: BM25 @2 recovered both supporting documents on 33/100 questions, and exact-title mention expansion on 46/100; at five documents the counts are 62 versus 84. At k=2, paired outcomes were both 31, expansion-only 15, BM25-only 2, neither 52. In 53/100 cases, the initial BM25 document contains an exact title link to at least one other gold source, but a title string occurring in a document is not automatically an asserted or semantically supporting relation. The source itself may deny, quote, cite, or describe the target.

The fundamental equal-quality control is important: when the offline title-link table encodes exactly the same edges visible to a dynamic string extractor, and both policies use identical base scores and bonus function, **they select identical documents**. Under these conditions a new graph controller cannot claim a document-retrieval advantage from having the graph in a different data structure. The distinction can only arise in amortized index-build/update expense, source bytes read before bridge selection, measured latency, or more accurate/fallible semantic edge extraction. The locally executed fixture tests verified the same selected titles between these two policies. A complete 100-question Python run is still required.

## 4. Nonlinear hypothesis graph and adversarial counterexamples

### H30.1: Query-dependent frame packing can beat fixed line alignment

Source frame selection depends on which evidence spans are jointly requested. A natural proposal is co-locating frequently co-requested span sets, analogous to weighted graph/hypergraph partitioning. But current evidence is insufficient: Round 27's line-heavy workload favored line alignment, Round 28's SQLite dominated footprint, and Round 29 found larger frames competitive on latency. A fair optimization should minimize a joint objective such as

\[
J = \lambda_{q}\,\mathbb{E}[L_q] + \lambda_{d}\,D_{\mathrm{total}} + \lambda_{u}\,\mathbb{E}[U] + \lambda_{r}\,R_{\mathrm{unsupported}}
\]

with latency \(L_q\), full storage footprint \(D_{\mathrm{total}}\), source-update cost \(U\) and unsupported-answer risk \(R_{\mathrm{unsupported}}\). The weights and conditional demand distribution are not yet estimated. The existing compression frames are per source and do not permit free cross-source packing with independent authorization/version semantics.

### H30.2: Exact link receipts may reduce unnecessary source reads

Index-time link materialization allows a second document to be ranked before the first is fully decoded. That can reduce *online* source materializations, but not without offline link construction and maintenance. In our current integrated prototype, **all selected documents are still decoded to evaluate candidate support**, so dynamic and indexed links have identical selected-document compressed bytes when their selections match. Any future claim of reduced I/O requires a separate policy that changes which source frames are materialized and a source receipt/verification contract. Precomputed links alone do not do this.

### H30.3: Index freshness is a correctness primitive

The compressed payload, source hash and FTS/link index must refer to the same immutable version. Otherwise an index built from version \(v\) can navigate into version \(v+1\) while still returning byte-valid but semantically outdated evidence. Checking a stored SHA against another stored SHA is tautological. A real freshness guarantee requires a trusted origin/version manifest and atomic publication/snapshot pinning. The existing reader reconstructs its indexed snapshot but does not enforce contemporaneous authority or authorization. This remains an unimplemented gap.

### H30.4: Contentless indexes shift work, not eliminate it

Removing stored body text is effective for *storage*, but the FTS index still contains tokens and postings. `bm25()` scoring retains a global or per-collection statistical view that must be maintained under updates. Source snippets and semantic verification must physically read the compressed payload. This makes accurate frame cost measurement more important. It also motivates evaluating `detail=column/none`, `columnsize=0`, alternative tokenization, and external token-position tables, each with explicit loss of capabilities and update complexity. These are standard FTS5 engineering options, not theoretical novelty.

### H30.5: A witness pair is an AND constraint, not a diversity score

Evidence completeness is structurally complementary: retrieving two valid supporting sources can turn an otherwise unsupported answer into a supported one. This is why Round 24's MMR baseline underperformed and Round 25's bridge expansion helped. However the existence of a link is not a proof of relation validity. The next valid predictor should estimate the probability that *all* required support is present, calibrated on held-out questions, rather than treating each link as equal evidence. If no calibrated predictor can beat simple iterative retrieval on the same sources, discard it.

## 5. Novelty audit and related methods

- **SQLite FTS5 `content=''`:** documented contentless storage. This work is an integration and measurement, not a new index design. https://www.sqlite.org/fts5.html
- **Zstandard seekable format:** independent compressed frames and a jump table are established. https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/README.md
- **IndexRAG (Findings IJCNLP-AACL 2026):** precomputes bridge facts at index time and evaluates HotpotQA, 2WikiMultiHopQA and MuSiQue. This directly rules out pitching index-time bridge links as novel. https://aclanthology.org/2026.findings-aacl.175/
- **IRCoT (ACL 2023):** interleaved retrieval and reasoning. https://aclanthology.org/2023.acl-long.557/

**Current contribution:** a disciplined source-grounded prototype and a negative control showing that correcting an ordinary database schema can dominate a proposed complex optimization on total storage. There is **no verified novel contribution or peer-reviewed result** yet.

## 6. Reproducibility

Run local physical and integration regression tests:

```bash
cd experiments/round-30
python -m unittest -v test_integrated.py test_contentless.py
python contentless_bench.py --files report1.md report2.md report3.md report4.md report5.md --output local.json --frame-size 512
```

To rerun 100 HotpotQA-derived questions locally, obtain the exact `qa_train.json` byte sequence at the pinned upstream commit (the Round 25 downloader includes a SHA-gated retrieval command) and run:

```bash
python integrated.py --data /path/to/qa_train.json --output real_corpus_reproduction.json --layout fixed --frame-size 512
```

**Not executed:** that 100-question Python run. Do not report the authored two-question smoke fixture as a real benchmark. Python FTS5 ranks documents by their best matching *line*, unlike Round 25's custom whole-document BM25, so even a faithful execution will not necessarily reproduce Round 25's 33/46 counts.

The historical `MANIFEST.json` is not yet an up-to-date complete manifest for these new commits. The current Git tree verifies submitted blobs; source lists and hashes should be regenerated before an external artifact evaluation.

## 7. Round 31 preregistered decision points

1. **P0:** make the true 100-question raw corpus locally available and execute *all* policies through the same physical store and FTS5 scoring. Split bridge and comparison cases; track complete documents and exact annotated sentence IDs; compare query-normalized I/O bytes and p50/p95. Obtain an official held-out sample before any paper-level claim.
2. **P1:** compare external-content, contentless FTS, `detail=column/none`, BM25 and title-link expansion with indexes/updates all charged. Measure per-document metadata lookup and construction, not a fixed modeled 16-byte link cost.
3. **P2:** implement immutable snapshot publication and atomic source+FTS+link-version switching; reject mismatched version receipts at read time. Test stale links, deletion, revision, ACL changes and conflicting evidence.
4. **P3:** only then test learned uncertainty gating and physical co-layout versus an ordinary contentless SQLite + seekable-Zstd + title-link baseline. If the learned controller is dominated, omit it.

**Decision:** KEEP the stripped-down, compressed-source/contentless-index baseline. **STOP** making claims based on duplicated-source index footprints. **DEFER** CDG graph-control novelty until an independently held-out complete-evidence quality/cost result exists.
