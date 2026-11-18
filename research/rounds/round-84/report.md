# CDG Round 84: Prospective BM25 Title Boost and Query-Budget Ablations on SciFact

**Date:** 18 November 2026. **Status:** five offline regression tests and full 5,183-source eight-policy retrieval sweep **passed** (GitHub Actions 44264954609). The initial selected-policy results are measured below; an exact-head rerun prints the full variant grid. This is an ablation of conventional retrieval, not a new BM25 algorithm or independent RAG generation.

## Motivation

Round 83 compared original SciFact TF-IDF retrieval to a strong conventional SQLite FTS5/BM25 baseline over **5,183 scientific abstracts**. The predeclared R83 FTS5 policy (title weight 5, abstract weight 1, OR up to 28 unique claim words) had **136/188 dev gold evidence Recall@1 = 72.34%**, versus original authors' TF-IDF **110/188 = 58.51%**. It also used a larger indexed footprint, so architecture-level superiority was not established.

R84 asks whether **the title boost and query length actually cause the observed retrieval difference**, and whether selecting them on official SciFact *train labels only* transfers to *dev*, rather than fitting retrieval hyperparameters to the already-inspected development set.

## Predeclared ablation grid

One original official SciFact dataset release with immutable SHA-256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`. Source locked by already merged R83 tool. Use **all 5,183 original corpus documents**, no labels in source indexing or query ranking.

- Independent method 1: authors' unchanged SciFact TF-IDF with English stopwords, unigram words and original descending score tie convention.
- Independent method 2: one full-corpus FTS5 \`unicode61\` index, \`bm25(sources,title_weight,1.0)\`, full-title and original abstract fields.
- **Predeclared 4×2 policy grid:** title weights (1, 3, 5, 10), source-only claim query budgets (12, 28 unique tokens) with R83's fixed stop list and quoted OR.
- All query/source matches ranked without reading support/contradiction labels or cited doc IDs. Gold source IDs are read solely for retrieval Recall@1, @3, @5 and @10.
- The default incumbent remains **title weight 5, budget 28**, exactly the model-free R83 baseline.

## Train-only selection and evaluation rule

Use all SciFact **train claims with annotated source evidence** to choose one BM25 variant. Optimize **train Recall@5**, then **train Recall@1**, then shorter query budget, then deterministic lexical name. DO NOT change this selection after examining dev. Evaluate the chosen policy, unchanged incumbent, and unchanged authors' TF-IDF on all **188 SciFact dev claims with annotated gold source documents**.

For transparency, output all eight dev recall results, but **they are exploratory outcomes** and cannot be used to claim that a hindsight-best dev variant is superior. Paired dev recall differences for chosen-vs-TFIDF and chosen-vs-R83 FTS5 use claim-level bootstrap (2,000 deterministic replicates) and present the interval including any null result.

## Cost and integrity obligations

- One FTS5 persistent index shared across all variants: measured database bytes, build seconds and per-query-sweep seconds.
- TF-IDF sparse data bytes and model-building query seconds separately, remembering dictionary/serialized data are not accounted equally between methods.
- No hidden model reranker, hallucination detector or answer generator. Retrieval is evaluated only at the annotated document ID level. A different unannotated source may still contain correct evidence.
- Original source abstract, annotations and derived per-claim labels stay upstream; CI artifacts store only aggregate recall/ranks and SHA identities.
- The train and dev queries have distinct claim identifiers, but their source corpus and medical topics overlap. Claim bootstrap intervals cannot prove deployment-scale generalization.
- A training-selected variant is no novel algorithm. Improvement must be meaningful against the **already strong FTS5** baseline, not only authors' weaker TF-IDF.
- If every alternative increases index footprint, query work, or false evidence selection without dev recall gain, the incumbent wins by simplicity.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-84 -p 'test_*.py' -v
    python experiments/round-84/retrieval_ablation.py --out experiments/round-84/ci-results.json

Workflow: \`.github/workflows/cdg-r84-scifact-retrieval.yml\`. Do not promote numerical claims until successful exact-head test.


## Measured main result: CI 44264954609

**[FACT]** Five isolated regression tests passed, immutable original SciFact dataset archive SHA verified. Official train has **809 claims**, **505 claims with annotated source evidence**. Official dev has **300 claims**, **188 claims with evidence**. Original data, not R80/R81 templates.

**[FACT]** Exactly one policy was selected using train Recall@5, then train Recall@1, then query cost: **FTS5 title weight 5, body weight 1, first 28 distinct query terms**. This is the **identical pre-existing R83 conventional incumbent**, not a discovered superior new architecture.

| Retrieval method | Train Recall@1 | Train Recall@5 | Dev Recall@1 | Dev Recall@5 | Dev Recall@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train-selected FTS5 5:1 / 28 terms | **.732673** | **.902970** | **.723404** | **.882979** | **.952128** |
| Authors' original TF-IDF | n/a in initial compact CI log | n/a in initial compact CI log | .585106 | .819149 | .867021 |
| R83 FTS5 incumbent | same as selected | same as selected | .723404 | .882979 | .952128 |

The selected retrieval policy ties the frozen incumbent **exactly** on each dev claim (claim bootstrap delta 0, 95% interval **[0,0]**), not merely the aggregate recall. Against original TF-IDF, the 188 paired dev claims give Recall@1 delta **+.138298** (95% claim-bootstrap interval **[+.079787,+.202128]**) and Recall@5 delta **+.063830** (interval **[+.010638,+.117021]**).

**[INFERENCE]** The 5:1 title weighting and 28-term query budget are reproducibly selected by an official training-label policy, reducing pure dev hindsight-selection risk from R83. This *does not* prove optimality beyond the eight fixed variants or independent out-of-domain generalization. No new retrieval advantage over the existing strong R83 FTS5 is shown.

**[REJECTION GATE]** Do not describe the current method as a new retrieval algorithm or source compression breakthrough. Preserve the incumbent until a new candidate beats it on a source-distinct, genuine evaluation at matched index/query/runtime costs.

Successful original full-run provenance: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44264954609 . A subsequent logging-only commit adds the whole eight-row grid to CI, without changing training selection or model inputs.


## Exact eight-configuration sensitivity grid (CI 44265142751)

**[FACT]** All five unit tests and the exact full-corpus reproducible rerun passed at https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44265142751 . The same train-only selector again chose **title5/terms28**. The table below contains **all predeclared variants**; unselected dev rows are disclosed as *exploratory diagnostics*, not independent confirmations.

| FTS5 title boost | Max claim query terms | Train Recall@1 | Train Recall@5 | Dev Recall@1 | Dev Recall@5 | Dev Recall@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12 | .722772 | .899010 | .702128 | .893617 | .952128 |
| 1 | 28 | .732673 | .900990 | .707447 | .893617 | .952128 |
| 3 | 12 | .728713 | .895050 | **.734043** | **.904255** | .952128 |
| 3 | 28 | **.738614** | .899010 | .728723 | **.904255** | .952128 |
| 5 | 12 | .718812 | .899010 | **.734043** | .893617 | .952128 |
| **5 (train selected)** | **28** | .732673 | **.902970** | .723404 | .882979 | .952128 |
| 10 | 12 | .718812 | .887129 | .718085 | .882979 | .936170 |
| 10 | 28 | .728713 | .891089 | .712766 | .872340 | .936170 |
| Authors' TF-IDF | n/a | .609901 | .855446 | .585106 | .819149 | .867021 |

**[FACT]** The dev-hindsight higher Recall@5 of weight3/terms12 or weight3/terms28 is **.904255** versus .882979 for the train-selected weight5/terms28, a difference of only 4/188 dev evidence claims. Its train Recall@5 is lower (.895050 or .899010 vs .902970). Weight10 reduces dev Recall@10 to .936170 while providing no top-one improvement. These are evidence of **train/dev hyperparameter variance**, not justification for selecting the dev-hindsight winner.

**[INFERENCE]** Conventional lexical retrieval remains a strong baseline, but there is no demonstrated robust advantage among these nearby BM25 configurations. Choosing a few percentage points from the best dev row would introduce the same outcome-selection bias this round was designed to prevent.

**[NEXT FALSIFIER]** Compare training-selected hybrid BM25+dense candidate routing or field-aware source selection on an additional genuinely independent corpus, at matched source-index bytes, retrieval latency, model rerank cost and relevant-source recall. Avoid claiming strong retrieval novelty for title weight sweeps.
