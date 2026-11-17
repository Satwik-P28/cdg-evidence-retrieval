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


## Continued experimental research: Rounds 44–52 (November 17, 2026)

The cumulative research record is now [Rounds 33–52](research/living-record-rounds-33-52.md), with original experiment code and CI checks retained per round.

**Evidence boundaries and useful findings:**

- **R44:** Global FTS5 with current-only index is faster to update and smaller to retain in tested workloads, but historical searches require expensive index reconstruction. Snapshot selection depends on historical-query rate.
- **R45:** Standard BM25 retrieved all 260 easily structured TimeConflict record queries without gold record IDs. This does not establish semantic or independent QA correctness. Temporal interval semantics remain a bottleneck.
- **R46–47:** Exact authentic-revision reconstruction under content-defined compressed frames plus compact manifests. Gear512 + compressed binary metadata retained a 17,769-byte archive on this one uv README history, smaller than a whole-document Zlib archive, but **not** smaller than the Git pack/index control. Historical query read patterns and manifest parsing matter.
- **R48:** FTS5 retrieved 276 exact historical source line spans, bound to versioned source hashes. The historical search index was 196,608 bytes, much larger than the compact archive, exposing indexing as a larger storage target.
- **R49:** Reducing FTS5 detail from full to none/columnsize=0 cut historical index bytes from 196,608 to 131,072 but lost phrase search and BM25 ranking parity. This is **not** a safe drop-in replacement.
- **R50:** Two-tier current-full/historic-slim indexing retained ranked/phrase query results on the tested dataset and reduced persistent index to 155,648 bytes, but uncached ranked queries cost 927 microseconds median versus 27.4 microseconds for full history.
- **R51:** Historical LRU caches improve repeated access but may exceed the conventional full index in total memory. Their value depends on query distribution.
- **R52:** Replacing per-query scans of entire source-span maps with batched row-ID retrieval reduced the median cached hot-trace query from 178 to 31 microseconds (capacity four) with unchanged measured SQLite cache pages. Batched lookups are now the experimental default.

**Run tests:** A GitHub Actions CI workflow executes earlier Python and Node regression suites, R42–R52 correctness checks, and reproducible comparison scripts. Raw benchmark data are uploaded as workflow artifacts. Reported microsecond numbers are short warm CI samples, not independent performance replications or device I/O measurements.

The next publication-grade step is independently held-out real RAG/temporal QA with complete, externally judged evidence and a fair end-to-end index-plus-archive-plus-verifier cost baseline. No state-of-the-art, new compressor, or full-RAG superiority claim is warranted by the existing results.
