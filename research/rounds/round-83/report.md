# CDG Round 83: Expert-Annotated SciFact Retrieval and Grounding Baselines

**Date:** November 18, 2026. **Status:** official upstream source lock, regression tests and complete pretrained-model / 5,183-source retrieval evaluation **passed** in GitHub Actions 44250358050. Initial source provenance run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44249807526 .

## The independent question

Rounds 80–82 used 220 related synthetic cases with template-derived labels. Does a published fact-checking verifier reproduce meaningful claim-support performance on *expert-annotated scientific evidence*, after actual retrieval rather than simply a chosen gold document? For each published verifier, what happens when the evidence source is selected by conventional retrieval rather than an oracle?

This uses **SciFact** (Wadden et al., EMNLP 2020, https://aclanthology.org/2020.emnlp-main.609/) and its original reference retrieval code. SciFact's claims and rationales are expert annotated, though existing pretrained checkpoints may have encountered the widely public benchmark and the SciFact dev labels are not an untouched new population. The experiment does not represent the original SciFact leaderboard or independent publication novelty.

## Verified immutable upstream source provenance

The dataset release was downloaded only from the official AI2 SciFact S3 location and a cryptographic lock now **rejects changes in any byte** even if the upstream latest alias moves.

| Source asset | Frozen SHA-256 | Bytes |
| --- | --- | ---: |
| Official data.tar.gz release | 11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be | 3,115,079 |
| data/corpus.jsonl | b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62 | 8,307,875 |
| data/claims_dev.jsonl | 86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217 | 65,007 |

The official release provides **5,183** scientific abstract sources and **300 dev claims**, of which **188** have at least one annotated gold evidence abstract. There are **209 annotated claim-document pairs** across SUPPORT 138 and CONTRADICT 71. Do not pretend the 112 claims without evidence annotations have documented negative proof against every possible abstract.

Claim/evidence annotations CC BY 4.0 and source abstracts ODC-By 1.0, per official allenai/scifact/LICENSE.md. No original annotations or abstract text will be committed or published by CDG.

## Conventional retrieval controls

- **Authors' SciFact TF-IDF:** reproduce their released TfidfVectorizer(stop_words='english', ngram_range=(1,1)), document = title concatenated with abstract sentences, rank cosine query similarity with their original argsort reverse tie convention. Use *all* 5,183 documents. No labels enter retrieval or rankings.
- **SQLite FTS5/BM25:** independent conventional index over title and abstract, fixed weights title 5, body 1. Claim query uses at most first 28 distinct content terms combined by OR. No tuning on dev outcomes. Charge persistent FTS5 bytes.
- **Metrics:** gold evidence *document* recall@1/@3/@5/@10 among the 188 dev claims with existing annotated evidence, separated by support/contradict source labels. This is acquisition, not hallucination classification.
- **Source store:** reconstruct every selected oracle and retrieval result from SHA-bound compressed whole-source and gear512 CAS archives. The arrays use document-slot IDs, not historical generations. Charge all retained archive bytes, logical activated compressed bytes and warm-memory read time. No true SSD cold I/O or fsync is claimed.

## Verification controls and critical gold-label boundary

Select **60** claim-document cases, 30 SUPPORT and 30 CONTRADICT, SHA-sorted from the dev gold pairs with unique claim IDs and unique source document IDs. Score the same public MiniCheck-DeBERTa, FactCG-DeBERTa and generic NLI xsmall checkpoints used in R80 under their original frozen model input rules and 0.50 support cutoffs.

Compare three source routes for the **same claim**: gold annotated abstract (nondeployable oracle), TF-IDF top-one abstract, and FTS5 top-one abstract. The model sees the entire byte-verified title + abstract source. Cost all three routes' model pair tokens and CPU time.

**Crucial label integrity:** SciFact's human label SUPPORT/CONTRADICT applies only to a specific annotated claim-document pair. If a retriever returns a *different* document with no SciFact annotation for that claim, a prediction of unsupported must NOT be scored as a correct rejection of the original CONTRADICT label. Only report conditional annotated-source confusion where the returned document has its own human SUPPORT/CONTRADICT annotation. Report acceptance rates of other retrieved sources descriptively, not correctness.

A source selection can miss relevant evidence, and a verifier can misinterpret correct evidence. These must be separately measured. Document label accuracy should never be conflated with claim truth or correct evidence citation.

## Promotion and stop rules

1. No evaluation until all official tar and member SHA-256 hashes match the immutable lock. Test the offline tar schema and corruption contracts.
2. Both conventional retrieval controls must run on the entire source corpus, not just 60 gold sources. Report indexed sizes and source recall.
3. All 60 SHA-selected source-unique gold examples are scored by the three models. Distinguish oracle from real retrieval and do not manufacture negative labels for wrong-source results.
4. If MiniCheck or FactCG underperforms NLI in this different domain, preserve the negative finding, including model size, context/truncation, and CPU work; do not retune a threshold on the test set.
5. Do not claim end-to-end RAG improvements: no generator, externally sourced responses or hallucination mitigation intervention. Any compression efficiency claim must beat conventional whole-source + TF-IDF/FTS5 at matched retrieval and model cost.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-83 -p 'test_scifact_data_probe.py' -v
    python -W error::ResourceWarning -m unittest discover -s experiments/round-83 -p 'test_scifact_eval.py' -v
    python experiments/round-83/scifact_eval.py --out experiments/round-83/ci-results.json

GitHub Actions workflows: .github/workflows/cdg-r83-scifact-source.yml and .github/workflows/cdg-r83-scifact-real.yml . Executed retrieval and model results are recorded below from exact-head run 44250358050.


## Executed results from upstream-locked real SciFact (CI 44250358050)

**[FACT]** Model-forward and retrieval test workflow succeeded. Official release SHA-256 \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\` verified. All 5,183 corpus abstracts and 300 development claims were used for retrieval. Recall denominator is **188 SciFact dev claims with at least one expert-annotated evidence document**, not every abstract or a zero-evidence case treated as negative.

### Gold evidence-document retrieval

| Retriever | Recall@1 | Recall@3 | Recall@5 | Recall@10 |
| --- | ---: | ---: | ---: | ---: |
| Authors' TF-IDF replica | **110/188 = 0.58511** | 140/188 = .74468 | 154/188 = .81915 | 163/188 = .86702 |
| Conventional SQLite FTS5/BM25 | **136/188 = 0.72340** | 156/188 = .82979 | 166/188 = .88298 | 179/188 = .95213 |

Stratified gold evidence recall@1, TF-IDF versus FTS5: SUPPORT **75/124 (.60484)** vs **93/124 (.75000)**; CONTRADICT **35/64 (.54688)** vs **43/64 (.67188)**.

**[FACT] Retrieval/index costs:** TF-IDF reproduced authors' source string and \`TfidfVectorizer(stop_words='english', ngram_range=(1,1))\` with original descending tie ordering. It used a 37,455-term vocabulary and **5,623,728 sparse matrix bytes** excluding the vocabulary object; build-plus-query time **1.029 s**. FTS5/BM25 used a fixed title/body weighting 5:1 and OR of up to 28 claim terms, with **14,778,368 B persistent index** and **0.870 s** to build and serve the 300 queries. These measurements do not have matched index accounting or independent performance repetitions; no causal speed ranking is claimed.

### Published verifier baseline on 60 annotated gold source/claim pairs

The sample was locked to **30 expert-labeled SUPPORT + 30 CONTRADICT**, with 60 distinct claim IDs and 60 distinct evidence source IDs (cohort digest \`72b5e02303d7357dd7b49fde35ba10a7b06bba30d765e3c44e908ce0c23f1804\`).

| Published checker | TP | FP | FN | TN | Balanced accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Generic NLI xsmall | 4 | **0** | 26 | 30 | **0.56667** |
| MiniCheck DeBERTa-Large | 17 | 4 | 13 | 26 | **0.71667** |
| FactCG DeBERTa-Large | **18** | 2 | 12 | 28 | **0.76667** |

These judgments refer only to **the original annotated gold evidence document**, not automatically to any retrieved top-one document. On the 60 selected claims, **33** TF-IDF top-one and **39** FTS5 top-one claim/doc pairs had a human annotation for the selected document; predictions on the remaining source pairs are NOT valid false-positive/false-negative labels.

**[FACT] Source archive/cost:** compressed full-corpus source+manifest byte count was **3,909,759 B whole-source zlib6** versus **4,791,255 B gear512** against **7,792,860 B** uncompressed original text. There were **180 selected route reads per layout**, each byte verified. Mean logical compressed activation per route **790.622 B** whole versus **917.667 B** gear. Total warm Python reader time **0.02522 s** whole and **0.06623 s** gear, no physical cold SSD I/O.

**[FACT] Model CPU cost:** across all 180 oracle/top-one query variants, general NLI used **53,197 input tokens and 58.673 s**, MiniCheck used **62,883 tokens and 1,108.029 s**, FactCG used **67,647 tokens and 1,180.822 s** including six source-model smoke probes. Models have different parameter count, input limits and prompting, so these are descriptive aggregate wall times, not a controlled throughput claim.

### Experimental interpretation

**[INFERENCE]** Standard FTS5/BM25 retrieval is an important baseline that beat reproduced official SciFact TF-IDF recall@1 by **13.83 percentage points** and recall@10 by **8.51 percentage points** on this dataset, without a novel retrieval model. It uses more stored index bytes under the reported accounting. This suggests source selection is a higher-leverage optimization target than only changing compressed frame size.

**[INFERENCE]** Expert-annotated scientific evidence changes the pretrained verifier ranking observed in the R80 fictional template fixture: FactCG now gives the highest **fixed-threshold gold-document** balanced accuracy of the three tested detectors, but on only 60 examples and with source access oracle supplied. There is no independent model-training exposure guarantee.

**[NOT SHOWN]** General-domain fact checker superiority; inference from a wrong retrieved source is correct; improved generated answers; zero-knowledge source attribution; cold SSD retrieval/throughput advantage; new compression novelty; or end-to-end RAG quality/cost Pareto dominance. Gold annotations are source-specific, and 112 original dev claims have no evidence documents in this release.

CI results: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44250358050 .
