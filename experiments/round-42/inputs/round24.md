# Round 24: Missing Bridges in Authentic Questions, and the Limits of Title-Only Evidence Search

**Date:** 12 November 2026  
**Stage:** Real question text, *restricted label-derived title index*. Not standard HotpotQA, not QA accuracy, and not held-out full-context retrieval.  
**Decision:** Reject diversity-only retrieval as the bridge remedy. Build an actual source-reading bridge acquisition baseline before proposing a graph controller.

## 1. Why I ran this test

Round 22's constructed questions let BM25 recover both relevant paragraphs almost all the time. Round 23 made the opposite case, but used synthetic route identifiers. Neither settled what happens when real questions mention one entity but omit the intermediate entity needed to find the second document.

I chose a deliberately narrow diagnostic with authentic HotpotQA-derived questions and their supporting article titles. The point was to test whether the missing-bridge phenomenon exists before paying for a full model-based stack. I resisted adding a graph predictor because we still do not have a defensible source of inference-time edges.

## 2. Data, provenance, and leakage

Upstream: `surpradhan/rag-benchmark`, revision `c9dc6c350accb3c07629f0465e57d38756a006b0`, `data/processed/dev_questions.json` and `test_questions.json`.

| File | Git blob SHA-1 | Questions |
| --- | --- | ---: |
| `dev_questions.json` | `553bca588cda339747dbdbffd876be4d4c9ef72d` | 500 |
| `test_questions.json` | `b76819e1aaa08f7146f781184cd4f935eef5b79c` | 500 |

Both files contain `question_id`, natural-language `question`, `answer`, `supporting_titles`, `type` and `level`; they do **not** contain source paragraphs, original sentence IDs, authorized source versions, source contents, or physical frame coordinates. There are 399 bridge and 101 comparison questions in the first subset, and 404 bridge and 96 comparison questions in the second. The question IDs do not overlap.

For a consistent candidate universe, I created the **union of supporting titles from both files**, yielding 1,975 distinct titles. **This construction leaks evaluation labels into the index.** No gold titles are passed to the ranker at query time, but the corpus omits ordinary distractor documents and guarantees the target titles are included. It is an engineered closed-world upper-opportunity test, not open-domain retrieval. The upstream file labels `dev` and `test` are publication-defined and should not be mistaken for an untouched official HotpotQA test server split.

The official HotpotQA distractor dev distribution includes per-question paragraphs and sentence-level supporting-fact annotations, which are required for a genuine follow-up benchmark; see https://github.com/hotpotqa/hotpot and https://huggingface.co/datasets/hotpotqa/hotpot_qa . The benchmark dataset is CC BY-SA 4.0. The question-only derivative was inspected through the connected GitHub resource; its bytes were not redistributed in this package.

## 3. Methods

A Unicode alphanumeric tokenizer splits lowercase question/title text. Each distinct title is a pseudo-document. BM25 uses `k1=1.2`, `b=0.75`, positive IDF `ln(1+(N-df+0.5)/(df+0.5))`, title length normalization and deterministic title sorting for ties. The query is only the question text.

The comparison is **MMR** over the first 50 (or fewer) ranked title candidates, greedily choosing 10 titles using `0.75 * normalized_BM25 - 0.25 * max_Jaccard_overlap_with_selected_titles`. Its purpose is to test whether diversity can rescue omitted support titles. It is not a neural, graph, or bridge-conditioned retrieval system.

For k in 1, 2, 3, 5 and 10, record:

* `any`: at least one annotated support title appears in the selected top k.
* `complete`: every distinct annotated support title appears in top k. In these files each question has two titles, so `complete@1 = 0` by construction.

Neither is a supporting-*sentence* metric, semantic entailment metric, answer EM, citation correctness, or token/SSD latency measurement. Gold `answer` labels are unused.

**Execution audit:** All 1,000 question rows and source blob identities were inspected using the GitHub connector; the scoring and counts below were computed in an independent JavaScript evaluation over the fetched text, not by executing the Python reproducer on the full dataset in this offline container. The Python reproduction code and four local standard-library unit tests are included; the latter passed. A networked rerun of `title_probe.py` against pinned upstream bytes is required before upgrading these counts to cross-implementation reproduction.

## 4. Results

### Complete two-title retrieval

| Subset | Type | n | BM25 complete@2 | MMR complete@2 | BM25 complete@10 | MMR complete@10 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dev | Bridge | 399 | 48 (12.0%) | 46 (11.5%) | 101 | 94 |
| Dev | Comparison | 101 | 97 (96.0%) | 96 (95.0%) | 100 | 100 |
| Test | Bridge | 404 | 74 (18.3%) | 70 (17.3%) | 114 | 114 |
| Test | Comparison | 96 | 93 (96.9%) | 93 (96.9%) | 96 | 96 |
| Both | All | 1,000 | **312 (31.2%)** | **305 (30.5%)** | 411 | 404 |

### Any annotated title retrieved

| Subset | BM25 any@1 | BM25 any@2 | BM25 any@10 | MMR any@2 |
| --- | ---: | ---: | ---: | ---: |
| Dev | 408/500 | 426/500 | 443/500 | 431/500 |
| Test | 413/500 | 424/500 | 443/500 | 425/500 |

The high first-title recall and low two-title recall on bridge questions is the important asymmetry. The bridge-vs-comparison gap persists across the two nonoverlapping question files. Diversity modestly increased any-title recall at k=2 on dev (426 to 431) but reduced complete-title recall (145 to 142). A metric that reports only one relevant document can therefore hide failure to reconstruct the full witness.

### Concrete error pattern

For the authentic question "In what country does the director of Shirin in Love, live?", the annotated support-title pair is `Shirin in Love` and `Nazanin Boniadi`. The title `Shirin in Love` is discoverable directly from the query; `Nazanin Boniadi` is not named. The corpus here contains titles only, so the system has no evidence text from which to learn the director relationship. Selecting more lexically diverse titles does not create that missing relationship.

This also limits interpretation: a correct answer could sometimes be given from a single source or background knowledge. Full annotated title coverage is a structural surrogate, **not a proof that both documents are logically necessary**.

## 5. Graph-of-thoughts continuation

### A. A missing bridge is a missing observation, not a ranking defect

An unobserved entity `v` may connect `u` in the question to an answer-bearing source. If the index contains only document titles and `v` does not occur in the query, a lexical scoring policy lacks the information needed to prefer the correct `v`-title over other unrelated titles. Suppressing redundancy or increasing k can change the shortlist, but cannot create evidence about the relation `u -> v`.

This is an identifiability problem under specified observations, not a new information-theory theorem. It motivates measuring **which acquisition actions reveal new conditional information**, rather than asserting that another graph scorer is better.

### B. Bridge extraction creates a causal dependency

A candidate two-step policy is:

1. Retrieve one question-linked source and inspect its sentences.
2. Propose a bridge entity with a source-coordinate receipt.
3. Search for a second source using that bridge entity.
4. Check that the two returned passages jointly entail the question's answer, or abstain.

The act of reading source 1 changes the input to stage 2. This is ordinary iterative retrieval and established prior art. The unresolved CDG question is whether exact source-aligned partial reads and conservative acquisition policies make it cheaper *at matched complete support*.

### C. Evidence is typed by identity, sufficiency and read cost

A typed evidence receipt needs at least `(source_version, canonicalizer_version, span_ranges, retrieval_reason, relation_claim, authorization_scope)`. The relation claim remains fallible even if source bytes and span positions are exact. A hash proves identity, not entailment or independence.

Physical frames add a submodular-looking activation **cost**: reading a second nearby span can be cheap if its frame is already resident. This observation does not make evidence sufficiency submodular. Multi-span AND requirements are often complementary. The correct objective is constrained source-acquisition planning, with confidence and metadata costs included.

### D. No confidence without a real uncertainty model

Round 21 showed that assumed dependency confidence can remain high under a no-signal shift. A bridge extractor must be evaluated on unfamiliar entities, including explicit abstention and false bridge proposals. Avoid tuning confidence cutoffs on the same questions used for evaluation.

### E. The contradiction branch

A source may mention two plausible bridges, use a stale relation, or quote another document. Before accepting a cheap answer, test exact identity, source version, permission and contradiction handling. Round 23 only proves that guards work in deterministic metadata fixtures, not on real conflicting articles.

## 6. Next controlled experiment (Round 25)

**P0: Obtain original HotpotQA distractor dev records with full `context` and `supporting_facts`, verify archive checksum, and freeze a 250–1,000-question predeclared subset.** Use official contexts, not an oracle-derived pool of titles. Measure complete supporting *document and sentence* recall under identical candidate sets.

**P1: Compare** BM25 and BM25+MMR, simple two-hop BM25 with extracted bridge entities, iterative retrieval without an LLM, and a frozen model-based query decomposition baseline. Charge every intermediate retrieval and source materialization. Put strong baselines ahead of a new graph controller.

**P2: Physical cost** use independent compressed frames and seekable Zstd: total archive+index+metadata bytes, p50/p95 cold/warm access, decoder CPU and source-update invalidation. Measure token cost only if an actual frozen reader is run.

**P3: Citations and calibration** evaluate span overlap, source version, missing/contradictory evidence, false-answer rate, abstention, and answer EM/F1 separately.

**Kill criterion:** If a conventional bridge-conditioned retriever recovers complete supporting evidence at the same or lower total resource cost than the CDG joint optimizer, drop the new controller and isolate any defensible contribution to verifiable source receipt / physical layout. If no official source texts are obtained, **do not claim end-to-end performance**.

## 7. Reproduce

```bash
python experiments/round-24/fetch_upstream.py --output-dir data/round-24-upstream
python experiments/round-24/title_probe.py --data-dir data/round-24-upstream --output experiments/round-24/results_reproduced.json
python -m unittest discover -s experiments/round-24 -p 'test_*.py' -v
```

The downloader pins the upstream Git commit and verifies both Git blob SHA-1s. The report's `results.json` contains the original independent connected-resource analysis and must not be silently overwritten to imply a successful local full-data rerun.

**Prior-art collision:** Standard iterative retrieval, IRCoT, IndexRAG, BridgeRAG and graph traversal already address much of the underlying idea. CDG's novelty is still unproven.
