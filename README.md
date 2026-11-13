# CDG: Source-Aligned Evidence Retrieval and Compression

**Research notebook and reproducible experiments, November 2026. Latest research: Round 30.**

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

| HotpotQA full-context mention expansion, Round 25 | On 100 HotpotQA-derived questions (curated upstream subset), complete supporting-document recovery @2 was BM25 33/100, exact-title mention expansion 46/100, MMR 32/100; @5 BM25 62/100 versus expansion 84/100. | Real source text, **closed-world candidate contexts**; title links are a conventional retrieval baseline. No semantic answer verification, SSD/codec measurements, or independently held-out improvement. Python unit tests pass, but full-data cross-language reproduction is pending. |

**Current verdict:** promising systems hypothesis; no verified held-out, end-to-end improvement over strong retrieval and storage baselines. The primary next step is a real, inference-time dependency predictor, with fixed costs and source-grounded answer evaluation.

## Repository guide

- [`research/living-record-rounds-19-30.md`](research/living-record-rounds-19-30.md): dated integrated working record. Earlier rounds are described in the record but not all source reports are accessible in this export.
- [`research/rounds/`](research/rounds/): recovered round-specific archives, source code, notes and artifacts. Some early source packages include previous-round snapshots.
- [`experiments/`](experiments/): directly accessible Round 20–23 scripts and machine-readable outputs.
- [`source-archives/`](source-archives/): exact downloaded historical ZIP packages preserved separately for auditability. Do not confuse archive existence with successful reruns.
- [`docs/methodology.md`](docs/methodology.md): evidence hierarchy, reproducibility and pitfalls.
- [`docs/research-decisions.md`](docs/research-decisions.md): negative results, hypotheses and next milestones.
- [`docs/provenance.md`](docs/provenance.md): dataset identities, missing sources, licensing concerns and source audit.
- [`MANIFEST.json`](MANIFEST.json): SHA-256 hashes of included files.

## Reproducing selected experiments

The source tree includes Python scripts with different dependencies and entry-point conventions. Some historical scripts expect the directory structure of their archived package or require networked datasets. Start by inspecting `experiments/round-20/`, `experiments/round-21/`, `experiments/round-22/`, `experiments/round-23/`, then read the corresponding appendices and run only those tests whose inputs and environment you can supply. A syntax/JSON integrity audit was performed on this export, **not** a complete rerun of every experimental result.

## Round 26: source-aligned frame activation

On the same 100-question HotpotQA-derived subset, five-document bridge retrieval contained every annotated supporting sentence in 84/100 cases when full source paragraphs were retained. Selecting only two query-BM25 sentences per source reduced complete evidence presence to 69/100; retaining additional observed bridge-mention sentences recovered 74/100. At **128-byte independent frames**, modeled mean raw source bytes activated were 2,722 for full sources versus 1,946 for top-two-plus-link. At **2,048-byte frames**, both activate 2,722 bytes in this short-document corpus. This is **not** a measured compressed SSD advantage: index/mention-sidecar costs, actual corpus-compressed frame bytes, and end-to-end QA remain unmeasured. Eight local tests passed for UTF-8 span offsets and lossless independent zstd/zlib frames on toy inputs. [Read the Round 26 report](research/rounds/round-26/report.md), [experiment code](experiments/round-26/frame_probe.py), and [model outputs](experiments/round-26/results.json).

## Round 27: actual Zstandard physical-access benchmark

A local source-archive experiment used **five CDG research reports** (90,163 original bytes), independently compressed frames, and two seeded synthetic workloads of 250 two-span requests each. **This is not HotpotQA or SSD read timing**. At 512-byte frames, line-aware framing used 64,722 archive+modeled-table bytes vs 62,338 for fixed frames, but retrieved 540 vs 855 compressed bytes per request on the whole-line workload. A subspan control showed 519 vs 684 compressed bytes/request. Seven local regression tests passed, including byte-for-byte UTF-8 reconstruction. These observations are a conventional source-layout trade-off, not a novel compression or RAG superiority result. [Round 27 report](research/rounds/round-27/report.md), [benchmark](experiments/round-27/storage_bench.py), [whole-line results](experiments/round-27/results.json), [subspan results](experiments/round-27/results_subspan.json).

## Round 28: real file-backed compressed frame retrieval

The prototype now writes independent Zstandard frames to disk, serializes byte-accurate frame offsets and source versions in SQLite, indexes lines with FTS5, and reconstructs selected original byte intervals with `os.pread`. On **88,679 bytes across five local research reports**, the total physical footprint at 512-byte frames was **291,755 B** (fixed) versus **301,449 B** (line-aligned), including actual SQLite files. On 250 seeded whole-line two-span requests, compressed payload reads averaged **833.9 B** versus **556.8 B** respectively. This decreased compressed read bytes but **did not demonstrate a warm-latency advantage** and used known span coordinates rather than authentic question-driven retrieval. Six local tests passed, including a repaired empty-span regression. See the [technical report](research/rounds/round-28/report.md), [source](experiments/round-28/filebacked_bench.py), [results](experiments/round-28/results.json) and [build measurements](experiments/round-28/build_results.json). This is a physical storage benchmark, **not** a novel compressor or proven RAG improvement.

## Round 29: query-driven retrieval to exact compressed source bytes

The physical benchmark now runs the entire search and source reconstruction path: **FTS5 full-text query → line ID and stored UTF-8 offsets → serialized independent Zstandard frames → file-backed read/decode → exact original bytes**. Five local technical reports (88,679 bytes) and 158 deterministically **source-derived**, label-leaked two-term queries were tested. Exact target-line recovery was **94.3% @3** and **97.47% @5**, with zero byte reconstruction errors. Across 474 warm requests per layout, fixed 2,048-byte frames gave a 126.8 μs observed full p50 versus 140.1 μs for line-aligned 512 B, despite the latter reading substantially fewer compressed bytes. Warm timings lack cold-cache and statistical controls. **This is not independent QA or evidence-completeness validation.** Six regression tests passed. [Technical report](research/rounds/round-29/report.md), [benchmark code](experiments/round-29/retrieval_bench.py), [machine-readable measurements](experiments/round-29/results.json).

## Round 30: contentless search indexes and integrated bridge retrieval

Reviewing the Round 28/29 storage layer revealed duplicated original source text in SQLite alongside Zstandard-compressed source frames. On five research reports (**88,679 bytes**), replacing the uncompressed `lines.body` table with a **contentless FTS5** search index reduced the measured total database-plus-compressed-payload footprint from **291,755 to 197,547 bytes at 512-byte frames (32.3%)**, while preserving the same ranked byte-verified results for 18 local lexical queries. The reduction was **30.8%** at 256 B and **33.4%** at 2,048 B frames. These are established SQLite techniques, **not** a new index algorithm or verified latency gain. A file-backed HotpotQA-shaped FTS5 + title-link baseline and tests were also implemented, but the complete pinned 100-question dataset **was not run through that local physical reader**. A connected GitHub analysis separately reconfirmed 403 exact title links and the prior BM25 33/100 versus title expansion 46/100 complete two-document retrieval result; do not combine those two separately executed experiments as an end-to-end score. **13 local regression tests passed.** [Report](research/rounds/round-30/report.md), [integrated prototype](experiments/round-30/integrated.py), [real storage measurements](experiments/round-30/contentless_all_results.json), [connected-source analysis](experiments/round-30/source_analysis.json).

## Research status and next falsification test

Round 23 introduced exact source-ID and version/scope guarded bridge lookup as a simple baseline. See [`research/rounds/round-23/report.md`](research/rounds/round-23/report.md) for the experiment and failure-injection analysis.

**Round 24 real-question diagnostic:** On 1,000 HotpotQA-derived questions using a gold-derived pool of 1,975 document titles, BM25 recovered both annotated titles at k=2 on 122/803 bridge questions versus 190/197 comparison questions. MMR did not help. This is not a standard HotpotQA benchmark and contains title-pool label leakage. [Read the study](research/rounds/round-24/report.md).

Round 25 uses authentic source paragraphs to test exact-title mention expansion as a strong *simple* baseline. See [the report](research/rounds/round-25/report.md), [code](experiments/round-25/bridge_probe.py) and [aggregate results](experiments/round-25/results.json). The simple baseline improves complete supporting-document recall on a small curated subset but does not establish a novel algorithm or total-cost advantage.

The central test is whether predicted evidence dependencies improve *complete-witness recall per total cost* on independently authored held-out multihop queries. Compare against BM25, hybrid retrieval, cross-encoder reranking, set-level selectors and simple expand-on-failure policies. Measure complete support, false citations, final answer accuracy, prompt tokens, compressed storage including indexes, cold/warm p50/p95 reads, and calibration under family shift.

If the graph controller loses to a simpler evidence-expansion baseline at matched costs, remove it. The goal is a reliable mechanism and a defensible empirical result, not an increasingly elaborate architecture.

## Intellectual honesty

This is ongoing exploratory research. Synthetic controls, oracle upper bounds, cost proxies, exact-quote alignment, and real held-out evaluation are different classes of evidence. They are labeled separately throughout. Research reports and scripts may include prior model-assisted analysis; authorship and execution history should be described accurately in applications. Code and text here should not be represented as independently peer-reviewed or accepted research.

See [methodology](docs/methodology.md) and [provenance](docs/provenance.md).

**Integrity note:** `MANIFEST.json` is a historical snapshot and does not enumerate all later research rounds. Git tree object identities verify the committed files; use `git ls-files` and SHA-256 locally if a fresh content-hash inventory is required. The Round 25 source data itself is not committed.
