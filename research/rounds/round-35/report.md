# Round 35: Classical Hybrids for Quantum-Inspired CDG Research

**Date:** 2026-11-16. **Status:** bounded exploratory literature analysis and two executed, reproducible classical experiments. No quantum hardware used; no performance claim about authentic RAG or production compression.

## 1. Research-state ledger

- **Established and implemented in CDG:** independently compressed Zstandard frames, SQLite FTS5, generation-bound source receipts, exact UTF-8 reconstruction, content-addressed frame reuse, small-instance synthetic evidence-cover testing. Rounds 25–34 establish limits of structural support and prediction/model error. See the committed round reports for exact caveats.
- **Unverified:** end-to-end fixed-generator QA benefit over strong open-source retrievers, real held-out evidence prediction, robust semantic verifier, cold-storage latency and optimized update comparisons.
- **Open theoretical/algorithmic issue:** minimize cost of an **observed and semantically valid** evidence witness under partially known candidate-to-facet links. The graph-selection objective is not necessarily submodular when facets are complementary and frame activation costs overlap.
- **Engineering limitation:** prior fast update result compares with deliberate full rebuild and thus is not a general systems performance advantage.
- **Next opportunity:** combine an ordinary classical verified retrieval pipeline with a planner that may use low-rank, annealing-inspired, or probabilistic subcomponents. Charge every build, index, read, verification, and abort cost.

## 2. Prior art and exact transfer conditions

1. **Liu, Bian, Meng, Zhang, Dahlsten (2024), *Information compression via hidden subgroup quantum autoencoders*, npj Quantum Information**, https://doi.org/10.1038/s41534-024-00865-2. Proves a quantum **oracle-query** advantage for sources with a hidden subgroup structure. Its quantum oracle access and data promises cannot be assumed for CDG plain-text histories. Candidate classical transfer: detect periodicity/equivalence transformations, explicitly code the transform, exact residuals and metadata, and evaluate against LZ/Zstandard/CDCs.
2. **Harvey, Yeung, Meichanetzidis (2025), *Sequence processing with quantum-inspired tensor networks*, Scientific Reports**, https://doi.org/10.1038/s41598-024-84295-2. Classical tensor-network sequence models can impose structure on learned representations. Candidate transfer: approximate dependency-score or embedding indexes; not the authoritative original source bytes.
3. **Oseledets (2011), *Tensor-Train Decomposition*, SIAM J. Sci. Comput.**, https://doi.org/10.1137/090752286. Tensor-train low-rank arithmetic is a classical baseline; include low-rank parameter, query and build costs and compare with sparse postings, SVD, PCA, quantization.
4. **Tang (2019), *A quantum-inspired classical algorithm for recommendation systems*, STOC**, https://arxiv.org/abs/1807.04271. The efficient sampling-access assumptions supply a classical alternative to some quantum-ML claims. Index and sampler construction cannot be free.
5. **Golovin & Krause (2011), *Adaptive Submodularity: Theory and Applications in Active Learning and Stochastic Optimization*, JAIR**, https://doi.org/10.1613/JAIR.3278. Approximation guarantees require structural assumptions; CDG evidence AND-dependencies and shared frames can violate them.
6. **Tishby, Pereira, Bialek (1999), *The Information Bottleneck Method***, https://mlanthology.org/misc/1999/tishby1999misc-information/. Task-specific approximate representations could preserve answer-relevant signals but require an authoritative lossless source and empirical entailment validation.
7. **Xia et al. (2016), *FastCDC: a Fast and Efficient Content-Defined Chunking Approach for Data Deduplication*, USENIX ATC**, https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia. Strong non-quantum baseline for version-stable block boundaries.
8. **Schumacher (1995), *Quantum coding*, Physical Review A**, https://doi.org/10.1103/PhysRevA.51.2738. Quantum state coding is not a direct lower bound or achieved compression rate for a classical byte archive.
9. **Djidjev (2023), *Quantum Annealing with Inequality Constraints: The Set Cover Problem***, https://doi.org/10.1002/qute.202300104. Formalization of constraints and penalty methods are transferable, but classical MIP/CP-SAT, exact search, and local heuristics remain mandatory baselines.
10. **Accuracy and performance evaluation of quantum, classical and hybrid solvers for the Max-Cut problem (2026)**, https://doi.org/10.1007/s11128-026-05263-5. Demonstrates solver-dependent tradeoffs on QUBO/Max-Cut; not evidence of an advantage for CDG.

**Coverage note:** This is a ten-source primary-source shortlist, **not** the 30-paper comprehensive review requested in the broader research brief. Further citations require verification rather than invented bibliography entries.

## 3. Classical combinations and classification

| Mechanism | Classical partner | Output / correct role | Prior-art class | Priority |
|---|---|---|---|---|
| Ising/QUBO | Branch-and-bound, local swap, simulated annealing | Bounded candidate evidence-cover decisions | Established combination applied to CDG | High |
| Hidden subgroup idea | KMP/periodicity, suffix arrays, Zstd, delta + exception channel | Exact structured-version reconstruction | Classical symmetry coding | High on specialized data |
| Matrix product states / tensor trains | SVD, PCA, sparse inverted indexes | Approximate candidate/facet prediction, never source truth | Existing low-rank models | Medium |
| Quantum-walk-style propagation | Personalized PageRank, best-first / beam search | Explore graph candidates, checked against simpler traversal | Existing graph ranking | Low / conditional |
| Amplitude-estimation intuition | Classical confidence intervals, sequential testing | Decide whether to inspect more evidence | Established statistical procedures | Medium-high |
| Quantum information bottleneck analogy | Classical information bottleneck, rate-distortion | Optional task-aware lossy retrieval metadata | Known information-theoretic framing | Medium-high |
| Quantum error correction analogy | Checksums, redundancy, authenticated manifests | Detect byte corruption / distinguish authority | Analogical, **not quantum correction** | Keep conventional approach |
| Quantum sampling | Classical norm sampling, sketching, leverage scores | Reduce approximate candidate-index construction | Dequantized linear algebra | Conditional |

## 4. Complete small-instance constrained formulation

Let `x_i` choose evidence candidate `i`, `y_f` activate frame `f`, `a_{ji}=1` if a **validated** candidate `i` covers facet `j`, and `b_{fi}=1` if candidate `i` requires frame `f`.

Minimize `sum_i t_i x_i + sum_f c_f y_f` subject to `sum_i a_{ji} x_i >= 1` for each required facet `j`, and `x_i <= y_f` for every `b_{fi}=1`.

This contains weighted set cover as a special case. For a QUBO with binary slack representations `s_j >= 0`, add penalties

`A * sum_j (sum_i a_{ji} x_i - 1 - s_j)^2 + B * sum_{(f,i): b_{fi}=1} x_i (1-y_f)`.

Choose enough slack bits to represent `0 .. N-1`, and choose `A` and `B` larger than an explicit known feasible upper bound on the nonnegative unpenalized objective. This sufficient but conservative bound ensures that a globally minimized invalid assignment cannot beat any feasible assignment, when integer squared violations are >=1. Quadratization introduces extra variables and dense couplings; this is **a mathematical encoding**, not an experimentally validated efficient solver. The number of variables and couplers, problem embedding and practical penalty precision must be measured before hardware comparisons.

If `a_{ji}` are merely predictions, satisfying these constraints need not provide **true evidence**. This is the failure exposed by CDG Round 34. Inference-time verification and abstention are independent contracts.

## 5. Executed experiment A: classical global-local optimization

Run `python hybrid_lab.py --output results.json --instances 100 --steps 1000`; then `python -m unittest -q test_hybrid.py`.

100 deterministic synthetic instances, 12 evidence candidates, seven required facets, eight possible shared frames. Compare marginal-cost greedy, greedy+bounded two-out/two-in repair, simple **classical simulated annealing** (1000 steps), annealing+repair, and complete enumeration of all 4095 nonempty selections.

| Method | Optimal instances | Mean cost / exact optimum | Mean runtime ms |
|---|---:|---:|---:|
| Greedy | 48/100 | 1.08323 | 0.082 |
| Greedy+repair | 95/100 | 1.00214 | 0.946 |
| Classical annealing | 93/100 | 1.00376 | 2.857 |
| Annealing+repair | 98/100 | 1.00106 | 3.594 |
| Exhaustive exact | 100/100 | 1 | 6.506 |

**[NEGATIVE]** The hybrid obtains three more optima than plain repair but takes substantially longer. These data do not justify applying annealing to every CDG query. A trigger rule must be evaluated on held-out instances and charged its prediction overhead. All synthetic facet labels are known and assumed correct. The annealer uses no quantum dynamics.

## 6. Executed experiment B: classical hidden symmetry versus standard coding

A deliberately elementary exact period representation stores a 9-byte header plus the shortest exact period. Compare the resulting bytes with `zlib` level 9 and `bz2`, with a one-byte raw fallback. Four seeded generated sequences are used, **not a real-version compression benchmark**.

| Source | Input | Period bytes | zlib-9 bytes | Best available candidate |
|---|---:|---:|---:|---|
| 16-value repeating sequence | 8,192 | 25 | 54 | Period 25 |
| Same sequence with 16 mutations | 8,192 | 8,201 | 102 | zlib 102 |
| High-entropy pseudo-random bytes | 8,192 | 8,201 | 8,203 | Raw fallback 8,193 |
| Repeated textual line | 7,800 | 61 | 99 | Period 61 |

The raw fallback includes a one-byte method selector. Method identification and decoding metadata for the other independently compared codecs are **not fully normalized**; comparisons are exploratory. A real model selector needs uniform framing, per-source costs, random reads, and a residual/exception channel.

**[NEGATIVE]** Tiny mutations destroy exact periodicity, and a naive exact-period representation can expand incompressible input. A periodic + sparse-exception encoder is the appropriate next classical test; compare it against Zstd and FastCDC on real document histories with metadata counted.

## 7. Fifteen hypothesis register, grouped by shared testbed

Each entry is a **hypothesis**, not a validated novelty claim. The decisive benchmark should be a frozen held-out retrieval workload and a live, byte-exact source store.

| ID | Hybrid hypothesis | Falsifier / stop rule |
|---|---|---|
| H35-01 | Classical annealing + repair improves hard evidence-cover instances | No cost-matched improvement over tuned repair or CP-SAT |
| H35-02 | Trigger annealing only when a greedy certificate is weak | Trigger overhead exceeds acquisition savings |
| H35-03 | Greedy + lower bounds reduces unnecessary global search | No query-time savings after bound computation |
| H35-04 | Learned facet probabilities plus exact verification reduce false completeness | Simple verified expansion dominates |
| H35-05 | Adaptive greedy under valid independence assumptions gets provable bounds | Empirical dependencies violate adaptive submodularity |
| H35-06 | Tensor-train compressed dependency scores retain coverage | Sparse or low-rank matrix baseline cheaper at equal recall |
| H35-07 | Norm-sampled candidate sketches reduce index preparation time | Preprocessing dominates or recall degrades |
| H35-08 | Low-rank retrieval guides exact byte acquisition efficiently | Exhaustive inverted-index retrieval is faster |
| H35-09 | Symmetry + sparse exceptions compress document histories | Zstd/CDC beats total archive footprint or update time |
| H35-10 | Repeated edit transformations give an exact residual code | Transform descriptions cost more than saved payload |
| H35-11 | Cross-version delta plus authenticated receipts reduce retained history | Source offset maps and provenance dominate |
| H35-12 | Walk-inspired scores improve bridge discovery | PageRank/beam search dominates |
| H35-13 | Classical information-bottleneck indexes reduce prompt tokens safely | Qualified evidence statements are lost |
| H35-14 | Sequential evidence testing enables safe abstention | Shifted verifier fails the claimed risk bound |
| H35-15 | Workload-aware frame layout + verified acquisition improves total costs | Plain seekable Zstd and SQLite dominates |

**Top five for implementation:** H35-04 (verification), H35-09 (exact symmetry + exceptions), H35-01 (adaptive optimizer, conditional), H35-06 (tensor scores on larger graph data), H35-15 (physical retrieval co-design). Most are **new combinations of prior art**, not novel algorithmic results.

## 8. Next five rounds

- **R36**: Validated, frozen real-multihop source benchmark through physical reader; stop if no verified evidence gain versus FTS5 + simple expansion. Requires official annotated dataset and fixed generator if answer quality is assessed.
- **R37**: Classical period+residual+Zstd+FastCDC on at least 100 genuine source versions. Stop if storage/update Pareto frontier is dominated. Requires corpus histories and cold/warm profiling.
- **R38**: CP-SAT/branch-and-bound versus local repair versus several fully classical annealers on at least three problem families. Stop hybrid if quality-at-time dominated. Requires solver versions, seeded 25+ repetitions, held-out instances.
- **R39**: Tensor-train/low-rank versus sparse/SVD/quantized dependency index, including build/update/query/storage costs and facet recall; stop if classical sparse baseline dominates. Requires dense enough data to justify the representation.
- **R40**: Integrate the strongest surviving pieces with verified, calibrated evidence inspection and immutable receipts; stop and simplify if conventional verified iterative retrieval is Pareto-superior. Requires latency + quality + storage + update full accounting.

## 9. Publication and negative results

This package is a **preliminary technical report** with two bounded classical experiments, not a full 30-paper survey, a quantum advantage demonstration, or a publishable end-to-end retrieval improvement. A workshop systems note becomes credible only after a held-out and optimized-baseline comparison. The present data indicate that the most valuable near-term research is a conventional classical verified acquisition layer with optional conditional optimization, not an actual quantum pipeline.

The correct interpretation of the original prompt's quantum research agenda is: borrow problem representations and approximation techniques where useful, but retain classical indexes, exact source receipts, strong baselines, and full cost accounting. A simulated annealer is not quantum annealing; an approximate tensor representation is not a lossless archive; and a quantum HSP oracle advantage is not a practical classical compression result.
