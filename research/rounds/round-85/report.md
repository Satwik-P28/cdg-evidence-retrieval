# CDG Round 85: Train-Calibrated Grounding Checks and Evidence-Context Routing on SciFact

**Date:** 18 November 2026. **Status:** code, frozen human claim-document cohort, synthetic regression tests and four separately isolated pretrained CPU model jobs submitted. Numerical real-model outcomes must come from successful exact-head runs. This is a continuation of Round 83/84; it is not a novel model or independent hidden benchmark.

## Question

Round 83 achieved real SciFact evidence Recall@1 .7234 with conventional FTS5/BM25 and reported only **fixed 0.50** support judgments for three pretrained checkers on 60 annotated gold claim-document pairs. Round 84 showed title weight/term-budget tuning on SciFact train selects the incumbent. What happens to *support versus contradiction* decisions when:
1. A verifier receives the **full original scientific abstract**, **a source-only lexical best-two-sentence excerpt**, or the **gold rationale sentences selected by the expert SciFact annotations**?
2. We select a support decision threshold **using only official SciFact train labels**, under 10% or 25% observed training false-acceptance allowance, then evaluate on separate dev source groups?

This is a frozen prospective comparison of pretrained **generic NLI, MiniCheck-DeBERTa, FactCG-DeBERTa and LettuceDetect**. Models, embeddings, weights, tokenizer caps, archive release and operating-point strategies were not fitted to the development cohort in this round.

## Cohort identity and upstream provenance

Official SciFact original AI2 archive URL and SHA256 locked at
\`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.
Original SciFact GitHub source code ref:
\`68b98a56d93e0f9da0d2aab4e6c3294699a0f72e\`.
SciFact expert annotated claims under CC BY 4.0, underlying S2ORC abstracts under ODC-By 1.0. The corpus contains 5,183 scientific abstracts. Original content remains upstream.

**Frozen selected pair-key SHA:** \`735fd797de6258eb0b667d5d789e76f341eb1abefdca284647d638974a5184df\`, with sampling salt \`CDG-R83-HUMAN-SCIFACT-SOURCE-DISJOINT-v1\` retained unchanged from preflight instead of resampling. Exactly **64 train/calibration claim-doc pairs** (32 SUPPORT/32 CONTRADICT) from 61 distinct source abstracts and 64 claim IDs, and **64 dev/evaluation pairs** (32/32) from 62 different source abstracts and 58 different claim IDs. The selected train/dev source and claim ID sets do not overlap.

This source-level split prevents shared source passage tuning within this analysis, but the same public SciFact benchmark and its development split have been used by prior methods and our Round 83, so it is **not a never-observed independent external test**. Expert SciFact labels are support-vs-contradiction, not proof of a generic no-evidence negative class. Model providers may have trained on SciFact or related publications.

## Evidence source routes and oracle boundary

Each fixed claim-document case is evaluated with 3 inputs:

| Route | Evidence model sees | Whether can be selected without human gold |
| --- | --- | --- |
| \`full\` | Original title and entire abstract | Yes, **after a correct source document is retrieved** |
| \`lexical2\` | Original title and two sentences with highest deterministic claim-token overlap | Yes, but only after downloading/scanning the correct source |
| \`oracle_rationale\` | Original title and human expert-annotated rationale sentences | **No**. This is a nondeployable human-oracle upper bound |

The gold source document ID is supplied by SciFact; model support scores cannot measure document retrieval recall or wrong-source hallucinations. A separate full-corpus standard TF-IDF retrieval baseline measures gold source recall@1/3/5/10 without using gold IDs in ranking.

## Prior-art model and fixed scoring

- \`cross-encoder/nli-deberta-v3-xsmall\` at SHA \`a150876415327c80daeff35ca6f68f5ed8cf5c24\`, support = published entailment probability, 384-token cap.
- \`lytang/MiniCheck-DeBERTa-v3-Large\` at SHA \`05782341a53df45bf7bee868863563907e083ee0\`, direct official short-document-chunk forward \`doc + EOS + claim\`, 2,048 cap.
- \`yaxili96/FactCG-DeBERTa-v3-Large\` at SHA \`7582b255f0b45a1be2db6fff5076d0e8ea7aa072\`, official documented \`Choose your answer...\` input format, 2,048 cap.
- \`KRLabsOrg/lettucedect-base-modernbert-en-v1\` at SHA \`0ff0f0dd23052cf751dae374f57a539aa092e772\`, unsupported span warning collapsed to binary support. This claim-as-answer adaptation is different from official RAGTruth training tasks.

Each model is now executed in **its own isolated GitHub Actions CPU job** rather than serializing all model inference inside one long-running runner, keeping complete per-model actual token and scorer CPU costs.

## Predeclared calibration and evaluation

For each model and evidence route, report three policies:
1. **Fixed original 0.50** score acceptance, or native LettuceDetect binary warning.
2. Train-only smallest support probability threshold satisfying **at most 10% observed false acceptances on 32 train CONTRADICT inputs**.
3. Same, allowing **at most 25% observed false acceptances on train CONTRADICT**.

The selected thresholds are then applied *unchanged* to the 64 dev annotated claim-document pairs. Compare TP/FP/FN/TN, dev balanced accuracy, support recall, contradiction rejection, F1, train FPR, dev FPR and evidence route impact. A 10%-train threshold is **not a distribution-free specificity guarantee** on dev. Report grouped claim bootstrap intervals for source-route changes, and no significance without uncertainty.

## Key falsifiers

- **Quality:** Does the lexical two-sentence route worsen contradiction false acceptance by removing key negation or scientific qualifiers? A high support recall alone is not a gain.
- **Oracle:** How often does human-selected rationale improve over full abstract? The oracle cannot be promoted as retrieval because it uses the labels in its input.
- **Calibration:** Does train-only threshold tuning keep dev false acceptance bounded, especially for FactCG's prior R80 synthetic scoring shift?
- **Latency:** Charge scoring tokens and CPU time for all three evidence routes, source-selection scan and TF-IDF retrieval index; avoid treating context selection as free.
- **Correctness:** No source ID was retrieved for the model; no generator or end-to-end wrong-answer reduction was evaluated.
- **Deployment:** Candidate selection and source support verification should eventually be tested together with real BM25/FTS5 top-k retrieval from Round 83 and a withheld source family.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-85 -p 'test_*.py' -v
    python experiments/round-85/real_grounding.py --model nli --out experiments/round-85/ci-nli.json
    python experiments/round-85/real_grounding.py --model minicheck --out experiments/round-85/ci-minicheck.json
    python experiments/round-85/real_grounding.py --model factcg --out experiments/round-85/ci-factcg.json
    python experiments/round-85/real_grounding.py --model lettuce --out experiments/round-85/ci-lettuce.json

Workflow: \`.github/workflows/cdg-r85-scifact-calibration.yml\`. Only aggregate metrics, source/checkpoint SHA, tokenizer/inference costs and uncertainty summaries should be committed. No original claim or abstract text is redistributed.
