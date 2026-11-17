# Round 43: Indexed Incremental FTS5 Control and Edit-Validity Audit

**Date:** 2026-11-17
**Branch:** research/round-43-indexed-fts-controls
**Status:** implementation committed; **three locally executed unit tests passed** in Python 3.11/SQLite 3.46.1 on a standalone copy of this round's module. The **full multi-architecture benchmark has not been run or independently validated** in this round. No end-to-end RAG accuracy, physical SSD I/O, new compression theorem, or production gain is claimed.

## Why this round is necessary

Round 42 found a Pareto trade-off between globally indexed CAS-backed history and source-sharded historical storage. But the global table declared source name UNINDEXED and removed every matching line with a source-name predicate. Thus former B (incremental global + CAS) was not a sufficiently optimized conventional SQLite competitor.

A second issue emerged in the code audit: Round 42's replacement edit uses the expression ord('a') + step % 26. At step 4 it writes the character 'e'. If this is the first time a document starting with 'evidence' is selected, the replacement can be **byte-identical to the original source**, yet the benchmark's nominal changed count records it as an edit. This can understate timing for sparse updates. Round 42's historical results remain archived unchanged rather than silently rewriting them.

## New conventional baseline (P)

The new experiments/round-43/lab.py introduces **IndexedDelta**, a competing global incremental FTS5 baseline.

- A normal SQLite table maps stable integer row IDs to source identities and full line text, with a B-tree index on source name.
- Contentless FTS5 stores tokens linked to the same row IDs, avoiding a second plaintext copy in the virtual FTS5 table.
- A deterministic Python difflib.SequenceMatcher(autojunk=False) edit script preserves row IDs for unchanged lines, deletes old postings by row ID, and inserts postings only for changed text.
- Each generation retains a full SQLite snapshot **just as B does** and a SHA-256-addressed zlib source payload map. Historical exact-byte reads rehash the decompressed payload before returning it.
- The baseline remains ordinary SQLite with Python diffing. It is not a new indexing algorithm. Diffing can itself dominate long or heavily repetitive documents.

The experimental comparison includes **B** (Round 42 GlobalDelta), **D** (Round 42 Hybrid), and **P** (new IndexedDelta), all exercised on the same sequence of source versions.

## Corrected edits and test contract

Four synthetic mutations of the five genuine internal Round 24–28 research reports are planned: append a provenance sentence; replace an existing lowercase ASCII byte with its cyclic successor, guaranteeing changed bytes; insert a unique line near the document middle; delete a line near the document middle.

The 20-source condition replicates the same five genuine report texts under distinct identities. It does **not** create independent evaluation documents. The default grid comprises **48 scenarios**: four edit modes, two source counts (5/20), three changed fractions (5%/20%/80%), and two seeded edit selections (11/23). Each scenario has four updates after initial generation.

The runner rejects a nominal edit if its bytes are unchanged. After **each generation**, it checks current exact FTS source-name match multisets for six queries and exact byte reconstruction of **all previously observed generations**, across B, D, and P. Each case reports update medians, retained total bytes, warm query medians, and unchanged line-ID reuse.

This is differential correctness under the inherited implementation and a limited query vocabulary. It is not a substitute for random phrase/Boolean queries, crash injection, true workload traces, or source-grounded QA.

## Executed local checks

Three focused standalone unit tests **passed**:
- No-op prevention, including the Round 42 step-4 counterexample and repeated append/replace/insert/delete edit sequences.
- Duplicate lines, line insertion and replacement, unchanged row-ID retention, source removal, FTS cleanup, and historical exact readback.
- UTF-8/emoji source-byte preservation across versions.

**Test outcome:** 3 run, 3 passed, 0 failed. The tests were executed locally using an independently created copy of the source before uploading the equivalent implementation to this branch. They are *not* a GitHub CI result. A full Round 43 benchmark result JSON is not present yet, and there are no new speedup or compression-ratio numbers to report.

## Reproduction

In a clone of the branch containing the Round 42 input files and the Round 43 module:

    python -W error::ResourceWarning -m unittest discover -s experiments/round-43 -p 'test_*.py' -v
    python experiments/round-43/lab.py --quick --out experiments/round-43/smoke.json
    python experiments/round-43/lab.py --out experiments/round-43/results.json

Do not interpret benchmark timing until actual source hashes, environment, failure-free query parity, complete update counts, and raw results have been archived.

## Graph-of-hypotheses continuation

- **H43-A: Sparse edit regime.** If P reuses most row IDs and changes only a few lines, its edit work may be lower than B's source-name scan, but diffing and historical SQLite backups may erase that saving.
- **H43-B: Dense/repetitive regime.** Under wide changes or repeated line patterns, SequenceMatcher overhead may outweigh partial posting reuse. B may remain better.
- **H43-C: Retention regime.** Full historical SQLite backups impose cost for both B and P even when only one source changes. Page-level snapshots, SQLite session/changeset approaches, or copy-on-write storage may beat all three. That is a separate, stronger future control.
- **H43-D: Retrieval regime.** Source-name multiset equality is weak. Genuine query distributions, ranking, historical queries, and evidence span extraction may change the optimum.
- **H43-E: Adaptive choice.** A learned policy should only be evaluated **after** the fixed baselines are fair. Train on an explicit workload history, test on disjoint histories, account for migration and decision costs, and compare to always-B, always-D and always-P.

## Promotion gates

**GO:** corrected edits, row-ID posting control, exact generation reconstruction, and targeted differential tests.

**HOLD:** no Round 43 full-grid result, independent corpus, read-write weighting, strong versioned SQLite baseline, or durability measurements.

**NO-GO:** claim that CDG's hybrid is superior to well-indexed conventional SQLite, or that a new compression/RAG theorem has been established.

**Next experiment:** execute the 48-case grid, investigate failures before interpreting numbers, then add a genuinely independent versioned text corpus and a SQLite historical-storage strategy that avoids complete index copying. Only afterward test adaptive selection with migration cost included.
