# CDG Evidence Graph Addendum: Round 79

**Date:** 18 November 2026. **Status:** five tests and real pretrained-model experiment passed, CI 44243476813. This is an append-only continuation of the existing research ledger. It must be consolidated only after the prior round documentation is merged and exact-head numerical checks succeed.

## New graph branch

R69-71 human annotation and source-only impossibility
-> R72 generic NLI semantic false-alarm failure
-> R74 calibration collapse under task/serialization shift
-> R75 source swapping barely moves *minimum* entailment
-> R76 in-domain trained span detector baseline
-> R77 original-prompt sensitivity small/uncertain
-> **R79: train-domain detector, source-only nearest/farthest interventions**

**Orthogonal physical branch:**

R48 reversible versioned reader
-> R73 selected window source-byte exactness
-> R78 archive-fed trained verifier input equivalence
-> potential retrieval+compression+verification cost frontier

## What Round 79 can answer

Does the trained detector change its *predicted unsupported spans* when the same answer and question are supplied with different same-task evidence, and do dissimilar substitutes change it more than similar substitutes? All choices are source-only, not response- or label-informed.

## What it cannot answer

Whether the substituted source factually supports the answer, whether a changed mask is an improvement, whether the system mitigates hallucinations, or whether this sensitivity transfers to unseen domains. RAGTruth human labels apply solely to original evidence. Even 100% switch rate would not establish support correctness.

## Falsification order

1. Verify pinned 141-response/24-source cohort, original model and regression tests.
2. Estimate near/far warning switches and character-mask changes with source-group uncertainty.
3. Compare against near/far lexical distance to expose superficial novelty sensitivity.
4. If a meaningful effect exists, commission **human-labeled or controlled truth-preserving / truth-changing** evidence interventions before promoting any accuracy or calibration claim.
5. Integrate with R78 physical costs only after semantic checks, then compare ordinary BM25/FTS5 + whole-compressed source against any more complex CDG selection.

[FACT] Actual source swapping changed the response-level warning decision on 111/141 original outputs for both nearest and farthest alternatives. Mean changed answer-character mask was 78.680% (near) versus 85.799% (far). Lexical Jaccard overlaps were only 0.049670 (near) and 0.010834 (far), and the binary far-minus-near switch-rate had source-group bootstrap interval [0,0]. CPU costs differed substantially (original 143.518 s; near 211.988 s; far 96.549 s), so source length/chunking is a confound.

[INFERENCE] Context sensitivity is visible in the trained model, but the response-level any-warning decision saturates on these weakly related alternative sources. Character-level behavior changes more, though the swaps have **no human counterfactual truth labels**. Controlled atomic fact edits and realistic full-corpus retrieval are still required before any semantic or efficiency promotion.
