# CDG Round 95: Both Archives Binding Under Fixed Source+Index Budgets

**Date:** 18 November 2026, late evening local. **Verified:** 10 unit/regression tests and complete SHA-locked original SciFact five-policy, three-seed, two-budget, two-architecture experiment PASSED, [GitHub Actions 44457395997](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44457395997). This closes the asymmetric-budget problem in R92–R94, where the entire compact index fit the tested budget and only conventional FTS had to drop documents.

## Research question and precommitted comparative arms

At the **same 6 MiB and 8 MiB total static persistent source+index SQLite file budgets**, does SHA-verified compressed contentless FTS5 improve annotated evidence retrieval versus complete-source-readable conventional FTS5 when **both** must discard original documents? Both source architectures use exactly the same conventional Unicode61 title-weight 5/body-weight 1 BM25, fixed first 28 content terms OR query and unchanged original text. The intervention is representation size, then a separately optimized deterministic document admission policy. There is no model-generation or human-answer evaluation here.

SciFact original release TAR SHA256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`; 5,183 sources, 300 dev claims, 188 claims with expert-annotated evidence. **Full source-and-index** footprint was **14,544,896 B** conventional and **9,224,192 B** compressed. Both are strictly larger than 8 MiB (8,388,608 B) and 6 MiB (6,291,456 B); neither architecture has a full-corpus exception.

## Train-fit and internal claim-disjoint selection

- 809 SciFact official training claims SHA-sorted and split by the fixed R93 claim-ID contract into **566 fit claims** and **243 internal validation claims**, of which **142** have original expert evidence annotations. Claim IDs do not overlap.
- Fit-split BM25 query top10 reciprocal-rank weights and fit-split gold evidence source frequency inform source prioritization. Corpus-only source title rarity is an unsupervised prior. Neither **dev query text nor dev human evidence annotations** enters policy construction or internal selection.
- Five fixed source priority methods for each architecture: **hash**, **fit-query reciprocal rank**, **fit-query reciprocal rank per approximate stored byte**, **fit-gold source frequency per approximate stored byte**, **unsupervised title rarity**. Scoring per-byte uses a heuristic \`256 + 2 * whitespace word count + source bytes\`, where compressed source bytes are the actual zlib6 size plus 32 estimated metadata bytes; this is **not** a faithful per-row SQLite byte cost.
- Budget enforcement does **not use the proxy**: independent SQLite indexes are actually constructed and vacuumed for source-prefix candidate lengths, the physical main SQLite file measured, and a binary search chooses the largest *observed* source-prefix length fitting each exact budget. The immediate successor is checked. This assumes practical near-monotonic file size, not globally optimal knapsack retention.
- Three fixed hash tie-breaking seeds **11, 37, 71**, five policies, two budgets, two architectures: **60 complete evaluated storage-constrained original-corpus scenarios**, plus full-corpus byte controls and a **400-document exact same-source rank parity control**. Each has SQLite original-source retrieval checks.
- For each architecture and budget, independently select one source admission method on **mean internal validation Recall@10** across the three seeds, then Recall@1 as tie-break. Only after selection report original development evidence recall on the same 188 gold-bearing dev claims.
- Source-disjoint stress cohort: **76** dev annotated evidence claims whose gold document IDs did not occur among *any* official train label source IDs. This is not independent topic/benchmark generalization.

## Preselected policies, no development hindsight

| Budget | Architecture | Internal validation selected source-priority method | Internal validation Recall@10 mean hits (denom=142) |
| --- | --- | --- | ---: |
| 6 MiB | Conventional full-content FTS5 | Fit-query reciprocal-rank per approximate stored byte | **90/142** |
| 6 MiB | Compressed source+contentless FTS5 | Fit-query reciprocal-rank | **106.3333/142** |
| 8 MiB | Conventional full-content FTS5 | Fit evidence source frequency per approximate stored byte | **102/142** |
| 8 MiB | Compressed source+contentless FTS5 | Corpus-only unsupervised title rarity | **127/142** |

The 8 MiB compressed development results illustrate why predeclared selection is necessary: fit-query RRF yielded **174** dev Recall@10 hits, higher than selected title-rarity's **170**, but had lower internal validation Recall@10 **123.3333/142 vs 127/142**. It is **invalid** to promote the 174/188 method as prospectively selected after seeing dev results.

## Test results: human annotated evidence-document retrieval

Means across the **three fixed seeds**, same 188 annotated dev claim denominator. Full compressed reference at 9.22 MB would not fit either budget, and is NOT an eligible candidate in this table.

| Budget | Conventional mean retained documents | Compressed mean retained documents | Conventional Recall@1 | Compressed Recall@1 | Conventional Recall@10 | Compressed Recall@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **6 MiB** | 2,220 | 3,436 | **110/188 = 58.5106%** | **123.6667/188 = 65.7801%** | **136/188 = 72.3404%** | **155/188 = 82.4468%** |
| **8 MiB** | 2,946.33 | 4,651 | **115/188 = 61.1702%** | **134/188 = 71.2766%** | **144.6667/188 = 76.9504%** | **170/188 = 90.4255%** |

**Measured relative gains, not causality beyond these controlled arms:** +**10.1064 percentage points** Recall@10 for 6 MiB, +**13.4752 points** for 8 MiB versus train-selected full-content competitors. At 6 MiB compact retains about 1,216 more source documents. At 8 MiB it retains about 1,705 more. Compression does **not** intrinsically make BM25 better: full and compact indexes with a fixed **identical** 400-document source set gave **300/300 exact top-10 ranked document lists**, and the compressed retrieved bytes were SHA verified.

### Selected policy per-seed outcomes

| Budget | Seed | Full R@10 hits | Compact R@10 hits | Pairwise gain out of 188 |
| --- | ---: | ---: | ---: | ---: |
| 6 MiB | 11 | 136 | 155 | +19 |
| 6 MiB | 37 | 136 | 156 | +20 |
| 6 MiB | 71 | 136 | 154 | +18 |
| 8 MiB | 11 | 146 | 170 | +24 |
| 8 MiB | 37 | 145 | 170 | +25 |
| 8 MiB | 71 | 143 | 170 | +27 |

At 6 MiB paired 188-claim bootstraps yielded point improvements **9.5745–10.6383** percentage points across seeds, with no measured claim-level losses. At 8 MiB point improvements **12.7660–14.3617** points with some claim-level losses (7–8 per seed). Separate per-seed paired bootstrap percentile bounds are in the original aggregate artifact; pooled seeds are **not** statistically independent. These are public data, topic-correlated claims and a within-benchmark comparison, not an unseen-domain statistical superiority theorem.

## Source-disjoint stress test

On **76 dev claims with gold sources never used as a labeled train source**, the validation-selected conventional and compressed results were:
- **6 MiB**: conventional **39/76** Recall@10 each seed versus compressed **54/76, 57/76, 54/76**.
- **8 MiB**: conventional **46/76, 47/76, 45/76**, versus compressed **71/76** each seed.

These label-disjoint results cannot rule out global document similarity or shared topic information, but they demonstrate that directly memorized training gold source IDs are not the sole driver of the observed differences.

## Negative results and alternatives

- Under **8 MiB** the unsupervised title-rarity method won compact internal validation, while supervised fit-query reciprocal rank was better on dev. We preserved that discrepancy rather than switching after seeing dev outcomes.
- RRF per stored-byte proxy gave only a slight 6 MiB development change from plain RRF in compressed storage (**154.6667 versus 155 hits**), despite extra computation. There is no demonstrated scientific novelty in this simple density heuristic.
- Source frequency per-byte prioritized known training gold and failed to consistently beat query-derived relevance on unseen dev labels. This underscores overfitting risk when documents and topics overlap.
- The two arm-specific validation-selected policies differ, so the improvement is from the **combined representation-and-priority architecture** under equal budgets, not a pure compression-only causal estimate. A separate same-document identity control isolates the fact that compression does not alter ranked results.

## Position relative to contemporary research

The documented topics of **cost-aware evidence retrieval** (https://arxiv.org/abs/2606.02245), **budget-aware retrieval allocation** (https://arxiv.org/abs/2606.29959), and **context-compressed evidence selection** (https://aclanthology.org/2026.acl-long.661/) provide close conceptual prior art, not proof of this work's novelty. Our budgets constrain offline **persistent source+index bytes**, not per-query access, context tokens or learned prompt compression, which are different resources. A claim of new mathematics or globally optimized retrieval is not justified.

## Decision and next falsifiers

**KEEP:** strong equal-byte independent source representations, train-fit/internal-validation source priority, exact-source receipts, and a 76-claim label-disjoint cohort. This is a reusable evidence retrieval systems result.

**BLOCK:** novelty claims about a new BM25, novel compression method, hallucination suppression, general performance significance, optimal document selection, or production end-to-end I/O. Count actual model weights, SSD cold reads, WAL histories and trained prioritizer construction overhead before full platform cost claims.

**NEXT:** independently reproduce on long-passage QASPER with explicit paper-scoped retrieval and human paragraph evidence. Then run a stronger published FactCG/MiniCheck human-annotation-backed verdict stage and add a generated-answer attribution benchmark; evaluate compressed + prioritized source against strong conventional/dense alternatives under a **joint byte/token/CPU cost frontier**. Do not conflate availability of evidence with correctness of its interpretation.

## Reproduction

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-95 -p 'test_*.py' -v
python experiments/round-95/dual_budget_evidence.py --out experiments/round-95/ci-results.json
\`\`\`

Source files \`experiments/round-95/dual_budget_evidence.py\`, regression tests \`experiments/round-95/test_dual_budget_evidence.py\`, workflow \`.github/workflows/cdg-r95-dual-binding.yml\`. Verified original SciFact full CI and JSON artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44457395997 .
