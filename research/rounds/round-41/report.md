# Round 41: Authentic Structured Temporal Transitions and the Limits of Date-Based Lookup

**Status:** Pinned authentic public TimeConflict factual transition records and accompanying QA text from PRISM-Edit. Executed a deterministic structural lookup diagnostic; this is **not** independent open-domain retrieval, independent factual truth verification, or end-to-end RAG evaluation.

## Why we changed datasets

Rounds 38–40 used authentic GitHub README changes but lacked claim-level temporal annotations. HoH's public GitHub tree exposes data-creation code and a Hugging Face dataset link, not directly readable full QA records via the connected GitHub interface. FRESCO's public GitHub tree similarly exposes templates and tooling, with no compact QA corpus in that tree. PRISM-Edit's public TimeConflict release does contain structured tuples, before/after object values, time ranges, and natural-language question/answer pairs directly in GitHub. This is therefore a suitable **structural temporal-lookup sanity check**.

**Data:** `CheerCHuang/PRISM-Edit`, relations P26 (spouse) and P35 (head of state), exact upstream Git blobs recorded separately. Dataset questions are generated from these same records; no independent question-level verification or live source bytes are present. Two small relation files supply 25+66=91 records.

## Experimental contract

1. Dataset row ID directly identifies a structured record with subject and relation. This is **oracle associated retrieval** for diagnostic purposes, not inference-time retrieval over candidate documents. The question's subject substring is checked but doesn't retrieve the record.
2. The naive baseline selects the `after_object` irrespective of the question's date.
3. A classical temporal eligibility filter selects the record's before/after object only if its supplied validity range covers the interpreted date; it abstains on none or multiple matches. No semantic model or compressed source reader is called.
4. Time interpretation: an explicit month+year maps to the **last day of that month**, bare year to **July 1**, and a range of years to its midpoint July 1. These heuristics can introduce ambiguity and should not be mistaken for validated natural-language time understanding.
5. Compare predicted labels to the question answer provided by the **same dataset**, not an independently sourced truth label. Report ambiguous and unassigned cases as abstentions, never silently resolve ties using the gold answer.

## Executed results

Total question variants: **260**, from 91 annotated transition rows. Baseline `latest` label matches **122/260**. Time-filtered lookup answers **230/260** and matches **227/260** labels, abstaining on 1 unmatched dates and 29 overlaps. 0 subject-substring checks failed, and 0 questions lacked recognized years. Record-level interval overlaps: 54.

Per relation: {"P26":{"records":25,"qa_rows":25,"questions":86,"latest_correct":44,"temporal_correct":59,"temporal_answered":59,"none":0,"ambiguous":27},"P35":{"records":66,"qa_rows":66,"questions":174,"latest_correct":78,"temporal_correct":168,"temporal_answered":171,"none":1,"ambiguous":2}}.

These are strictly **within-dataset structural consistency** values; improvements over always-current are expected by construction from old/new QA labels. They cannot be used as claims of verified RAG accuracy. The question forms and row assignments leak the task decomposition. Ambiguous time intervals may reflect real overlap, missing end-date annotations, or data inconsistencies, not necessarily model errors.

## New hypothesis from the overlap failure

**Temporal validity is not a total order on source versions.** When multiple facts overlap, the system needs cardinality, relation-specific semantics, source authority, and evidence of supersession. An algorithm that picks the "newest" fact will be wrong for relations that are not single-valued or for records with open-ended end dates. CDG should adopt **set-valued temporal relations** and an explicit `unknown/conflict` state before deciding whether to answer.

This connects bitemporal database theory, constraint-aware knowledge graphs, and CDG's exact version receipts. But the design is standard temporal database engineering unless empirically shown to improve verified-answer quality/cost beyond strong time-aware SQL.

## Next experiment

Build question-to-record retrieval that does **not** use the QA row's gold ID, freeze a timestamp parser, and add an independent semantic validity judge on source texts. Compare indexed SQLite and BM25 baselines against any CDG acquisition policy on the same held-out questions, accounting for index construction, compressed bytes, update cost and abstention. Include injected source conflicts only in a separate stress test, not mixed into authentic data statistics.

## Reproduce

```bash
node experiments/round-41/temporal.js experiments/round-41/timeconflict experiments/round-41/recomputed.json
node experiments/round-41/test_temporal.js
```

Source dataset release: https://github.com/CheerCHuang/PRISM-Edit (license: consult original release). No custom training or quantum runtime.
