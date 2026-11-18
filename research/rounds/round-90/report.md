# CDG Round 90: Source-Exact Incremental Contentless FTS5 Repair

**Date:** 18 November 2026. **Status: original SciFact CI PASS.** [GitHub Actions run 44349742955](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44349742955) passed eight adversarial and synthetic regression tests and all four full original SciFact 500-update comparisons. This round isolates an **existing documented SQLite FTS5 old-text deletion technique**, not new retrieval mathematics.

## Hypothesis, compared to Round 89's falsification

R89 found that under SQLite 3.46.1, \`contentless_delete=1\` index updates increased FTS5's global BM25 document count from 5,183 to 5,683 after 500 synthetic edits while only 5,183 live docs existed; the strong full-content FTS5 BM25 reference retained correct stats and exact top-10 equality collapsed to 150/300 diffuse, 152/300 hot queries. A complete index rebuild corrected ranks but cost O(corpus) and required a structured replay oracle.

SQLite has another pre-existing feature: **ordinary contentless FTS5** (\`content=''\` *without* \`contentless_delete=1\`) supports an \`INSERT INTO sources(sources,rowid,title,abstract) VALUES('delete',?,?,?)\` operation if supplied the *exact old values used when indexing*; it then supports a regular insert for the new index terms. Importantly, **contentless-delete tables do not support the special 'delete' command**. Relevant official documentation: https://www.sqlite.org/fts5.html (sections 4.4.1, 4.4.2 and 6.3).

R90 pairs ordinary contentless FTS5 with R87's compressed document table. Inside a single \`BEGIN IMMEDIATE\` transaction, it reads and SHA-256-verifies the old compressed source, derives exact old title and abstract strings, submits FTS5's source-assisted old-text 'delete' instruction, inserts the new postings, writes zlib6 compressed new source with SHA+generation, and COMMITs. Any error rolls back both source and index. This avoids whole-index rebuilding per revision.

**Serialization caveat:** R87's old format is \`title + newline + joined abstract\`, so this implementation explicitly refuses title strings containing newlines. Production migration should retain an explicit title byte-length or lossless structured canonical representation for arbitrary text.

## Tests and controls

- Eight synthetic regression tests pass: SHA-bound original source, single update, 35 repeated updates, three failure injection stages restoring old source/index, delete success+rollback, corrupted old zlib and wrong doc-ID fail-closed, byte-exact UTF-8, and four small three-way comparisons.
- Original official SciFact TAR SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`; 5,183 abstracts, 300 development claims, identical R83/R84 title5/body1 term-budget28 OR BM25 policy.
- Three data-preserving contenders: conventional full-content FTS5 control, current R87 compressed contentless-delete (negative control), and new source-assisted standard contentless + compressed source R90.
- Each of four workloads applies 500 identical artificial title/abstract edits (500 distinct source IDs or ten edits each to 50 IDs) under DELETE rollback-journal and WAL. Execution order rotates across the three methods; per-commit latency uses warm GitHub-hosted Linux runner measurements.
- FTS internal \`integrity-check\`, main SQLite \`PRAGMA integrity_check\`, compressed SHA source readbacks, and all updated source text checked.

## Measured original SciFact results

| Journal / pattern | Full FTS5 global N | R87 global N | R90 global N | R87 exact top-10 | R90 exact top-10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| DELETE / diffuse | 5,183 | **5,683** | **5,183** | 150/300 | **300/300** |
| DELETE / hot | 5,183 | **5,683** | **5,183** | 152/300 | **300/300** |
| WAL / diffuse | 5,183 | **5,683** | **5,183** | 150/300 | **300/300** |
| WAL / hot | 5,183 | **5,683** | **5,183** | 152/300 | **300/300** |

All three indices had 5,183 live source rows. R90's complete FTS5 aggregate \`[N,title_tokens,abstract_tokens]\` also **exactly equaled** conventional FTS5 for all four cases, not merely the global document count. Original bytes of every revised document verified against both compressed implementations, and the full control kept exact title/abstract.

### Persistent bytes

Measured file size includes main .sqlite plus any existing \`-wal\` and \`-shm\`, after an explicit WAL TRUNCATE checkpoint and VACUUM for steady state. R90 initial after full build: **9,224,192 B** versus R87 **9,236,480 B**, control **14,544,896 B**.

| Mode / pattern | Full FTS after VACUUM | R87 (ranking drift) after VACUUM | R90 correct after VACUUM | R90 saving vs full |
| --- | ---: | ---: | ---: | ---: |
| DELETE / diffuse | 14,712,832 | 9,293,824 | **9,375,744** | **36.2751%** |
| DELETE / hot | 14,577,664 | 9,142,272 | **9,252,864** | **36.5271%** |
| WAL / diffuse | 14,745,600 | 9,326,592 | **9,408,512** | **36.1944%** |
| WAL / hot | 14,610,432 | 9,175,040 | **9,285,632** | **36.4452%** |

Pre-checkpoint **WAL active** bytes on diffuse workload: full 24,150,320; R87 15,941,200; R90 18,623,616. R90's contentless special delete entries have a different tombstone/segment accounting pattern, explaining why source-exact update costs and active storage must be reported separately from the post-VACUUM numbers. These sizes are not guaranteed high-water marks.

### Per-update latency, descriptive only

| Mode / pattern | Full median ms | R87 median ms | R90 median ms | Full p95 ms | R90 p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| DELETE / diffuse | 1.00320 | 1.08256 | **1.10341** | 6.79202 | 9.05875 |
| DELETE / hot | 0.97870 | 1.04846 | **1.06542** | 2.73689 | 6.06850 |
| WAL / diffuse | 0.22986 | 0.28426 | **0.30734** | 0.83830 | 0.94688 |
| WAL / hot | 0.23818 | 0.28563 | **0.31166** | 0.99095 | 1.95657 |

Single GitHub runner and OS cache, no controlled cold SSD, multi-writer load or repeated independent CI runs. R90 is not faster than conventional full-content FTS5 in these tests; correctness comes with some extra update work because it must decompress, hash and tokenize old text.

## Decision and risk boundary

**KEEP as a validated experimental architecture:** ordinary FTS5 contentless with SHA-verified old source data supplied to the documented FTS5 'delete' operation, new postings inserted and compressed source updated in *one* SQLite transaction. Correctly preserves the actual BM25 ranking control under these revisions and retains roughly 36.2–36.5% of space savings after compaction.

**Do not replace production R87 yet:** old-content precision is essential and source/index divergence can be hard to detect; a corrupted FTS store may require independent full replay. Current source serialization can be ambiguous if a title contains a newline; tests only one source per index row, warm synthetic edits, no SIGKILL tests on the special delete implementation, and no multi-process hot-reader interference yet.

**NOT CLAIMED:** novel compression science, new BM25 ranking, hallucination reduction, human-labelled answer correctness, greater speed or worst-case durability.

**NEXT:** version-aware faithful old-text encoding, kill-at-update-boundaries, source/index independent consistency audit using canonical rebuild, compaction overhead over longer histories, concurrent snapshot retrieval, and comparable other corpora. Once infrastructure is stable, prioritize actual claim-grounding and model answer-quality evaluations instead of conflating byte integrity with factual evidence support.

## Reproduce

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-90 -p 'test_*.py' -v
python experiments/round-90/old_source_incremental.py --full --out experiments/round-90/ci-results.json
\`\`\`

Artifacts and job results: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44349742955 . Only aggregate source SHA/size/ranking/latency outcomes persisted, not the upstream original corpus.
