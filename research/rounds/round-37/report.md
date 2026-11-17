# Round 37: A Versioned Multihop Retrieval Counterexample and the Limits of Receipt-Based Validation

**Date:** 2026-11-16  
**Status:** executed deterministic synthetic benchmark (900 cases, seven Python regression tests). Isolated research-branch experiment. **Not an authentic HotpotQA run, semantic verifier evaluation, measured compressed I/O, external freshness guarantee, or quantum-computing result.**

## Research question

Does combining version-bound source receipts, iterative title-link traversal and a budgeted structural check improve retrieval of a complete two-document witness when the source collection changes? More importantly, can the same technique distinguish a valid **new fact** from a **newly indexed but stale fact**?

This asks two distinct questions often conflated in RAG implementations:

- **Generation consistency:** did the reader retrieve the bytes from the version it intended? A SHA-256 receipt can help test this under a trustworthy manifest.
- **Temporal/semantic applicability:** do those bytes give the correct fact at the requested time, and do they support the answer? The receipt does not settle this.

A third question is cost: is a verification stage necessary when a simpler title/version lookup already solves the retrieval structure?

## Closest prior work and CDG intersection

- **HoH** (ACL 2025), *A Dynamic Benchmark for Evaluating the Impact of Outdated Information on Retrieval-Augmented Generation*. Outdated evidence coexisting with current material harms both retrieval and generation. https://aclanthology.org/2025.acl-long.301/
- **FRESCO** (Findings EMNLP 2026), *Benchmarking and Optimizing Re-rankers for Evolving Semantic Conflict in Retrieval-Augmented Generation*. Strong rerankers prefer older semantically rich information; recent evidence ranking requires more than lexical relevance. https://aclanthology.org/2026.findings-emnlp.54/
- **Stale-Document Poisoning** (Ahmed et al., 2026, preprint). Outdated retrieved evidence can flip otherwise correct model answers; temporal validity cues affect trust. https://arxiv.org/abs/2609.31342
- **Temporal Validity in Retrieval Memory** (Yadav, 2026, preprint). A subject-relation-object supersession ledger addresses some outdated-fact patterns, but correctness depends on accurately identifying the update relationship. https://arxiv.org/abs/2606.26511
- **IndexRAG** (Findings AACL 2026) and **IRCoT** (earlier multihop retrieval literature): index-time or iterative bridging is established practice. New CDG work cannot claim title-link expansion as novel. https://aclanthology.org/2026.findings-aacl.175.pdf

**Possible narrow addition:** quantify how stale temporal facts, retriever materialization cost, immutable source receipts and a fallible verifier interact under matched total budget, rather than optimizing only document recall or citation string validity. **Novelty unverified.**

## Executed benchmark

`experiments/round-37/benchmark.py` creates 300 query instances per condition. Each contains a `locatorNN` source linking to one destination title with two versions, an unrelated decoy and distractor. A fixture evaluator names the two required documents, but policies do not receive that label. The query parser and deterministic titles make this an intentionally simplified closed-world test. A 3-document selection budget is held constant.

The three conditions are:

1. **Standard:** current source can be found by ordinary lexical ranking.
2. **Shifted:** a lexical-heavy obsolete record outranks the valid current destination; title and version fields are still trustworthy.
3. **Misleading version:** the obsolete record receives a larger version number than the valid record. Thus the metadata order is not a semantic-validity order. This scenario is engineered to expose that limitation, not to estimate its prevalence.

Policies:

- `fixed`: lexical top three.
- `iterative`: lexical start, then title-link expansion.
- `version_filtered`: lexical start, then highest-version linked document.
- `title_version`: parse the source title and follow the link to the highest-version destination.
- `adaptive`: same deterministic title/version lookup plus a charged structural-check step. The check is not a semantic or temporal verifier. It must **not** be described as verifying answer correctness.

All metrics of true completeness are computed *after* selection, using fixture-only labels. `accepted` is a policy decision that can be wrong. `stale_citation` counts selections of the obsolete target without the correct target. The `read_cost` is an integer simulated source-size proxy, and a structural check costs four units. No real `os.pread`, SQLite transaction, zstd decompression, LLM call, or semantic support prediction was benchmarked here.

## Results

| Policy | Standard complete /300 | Shifted complete /300 | Misleading metadata complete /300 |
|:--|--:|--:|--:|
| Fixed lexical top 3 | 300 | 0 | 0 |
| Iterative link | 300 | 0 | 0 |
| Iterative version filter | 300 | 0 | 0 |
| Direct title + highest version | 300 | 300 | 0 |
| Title + highest version + structural check | 300 | 300 | 0 |

The direct title/version policy dominates the added structural-check policy **on this fixture**, because its selections and completeness are identical while the check adds four modeled cost units. The lexical-first version-filtered policy does not recover from a wrong initial lexical head. A direct title lookup does, but uses an artificially reliable query parser and title index. Version recency fails when it is not a reliable proxy for true applicability. All policies can falsely accept a stale evidence pair on the misleading-version regime.

These deterministic extremes are **not representative empirical probabilities**. They are constructive counterexamples to unconditional claims that a version index or a source receipt ensures factual currency. They also show why it is insufficient to report only document recall and byte-perfect citation identity.

## Correctness and test provenance

Seven local `unittest` checks passed, covering determinism, budget constraints, post-selection scoring, receipt-hash presence, shift consistency, the direct-title baseline's cost advantage over an identical structural-check policy, and false-acceptance accounting. These unit tests establish code-level fixture behavior, not independent scientific replication.

Code and outputs are in `experiments/round-37/`. Run:

```bash
cd experiments/round-37
python -m unittest discover -v
python benchmark.py --output results_reproduced.json
```

Python standard library only. Seed: 20261116. `results.json` records first-three selected document IDs and SHA-256 hashes, enabling inspection of deterministic choices without confusing those hashes with authentication.

## Graph-of-thoughts: promising transfers and falsifiers

### A. Temporal databases × evidence receipts

Separate `record_time`, `valid_from`, `valid_until`, and `origin` instead of treating an integer revision as truth. A bitemporal or event-sourced ledger can record a source's publication and applicability intervals. **Counterargument:** validity labels can themselves be wrong or missing, and semantic supersession is difficult. Test with dated official revisions and missing metadata, not with a trusted timestamp oracle.

### B. Query planning × complete evidence witnesses

A version-aware query plan might first resolve entity identity, then temporal applicability, then evidence joins, and materialize source bytes only when needed. **Counterargument:** ordinary title lookup can dominate elaborate planning when identifiers are exact. Compare to indexed SQLite joins and a temporal relational baseline.

### C. Verified stopping × fallible evidence checking

A source receipt only authenticates a specific byte string relative to its manifest. A semantic verifier must assess whether the evidence supports the target answer, including negation, citation context, and update applicability. **Counterargument:** the verifier might fail under shift (Round 36). Report false acceptance and retained correct answers; do not force coverage by using gold facts at inference time.

### D. Compression × temporal-delta structures

Versioned content-addressed frames (Round 32) can potentially store the actual old and new evidence bytes while a bitemporal index holds applicability metadata. This enables a test of both historical correctness and current-answer correctness under identical storage. **Counterargument:** CAS or compression does not change which version should be believed. Charge the entire temporal index, update work and materialized frame bytes.

### E. Classical optimization × uncertainty

Budgeted search over alternative versions is a cost-cover problem only once candidate support probabilities and validity conditions are specified. Annealing and exact branch-and-bound (Rounds 33–35) optimize a surrogate. **Counterargument:** if the temporal support model is wrong, a mathematically optimal acquisition can be wrong faster. Run a calibration and shift study before increasing optimizer sophistication.

## Kill / promotion criteria

**Do not promote** the current fixture to a comparative retrieval-performance claim. It is synthetic and has strong query-title and graph structure engineered into the generator. A next experiment must use authentic dated source revisions and independent evidence judgments, match conventional temporal SQL lookup plus title-link retrieval, report the verifier's error rates, and price retrieval and version-index updates. A candidate policy is useful only if its improvement in *correct supported answers per unit total cost* survives matched conditions and distribution shift.

**Round 38 recommendation:** build a source-revision evaluation with time-bounded questions, ambiguous entity names, incorrectly or incompletely dated updates, contradictory evidence and independently judged validity. Compare lexical top-k, title/version joins, temporal database joins and verified iterative acquisition at equal costs. Run on the actual file-backed versioned store once data licensing and local corpus access are solved.
