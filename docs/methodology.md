# Methodology and evidence standard

## Unit of evaluation

A *witness* is a set of source spans sufficient to cover a mechanically specified evidence requirement. Multiple witnesses can be acceptable. For naturally expressed claims, annotator/semantic judgments are separate from structural coverage. A quoted string appearing in a document is not a semantic proof.

## Evidence tiers

- **Empirical, real external text:** source and query provenance must be pinned; report dataset split, preprocessing, baseline implementation and retrieval/answer metrics.
- **Empirical, internal real text:** useful for systems checks but not equivalent to externally held-out QA evaluation.
- **Synthetic:** tests a mechanism under a known generating distribution and must not be described as real-world generalization.
- **Oracle:** lower or upper bound involving unavailable gold witness information.
- **Modeled physical cost:** counts frame activations or metadata under explicit assumptions; does not measure actual cold storage performance.
- **Hypothesis:** a proposal pending a controlled test.

## Checklist for every experiment

1. Fix corpus commit/hash, split, query set, random seed and preprocessing.
2. Declare which information the selector can access at inference time.
3. Implement simple baselines first and include strong external baselines where feasible.
4. Define the full resource accounting boundary: source bytes, indexes, sidecars, cache, compressed frames, actual I/O, tokens.
5. Keep structural witness recall, verifier accuracy and generated answer quality separate.
6. Stress unseen source families, offset shifts, ambiguous spans, copied citations, and ACL changes.
7. Report failure cases and negative or negligible improvements.
8. Test statistical uncertainty and significance when using sampled workloads.

## Reproduction limitations

Earlier reported SciFact full-corpus results were computed through connected GitHub analyses and have not been independently rerun from the exact official source archive in this export. Source code shipped in historical ZIPs may have platform-specific paths or requirements. Re-run results on a clean machine before making performance claims in an application or paper.
