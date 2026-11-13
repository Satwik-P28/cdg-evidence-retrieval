# CDG: Source-Aligned Evidence Retrieval and Compression

**Research notebook and reproducible experiments, November 2026. Latest research: Round 24.**

CDG studies a practical mismatch in retrieval-augmented systems: a search result can be relevant without providing a *complete* basis for a claim. Retrieving more context often fixes omissions, but increases tokens, source reads, and decoding work. The working question is whether a system can recover complete evidence more economically by treating source identity, evidence dependencies, and physical storage layout as one optimization problem.

This repository is a record of an investigation, **not a claim of a production system or a published breakthrough**. It includes exploratory analyses, implementations, counterexamples, synthetic controls, measured compression pilots, and decisions to reject approaches that did not improve the relevant baselines.

## What I am investigating

A query can require multiple fragments from one document or several independent sources. If the retrieval policy scores each fragment separately, it may collect a set of individually useful passages while missing a required link. CDG examines whether dependency-aware evidence selection can lower that risk without an unreasonable cost in I/O, decompression, prompt length, or source fidelity.

The architecture deliberately separates four claims that can otherwise be confused:

1. **Source identity:** do the referenced bytes correspond to the intended source version?
2. **Text location:** do exact, possibly discontiguous spans exist in that source after a declared canonicalization transform?
3. **Evidence completeness:** does the selected span set cover the structural evidence requirements?
4. **Semantic validity:** does the source actually support the answer? Exact matching does not settle this.

## Evidence so far

| Study | Observation | Interpretation and limitation |
|---|---|---|
| SciFact corpus, Round 19 | BM25 abstract-only found an annotated source in the top 3 for 159/188 evidence-bearing claims, and top 10 for 174/188. | A strong lexical control; not an end-to-end RAG result. Full-data analysis used connected resources; local reproduction was not completed. |
| Source alignment, Round 19 | 338/338 published rationale quotations were uniquely re-located under declared canonicalization; nine required discontiguous fragments. | Establishes text-location feasibility on the inspected flattened corpus, **not** official raw-byte provenance or entailment. |
| Evidence budget, Round 19 | In a heuristic sentence selection proxy, five BM25-selected sentences contained a complete rationale for 133/188 claims. | More selection budget increases coverage; no general dominance for neighbor boosting. |
| Physical frames, Round 19 | Modeled source-frame reads fell with smaller frames while archive metadata rose. | Model uses source byte lengths and assumed metadata, not SSD timings or compressed archive measurements. |
| Cost-aware alternatives, Round 19 | Oracle selection improved modeled prompt-plus-frame cost by 2.91% at 512 B. | Modest gain, requires gold witness identities unavailable at inference. |
| Dependency signal, Round 21 | Non-oracle *synthetic* matching improves as the noisy signal becomes informative; confidence is badly miscalibrated under shift. | Shows a mechanism to test, not field evidence of better retrieval. |
| Real-text local stress test, Round 22 | BM25 recovered complete constructed evidence pairs in 96% of cases at two paragraphs; facet selection reached 97.6%. | Small and artificially easy benchmark; complex selection barely helps. |
| Bridge/version/scope injection, Round 23 | Guarded lookup returned the stipulated correct answer or abstention on 600/600 generated two-hop fixtures; naive bridge lookup made 360 injected invalid answers. | **Template-based and deliberately adversarially ordered** inputs; metadata lookups were not charged; no naturally authored benchmark or full QA evaluation. |

**Current verdict:** promising systems hypothesis; no verified held-out, end-to-end improvement over strong retrieval and storage baselines. The primary next step is a real, inference-time dependency predictor, with fixed costs and source-grounded answer evaluation.

## Repository guide

- [`research/living-record-rounds-19-24.md`](research/living-record-rounds-19-24.md): dated integrated working record. Earlier rounds are described in the record but not all source reports are accessible in this export.
- [`research/rounds/`](research/rounds/): recovered round-specific archives, source code, notes and artifacts. Some early source packages include previous-round snapshots.
- [`experiments/`](experiments/): directly accessible Round 20–23 scripts and machine-readable outputs.
- [`source-archives/`](source-archives/): exact downloaded historical ZIP packages preserved separately for auditability. Do not confuse archive existence with successful reruns.
- [`docs/methodology.md`](docs/methodology.md): evidence hierarchy, reproducibility and pitfalls.
- [`docs/research-decisions.md`](docs/research-decisions.md): negative results, hypotheses and next milestones.
- [`docs/provenance.md`](docs/provenance.md): dataset identities, missing sources, licensing concerns and source audit.
- [`MANIFEST.json`](MANIFEST.json): SHA-256 hashes of included files.

## Reproducing selected experiments

The source tree includes Python scripts with different dependencies and entry-point conventions. Some historical scripts expect the directory structure of their archived package or require networked datasets. Start by inspecting `experiments/round-20/`, `experiments/round-21/`, `experiments/round-22/`, `experiments/round-23/`, then read the corresponding appendices and run only those tests whose inputs and environment you can supply. A syntax/JSON integrity audit was performed on this export, **not** a complete rerun of every experimental result.

## Research status and next falsification test

Round 23 also introduces exact source-ID and version/scope guarded bridge lookup as a simple baseline. See [`research/rounds/round-23/report.md`](research/rounds/round-23/report.md) for the experiment and failure-injection analysis.

**Round 24 real-question diagnostic:** On 1,000 HotpotQA-derived questions using a gold-derived pool of 1,975 document titles, BM25 recovered both annotated titles at k=2 on 122/803 bridge questions versus 190/197 comparison questions. MMR did not help. This is not a standard HotpotQA benchmark and contains title-pool label leakage. [Read the study](research/rounds/round-24/report.md).

The central test is whether predicted evidence dependencies improve *complete-witness recall per total cost* on independently authored held-out multihop queries. Compare against BM25, hybrid retrieval, cross-encoder reranking, set-level selectors and simple expand-on-failure policies. Measure complete support, false citations, final answer accuracy, prompt tokens, compressed storage including indexes, cold/warm p50/p95 reads, and calibration under family shift.

If the graph controller loses to a simpler evidence-expansion baseline at matched costs, remove it. The goal is a reliable mechanism and a defensible empirical result, not an increasingly elaborate architecture.

## Intellectual honesty

This is ongoing exploratory research. Synthetic controls, oracle upper bounds, cost proxies, exact-quote alignment, and real held-out evaluation are different classes of evidence. They are labeled separately throughout. Research reports and scripts may include prior model-assisted analysis; authorship and execution history should be described accurately in applications. Code and text here should not be represented as independently peer-reviewed or accepted research.

See [methodology](docs/methodology.md) and [provenance](docs/provenance.md).
