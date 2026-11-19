# CDG Round 92: Fixed-Storage Scientific Evidence Coverage

**Date:** 18 November 2026, tested during local evening. **Status:** verified original hash-locked SciFact dataset and eight synthetic regression tests in [GitHub Actions 44444069747](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44444069747). Full 5,183-source/300-query SciFact retrieval experiment with five predeclared label-independent source selection seeds and two total SQLite storage budgets passed.

## Question

Rounds 86–91 demonstrated source-exact storage, concurrency consistency, incremental update equivalence and recovery. But they did not test whether the compression architecture improves **retrieval of human-annotated evidence under a binding physical persistent storage budget**, compared with a *complete source-readable* conventional FTS5 implementation.

Round 92 asks: If both retrievers use exactly the same predeclared FTS5/BM25 tokenizer, title weight 5 and body weight 1, at most 28 OR claim terms, and return the **original source text**, can the smaller architecture keep enough documents to retrieve more human-annotated SciFact evidence within a 10 MiB or 12 MiB storage cap?

This is not an end-to-end generative hallucination test. Evidence-document Recall@k from SciFact's annotated claim-source pairs is the only quality metric. No incorrect source is assigned the gold label of another annotated source.

## Experimental contract

- Original official SciFact source TAR SHA256: \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`. Raw dataset never committed.
- Full corpus: 5,183 abstracts, 300 development claim queries; **188 claims have at least one expert-annotated gold evidence document**. Recall denominator is 188, and 112 claims without annotations are never treated as known negatives.
- Conventional baseline: **source-readable full-content** SQLite FTS5 on the retained subset. Persistent index bytes include the stored title+abstract source, not only inverted postings.
- Compressed intervention: Round 90's **ordinary contentless FTS5 + SHA-256-verified zlib6 original source BLOBs in SQLite**, with verified bytes re-materialized for every top-one query receipt. This is existing SQLite + zlib composition, not original compression mathematics.
- Budgets predeclared: **10 MiB = 10,485,760 B** and **12 MiB = 12,582,912 B**, applied to total static SQLite database file after VACUUM. Both bounds sit between the measured complete compressed and conventional original corpus size.
- Subset selection: SHA-256 hash ordering of \`CDG-R92-v1-UNLABELLED-ROW-PRIORITY|seed|doc_id\` for five fixed seeds **11, 23, 37, 53, 71**. The human gold labels, claims and retrieval results are never consulted to choose documents. For each seed and budget, binary-search a nested hash prefix for the largest observed fitting conventional contentful index size. This is **not an optimized corpus selection/knapsack algorithm** and practical near-monotonic FTS file size is assumed, with n+1 explicitly checked.
- Strong same-document control: build a **compressed matched subset of exactly the same documents and in exactly the same order** as each capacity-limited conventional subset. Verify the top-10 BM25 doc-ID rankings match on **all 300 queries** and SHA-bound source bytes are exact. The full-corpus compressed and full-content systems also match all 300 top-10 rankings.
- Only post-build static file bytes are compared. No ephemeral journals, concurrent update WAL growth, model inference/token cost, cold SSD reads, human-annotated generated answers or archive history are charged. This is a static persistent-storage scenario.

## Results: full-corpus compression preserves source selection

Full original corpus:
- Conventional FTS5 source+index persistent: **14,544,896 B**.
- Compressed contentless FTS + original SHA-bound source persistent: **9,224,192 B**.
- **36.5812%** fewer retained bytes for the complete index+source.
- **300/300** same-query top-ten rankings identical, and **300/300** original top-one sources read/verified for each architecture.
- Expert-labelled SciFact evidence Recall@1 **136/188 = 72.3404%** and Recall@10 **179/188 = 95.2128%**, unchanged from R83/R84 when all documents are present. This does NOT mean a generated answer is true or faithfully cites the source.

## Results: conventional storage-cap source drops versus compressed full corpus

| Budget | Conventional docs across five hash seeds | Mean conventional Recall@1 | Compressed full Recall@1 | Mean conventional Recall@10 | Compressed full Recall@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| **10 MiB** | **3,687–3,742** (mean 3,721.8) | **96.8/188 = 51.4894%** | **136/188 = 72.3404%** | **124/188 = 65.9574%** | **179/188 = 95.2128%** |
| **12 MiB** | **4,457–4,524** (mean 4,495.0) | **115.6/188 = 61.4894%** | **136/188 = 72.3404%** | **150.6/188 = 80.1064%** | **179/188 = 95.2128%** |

Differences across five random hash prefixes, **not** measured independent paper-level trials:
- 10 MiB: full compressed gains **20.8511 percentage points Recall@1**, **29.2553 percentage points Recall@10** compared with the average conventional random-prefix retention baseline.
- 12 MiB: full compressed gains **10.8511 percentage points Recall@1**, **15.1064 percentage points Recall@10**.
- For each of the ten matched full-content versus compressed **same-subset** runs, exactly **300/300 top-ten rankings matched**. Compression itself did not change BM25 ranking, only the number of source documents fitting the fixed budget.
- Individual paired 188-claim nonparametric bootstrap intervals, wins/losses and all per-seed full/budget recall@1/@5/@10 are retained in \`experiments/round-92/ci-results.json\` GitHub Actions artifact. They should not be treated as independent cross-seed or out-of-distribution confidence because the same public test claims and corpus are reused five times.

### Sensitivity to document selection

At 10 MiB, conventional Recall@1 across five hash seeds ranged **86/188 to 106/188**, and Recall@10 **115/188 to 136/188**. At 12 MiB, Recall@1 ranged **106/188 to 124/188**, and Recall@10 **143/188 to 159/188**.

This variation demonstrates a crucial limitation: an optimized trained/semantic document-selection or eviction algorithm could outperform uniform hash selection substantially under the same conventional budget. Any broad superiority assertion must challenge that stronger adaptive baseline before promotion.

## Interpretation and scope

**FACT:** Under these two fixed static SQLite file-size budgets, using a complete compressed source/index allowed the system to keep all 5,183 original scientific abstracts, while conventional contentful FTS5 kept only 71–87% of the documents under five hash-prefix permutations. That yielded higher *annotated evidence-document recall* at both k=1 and k=10, with exact sources and unchanged same-subset ranking.

**INFERENCE:** Source compression creates extra indexable evidence capacity under constrained persistent storage. It can improve *availability* of human-annotated evidence without changing the retriever or claim wording.

**NOT SHOWN:** Any increased human-rated generated-answer faithfulness, hallucination mitigation, new retrieval/ranking mathematics, general superiority against document-prioritization baselines, higher SSD throughput, storage-budget quality gains on unseen external corpora, or general compression algorithm novelty. Data-specific effects and cherry-picked budget thresholds are possible: the 10/12 MiB caps were predeclared before measurements, but chosen in knowledge that the complete compressed layout fits while conventional full does not.

## Next explicit falsification

1. **Stronger conventional selection strategies:** use **SciFact training split only** to prioritize source documents based on training query coverage or train evidence frequencies, plus unsupervised title/term uniqueness. Do not use dev claim text/labels for capacity selection. Compare under the same storage budgets and source+index byte accounting.
2. Add **real answer-level human ground-truth** rather than equating retrieval availability with correct answers. Model verdict scoring on wrong retrieved sources cannot inherit labels from annotated gold doc IDs.
3. Compare token/model CPU inference at equal input contexts, real cold-storage I/O and an independent corpus before publication claims.
4. Eventually test optimal allocation of compressed source bytes, FTS postings and a task-specific evidence retention policy under the same budget, including storage metadata, cost of rebuilding and source exactness.

## Provenance and reproducibility

Primary SciFact reference: Wadden et al., EMNLP 2020, https://aclanthology.org/2020.emnlp-main.609/ .

Relevant code:
- \`experiments/round-92/storage_budget_eval.py\`
- \`experiments/round-92/test_storage_budget_eval.py\`
- \`.github/workflows/cdg-r92-budget-evidence.yml\`

Reproduce:
\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-92 -p 'test_*.py' -v
python experiments/round-92/storage_budget_eval.py --out experiments/round-92/ci-results.json
\`\`\`

Verified job and full aggregate results artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44444069747 . All original source texts remain upstream.
