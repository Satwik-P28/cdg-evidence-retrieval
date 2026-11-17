# Round 40: Selective Claim Review versus Citation-Destination Audit

**Date:** 2026-11-17. **Status:** real-document edit accounting and constructed adversarial screening checks. **No independent factual-change labels, semantic verifier execution, full Node clean-room test run, or end-to-end retrieval/answer-quality benchmark.**

## Research question

Can a classical, cheap preliminary check reduce **semantic verification** workload without assuming that similar text is semantically equivalent? This follows Round 39's failure of treating high lexical overlap as safe-to-skip. It tests one narrowly applicable source-format insight: a visible assertion and the link identifying its supporting source are separate mutable objects.

## Relevant external work

- HoH, Ouyang et al., ACL 2025, [paper](https://aclanthology.org/2025.acl-long.301/), [code](https://github.com/0russwest0/HoH): diff extraction followed by LLM verification and annotated outdated evidence. **This round did not run their QA data.**
- FRESCO, An et al., Findings EMNLP 2026, [paper](https://aclanthology.org/2026.findings-emnlp.54/), [code](https://github.com/facebookresearch/fresco): temporal evidence conflict and reranking. Its GitHub tree exposes generation tools and templates; the labeled evaluation set was not locally ingested.
- When Facts Change, Wallat et al., Findings ACL 2026, [paper](https://aclanthology.org/2026.findings-acl.103/): detecting temporally mutable facts need not cause an LLM to act on that knowledge.

HoH already investigates diff-triggered expensive reasoning, so two-stage detection is **prior art**. The candidate CDG distinction would be tying source/citation version checks to exact compressed source receipts and explicitly evaluating joint semantic-reliability and physical-cost trade-offs. That has not yet been demonstrated.

## Inputs and matching

- Same **12 genuine dated astral-sh/uv README.md Git revisions** as Rounds 38-39; full historical text and commit/blob IDs already committed in `research/rounds/round-38/uv_readme_revisions.json`.
- Consider lines with 25–320 characters and at least four whitespace terms. Match removed/added lines in adjacent revisions greedily and one-to-one using token-set Jaccard >= 0.75, as in Round 39. Unmatched lines remain separate events.
- The result is **54 independent change events**, comprising **23 aligned old/new pairs** and **31 unmatched** changes. These are *review events*, not independently annotated fact changes.
- For aligned pairs, parse ordinary inline Markdown links `[label](target)`. If visible text differs, choose semantic review. If text is identical but link destinations differ, choose citation audit. Otherwise mark presentation-only. Any unmatched insertion or deletion goes to semantic review. Citation review may escalate to semantic review if linked source content has changed.
- The parser does **not** guarantee safe handling of nested Markdown, reference links, HTML, changing code context, visually meaningful emoji, or adversarial URL syntax. Thus it is a triage prototype, not a sound semantic equivalence oracle.

## Observed edit categories

| Triage action | Real GitHub edit events |
|---|---:|
| Full semantic review | **47** |
| Citation target audit, possible escalation | **7** |
| Presentation-only | **0** |
| **Total** | **54** |

All seven citation-audit cases arose from aligned pairs whose text after inline Markdown rendering was unchanged while link destinations changed. This does **not** imply the changes are harmless. Link destination changes can alter source authenticity or support even when visible language stays fixed.

## Explicit cost assumption and sensitivity

With illustrative costs of semantic review **10**, citation audit **2**, and screening **0.1** units per change event:

| Policy | Cost units | Validity |
|---|---:|---|
| Semantic review all 54 events | **540** | Simple conventional reference |
| Unconditionally skip 23 similar pairs | **310** | Unsafe; Round 39 found counterexamples |
| Review 47 semantically, audit 7 citations and screen 54 | **489.4** | **9.37% modeled** reduction; may fail if citation checks require semantic escalation |

The difference between two review costs is `7*(10-2) - 54*0.1 = 50.6` units. A citation audit cost of 10, or escalation of every citation case to semantic review, eliminates the benefit and screening adds overhead. These are **assumed units**, with no measured latency, token, API, or disk I/O. We do not claim a 9.37% real speedup.

## Adversarial correctness controls

Six purpose-built changes involving negation, numeric limits, dates, unsafe/ safe claims and permissions are routed to semantic review. A seventh attack preserves a link label but changes its URL, and is routed to citation audit. These are contract checks, **not** an unbiased sample and not estimates of real-world semantic recall or false acceptance.

The `test_screen.js` file contains Node assertions for these cases and fixture cases, but was **not independently executed in Node in this round**. The authentic revision analysis was executed in a separate connected JavaScript environment and produced the results above. Full clean-room Node reproduction is a required next validation step.

## Additional graph-of-thoughts synthesis

1. **Reference-dependency invalidation.** A content-preserving edit may still change which source a claim cites. The correct invalidation unit is not merely a document hash but a tuple `(claim bytes, source identity, target identity, valid interval, observed version)`. This resembles database foreign-key dependency tracking; it is not quantum.
2. **Two-lane audit.** Separate semantic entailment from origin/citation authorization. This avoids wasting expensive model calls on clearly purely referential changes, but only when the cheaper reference checker detects escalation conditions.
3. **Cost of uncertainty.** If uncertainty is high, both checks should run. An optimal gate depends on calibrated error costs, not only lexical similarity.
4. **Compression and change review.** Exact versioned compressed source frames retain original evidence for later verification while approximate indexes triage candidate edits. This is an architectural compatibility hypothesis, not a measured performance result.
5. **Bitemporal validity.** Neither new commit time nor a changed link establishes the real-world effective interval. Both system-observed time and fact-valid time remain required before answering historical questions.
6. **Prior art pressure.** Standard diff tools, Git history, SQL temporal indexing, and conventional verification loops are strong competitors. A new CDG algorithmic claim requires a controlled end-to-end gain beyond their combination.

## Falsification priorities

**Primary:** acquire independently labeled factual reversals from HoH or FRESCO and run a zero-shot, frozen edit-screening comparison: full verifier, unconditional similarity skip, qualifier-sensitive screen, and two-lane source/citation audit. Report factual-change recall, unsupported accepted claims, useful accepted answers and total measured cost.

**Systems:** run the pipeline through CDG's versioned compressed source engine, compare with bitemporal SQL and Git-like archived text, and charge index storage, source byte reconstruction, deep verifier, audit escalation, and update invalidation.

**Kill criterion:** if safe citation audit costs as much as semantic review, or if missed semantic changes make the reliability trade-off unacceptable, abandon this split and prioritize full review of changed evidence.

## Reproduce

```bash
node experiments/round-40/screen.js research/rounds/round-38/uv_readme_revisions.json experiments/round-40/recomputed.json
node experiments/round-40/test_screen.js
```

The full inputs are pinned with commit and blob identities. Output metrics are not a claim that 54 events correspond to 54 factual changes.

## Post-publication execution check

On 2026-11-17, the exact committed `screen.js` and `test_screen.js` contents were fetched and executed in an isolated JavaScript runtime with the Node `fs` module stubbed and no filesystem access. The fixture and adversarial assertion code completed (`PASS: 10 fixture and adversarial invariants`), and rerunning the exact committed scanner on the 12 pinned revisions reproduced all six published event counts (54 total, 23 paired, 31 unpaired, 47 semantic, 7 citation, 0 presentation). **This is executable-source validation, not a separately installed Node CLI test, human semantic-label audit, or QA evaluation.**
