# Round 33: Complexity-Theoretic Evidence Cover and a Riemann-Zeta Relevance Test

**Research date:** 16 November 2026  
**Status:** literature synthesis plus two locally executed, controlled experiments. Five Python unit tests passed. **No proof of P vs NP, no progress toward proving RH, no independently held-out RAG improvement.**

## Executive decision

**Keep:** complexity-aware evidence acquisition as a bounded optimization problem, with source-frame union cost and a verifier for complete *structural* evidence coverage. **Reject:** applying the Riemann hypothesis, its zeta zeros, or prime-number frame sizes as a generally useful text compressor. **Do not claim:** any discovered complexity-class lower bound, exact semantic entailment, or verified optimality for real RAG queries.

## 1. Distinguish mathematical partial results from the unsolved targets

### Riemann Hypothesis (RH)

Clay lists RH as unsolved: all nontrivial zeros of the Riemann zeta function are conjectured to have real part 1/2. Platt and Trudgian rigorously verified zeros through imaginary height approximately 3e12, a finite statement, not the full theorem. Mossinghoff, Trudgian, and Yang established explicit zero-free regions near Re(s)=1. Johnston derived finite-range prime-counting bounds from finite verification. The 2026 reported improvement to the proportion of zeros on the critical line is likewise an asymptotic partial result. Newer proposed half-plane exclusions, if correct, are still far weaker than RH and have no verified general-text compression consequence.

Sources: https://www.claymath.org/millennium/Riemann-Hypothesis/ ; https://link.springer.com/article/10.1007/s11139-022-00616-x ; https://doi.org/10.1007/s40993-023-00498-y ; https://www.anthropic.com/research/riemann-zeta

A proof of RH would sharpen prime-distribution estimates. It would **not** directly create short encodings for arbitrary text or show that primes encode unknown structure. A deterministic prime-position schedule is not a content-sensitive chunking function.

### P vs NP

Clay still lists P vs NP as unsolved. The established *smallest grammar problem* is NP-complete and exhibits approximation hardness under P != NP. This directly warns against expecting a universal polynomial-time minimum-size grammar finder for unrestricted documents. A separate line of work connects resource-bounded compression / Minimum Circuit Size Problem lower bounds to complexity separations, but it provides no immediate practical compression algorithm.

Sources: https://www.claymath.org/millennium/p-vs-np/ ; Charikar et al., IEEE TIT 2005, https://doi.org/10.1109/TIT.2005.850116 ; https://people.csail.mit.edu/rrw/MCSP-MKTP-stoc19.pdf ; Aaronson/Wigderson algebrization barrier https://www.scottaaronson.com/papers/alg.pdf

**Do not confuse:** hardness of finding a minimum *grammar* with proof that all compression is impossible, and do not confuse a compact witness with the computational ease of discovering it. Likewise, P != NP alone does not prove one-way functions exist.

## 2. New CDG connection: joint evidence cover with shared frame costs

Let U be required evidence facets, candidates i have known structural coverage sets E_i subset U, token/verification costs t_i, and physical frame sets F_i. Let c_f be estimated read-and-decode cost per frame. The small-instance *optimization oracle* is

    minimize J(S) = sum_{f in union_i F_i} c_f + lambda sum_{i in S} t_i
    subject to union_i E_i = U.

This *contains weighted set cover* when frames are unique to candidates and token cost is zero. Thus it is NP-hard in general, even though verifying the selected cover and its modeled cost is straightforward. The label sets E_i are NOT available at inference time without an imperfect extraction or verification system. A real deployment must estimate and test them, not take this benchmark's ground truth as a free input.

The physical activation cost is a monotone submodular set function, but evidence-completeness is a conjunctive constraint. Shared frames can make marginal acquisition cheap after another span has been read. Common modular-cost greedy approximation guarantees do not automatically carry over to arbitrary shared-frame instances. This is the motivating theoretical nuance, not a new theorem.

Candidate implementations: (A) per-item gain / marginal physical cost greedy, (B) bounded exact search on a top-n pool, (C) frame-aware local exchange and branch-and-bound, (D) a two-stage verifier that checks facet coverage and receipt identity. Exact search is a small-scale upper-performance benchmark, not an inference-time zero-cost oracle.

## 3. Executed experiment A: exact vs greedy controlled evidence cover

Implementation: `experiments/round-33/selection_lab.py`. 300 seeded synthetic instances, 100 each of independent frames, shared frames and clustered bridge-like evidence. Each has 7 required facets, 11 candidate spans, 6 modeled physical frames, randomly sampled frame costs and per-span token costs. A deterministic generator guarantees every facet can be covered. An exhaustive 2^11 enumeration gives the exact optimum, against a greedy policy maximizing uncovered facets divided by incremental union-frame plus token cost. The same declared cost function scores both.

| Family | Instances | Mean greedy / optimum | Worst observed ratio | Greedy exactly optimal |
|---|---:|---:|---:|---:|
| Independent frame assignment | 100 | 1.1073x | 2.3608x | 52 |
| Shared frame assignment | 100 | 1.0844x | 1.6627x | 42 |
| Bridge-like clustered facets | 100 | 1.0459x | 1.7437x | 49 |

No evidence is inferred from genuine text. These are **known-facet synthetic covers** and physical-cost proxies, not RAG answer rates, SSD times, general approximation ratios, or real-world overhead savings. Source-free greedy can perform poorly under a contrived arrangement; an exact optimizer's advantage grows less clear when its own CPU expense is included. Five unit tests passed, including shared-frame deduplication, exact optimum, impossible cover, deterministic seeds and correctness ordering.

The worst observed independent case is not a certified worst-case bound on the algorithm. The 300-case exercise tests the mechanism and yields adversarial regression seeds, not a paper-level empirical advantage.

## 4. Executed experiment B: prime-derived boundaries, a negative control

Implementation: `experiments/round-33/prime_boundary_probe.py`. Five authentic local CDG Markdown reports from Rounds 24–28, 250 identical sampled two-line source requests. Independent frames compressed by libzstd level 3. Fixed 509-byte, fixed 512-byte and rotating prime-length [487, 503, 509, 521, 523] chunks are compared with identical requests. Each scheme's compressed payload and modeled 16-byte per-frame table are counted; no disk timing or FTS index is measured.

| Layout | Compressed payload | Frames | Mean compressed bytes per query |
|---|---:|---:|---:|
| Fixed 509 B | 42,431 B | 127 | 873.32 B |
| Fixed 512 B | 42,369 B | 127 | 877.86 B |
| Prime-length schedule | 42,429 B | 128 | 879.92 B |

This exercise **does not test RH**: prime scheduling is merely an arbitrary deterministic size sequence. It finds no improvement. Prime-number theory could be relevant to highly structured arithmetic datasets using specialized prediction or rank/select methods; no reason presently connects zeta-zero bounds to a general corpus-level representation advantage.

## 5. Connected graph of research directions

- **Complexity -> exact optimization ceilings -> practical search:** if full evidence selection contains set cover, use exact search as an oracle for small candidate pools to quantify heuristic regret; then design parameterized methods keyed to *small required evidence facet count*, not enormous corpus size.
- **Compression -> shared frame activation -> nonadditive query costs:** marginal source reads depend on which frames are resident. Use a conditioned cost estimator; evaluate with actual byte reads and decoding CPU from Rounds 28–30. Fewer bytes is not necessarily lower latency (observed R29).
- **Versioning -> proof-carrying acquisition:** each selected span must carry a pinned source generation and exact byte offset (Rounds 31–32). Those receipts certify bytes and version consistency, not semantic entailment.
- **P vs NP -> algorithm design discipline:** choose a tractable approximation plus falsifiable exact small-pool upper bound, rather than asserting that a universal minimal witness generator can be efficient.
- **RH -> arithmetic corpus specialization:** potentially study predictive residual coding of a prime-gap sequence; compare entropy coder, delta/varint, arithmetic prediction and zstd on holdout arithmetic sequences. Do not imply applicability to natural language unless transfer is demonstrated.
- **Novelty collision:** weighted set cover, graph-based retrieval, and content-addressed storage are prior art. Any CDG paper needs a measured improvement in a clearly specified coupled objective compared with ordinary iterative retrieval plus conventional database indexing.

## 6. Priority next experiment and explicit kill tests

1. Use an **authentic externally sourced multihop corpus**; extract predicted evidence facets from source spans without exposing annotation labels at selection time. Keep a fixed candidate pool and held-out questions. Compare BM25, simple iterative title expansion, greedy facet cover, bounded exact small-pool cover, and frame-naive versus frame-aware costs at matched evidence completeness.
2. Charge **all** index/metadata costs, candidate acquisition, FTS queries, decompress, span verification, and planning time. Track total bytes stored, p50/p95 reads and updates across versions.
3. Add incomplete/contradictory/ambiguous evidence cases with appropriate abstention and scope/version checks. Measure unsupported-answer rate under a frozen semantic answerer, not just mechanically sufficient facets.
4. Kill the advanced planner if greedy + established iterative retrieval matches it at equal total resources. Kill prime/zeta-based text-frame tuning unless it beats equal-mean-size fixed and content-defined boundaries on held-out corpora.
5. The existing R32 result only compares CAS reuse to a deliberately full-rebuild storage control. It is not a result about complexity theory, NP hardness, or superiority over optimized SQLite.

**Decision:** continue complexity-aware evidence-acquisition research with mathematically explicit contracts. Do not dedicate CDG resources to proving RH or P != NP, or to prime-derived general text compression.

## Reproduce

```bash
python -m unittest discover -s experiments/round-33 -p 'test_*.py' -v
python experiments/round-33/selection_lab.py --out experiments/round-33/results.json --repetitions 100
python experiments/round-33/prime_boundary_probe.py \
  path/to/round24.md path/to/round25.md path/to/round26.md path/to/round27.md path/to/round28.md \
  > experiments/round-33/prime_results_reproduced.json
```

The five original input SHA-256 hashes are recorded as distinct keys in `prime_results.json`. Source reports are already committed in prior rounds. A network-free local run used the available copies of the source text. Do not interpret reported synthetic optimization costs as hardware measurements.
