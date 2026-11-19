# CDG Round 98: Independent QASPER Binding-Byte Evidence Coverage and Paper-Balanced Admission

**Date:** 18 November 2026, late evening. **Verified:** nine regression tests and original SHA-locked QASPER dev complete matched budget comparison PASSED [GitHub Actions 44458788401](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44458788401).

## Research question

R97 established that compressing original QASPER paragraph source+FTS5 storage reduces total static persisted SQLite bytes by **18.8219%** while preserving every top-10 retrieved ranking among all **1,005** dev questions. Does the advantage survive when **both** conventional FTS5 and compressed contentless FTS5 must discard original paragraphs at equal physically measured 6 MiB or 8 MiB? How does source allocation policy change retrieval evidence results?

Task is **paper-scoped** QASPER passage evidence retrieval: the original research-paper ID is given. All full text paragraphs in the same known article are searchable; original paragraph is verified against source bytes. This is not global paper retrieval or generated answer scoring.

## Controls and frozen source contract

- Official QASPER v0.3 release and dev JSON independently SHA pinned in R96:
  \`a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a\`;
  \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`.
- **281** development papers, **13,266** original text paragraphs, **1,005** questions. Exactly **888** question instances have one or more human gold evidence paragraphs matched to exact original text; the remaining **117** cases are excluded, not treated as known negatives.
- Complete full-text SQLite source+FTS = **12,099,584 B**; complete compressed SHA-verified source+contentless FTS = **9,822,208 B**. Both are **greater** than 8 MiB = 8,388,608 B, and both must discard original text under **6 MiB = 6,291,456 B** and 8 MiB.
- Both retrieval representations use R97's identical original paragraph data and fixed BM25 title weight 5/body weight 1 with up to 28 source-independent content-query terms, article rowid scope, and original title/paragraph source text.
- Two **predeclared source-only policies**, never consulting question text, validation answers or human gold evidence:
  1. \`global_hash\`: assign each original paragraph a SHA-256 source-identity priority.
  2. \`paper_balanced_hash\`: rank each paragraph by SHA **within its original paper**; then keep each paper's first-priority paragraph before most papers' second-priority paragraph, and so on. This is an unsupervised paper-diversity heuristic, not a learned evidence selection model.
- Fixed SHA seeds **11, 37, 71**. Two policies × three seeds × two budgets × two architectures = **24** original QASPER physical SQLite source+index controls, plus R97 exact full-corpus source control.
- Source subset is selected by SHA/paper priority and then **restored to its original paragraph order** before SQLite indexing so each known paper has contiguous rowids. A paper with zero retained paragraphs gets an empty query. Both representations verify every retrieved original top-ten source byte. Actual \`VACUUM\`ed on-disk main SQLite bytes enforce the budget. Binary search assumes practical near-monotone prefix file sizes, checks immediate successor, and does not solve globally optimal byte-constrained selection.

## Original expert paragraph evidence results

**Mean across three fixed seeds**. All evidence recall denominators are **888** originally eligible QASPER development questions. The full-corpus reference has **664/888 = 74.7748% Recall@10** and is **not eligible** under either budget.

| Static budget | Unsupervised retention policy | Conventional mean docs | Compressed mean docs | Conventional mean Recall@10 hits | Compressed mean Recall@10 hits | Conventional rate | Compressed rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 MiB | global hash | 6,809.67 | 8,434.67 | 460.67 | 525.33 | **51.877%** | **59.159%** |
| 6 MiB | paper-balanced | 6,483.67 | 8,125.67 | 514.67 | 576.00 | **57.958%** | **64.865%** |
| 8 MiB | global hash | 9,167.33 | 11,337.00 | 554.00 | 612.67 | **62.387%** | **68.994%** |
| 8 MiB | paper-balanced | 8,798.33 | 11,134.00 | 598.33 | 643.67 | **67.380%** | **72.485%** |

**Observed tradeoff:** Paper-balanced admission improves Recall@10 for both architectures and both budgets despite admitting **fewer** total paragraphs, indicating that not all retained paragraph capacity is equally useful. All 281 papers retained at least one source paragraph under the tested budgets for both policies, so this is not simply preventing completely empty papers. Different per-paper paragraph allocation, and the fact that correct evidence is often within a paper, change retrieval outcomes.

**Important negative:** At 8 MiB, compressed **global-hash Recall@1 mean 224.333/888** versus compressed paper-balanced **220.333/888**, so the paper-balanced allocation is *not* universally superior. It also cannot be called a prospective learned policy winner, since no distinct QASPER train/internal-validation selection was performed in this round.

### Paired win/loss sensitivity

Differences are not monotonically positive for all questions. Example 6 MiB global hash, seed 11: compressed top-10 retrieval improved **74** of 888 claim outcomes, lost **11**, tied the remainder, versus conventional same-SHA policy. For 8 MiB paper-balanced seed 71: compressed improved **63**, lost **26**, tied the remainder. Different corpora, query scopes, BM25 global statistics and subset compositions can reorder retrieval even when compressed retains more documents.

The same public QASPER development questions are reused across seeds. These values are descriptive repeated source selections, **not** three independent held-out datasets or a universal confidence interval.

## Mechanistic synthesis

R95's **SciFact** 6/8 MiB binding-budget gain survived train-selected document retention, on short biomedical abstracts with 36.58% storage savings. R98 now replicates the direction of capacity-versus-evidence benefit on **QASPER long-paper paragraphs**, with a smaller full-corpus storage saving of 18.82% and independent text-evidence labels. That is **two distinct tasks and source granularities**, not independent prospective datasets unobserved by the researchers. Both still use a conventional lexical FTS5 retriever and existing lossless compression codecs.

This points to a possible co-design thesis: optimize **losslessly verified evidence capacity, query-informed or document-coverage-aware source admission, and retrieval rank-depth simultaneously** under a fixed *fully accounted* byte budget. The specific source-priority methods are not new theoretical algorithms and no semantic answer fidelity gain is demonstrated.

## Scientific limits

- Paper ID is known for every QASPER query, not an external document retrieval problem.
- Uniform hash and paper-balanced admission are unsupervised, not strong learned selection/dense retrieval baselines.
- Budget includes static SQLite source+FTS postings but excludes model weights, RAM, compression work, active WAL, cold SSD I/O and source-update costs.
- R96 original annotation mapping excludes figure/table and unmatched evidence strings; 117 questions have no exact matched text evidence.
- No generated-answer evidence attribution or hallucination reduction measured.
- Compression does not alter BM25 rankings on identical subsets (R97), but under different subsets ranking can change due to corpus-level term statistics and competition.

## Next experiments

Investigate a *cross-corpus* source codec frontier on original SciFact and QASPER (zstd/Brotli/lzma/zlib) to see how much of the byte tradeoff comes from the individual compressor rather than FTS overhead. Then test whether changing evidence block granularity while retaining exact paragraph boundaries changes the storage versus human evidence utility frontier. The latter must enforce equal total retrieved **source tokens/bytes**, not compare top-10 blocks containing arbitrary numbers of paragraphs.

## Reproduce

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-98 -p 'test_*.py' -v
python experiments/round-98/qasper_binding_budget.py --out experiments/round-98/ci-results.json
\`\`\`

Files \`experiments/round-98/qasper_binding_budget.py\`, \`experiments/round-98/test_qasper_binding_budget.py\`, workflow \`.github/workflows/cdg-r98-qasper-tight-budgets.yml\`. Full source-locked CI and aggregate artifact https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44458788401 .
