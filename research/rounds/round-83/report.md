# CDG Round 83: Published Verifiers on Real Expert-Labeled SciFact Claims

**Date:** 18 November 2026. **Status:** official data acquisition and four source-contract regression tests **passed** (GitHub Actions 44262962038). Published-model calibration and source-route scoring submitted to pinned CPU GitHub Actions; their numeric accuracy results are **not yet verified at report creation**.

## Research motivation

Rounds 80-82 established measurable differences among general NLI, MiniCheck, FactCG and LettuceDetect on closely related **synthetic** and heavily inspected factuality templates. Round 82's highest-recall source-window union improves template balanced accuracy at ~5.27x pair work, but whether source selection works on expert-written claims is unknown.

The next promotion gate is **expert-labeled, non-template evaluation**, separating training-only calibration from development-set scores. SciFact (Wadden et al., EMNLP 2020, https://aclanthology.org/2020.emnlp-main.609/) provides scientific claims, 5,183 scientific abstracts and annotated SUPPORT/CONTRADICT rationales; it is not a general RAG benchmark. MiniCheck (Tang et al., EMNLP 2024) and FactCG (Lei et al., NAACL 2025) are strong published baselines, not CDG inventions.

## Source identity, legal provenance, and preflight

The official AllenAI SciFact GitHub reference is frozen at **68b98a56d93e0f9da0d2aab4e6c3294699a0f72e** and describes the data release archive URL:
https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz

The **exact actual release bytes** used here have SHA-256:
\`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.
Reruns fail if upstream data bytes drift. The source-retrieval and model workflows obtain data on the fly and never redistribute the SciFact originals.

The original repository identifies **SciFact claims and expert annotations as CC BY 4.0 and S2ORC abstracts as ODC-By 1.0** (https://github.com/allenai/scifact/blob/master/LICENSE.md); the HF repackaging lists a different aggregate CC BY-NC license, so use originals according to their own provenance. This study uses the original authors' release, not repackaged train splits.

**[FACT] Preflight counts:** 5,183 abstracts, 564 annotated train claim-document evidence pairs (370 SUPPORT/194 CONTRADICT) and 209 original dev evidence pairs (138 SUPPORT/71 CONTRADICT). R83 fixed SHA-ranked selection takes **32 SUPPORT + 32 CONTRADICT** claim-document pairs from train, then independently **32 + 32** from dev after excluding source-document and claim-ID intersections. Train has 61 distinct annotated source docs/64 claims, and dev 62 distinct docs/58 claims. Frozen selected case-key SHA-256:
\`735fd797de6258eb0b667d5d789e76f341eb1abefdca284647d638974a5184df\`.
The sampling salt is fixed in code; *balanced sampling uses dev annotations to establish equal classes but does not use dev outcomes to select models or thresholds*.

The full original corpus text is 7,880,971 UTF-8 bytes; independently per-document Zlib6 storage is 3,781,388 bytes, a ratio of **0.47981** excluding manifests and retrieval indexes. These bytes do not establish efficient source access or truthful answers.

## Predeclared context routes for each fixed claim

| Route | Text passed to an unchanged verifier | Available at deployment? |
| --- | --- | --- |
| Full abstract | Title and complete original abstract | Only if correct document retrieved |
| Lexical two-sentence | Title and two sentences ranked by deterministic overlap with claim words | Yes if correct document is already available; requires full sentence scan |
| Gold rationale oracle | Title and human-labeled evidence sentences supporting or contradicting the claim | **No**, uses evaluation annotations and is an oracle upper bound |

All 128 selected human claim-document pairs are scored under each route. Lexical two-sentence selection does **not** inspect human evidence sentence IDs or truth labels. A standard 5,183-abstract TF-IDF l2 cosine retrieval baseline independently ranks possible corpus documents using only original claim words and source text. Gold supporting/contradicting doc IDs are revealed only after ranking for recall@1/3/5/10. Do not call a retrieved *unannotated* document false simply because it lacks the original gold ID.

## Frozen pretrained verifier controls and calibration

1. **General cross-encoder/nli-deberta-v3-xsmall**, SHA a150876415327c80daeff35ca6f68f5ed8cf5c24, entailment probability, 384-token first-sequence truncation.
2. **MiniCheck-DeBERTa-v3-Large**, SHA 05782341a53df45bf7bee868863563907e083ee0, official short single-chunk document+EOS+claim input, 2,048-token cap.
3. **FactCG-DeBERTa-v3-Large**, SHA 7582b255f0b45a1be2db6fff5076d0e8ea7aa072, authors' exact conditional support question with Yes/No options, 2,048-token cap.
4. **LettuceDetect ModernBERT base**, SHA 0ff0f0dd23052cf751dae374f57a539aa092e772, claim treated as a one-sentence answer; support decision = no predicted unsupported character span. This framing is non-native to SciFact and deliberately diagnosed.

**Train-only threshold policies, predetermined before dev results:**
- Frozen fixed 0.50 model-score threshold for MiniCheck, FactCG and NLI; LettuceDetect native any-unsupported warning decision (not a probability calibrated to support).
- Minimum training threshold on each model/route achieving empirical training false-positive allowance of at most **10%** and **25%** over the annotated CONTRADICT pairs. All threshold computation uses 64 calibration examples only, *never development labels/scores*.
- Compare balanced accuracy, support recall, contradiction rejection, F1, threshold drift and source-group paired bootstrap CI for lexical2-minus-full and oracle-minus-full. No testing multiple thresholds and then retroactively choosing the best dev score for a scientific claim.

**Critical threshold semantics:** A 10% observed train false-positive allowance does not guarantee a 10% dev false-positive rate. Train and dev sampling are distinct sources but part of the same scientific benchmark, and released models may have been exposed to SciFact during training.

## Resource accounting and falsification gates

- Charge total model-input tokens, model parameter counts, actual CPU scorer+tokenization wall, context bytes, and token truncation counts.
- Separately record TF-IDF corpus index build and query wall time, serialized index bytes, evidence-doc recall@k. Do not omit retrieval when interpreting deployability.
- Avoid conflating gold rationale selected using human labels with ordinary source selection.
- If full abstract beats lexical or oracle evidence, record the negative result and inspect whether claim terms, absence of context or scientific writing cause failure.
- If a train-calibrated threshold loses specificity on dev, reject portable calibration at that operating point. Compare uncertainty over **claim groups**, not 64 nominally independent observations.
- If one model wins accuracy but has >10x CPU cost, report the non-dominated quality/latency curve instead of selecting by accuracy alone.
- SciFact labels are support-vs-contradiction. They cannot evaluate **unknown / insufficient evidence**, which must remain a distinct future test.
- No human-independent newly created truth annotation is claimed. No model fine-tuning, compression novelty, external-corpus full RAG generation, domain-general semantic proof or production SSD metric.

## Reproduction

    python -m unittest discover -s experiments/round-83 -p 'test_*.py' -v
    python experiments/round-83/scifact_data.py --out experiments/round-83/profile.json
    python experiments/round-83/real_grounding.py --out experiments/round-83/ci-results.json

Workflows: \`.github/workflows/cdg-r83-scifact-profile.yml\` and \`.github/workflows/cdg-r83-scifact-models.yml\`. Preflight: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44262962038 .

**Status discipline:** Numerical model results require exact-head successful inference CI; do not infer outcomes from the synthetic Round 80–82 results.
