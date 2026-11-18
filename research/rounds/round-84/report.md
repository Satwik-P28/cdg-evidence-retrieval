# CDG Round 84: Prospective BM25 Title Boost and Query-Budget Ablations on SciFact

**Date:** 18 November 2026. **Status:** implementation, offline regression tests and pinned real SciFact train/dev retrieval workflow submitted; measured results pending successful exact-head GitHub Actions. This is an ablation of conventional retrieval, not a new BM25 algorithm or independent RAG generation.

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
