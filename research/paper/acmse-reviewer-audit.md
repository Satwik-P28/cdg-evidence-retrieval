# ACMSE claim audit and reviewer response

## Scope

Use the integrated R151 archive as the strongest validated implementation, R148 as the fully matched R147 encoding comparison, and R153 as the fair timing control. R159 adds a quotient-snapshot factorial baseline and process I/O measurements; do not cite pending numbers. R154–158 exploratory results belong in an appendix or follow-up, not the central claim. Do not call temporal retrieval, bounded delta compression, dedup, or BM25 novel.

## Prior art and precise differentiation

TimIR (Staudinger et al., https://arxiv.org/abs/2411.04051 and https://repositum.tuwien.at/handle/20.500.12708/224602) maintains timestamped term/document statistics and reproduces historical sparse rankings using Lucene and MonetDB. R140 reproduces actual upstream SQL scoring on pinned histories and native Lucene: 288/288 rank agreements per corpus with nonzero numerical differences; not a full service, storage or latency comparator. Our problem is the joint cost of retaining exact revision bytes and replaying a ranking plus evidence commitment in an atomic archive. TimIR's historical ranking ability is not a gap. We have not established that every deployment of TimIR lacks exact source storage or provenance, and do not claim faster retrieval.

Bhattacherjee et al., Principles of Dataset Versioning (PVLDB 2015, https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/) formulates storage/recreation-cost tradeoffs and maximum recreation cost constraints, including hard optimization problems. He/Suel positional versioned indexes (https://doi.org/10.1145/2348283.2348319) establish fragment reuse. Git pack depth bounds and existing bounded deltas are established. Our narrow implementation contribution is a causal literal-anchor admission rule with TWO normalized per-source budgets (logical decoded bytes <=2.5x raw source; logical activated frame bytes <=1.5x standalone compressed source), evaluated under an identical historical retrieval and provenance contract. This is a specialized design point, not a new general delta optimization theorem. R136 demonstrates depth-only control is insufficient for byte bounds; R149 adds marginal encoded-frame cost selection and reduces average logical decoded work. R151 combines this with exact-content quotient positional index and atomic provenance replay. R153 shows that a fair efficient revision control has similar median rank latency, so storage and correctness are the main benefits.

## Evidence matrix

- R148: feature-matched v2 snapshot vs bounded anchors, 245,412,623 -> 220,334,630 B, 10.22% savings; no query speed superiority.
- R151: same v2 integrated archive, 220,334,630 -> 157,256,231 B, 28.63% savings relative to R148 bounded anchor; factorial results isolate marginal encoding vs quotient; no feature-matched quotient snapshot until R159 passes.
- R136: source-only logical maximum decoded ratios 489.02 (prev8) and 128.89 (anchor8) vs bounded 2.488. No physical IO claim.
- R142: finalized native Git depth1 214,888,975 B with common revision index, not v2 or update matched; max logical decoded 32.59 vs 2.49; Git average work lower than earlier CDG. No claim integrated R151 beats Git solely by compression (different index representation).
- R143/R147/R151: process-death and mutation tests, not hardware power-loss tests.
- R153: full median rank receipts 21.711 ms legacy revision, 1.103 ms optimized revision, 1.128 ms quotient. Do not cite 27.67x as inherent index speedup.
- R129/R132/R137: real Git histories, first-parent/path-touch, not general wall-clock news history. R141 CLARK has dated availability but few revised sources; AP ordinal schedule synthetic. Avoid claims of true AP chronological ranking.
- R141 latest-only top10 coverage exceeded historical on sampled proxy; historical replay is a reproducibility property, not automatic relevance gain. LLM QA not in scope.
- Independent human reproduction not performed. CI is not independent replication.

## Proposed contribution wording

We evaluate a transactional revision archive coupling bounded logical source reconstruction, historical BM25 replay and externally retained evidence commitments. Under matched metadata and retrieval contracts, causal frame-cost selection and exact-content index sharing reduce archival storage and preserve native ranking on versioned corpora. We characterize the storage/reconstruction tradeoffs against snapshot, depth-limited and finalized Git controls, and distinguish logical costs from measured IO and latency. Prior art already solves historical ranking and version-graph optimization; the contribution is the integrated, measured contract and explicit design constraints. Avoid first-of-kind or universally optimal claims.

## Independent reproduction handoff

Clone the repository at the exact experimental commit; Python 3.11, Linux, pinned packages in workflows. Rebuild native extension with the workflow compiler invocation. Run R148 matched_final.py, R151 joint_archive.py, R153 fair_receipt.py and R159 physical_io.py after acquiring AP database using round-136/download_source.py. Verify source SHA, manifest hashes and query-plan fingerprints against archived JSON; compare deterministic byte sizes, bounds and receipt commitments, not exact timing. Record machine, filesystem, SQLite and zstd versions, commands, raw logs and discrepancy. Run tests without modifying expected outputs. Ask an independent person to perform this procedure and document their findings; this document is an invitation, not completed independent reproduction.