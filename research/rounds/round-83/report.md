# CDG Round 83: Expert-Annotated SciFact Retrieval and Grounding Baselines

**Date:** November 18, 2026. **Status:** locked official upstream dataset SHA source audit passed; full external-data retrieval/model CI submitted and requires actual results. Initial source provenance run: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44249807526 .

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

GitHub Actions workflows: .github/workflows/cdg-r83-scifact-source.yml and .github/workflows/cdg-r83-scifact-real.yml . Full numerical retrieval and model outputs pending exact-head model run.
