# Provenance and completeness audit

This export assembles raw files that were available in this chat's workspace or could be materialized from the user's file Library on 12 November 2026. It is **not** a claim that every artifact ever discussed or generated in Rounds 0–22 was recovered.

## Available

- Primary integrated document through Round 22, original Round 19 report, appendices and runnable Python/result JSON for Rounds 20–22.
- Original round ZIP archives for Rounds 3–10 (where accessible); included unchanged under `source-archives/` and unpacked to retain their experiment code.
- Round 3 archive contains some earlier Round 2 materials. Archive trees occasionally contain historical duplicate files; they are intentionally retained as source snapshots.

## Missing / inaccessible raw artifacts

- Several Round 11–18 ZIP archives were indexed in the user's Library but the service did not authorize a raw-byte materialization path. Their absence is explicitly documented rather than silently rewritten.
- Original standalone Round 0–2 master notes were not found as an accessible authoritative raw export.
- The Round 19 reproduction script was indexed but raw-byte materialization was denied. Its results and methodology are documented in the report, but its code is not present as a runnable local copy.
- Official SciFact original archive, source corpus bytes, and full trained-model or SSD benchmark artifacts are not included.

## External sources pinned in Round 19

- Flattened SciFact corpus: `rinaxosman/ir_system/data/scifact/corpus.jsonl` Git blob `93e4d620e75aac00dc2be20a8361211b408a0c84`.
- Original-schema dev claims: `traceloop/openllmetry/packages/sample-app/data/scifact/scifact_claims.jsonl` blob `280ea26476673e40194bddc957490a2e0af2865c`.
- Quote mirror: `aryash45/docucheck/evals/data/public/scifact_dev.jsonl` blob `3e6c34bc7c4565f91bfe27de8b918b3cd8d1a084`.
- Published reranker output: `thunlp/KernelGAT/scikgat/prediction/abstract_rerank_dev_mlm.jsonl` blob `c76169c31e915a8f12d812be12034c00ddc1ac14`.

These hashes and paths are *reported from the Round 19 research record*, not newly reverified in this export. External datasets have their own licenses; this repository links to them but does not redistribute corpora.

## Attribution and evaluation ethics

Results are preserved as dated research observations. Some reports and code were produced with AI assistance and should not be presented as solely handwritten or as formally peer-reviewed work. For program applications, focus on the specific research question, experiments undertaken, limitations found, and next falsifiable tests rather than unsupported claims of novelty.
