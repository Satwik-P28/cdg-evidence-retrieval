# Round 25: Exact-Mention Bridge Expansion on Authentic Multi-Document Contexts

**Research date:** 12 November 2026  
**Status:** Exploratory retrieval-only analysis of 100 HotpotQA-derived questions with authentic paragraph text and annotated supporting sentences. Full-dataset results computed in the connected GitHub JavaScript analysis; seven local Python regression tests passed. The local offline environment did **not** rerun the Python reproducer on the source corpus. No held-out claim, answer-generation evaluation, cold-SSD measurement, compression advantage, or novel-algorithm claim.

## Research question

Round 24 showed that lexical title ranking on actual multihop questions often identifies the first supporting document but not the hidden bridge. This round asks whether **reading the first retrieved paragraph** and extracting references to other candidate-document titles can restore evidence completeness. This is an intentionally *simple established baseline* before constructing a graph controller or source-aligned compressed evidence index.

## Corpus provenance and limits

- Repository: `OpenSPG/KAG`, revision `fdab15b3929d2ee40dfcdd388f90233096a6afc9`.
- File: `kag/open_benchmark/hotpotqa/data/qa_train.json`, Git blob SHA-1 `7dbdf068a437f0577043667ffee3a20f0a602154`.
- **100 questions**, including **78 bridge** and **22 comparison** questions, **994 question-local candidate paragraphs**, **4,139 sentences**, and **229 annotated supporting sentences**. Every cited supporting sentence is available in the supplied per-question context.
- The sample is curated upstream; the selection process and exact relation to the official held-out dev split were not independently audited. It is **not** a randomized, pre-registered test split, and the original official archive has not been matched bytewise.
- Every question has a closed-world candidate pool that includes its gold paragraphs, as in the distractor formulation. Gold titles and sentence IDs are used **only to score** a policy, never to choose its documents. This is not the Round 24 gold-title-pool construction, but it is still closed-world rather than open-domain retrieval.
- Corpus text is not redistributed in this repository. `bridge_probe.py` can fetch the exact pinned raw file with Git-blob SHA verification on a networked machine. Attribution and upstream dataset licensing must be respected.

## Policies and cost boundary

All policies see the same query-local candidate documents. A Unicode-alphanumeric tokenizer and independently implemented positive-IDF BM25 (`k1=1.2`, `b=0.75`) score full document titles plus text. Ties use ascending title; no model training or tuning on external data occurs here.

1. **BM25**: score, rank, take top K.
2. **MMR**: greedily choose at most K using `0.75 * normalized_BM25 - 0.25 * max_document_token_Jaccard_overlap`.
3. **Exact-title bridge expansion**: take the highest-scoring document; for subsequent selections, add a fixed **2.0 BM25-score bonus** to each unselected candidate whose *canonical title* occurs as a **whole token sequence** in any already selected source paragraph. The exact title itself is candidate metadata; the mention must be observed in selected source content. This is ordinary string matching and iterative expansion, **not** natural-language relationship understanding or semantic certification.

**Cost accounting warning:** All candidate texts are scored via a prebuilt BM25-style index, but the prototype's analysis does not charge building or consulting that index or a title-mention lookup. The report's `selected_chars` counts **only the selected source paragraphs** as an output/text-exposure proxy. Lower selected characters do **not** demonstrate lower total I/O, CPU, or wall-clock latency. No physical compression was run in this round.

**Evaluation units:** `complete_docs@K` requires all distinct gold-annotated titles among K selected documents. `any_docs@K` requires at least one. To measure how far sentence filtering can undermine a successful document retrieval, `complete_sentences_topM@K` requires every annotated gold `(title, sentence ID)` to appear after selecting up to M BM25-ranked sentences *per selected document*. The latter is a cheap sentence-level lexical proxy, not a learned claim-conditioned extractor. Evidence presence is not semantic entailment or generated-answer correctness.

## Core observed results

| Policy | Complete docs @2 | @3 | @5 | Mean selected chars @2 | @5 |
|---|---:|---:|---:|---:|---:|
| BM25 | 33/100 | 46/100 | 62/100 | 1,035 | 2,781 |
| MMR | 32/100 | 47/100 | 62/100 | 1,044 | 2,810 |
| Exact-title bridge | **46/100** | **64/100** | **84/100** | 990 | 2,707 |

**Paired @2 outcomes:** both methods succeed on 31 questions, bridge expansion alone succeeds on 15, BM25 alone succeeds on 2, and neither succeeds on 52. Bridge questions gain the most: 26/78 (BM25) to 41/78 (bridge expansion) at K=2; comparison questions fall from 7/22 to 5/22. At K=5, bridge questions go from 46/78 to 64/78, and comparison from 16/22 to 20/22.

This is **13 additional complete-document cases at K=2 and 22 at K=5** in this small and selected sample. These exploratory differences are not a new algorithm claim. No hyperparameter search was performed for the 2.0 mention bonus, but the analysis and policy were constructed with access to the same upstream dataset family, so an independent held-out replication remains necessary.

### Gold sentence coverage is harder

| Policy, K | All annotated sentences present in full selected docs | All annotated sentences among top-2 BM25 sentences per selected doc |
|---|---:|---:|
| BM25, 2 | 33/100 | 26/100 |
| Bridge, 2 | 46/100 | 36/100 |
| BM25, 5 | 62/100 | 50/100 |
| Bridge, 5 | 84/100 | 69/100 |

Thus document-level success materially overstates evidence preserved by a simple sentence filter. Under the stronger `top-3 sentences per selected doc` proxy, bridge expansion reaches 43/100 at K=2 and 79/100 at K=5. Full context access remains essential for some queries, and no semantic verifier was tested.

### Observed failure examples

- **Beneficial bridge:** A question about the man who resigned before the Israeli presidential election of 2000 retrieves the election article. That paragraph mentions **Ezer Weizman**, whose title can be found and used as a second-hop key; BM25 alone ranked a different election.
- **Beneficial bridge:** A question about a film shot near Leland, North Carolina retrieves the location article, then selects **Maximum Overdrive** rather than another document matching the location name.
- **Harmful expansion:** A comparison asking whether Christopher Nolan and Sathish Kalathil are both directors already has both gold titles in BM25's top two. The mention booster instead promotes an additional film referenced in one selected document. This illustrates why expansion should not be blindly used for comparison questions or without a stopping rule.

These examples were inspected as retrieval identities; no generated answer was produced or independently checked for truth.

## Implications for the compression/RAG graph of hypotheses

**H25-A, document bridge as an information-acquisition action.** The hidden second target cannot be reliably recovered from the original query vocabulary alone; a first selected source can reveal a candidate name. This is a standard and empirically useful retrieval operation. It is not a new mathematical result.

**H25-B, source-aligned branch factor.** A full paragraph may contain several names, but only a minority are useful bridges. A future version should produce reversible span receipts for the **sentence that contains each candidate title mention**, then selectively decode adjoining physical frames. Crucially, one cannot claim these cheaper than full document reads until index, mention lookup, frame metadata, and cold-cache costs are measured.

**H25-C, conditional routing.** In this sample, unconditional mention expansion damages some comparison questions. A policy might condition expansion on expected marginal complete-witness gain, predicted question type, remaining budget, and source confidence. A learned gate must be calibrated on held-out data. A hand-labelled question-type gate would contaminate inference and is not acceptable.

**H25-D, structural coverage and semantic support are different types.** Exact title occurrence proves that a sequence of words occurs in a source, not that the source endorses the relationship. Copied quotations, negations, outdated source versions, and forged metadata can all break the intended inference. The next prototype must distinguish `mention_present`, `relation_verified`, `source_current`, and `answer_supported` rather than using a single Boolean evidence flag.

**H25-E, physical savings could disappear.** Whole selected source characters are marginally lower for the bridge policy, but it may pay extra CPU for repeated scoring/inspection, and a compressed frame layout might increase bytes read because of scattered mentions. Database inverted indexes and title-link graphs are mature competing solutions. A new CDG method must compete with precomputed document-link indexes and source-aligned compressed frames under identical complete evidence and real cost constraints.

## Prior-art collision

- Trivedi et al., **IRCoT**, ACL 2023, interleaves reasoning and retrieval: https://aclanthology.org/2023.acl-long.557/ .
- **IndexRAG**, Findings IJCNLP-AACL 2026, precomputes bridge facts during indexing: https://aclanthology.org/2026.findings-aacl.175/ .
- **BridgeRAG**, 2026, bridge-conditioned retrieval: https://arxiv.org/abs/2604.03384 .
- Other practical systems create document-mention graphs and use query-conditioned expansion; the underlying idea is **not new**.

## Reproduction

```bash
python experiments/round-25/bridge_probe.py \
  --data data/round-25/qa_train.json --download \
  --output experiments/round-25/reproduced.json
python -m unittest discover -s experiments/round-25 -p 'test_*.py' -v
```

The pinned upstream SHA-1 check prevents accidental use of a changed corpus. Results embedded in `results.json` were computed with a **separate JavaScript implementation** over the connected source file; executing the Python full-data benchmark on an offline machine remains undone. The seven Python unit tests test local function contracts only. All code is source-available; full-data cross-implementation agreement is a future gate.

## Round 26 preregistration and kill test

1. Obtain the official HotpotQA distractor dev archive and independently verify sample membership, or use a defensible held-out alternative. Freeze a split before tuning.
2. Compare current BM25, exact-title expansion, precomputed title-link graph, IRCoT-style iterative retrieval, dense/hybrid retrieval and an always-read-full-paragraph baseline on identical candidate pools.
3. Implement reversible canonical-to-original offset receipts and independently compressed source frames. Count full archive + index + title-link sidecar + metadata bytes. Measure p50/p95 cold and warm reads, decompression and actual bytes, not just output characters.
4. Evaluate answer EM/F1, source- and sentence-grounded citation precision, complete evidence recall, selective abstention and calibration under source-version drift and authority uncertainty.
5. **Kill or simplify** the proposed joint controller if plain title-link indexing plus seekable frames matches quality/cost. Do not submit a superiority paper on the basis of this round.

**Decision:** GO for the narrow source-mention/physical-frame integration benchmark. NO-GO for an end-to-end or theoretical novelty claim.
