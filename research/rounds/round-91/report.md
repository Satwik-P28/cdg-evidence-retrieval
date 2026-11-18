# CDG Round 91: Source-Only FTS Replay and Process-Kill Boundary Recovery

**Date:** 18 November 2026. **Verified:** original SciFact and eight regression tests passed in [GitHub Actions 44350868152](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44350868152), using the Round 90 ordinary contentless FTS5 + SHA-verified compressed source design. No real hardware power-loss or arbitrary corruption safety claim.

## Gap closed relative to R90

R90's old-text-assisted contentless FTS5 updates passed synthetic exceptions and 500-event original SciFact ranking experiments, but had not faced actual killed OS processes, concurrent WAL readers, or reconstruction **without passing in the original source corpus and revision ledger**.

R91 tests all three.

The self-repair routine \`rebuild_from_compressed_docs\` begins a write transaction, enumerates **only current rows in \`docs\`**, verifies each compressed blob against its stored SHA-256 and exact byte count, splits its current serialized title and abstract, issues the existing FTS5 \`delete-all\`, and repopulates ordinary contentless FTS postings from those verified source bytes before COMMIT. On any failure it ROLLBACKs. It never receives SciFact original corpus, external revision events or gold labels.

The repair is **O(number of live documents)**, and this proof-of-concept assumes the existing R87 text serialization \`title + "\\n" + joined abstract\` with title containing no newline. The code does **not** silently extend support to arbitrary ambiguous boundaries.

## Eight true subprocess SIGKILL cases

Created eight independent physical SQLite files, four process termination points in each of rollback journal DELETE (\`synchronous=EXTRA\`) and WAL (\`synchronous=FULL\`). Each subprocess is killed using OS SIGKILL. A separate process reopens and verifies SQLite core integrity, FTS5 internal integrity, old/new token search, SHA-verified compressed source and generation, and FTS5 aggregate doc count.

| Kill point | DELETE recovered | WAL recovered |
| --- | --- | --- |
| After FTS old-text delete, pre-insert | Old source+index, generation 1 | Old source+index, generation 1 |
| After new FTS insert, pre-source update | Old source+index, generation 1 | Old source+index, generation 1 |
| After compressed source update, pre-COMMIT | Old source+index, generation 1 | Old source+index, generation 1 |
| Immediately after COMMIT | New source+index, generation 2 | New source+index, generation 2 |

**All 8/8 cases passed.** These are deterministic SIGKILL positions, not a complete power-loss/crash consistency proof, arbitrary instruction stop test, disk controller failure injection or network filesystem study.

## Independent index poisoning demonstration

A controlled test replaced one old FTS document's postings with completely different indexed terms *without changing its valid SHA-verified compressed source*. The FTS5 **internal** \`integrity-check\` passed, yet queries returned the spurious term, proving internal structural consistency does not imply index↔source provenance coherence.

The \`rebuild_from_compressed_docs\` repair discarded forged postings and restored original search terms and FTS global statistics. Two failure injections, after \`delete-all\` and after the first reinsert, both rolled back to the original (deliberately poisoned) index, preventing partial repair visibility. A deliberately corrupted zlib source blob made the repair fail closed instead of silently reconstructing an incorrect index. This demonstrates the existence of a repair path, not that it detects every possible tampering or guarantees availability under arbitrary damage.

## WAL snapshot concurrency

A reader began the existing R88 \`retrieve_snapshot\` transaction and queried generation 1. The writer committed the new R90 old-text-assisted index+source inside its own transaction before the reader materialized the evidence. The reader retained byte-exact old evidence within its snapshot, and subsequently observed the new source/index after its transaction. The test passed.

## Original, hash-locked SciFact reconstruction

- Original upstream release SHA256: \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.
- **5,183** SHA-verified compressed current sources rebuilt into FTS5 using only the \`docs\` table in the repair itself.
- Rebuilt FTS5 global stats \`[5183,70349,1097525]\` exactly matched the independent conventional full-content FTS5 source reader.
- **300/300** original dev claim queries gave identical top-10 BM25 rankings to conventional FTS5, and **300/300** top-ranked SHA-verified compressed reads matched original source bytes.
- Source-only rebuilding wall time on one GitHub Actions runner: **0.3032 seconds**. This excludes independent cold SSD, mobile/edge hardware and live concurrent traffic.

## Research decision

**KEEP:** The R90 old-source-assisted contentless FTS approach with single write transactions, R88 reader-owned snapshot retrieval, and a source-only O(n) repair path. Existing SQLite FTS5 source verification and transactions are documented engineering building blocks, not novel theoretical results.

**KEEP:** An explicit operational invariant requiring independent source/FTS audit. SQLite \`integrity-check\` validates internal FTS consistency but cannot authenticate an external compressed evidence store.

**BLOCK deployment until:** handling titles with embedded newlines using versioned length-delimited format, durable upgrades and corruption injection, concurrent write/read throughput, repeatable cold-storage measurements, updates across actual different corpora and model-grounding impact.

**NEXT:** favor an independent human-labelled factuality/retrieval task. Prove retrieval-storage efficiency at matched answer faithfulness instead of claiming that source exactness itself solves semantic hallucinations.

## Reproduction

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-91 -p 'test_*.py' -v
python experiments/round-91/self_healing_archive.py --full --out experiments/round-91/ci-results.json
\`\`\`

Code: \`experiments/round-91/self_healing_archive.py\`, \`experiments/round-91/test_self_healing_archive.py\`. Workflow: \`.github/workflows/cdg-r91-source-replay.yml\`. Dedicated CI and aggregate artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44350868152 .

Prior art:
- SQLite FTS5 old-text 'delete', contentless tables and \`delete-all\`: https://www.sqlite.org/fts5.html
- SQLite WAL snapshot readers: https://www.sqlite.org/wal.html
