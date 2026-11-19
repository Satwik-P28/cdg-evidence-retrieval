# CDG Round 93: Stronger Train-Selected Conventional Retention Baselines

**Date:** 18 November 2026, local evening. **Verified:** nine synthetic/regression tests and complete SHA-locked SciFact six-policy, three-seed, two-budget evaluation PASSED, [GitHub Actions 44445214973](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44445214973). This round deliberately challenges Round 92's weaker hash-random source-retention comparator, rather than assuming compression is a uniquely effective solution.

## Research question

R92 found a 36.58% source+index byte reduction and higher expert-annotated SciFact retrieval recall under 10 MiB / 12 MiB budgets by retaining all 5,183 sources. But conventional FTS5's budget retention randomly dropped documents. Does the advantage survive against conventional index **source selection informed by prior training queries** and source value estimates?

The training-only priority policies are standard deterministic heuristics, not new retrieval algorithms. Each conventional candidate retains complete original source text and uses exactly the same SQLite FTS5 Unicode61 BM25 title weight 5/body 1, first 28 source-independent query tokens. Exact persistent SQLite bytes after VACUUM enforce both budgets, not an estimated number of documents.

## Leakage-control design

- Original SciFact release TAR SHA256: \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`.
- **809 original SciFact training claims**, frozen SHA-sorted claim-ID split into **566 policy-fit** and **243 internal policy-selection/validation** claims, with **zero shared claim IDs**. Among internal selection claims, **142** have human gold evidence docs.
- Policy fit uses only **566 fit claims and optional original evidence annotations**. Internal 243 claims select one policy for each storage budget by mean internal-source Recall@10 over three predeclared hash tie-break seeds **11, 37, 71**, with Recall@1 tie breaker. **No SciFact dev claim text or annotation enters priority construction or internal policy selection.**
- Evaluate on **300 official SciFact dev claims**; **188** have at least one annotated evidence source. Human labels do not select output documents, so nonannotated retrieved sources are not declared wrong.
- Source-disjoint stress subset: **76** dev evidence claims whose annotated gold source IDs never appeared in the full 809 train claims' labeled evidence. This removes direct reuse of the source as a labelled training evidence example, not topical or pretrained-model overlap. Full corpus BM25 evidence Recall@10 on this subset is **75/76**.
- Six predeclared source ordering policies: (1) SHA hash only; (2) fit-split evidence-source frequency; (3) fit-claim BM25 top10 reciprocal rank counts; (4) greedy fit-claim best-top10 coverage under estimated source-byte cost (400 greedy steps then reciprocal-rank tail); (5) shortest original source first; (6) corpus-only rare-title token score. All source selection is independent of dev labels. The 400-step greedy is a heuristic, not exact optimal knapsack selection.
- Three fixed seeds × six policies × two budgets = **36 full original-corpus SQLite subset build and 300-dev-query evaluations**, plus the original full-corpus FTS control.
- An earlier provisional design scored priorities on the same training claims used to build them. It was **not promoted**. The final exact-head CI uses separated fit/internal-selection claims; the related regression enforces disjoint IDs.

## Overall expert evidence Recall@10 on development

These values are means over three fixed hash-tie seeds; denominators are always the **same 188 annotated development claims**, not a conditional subset of the retained documents. Source retention counts vary by source text length and SQLite pages.

| Conventional contentful FTS prioritizer | 10 MiB: mean docs | 10 MiB: dev Recall@10 | 12 MiB: mean docs | 12 MiB: dev Recall@10 |
| --- | ---: | ---: | ---: | ---: |
| Hash random only | 3,720.33 | **69.8582%** | 4,496 | **82.8014%** |
| Fit evidence-source frequency | 3,702 | **81.9149%** | 4,487 | **88.4752%** |
| Fit query reciprocal rank | 3,659.67 | **84.3972%** | 4,447.67 | **90.9574%** |
| Fit query greedy best-hit coverage | 3,652.33 | **84.3972%** | 4,429.33 | **90.9574%** |
| Shortest original sources first | 4,330.67 | **66.4894%** | 4,808 | **74.4681%** |
| Unsupervised rare-title prioritization | 3,568 | **69.6809%** | 4,414 | **86.7021%** |
| **Full compressed corpus (R92, both budgets)** | **5,183** | **95.2128%** | **5,183** | **95.2128%** |

A larger number of retained sources is not sufficient: shortest-source-first saved enough pages for more documents but reduced quality compared with evidence-aware priority policies. The greedy coverage method did **not** improve the observed Recall@10 beyond simple reciprocal-rank priority, despite extra algorithmic complexity. These are negative results worth retaining.

## Primary policy-selection outcome, chosen without dev performance

**10 MiB:** internal validation selected **train-query reciprocal-rank source priority**, internal mean Recall@10 **108/142 = 76.0563%**, beating the original hash baseline on internal selection. On dev it yielded mean **84.3972% Recall@10**, **67.3759% Recall@1**. Complete compressed source/index yielded **95.2128% Recall@10, 72.3404% Recall@1**. The compressed system therefore retained a measured difference of **10.8156 percentage points Recall@10** and **4.9645 points Recall@1** against the train-selected conventional strategy.

**12 MiB:** internal validation selected **unsupervised rare-title priority**, internal mean Recall@10 **125/142 = 88.0282%**. On dev it yielded **86.7021% Recall@10**, **68.0851% Recall@1**. Complete compressed source/index outperformed by **8.5107 points Recall@10** and **4.2553 points Recall@1**.

**Important development-hindsight contrast:** training-query reciprocal-rank priority actually obtained **90.9574% development Recall@10** at 12 MiB, closer to full-compressed **95.2128%** (4.2554-point gap), but **was not selected** by predeclared internal validation. It is scientifically invalid to relabel it the prospective 12 MiB policy winner after seeing dev results. The positive evidence is therefore less dramatic than the random-source comparison in R92, and even the train-selected comparison is not a universal compression advantage.

## Source-disjoint dev sensitivity

Only **76 dev claims** have annotated gold source IDs absent from all labelled official training evidence. Full-corpus recall on that cohort: **75/76 = 98.6842%**.

| Conventional candidate | 10 MiB source-disjoint dev Recall@10 | 12 MiB source-disjoint dev Recall@10 |
| --- | ---: | ---: |
| Hash | 71.4912% | 88.5965% |
| Fit evidence-source frequency | 70.6140% | 85.5263% |
| Fit query reciprocal rank | 77.1930% | 90.7895% |
| Fit query greedy best-hit coverage | 77.1930% | 90.7895% |
| Shortest source | **81.5789%** | 85.5263% |
| Unsupervised title rarity | 68.4211% | **92.1053%** |

The source-disjoint cohort still favors full compressed source retention for both budgets, but policy rankings change, especially 10 MiB shortest-source versus train evidence-source frequency. The 76 claims are a subset of the same public SciFact dev set, not a new benchmark; tests use only sources absent from *labelled train gold*, so source-related distribution overlap may still exist.

## Interpretation and limits

**FACT:** At the same strict static post-VACUUM SQLite file budget, conventional corpus selection guided by fit-split train queries substantially improves source evidence recall over random retention. This reduces the apparent compressed advantage from R92.

**FACT:** Full compressed source+index still preserves greater original SciFact evidence availability under these exact budget conditions. At matched document identity the BM25 ranker is identical (demonstrated in R92); thus remaining gains are entirely from higher retained source coverage.

**NOT SHOWN:** Any novel retrieval theorem, model-generated answer fidelity, a general result against learned dense or submodular evidence selection, cold SSD throughput, storage advantage with model weights counted, or independent unseen-corpus generalization. Human-labelled SciFact sources are reused by its own training claims, and all tuning/evaluation occurs within a public dataset and common scientific corpus. The internal validation split prevents claim-ID overlap only; sources and topics may overlap.

## Research decision

**KEEP:** Compact contentless+compressed source as a static storage-cap enabling architecture, with train-selected conventional priority and same-corpus source-disjoint stress cohorts as *mandatory* reference controls in future budget studies.

**KEEP:** Negative results for shortest-source and 400-step train-query greedy, and the discrepancy between internal validation winner and dev hindsight at 12 MiB.

**NEXT:** (1) score actual publicly pretrained claim verification on *retrieved* source documents, not gold-oracle evidence; (2) evaluate compact plus train-informed source selection on a larger independent corpus that does not fit the compact budget either; (3) optimize task-specific evidence coverage under both postings and compressed-source byte limits, with exact fair baselines and independent budgets.

## Reproduce

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-93 -p 'test_*.py' -v
python experiments/round-93/train_budget_selection.py --out experiments/round-93/ci-results.json
\`\`\`

GitHub Actions and aggregate artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44445214973 . Code \`experiments/round-93/train_budget_selection.py\`, \`experiments/round-93/test_train_budget_selection.py\`, workflow \`.github/workflows/cdg-r93-train-budget-selection.yml\`. Official benchmark reference: https://aclanthology.org/2020.emnlp-main.609/ .
