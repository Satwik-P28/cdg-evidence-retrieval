# Round 39: Do Not Confuse Text Diff, Factual Change, and Temporal Validity

**Status:** executed audit of the 12 publicly committed `astral-sh/uv` README revisions carried forward from Round 38, plus six hand-authored adversarial phrase pairs. This is an empirical editing/label-integrity study, **not** an HoH or FRESCO QA evaluation, not semantic entailment, and not an improvement in RAG accuracy.

## Main gap found

Round 38's 77 gold-derived line membership queries are exact historical-presence checks. They are not 77 independently labeled factual reversals. Before using document diffs to trigger claim invalidation or retriever retraining, CDG must distinguish source-byte change, cosmetic/lexical changes, asserted proposition change, true-world change, and applicability.

HoH (Ouyang et al., ACL 2025) uses diffs and LLM pipelines to extract temporal facts; this increases the importance of quality-controlled **claim-level** change labels. FRESCO (An et al., Findings EMNLP 2026) evaluates evolving semantic conflict, and When Facts Change (Wallat et al., Findings ACL 2026) shows that detecting knowledge mutability need not translate into correct final predictions. Related prior art exists; the gap is a concrete integration and evaluation challenge, not a discovery of a new class of temporal conflict.

## Executed revision comparison

The audit applies the same 25–320 character and >=4 whitespace-token line filter as Round 38. Each consecutive pair yields added and removed lines. A **one-to-one greedy match** pairs removed/added lines when lowercase, punctuation-adjusted token-set Jaccard is >=0.75. It is a **high-overlap review queue**, not a claim that matched lines have unchanged meaning.

- 77 changed line observations.
- 23 near-duplicate edit pairs, comprising 46 changed line observations.
- 31 unmatched observations.
- 2 pairs become exactly identical after the defined normalization, which itself can erase meaningful punctuation or link destinations.
- The threshold was selected illustratively, **not optimized** on semantic ground truth.

No source edit is automatically labeled a factual correction. We preserve original source bytes and both commit IDs for independent scrutiny.

## Adversarial similarity control

Six hand-authored examples change negation, a numeric amount, a date, safety language or permissions while maintaining similar surrounding words. Under an indiscriminate 'high lexical similarity means cosmetic, skip verification' rule, **6/6** examples would be skipped at the 0.75 similarity threshold.

This does not estimate a real-world error rate: hand-authored examples were deliberately chosen to challenge the rule. It **falsifies the soundness of lexical similarity as a sufficient semantic-safety test**.

## Working correctness contract

A proposed temporal fact edge should carry `(source_blob_sha, source_commit, source_byte_range, extracted_claim, claimed_valid_interval, ingestion_time, verification_status)`. These are distinct fields, and source commit time is *not* necessarily the validity start. Any lossy representation or high-overlap text detector can prioritize review but may not silently suppress review of negation, numbers, scopes, dates, or other meaning-bearing qualifiers. An observed edit can create an *unknown* state rather than implying a new fact.

A safe staged workflow:
1. Detect source bytes changed and preserve immutable old/new original spans.
2. Generate candidate edit alignments and screening scores only, keeping uncertain pairs.
3. Use independent claim extraction and verification before updating temporal fact records.
4. Query by both knowledge-as-of and applicable-valid-time, with abstention when effective dates remain unresolved.
5. Benchmark against ordinary diff, token-overlap filtering, bitemporal SQL, and a full semantic review baseline, counting token/API costs and versioned compressed storage.

## Research decision

[NEGATIVE] A text-diff event or high similarity is not an answer to 'which fact changed?'.
[FACT] We can identify real line edits and preserve their provenance across 12 genuine source revisions.
[UNCERTAIN] There are no independently labeled factual-change annotations for this README corpus, so the precision/recall of any proposed claim-change detector is **not measurable** here.
[HYPOTHESIS] CDG's content-addressed source receipts and selective materialization can make a two-stage semantic fact-change verifier cheaper without increasing stale-answer acceptance, compared with full semantic review or conventional temporal SQL plus retrieval.

## Reproduction

```bash
node experiments/round-39/audit.js research/rounds/round-38/uv_readme_revisions.json experiments/round-39/recomputed.json
node experiments/round-39/test_audit.js
```

All methods are classical. No quantum speedup, new coding theorem, or knowledge truth guarantee is claimed.

## Next round, preregistered

Obtain authentic independently annotated temporal QA cases from HoH or FRESCO. Record the dataset version, evidence fields, source revisions, and license. Evaluate semantic change classification and final answer grounding rather than diff membership alone. Include a no-graph temporal lexical baseline, as-of SQL, and an oracle diagnosis explicitly segregated from deployable models.
