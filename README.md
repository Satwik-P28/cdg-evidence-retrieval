# CDG | Evidence-Preserving Retrieval and Versioned Compressed Storage

**Research prototype · Python / SQLite FTS5 / Zstandard / content-addressed storage · November 2026**

CDG began with a question about retrieval-augmented generation: *why can a system retrieve individually relevant passages yet fail to collect the complete evidence needed for an answer?* I explored multihop document selection, lossless source-byte reconstruction, and the physical cost of accessing evidence. The most mature outcome is an experimental **versioned source store** that couples immutable search-index segments with content-addressed, independently compressed frames and generation-bound evidence receipts.

The central engineering problem is a constrained trade-off between **evidence coverage, read amplification, write amplification, index size, historical retention and source consistency**. The prototype is not a production RAG model and has not demonstrated end-to-end answer-quality superiority.

## Selected results, with the comparison boundaries

| Experiment | Observed result | What it does and does not establish |
| --- | --- | --- |
| **Incremental historical storage, R32** | **1,174,447 B** retained vs. **4,602,314 B** for full rebuilds across 11 versions (**74.5% less**); **24.5 ms** vs. **475.6 ms** median update time (~**19.4x** speedup) in the replacement regime | Actual local SQLite/Zstd results, 5 reports and 10 source updates. Control deliberately rebuilds all segments. **Not** an optimized incremental SQLite comparison, robust latency study or large-scale result. [Report](research/rounds/round-32/report.md) · [results](experiments/round-32/results.json) |
| **Avoiding duplicated indexed plaintext, R30** | At 512-byte frames, source-store footprint fell from **291,755 B to 197,547 B (32.3%)** | Measured on 5 internal reports using SQLite's existing contentless FTS5 feature. Retrieval outputs matched across 18 local queries. **Not** novel indexing. [Report](research/rounds/round-30/report.md) · [results](experiments/round-30/contentless_all_results.json) |
| **Multihop evidence discovery, R25** | Complete annotated supporting-document recovery at top 2: **46/100** with exact title-mention expansion vs. **33/100** with BM25; at top 5: **84/100 vs. 62/100** | 100 curated HotpotQA-derived questions, each with supplied candidate documents; independent JavaScript analysis. The Python full-corpus reproducer has **not** been independently run. Conventional iterative retrieval, **not** original algorithmic novelty. [Report](research/rounds/round-25/report.md) |
| **True byte reconstruction and version checks, R28–R32** | Regression-tested exact UTF-8 reconstruction, corrupted-frame rejection, stale-receipt refusal and old-reader snapshot pinning | Local correctness under defined trust assumptions. **Not** proof of origin authenticity, crash-safety across all failures, or source entailment. [Snapshot implementation](experiments/round-31/snapshot_store.py) · [CAS implementation](experiments/round-32/incremental_store.py) |

**A negative result worth retaining:** R29 showed that reading fewer compressed bytes does **not** necessarily mean a lower measured query time. Smaller line-aligned frames improved read traffic but lost to larger frames in the observed warm timing. [R29 report](research/rounds/round-29/report.md).

## System design

```text
source version ──► UTF-8 byte spans ──► independently compressed Zstd frames
      │                                        │
      ├──► contentless FTS5 index segment      ├──► SHA-256 content address
      │                                        │
      └──► source descriptor + frame map ◄─────┘
                       │
             immutable generation manifest
                       │
         pinned reader + version-bound receipt
                       │
            exact source-byte reconstruction
```

A receipt binds `(generation, source digest, byte start, byte end)`. A new reader rejects old-generation receipts, while a reader pinned to a historical generation can still return its original bytes. Unchanged source versions reuse their search indexes, and identical frames reuse compressed payloads. This is **single-writer local experimental software**, without signed provenance, ACL enforcement, multiwriter transactions or lease-aware garbage collection.

## Where to start

- **[Jane Street FOCUS project brief](docs/focus-project-description.md):** short and long application-ready descriptions, validated accomplishments and interview explanation.
- **[Technical evidence dossier](docs/focus-technical-dossier.md):** design choices, measurement contracts, failure modes and source-specific proof map.
- **[Round 32 implementation](experiments/round-32/incremental_store.py)** and **[tests](experiments/round-32/test_incremental.py):** most mature versioned-storage prototype. [Benchmark](experiments/round-32/benchmark.py), [results](experiments/round-32/results.json).
- **[Round 30 implementation](experiments/round-30/integrated.py):** experimental FTS5/source-link/compressed retrieval integration.
- **[Research record through Round 32](research/living-record-rounds-19-32.md):** extensive exploration and failed hypotheses. Historical source ZIPs and early notebooks remain available.
- **[Provenance and missing artifacts](docs/provenance.md)** · [Research methodology](docs/methodology.md) · [Licensing notes](LICENSE-NOTE.md).

### Reproduction starting points

Python 3.10+, SQLite with FTS5, and `libzstd` are needed for the Round 32 prototype. In a clean checkout, run:

```bash
python -m unittest discover -s experiments/round-32 -p 'test_*.py' -v
python -m unittest discover -s experiments/round-31 -p 'test_*.py' -v
```

A full Round 32 numerical reproduction also needs the five historical Round 24–28 report inputs identified by SHA-256 in `experiments/round-32/results.json`. The current root `MANIFEST.json` is a **historical snapshot** and does not list every later round. The repository is a research archive, not a fully automated CI-validated release.

## What I learned

The most promising gains came from questioning system boundaries, not piling on retrieval heuristics. I rejected diversity-only search as a bridge solution; distinguished source consistency from semantic truth; found that the original SQLite schema stored redundant plaintext; and discovered that straightforward immutable snapshots incurred full-rebuild write amplification. The next fair comparison is **custom content-addressed segments against a strong incremental SQLite/FTS5 baseline**, followed by an end-to-end source-grounded QA evaluation on independently held-out questions. If the simpler design matches CDG on quality and total cost, it should replace it.

**Status:** independent research and iterative prototyping with model-assisted tooling and analyses, including separately executed connected-data studies. No peer-reviewed publication or claimed state-of-the-art result. For a statement-by-statement provenance audit, see the technical dossier and individual round reports.

## Round 33: complexity-aware evidence cover and Riemann-prime negative control

The Riemann Hypothesis and P versus NP remain unsolved. Known NP-hardness of the smallest grammar problem, weighted set cover, and resource-bounded compression motivate **bounded evidence-cover optimization with shared physical-frame costs** rather than claiming a universal optimal compressor. In **300 controlled synthetic seven-facet instances** (100 each of independent, shared-frame, and clustered-bridge configurations), marginal-cost greedy yielded mean cost ratios **1.1073× / 1.0844× / 1.0459×** against exhaustive optimal selection; worst observed ratios were **2.3608× / 1.6627× / 1.7437×**. These are known-label synthetic tests, **not actual RAG accuracy**. A separate negative control compressed five real technical reports with independent Zstandard frames: a rotating prime-sized schedule retrieved **879.92 B** mean compressed data per sampled two-span query, versus **873.32 B** for fixed 509-byte frames; no improvement was found. This is **not a test of RH**. Five local correctness tests passed. [Full Round 33 report](research/rounds/round-33/report.md), [optimization lab](experiments/round-33/selection_lab.py), [results](experiments/round-33/results.json), [prime control](experiments/round-33/prime_results.json).


## Round 34: verified acquisition versus optimizing a faulty evidence model

A cross-disciplinary literature audit considered hypergraph retrieval, adaptive cost-aware RAG, calibrated citation risk, adaptive submodular covering, database selective late materialization, lossy prompt compression and versioned storage. On **300 seeded synthetic small-instance evidence-cover problems**, marginal-cost greedy achieved **143/300** exact-optimum solutions versus **292/300** for deletion plus bounded two-out/two-in local repair. However, when candidate-to-evidence facet predictions were perturbed by 15% independent label flips, true complete-evidence recovery was **114/300 greedy** versus only **99/300 repaired**. A deliberately **idealized** post-read facet verifier that saw true facet labels only for inspected candidates recovered 300/300, paying increasing acquisition cost under noise. These are synthetic mechanism and upper-bound tests, not genuine semantic entailment, QA accuracy, or an empirical verifier. **Six local regression tests passed**. The research decision is to prioritize validated source-grounded verification and calibrated abstention over stronger optimization of an untrusted evidence model. [Research map and report](research/rounds/round-34/report.md), [experiment](experiments/round-34/planner_lab.py), [results](experiments/round-34/results.json).



## Round 43 continuation: fairer FTS5 baseline (research branch)

Round 43 audits a **no-op edit generator flaw** in Round 42 and introduces a separate conventional control using stable integer line IDs and a contentless FTS5 index. It compares the old global+CAS (B) and hybrid (D) to row-ID-based incremental global FTS5 (P) across append, replacement, insertion, and deletion edits. The code includes generation-by-generation byte-reconstruction and search-parity checks. **Three focused local unit tests passed; the 48-scenario benchmark has not yet been executed or published.** There is no new speedup claim. See [Round 43 report](research/rounds/round-43/report.md), [experiment](experiments/round-43/lab.py), and [tests](experiments/round-43/test_lab.py).

**Research decision:** validate the full grid, independently held-out data, and a stronger historical SQLite strategy before claiming an adaptive storage-policy advantage. The older README results above remain scoped to their original rounds.


## Continued experimental research: Rounds 44–53 (November 17, 2026)

The cumulative research record is now [Rounds 33–53](research/living-record-rounds-33-53.md), with original experiment code and CI checks retained per round.

**Evidence boundaries and useful findings:**

- **R44:** Global FTS5 with current-only index is faster to update and smaller to retain in tested workloads, but historical searches require expensive index reconstruction. Snapshot selection depends on historical-query rate.
- **R45:** Standard BM25 retrieved all 260 easily structured TimeConflict record queries without gold record IDs. This does not establish semantic or independent QA correctness. Temporal interval semantics remain a bottleneck.
- **R46–47:** Exact authentic-revision reconstruction under content-defined compressed frames plus compact manifests. Gear512 + compressed binary metadata retained a 17,769-byte archive on this one uv README history, smaller than a whole-document Zlib archive, but **not** smaller than the Git pack/index control. Historical query read patterns and manifest parsing matter.
- **R48:** FTS5 retrieved 276 exact historical source line spans, bound to versioned source hashes. The historical search index was 196,608 bytes, much larger than the compact archive, exposing indexing as a larger storage target.
- **R49:** Reducing FTS5 detail from full to none/columnsize=0 cut historical index bytes from 196,608 to 131,072 but lost phrase search and BM25 ranking parity. This is **not** a safe drop-in replacement.
- **R50:** Two-tier current-full/historic-slim indexing retained ranked/phrase query results on the tested dataset and reduced persistent index to 155,648 bytes, but uncached ranked queries cost 927 microseconds median versus 27.4 microseconds for full history.
- **R51:** Historical LRU caches improve repeated access but may exceed the conventional full index in total memory. Their value depends on query distribution.
- **R52:** Replacing per-query scans of entire source-span maps with batched row-ID retrieval reduced the median cached hot-trace query from 178 to 31 microseconds (capacity four) with unchanged measured SQLite cache pages. Batched lookups are now the experimental default.
- **R53:** The original Python 100-question HotpotQA-derived multihop retrieval reproducer now independently agrees exactly with the earlier JavaScript analysis on BM25/bridge/MMR complete-document results, paired successes and top-two supporting-sentence recovery. This is a reproducibility improvement, not a new held-out test or model-level QA claim.

**Run tests:** A GitHub Actions CI workflow executes earlier Python and Node regression suites, R42–R53 correctness checks, and reproducible comparison scripts. Raw benchmark data are uploaded as workflow artifacts. Reported microsecond numbers are short warm CI samples, not independent performance replications or device I/O measurements.

The next publication-grade step is independently held-out real RAG/temporal QA with complete, externally judged evidence and a fair end-to-end index-plus-archive-plus-verifier cost baseline. No state-of-the-art, new compressor, or full-RAG superiority claim is warranted by the existing results.


## Independent evidence and heterogeneous storage experiments, Rounds 54–59

The latest cumulative record is [Rounds 33–59](research/living-record-rounds-33-59.md). Every experiment has its own code, regression suite, result report and GitHub Actions numerical artifact.

- **R54, source retrieval across data splits:** 512 SHA-locked official HotpotQA distractor development questions, frozen R25 title-link bridge recovered all supporting documents in 212 questions at top 2 versus BM25 168; at top 5 it recovered 439 versus BM25 345. Precomputed title-link indexing gave the same rankings; all 512 sample records had valid support annotations.
- **R55, compression integrated with indexed evidence:** On 128 dev questions, the source-sentence FTS5 index occupied 708,608 bytes. Whole-source Zlib was smaller than content-defined source archives; FTS top-two sentence pruning recovered only 79 complete support sets compared with 107 when full selected gold documents were retained.
- **R56–57, sentence budget experiments:** Title-mention sentence priority was not consistently best. A global at-most-ten-sentence budget with rank-frontloaded assignment gave favorable exploratory recovery and compressed traffic on two sets of 128.
- **R58, heterogeneous archive:** Online greedy selection charging both stored bytes and predicted read traffic selected whole Zlib for most independent sources and content-defined frames for a subset. On 1,288 real source blobs the mixed archive occupied 487,779 bytes versus 511,165 for always whole Zlib, with mean sampled compressed span traffic 324 vs 361 bytes. This is a small, domain-specific systems result and does not establish a new codec.
- **R59, confirmation:** On the remaining 256 dev questions, frontloading recovered 187 complete annotated support sets versus recycled uniform 183, paired exact p=0.618. The primary superiority hypothesis was **not confirmed**. Recycling unused sentence slots is a safe monotonic coverage mechanism under a fixed upper budget, subject to additional reading/model cost.

**Reproduction:** The held-out evaluation workflow verifies original input SHA-256, runs R54–R59 test suites and benchmarks, and uploads raw results. The corpus is licensed CC BY-SA 4.0 and downloaded transiently rather than redistributed. The broad research workflow continues checking prior rounds.

**Research state:** Component-level exact source-byte storage, retrieval and selective evidence coverage have been evaluated. End-to-end factual support, hallucination mitigation, independent external-domain generalization, crash-safe history, and full latency/index/token Pareto gains remain unproven. Do not advertise this repository as a production research breakthrough or a new general compression algorithm.


## Conventional compression controls and mixture shift: Rounds 60–61

[Updated cumulative CDG record through Round 61](research/living-record-rounds-33-61.md). R60 and R61 are **experimental source-storage component studies**, not new lossless compression algorithms or end-to-end RAG gains.

- **R60, strong prior-art baselines:** Using the same 1,288 genuine uv README and HotpotQA source blobs as R58, compared Zlib6 against Zstandard 3/9 and a real aggressively packed Git repository. Whole Zstd3 archive 531,600 bytes, Zstd3 online read-weighted 508,271 bytes, frozen Zlib6 online read-weighted 487,779 bytes; Git pack+idx 494,194 bytes and full Git metadata 635,473 bytes. Git retains commit and tree information, so the archive byte boundary is not logically identical to a custom CAS manifest. Zstd loses on this short-document mix, not universally.
- **R61, mixture falsification:** Held-back dev source paragraphs (same domain) mixed with 0, 3, 6, or 12 related README revisions under 96, 384 or 1,024 independent documents. Frozen R58 online read-weighted layout reduced logical compressed partial-read bytes in 12/12 scenarios but reduced retained archive size in only 6/12. With few or no related revisions, the mixed archive became larger than whole Zlib. The gain depends on source relatedness and mix, so no universal policy is promoted.
- **Reproduction:** The CDG strong compression workflow pins Python zstandard==0.25.0 and runs exact SHA-and-byte restoration checks, realistic Git pack reconstruction, Zstd codecs, mixture stress tests, and uploads JSON results.
- **Open requirement:** Independent versioned source families, controlled physical I/O and cold cache, full index/citation metadata and reader/verifier token budgets, and matched Git/Zstd semantics must be evaluated before claiming end-to-end efficiency.


## Independent source history transfer and similarity falsification: Rounds 62–63

The updated [CDG cumulative research record through Round 63](research/living-record-rounds-33-63.md) documents two tests beyond uv's original source history.

- **R62, independent histories:** Pinned source README revisions from Ruff (12), Transformers (12) and Flask (7), tested with 0, 128 and 512 independent source paragraphs under the frozen R58 adaptive policy. At 512 independent docs, archive savings versus whole-Zlib were **20.4% for Ruff** and **21.6% for Transformers**, but a **1.9% storage penalty for Flask**. These outcomes strengthen the observation that historical redundancy controls whether content-defined source framing is worthwhile.
- **R63, label-blind relatedness:** Tested online 96-byte fingerprint overlap and prespecified .20/.50/.80 gates without gold labels. A permissive gate nearly eliminated Flask's archive penalty but suppressed useful framing in the two larger histories. **No fixed overlap threshold was promoted.** Reported archive bytes exclude the detector's own RAM and building costs.
- **Reproduction and provenance:** The independent history CI workflow obtains content from immutable upstream Git commits, verifies SHA-256 and Git blob checksums, records each sampled file revision, and publishes only compact metrics and hashes. Upstream file bytes are not redistributed. Prior compression, history and retrieval suites remain active.

These are experimental and established-codec systems comparisons, not a novel codec, semantic verification, complete RAG pipeline or demonstrated reduction in hallucinated answers. The next falsifier is cost-accounted, source-family-sensitive migration or direct reuse-cost estimation, ideally on additional untouched version histories.


## Bounded migration and incremental metadata experiments: Rounds 64–65

See [the updated cumulative CDG research record through Round 65](research/living-record-rounds-33-65.md).

- **R64, retroactive source migration:** When a second sufficiently overlapping version arrives, a first version can be re-encoded from whole Zlib to shared content-defined frames with CAS reference-count repair. All exact source bytes were verified on Ruff, Transformers, Flask and two additional pinned version families, **vLLM and Pydantic**. Relative to frozen R58 ungated routing, the final 512-independent-source archives were ~1.7–1.9% smaller in four of five histories, but **0.5% larger in vLLM**. Plain whole-Zlib remained smaller for Flask. No unconditional migration policy is promoted.
- **R65, metadata journal and checkpoint:** Full compressed manifest rewrite after every source update caused 5.1–5.8 MB of cumulative encoded metadata writes under 500-plus-source ingestion. Length-framed checksummed event logs and every-128-event checkpoints reduced *encoded metadata writes* by ~97.5% against this naive full-rewrite baseline, while increasing persistent metadata ~6–9% and requiring ~1.5–1.9 ms warm cold-replay CPU. These are user-space write counts, **not** fsync-durable SSD measurements or a claim of novelty.
- **Reproduction:** The CDG migration GitHub Actions workflow executes both focused unit test suites and the full live SHA-pinned independent revision-history benchmarks, and uploads compact JSON research artifacts. External README and HotpotQA original sources are downloaded transiently.
- **Next falsifiers:** Compare a conventional durable SQLite WAL or log-structured store, crash safety and physical write amplification, followed by a unified evidence retrieval plus factual claim support evaluation with exact token/index/archive costs.


## From byte-exact evidence to actual answer correctness: Rounds 66–68

The latest [CDG cumulative record through Round 68](research/living-record-rounds-33-68.md) includes a SHA-pinned pretrained reader, fixed dataset partitioning, model-level answer metrics and separate checks for source-byte citations versus annotated evidence completeness.

- **R66, independent paragraph reader:** 64 fixed HotpotQA distractor dev questions, frozen BM25/bridge/random top-2/top-5 retrieval, two reversible source archive layouts and FTS sentence selection. With top-5 full paragraphs, title-bridge found all annotated supporting documents in 51/64 versus 44/64 for BM25, **but both readers achieved 11/64 exact answer matches** under a shared pretrained SQuAD2 extractive model.
- **R67, one 384-token context plus source-evidence oracle:** Top-5 title-bridge retrieved 51 complete document sets but preserved all annotated gold sentences inside its *actual bounded model input* on only 38/64 questions. The joint reader correctly answered 8/64 vs BM25 7/64. A separately labeled, annotation-informed oracle input of exact gold support yielded 23/64 correct, illustrating substantial reader/synthesis failure even under perfect source selection.
- **R68, frozen answer-level holdback:** Applied both unchanged readers to distinct fixed SHA-selected development questions at indices 448:512. Across **128** total questions at top 5, BM25 vs bridge complete source sets were **88 vs 106**, per-document answer exact matches **31 vs 33**, and joint-context exact matches **22 vs 24**, paired exact **p=0.50**. The gold supporting-sentence oracle correctly answered 49/128. **No reliable answer-quality improvement was established.**

The pinned reader is **deepset/tinyroberta-squad2** commit **12b287c9df677e28b07f0a023850dba68c997dbf** (CC BY 4.0). CI installs pinned PyTorch CPU, Transformers and tokenizers; source SHA references, reader output/citation validation, model input-token counts, source index/archive footprints and inference wall time are recorded. Source paragraphs and model weights are downloaded only transiently.

**Scientific limits:** The source pool is closed-world HotpotQA distractor dev, and the model is a small single-paragraph extractive SQuAD2 reader, not a multihop-trained generator. Literal source-span citation is not semantic entailment or proof of causal provenance. Strong relevant prior work already evaluates evidence granularity and answer quality in this dataset; these experiments are diagnostics for how much the current CDG components affect actual answers, not a novel RAG benchmark victory. Next priorities are stronger multihop readers, independently annotated hallucination/claim grounding (RAGTruth), and a full indexed-storage plus inference cost frontier.


## Human-labeled response grounding and source-only limits: Rounds 69–71

[Updated cumulative CDG research record through Round 71](research/living-record-rounds-33-71.md) and individual R69, R70 and R71 reports add a separate human-annotated QA faithfulness benchmark.

- **R69, RAGTruth QA test labels:** 768 generated responses from 128 SHA-pinned source groups. Original human-annotated unsupported positives were 138/768. A content-overlap warning had 87.7% recall but 367 false alarms among 630 apparently clean responses (precision 24.8%). Adding name/number novelty reached 98.6% recall but 590 false alarms. **Simple lexical source overlap is not a reliable semantic verifier.**
- **R70, training-only warning calibration:** 4,892 quality-good QA training examples, followed by 131 good responses from 22 previously unexamined QA test source groups. Maximum sentence novelty calibrated for at most 10% observed train false alarms detected **0/22** human positives. The novel-sentence fraction detected **1/22** with five false alarms; the original sensitive warning detected 20/22 but generated 51 false alarms. **A lexical cutoff cannot provide acceptable specificity and sensitivity simultaneously in these controls.**
- **R71, source-only information limit:** Among 900 responses to 150 fixed QA sources, 94 distinct source groups contain both human-labeled supported and unsupported responses. Any deterministic warning system reading *only the source content/identity* must misclassify at least 150/900 examples, even given an oracle source-label majority. Exact source archive receipts were verified across 300 full and 600 partial reads. Whole Zlib archive 96,202 B, gear512 117,721 B, FTS5 index 163,840 B.
- **Reproduction:** A dedicated RAGTruth QA workflow pins upstream RAGTruth source blobs by Git SHA and downloads them temporarily, runs all R69–71 tests and source-group heldout analysis, and uploads compact numerical outputs. No original source passages or generated responses are redistributed.

**Critical limits:** Human RAGTruth labels are source-faithfulness annotations, not a definitive universal truth oracle. These rounds evaluate existing model outputs and do not generate new CDG answers or prevent hallucinations. Citation byte integrity is provenance, not entailment or causal reliance. Next research should benchmark a strong response-conditioned NLI/verifier under human-label and compute constraints, then integrate the actual answer reader and versioned archive into one total-cost frontier.


## Frozen, response-conditioned NLI semantic verification: Round 72

The [cumulative research record through Round 72](research/living-record-rounds-33-72.md) now contains a pinned pretrained **general-purpose SNLI/MultiNLI NLI** control against RAGTruth human-labeled QA and previously unexamined Summary test source groups.

- **Model:** cross-encoder/nli-deberta-v3-xsmall at immutable Hugging Face SHA a150876415327c80daeff35ca6f68f5ed8cf5c24 (Apache-2.0), **not fine-tuned on RAGTruth**.
- **Workload:** 141 quality-good RAGTruth test responses, 760 sentence-like hypotheses and 2,273 real model forward pairs. A strict 384-token NLI context, first source window vs lexical best vs top-three windows, fixed entailment threshold 0.50. Actual input 426,627 tokens and 251.993 s shared CPU forward inference.
- **Negative result:** 31/31 human-positive unsupported responses were flagged but **108/110 human-negative responses were also flagged** under best-window/top-three NLI (F1 0.365). The original lexical warning baseline flagged 27/31 positives with 48/110 false alarms (F1 0.509). More NLI evidence windows barely changed its judgments and added compute.
- **Prior-work distinction:** ModernBERT LettuceDetect is specifically trained on RAGTruth and already reports strong RAGTruth in-domain results. It must not be counted as independently validating transfer. The generic NLI source-window experiment does not demonstrate semantic reliability, end-to-end RAG improvements or hallucination mitigation.
- **Next tests:** Train-only NLI risk calibration on source-disjoint QA and a new Data2txt test family, then materialize the exact source windows through cryptographically verified compressed archives while charging all window/index, model-token, inference and storage costs.

The new round's [research report](research/rounds/round-72/report.md), five unit tests, immutable model lock and dedicated GPU-free GitHub Actions workflow reproduce the figures. No original passages or generated responses are committed.


## Research Rounds 74–77: Cross-task grounding, counterfactual sources and strong trained baseline

[CDG cumulative research ledger through Round 79](research/living-record-rounds-33-79.md) links each executable report, actual model task and negative outcome.

- **R74, QA-to-Data2txt transfer:** Same pinned generic pretrained R72 NLI, thresholds fitted only on QA train human-negative answers (32 source groups, 190 responses), confirmed on 16 disjoint Data2txt test groups (96 responses with 61 human-positive). Frozen 0.50 threshold rejected **all 96**, and positive prevalence makes its response F1 look good at .777. QA-train 10% FPR target gave 25.7% Data2txt FPR and 19/61 true positives for top3 max risk. 7,550 actual NLI pairs and 1,552,487 input tokens. **Calibration did not transfer.**
- **R75, evidence substitution:** On the same 96 Data2txt responses, replace the actual source with the nearest different source before NLI. Only **54/96** response weakest-claim scores preferred the actual source; mean actual-minus-alternative weakest-claim entailment difference **+.00023**, source-group bootstrap 95% interval **[-.00589,+.00629]**. Mean across claims rose +.12649 for actual evidence, showing how a single low-scoring claim can mask source sensitivity. Swapped data are not independently truth-labeled and the result is not counterfactual factual correctness.
- **R76, strong trained prior-art comparator:** Published RAGTruth-trained LettuceDetect ModernBERT, immutable model SHA and MIT license, **149.6M** parameters, on R72's original 141 QA/Summary test responses. Combined response TP14 FP16 FN17 TN94, response F1 **.4590**, human character-level span F1 **.4054**, 179.992s cumulative CPU inference. Its RAGTruth training and differing model/context budgets preclude independent-transfer and matched-performance claims.
- **R77, original prompt formatting:** With identical model and 141 response strings, using original RAGTruth generator prompts instead of reconstructed passages changed **5** predictions. F1 increased from .4590 to **.4839**, but source-group bootstrap F1 change interval **[-.02297,+.08602]** includes zero. Input framing matters slightly in this sample, but no reliable improvement was established.
- **Reproduction and scope:** R74–R77 code and independent GitHub Actions model/inference workflows pin upstream Git blob source and model revisions. The source passages, human labels and original generated responses remain with upstream authors and are not redistributed. Full numerical results, source-group isolation, cpu inference and model token-cost limitations are retained in separate reports. No new end-to-end hallucination prevention or novel lossless codec is claimed.

The research priority is now atomic fact/claim verification over **actual retrieved, versioned and byte-verified evidence**, compared with trained prior-art checkers and conventional storage at matched end-to-end compute and false-acceptance costs. Do not use source receipts, NLI confidence, or high F1 on imbalanced labels as unqualified proof of trustworthy answers.


## Research Rounds 78–79: Verified archive-fed semantics and sensitivity limits

The [cumulative living research record through Round 79](research/living-record-rounds-33-79.md) consolidates the evidence and decisions; the [Round 78](research/rounds/round-78/report.md) and [Round 79](research/rounds/round-79/report.md) reports preserve reproducibility and limitations.

- **R78 archive-fed trained detector:** 24 exact original SHA-bound source blobs, 141 QA/Summary generated responses, 48 full-source and 282 response source receipts verified. Original-versus-reconstructed pretrained LettuceDetect character masks match on **141/141** responses; response F1 unchanged at **0.45902**. Whole-Zlib source archive 28,398 B versus gear512 35,437 B; mean per-response logical compressed activation 1,154 vs 1,347 B. Warm in-memory receipt timing favors gear, not proof of cold SSD advantage. Source identity was supplied by the benchmark, not retrieved.
- **R79 same-answer evidence swaps:** SHA-frozen, task-matched lexical nearest/farthest alternative sources trigger **111/141** response warning decision changes for each alternative rule. Mean mask disagreement is **78.68%** near and **85.80%** far, yet original/alternative sources are *not* independently labeled support counterfactuals. Their Jaccard similarities are both low, and model CPU costs differ greatly. No hallucination reduction or reliable near/far response-level discrimination was demonstrated.

**Next:** independently labeled, length-controlled atomic evidence edits and full-corpus retrieval, combined with conventional baseline storage and trained model inference costs. No source byte receipt or source-swap sensitivity alone establishes causal correctness of RAG answers.


## Original-corpus integer coding and physical index studies: Rounds 107–110 (November 23, 2026)

These are **experimental docID posting-list studies**, not new general compressors, changes to SQLite FTS5 native segments, or evidence of improved RAG answers.

- **R107:** First reversible dyadic-scale BARM-R/BARM-G pilot. Original checked-in Markdown report FTS5 logical posting proxy: 44,662 B BARM-R vs 53,279 B framed varint over 35,387 posting entries; [report](research/rounds/round-107/report.md). These were *logical streams*, not physical index savings.
- **R108:** SHA-locked original **QASPER DEV** and **SciFact** studies, predeclared term-frequency strata, 1,950 hash-selected terms per corpus. BARM-R used **130,129 B** vs framed varint 187,580 B and reference partitioned Elias-Fano 150,961 B for 144,717 QASPER postings; **110,142 B** vs 149,854 B and 116,932 B for 116,186 SciFact postings. [Report](research/rounds/round-108/report.md), [QASPER metrics](experiments/round-108/results-qasper.json), [SciFact metrics](experiments/round-108/results-scifact.json). The partitioner is an *in-sample dynamic-programming reference*, not production PEF; StreamVByte is scalar Python, not SIMD.
- **R109:** Materialized **independently seekable SQLite BLOB posting stores** using the *same selected term sets* and identical schema, counting actual term B-tree and page overhead. Physical BARM-R stores: **212,992 B** QASPER and **155,648 B** SciFact vs varint **307,200 B** and **237,568 B**, and EF reference **241,664 B** and **188,416 B**. All 384 sampled term lookups per codec matched original FTS5 docID results; 128 AND/OR pairs matched. [Report](research/rounds/round-109/report.md), [QASPER](experiments/round-109/results-qasper.json), [SciFact](experiments/round-109/results-scifact.json). **Not** feature-equivalent to FTS5: positions, term frequencies, phrase search and BM25 are absent.
- **R110:** Same-wire packed-bit BARM-R reference decoder with 68 tests and repeated CPU-only original-corpus batches. BARM decoding improved from **224.84 to 106.00 ms** on QASPER and **185.80 to 86.95 ms** on SciFact (2.12–2.14x), **but remained roughly four times slower than scalar varint**. [Report](research/rounds/round-110/report.md), [QASPER](experiments/round-110/results-qasper.json), [SciFact](experiments/round-110/results-scifact.json). No native SIMD, controlled cold I/O, independent-machine timing or end-to-end latency claim.

**Current decision:** BARM is a storage-efficient experimental codec for the selected docID-only posting workloads, with a material decoding CPU penalty. Do not promote to the CDG default before full-index positional/ranking semantics, optimized production codecs, actual random-seek p95, complete source+index+version-storage accounting, and independent held-out workload tests.
