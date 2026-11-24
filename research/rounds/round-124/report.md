# R124: Exact temporal position vectors and bounded gap-splice patches

**Status: PASS. Three unit tests and original-source [CI 45296315925](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45296315925).**

R123 term-frequency-only layouts are not positional substitutes for FTS5.
Extract all Unicode61 positions from original sources. Compare per-version
position vectors, coalesced identical local-ordinal vectors, direct versus
hybrid blocks, and bounded patches against the latest literal gap vector
within the same term/article. Patches encode common prefix/suffix lengths
and literal middle gaps; only use when shorter than a full vector. Depth
at most one, no cross-article anchors. Persisted vectors are expanded against
every original revision; coverage counts and complete interval equality
checked. Exact phrase counts including overlaps and repeated terms come
from positional intersections and are independently checked with native
FTS5 phrase counts on rebuilt active indexes. Compare native historical
full-detail FTS5, same version/article metadata, source payload excluded.
The query plan adds two-/three-token phrases and mixed AND/OR probes.
Three randomized warm timing passes; Python decoder, prepared active maps.
No NEAR, prefix, NOT, arbitrary grammar, online updates, WAL, independent
corpus, real access trace, or novelty claim. Gap coding, delta coding and
temporal coalescing are established.

## Results

445 articles, 2,504 revisions, 43,147 native Unicode61 terms. All six external layouts reproduce every one of the 754,641 original position vectors and 1,663,050 positions (4,527,846 vector expansions and 9,978,300 position checks across six layouts). Exact coalescing reduces positive vector records to 632,622, a 16.17% reduction rather than R121's 58.07% TF-only reduction. Four cutoffs, 159 queries per cutoff including 56 containing phrases; 636 exact ranking comparisons per method (224 phrase-containing), 3,204 ordered hits per method, 29,934 positive phrase/term frequency pairs checked per historical method. Zero observed score error; 3 regression tests passed. The plan includes exact phrase intersections, repeated-token fixture, mixed AND/OR, no arbitrary grammar.

| Layout | SQLite bytes | Vector intervals | Final median us | Final phrase median us |
|---|---:|---:|---:|---:|
| version_hybrid4 | 4,456,448 | 754,641 | 1634.427 | 13611.748 |
| coalesced_direct | 6,242,304 | 632,622 | 1388.191 | 11782.727 |
| coalesced_hybrid4 | 4,505,600 | 632,622 | 1471.737 | 11786.572 |
| coalesced_hybrid16 | 4,124,672 | 632,622 | 1595.135 | 11977.005 |
| patch_hybrid4 | 4,472,832 | 632,622 | 1475.284 | 11359.044 |
| patch_hybrid16 | 4,112,384 | 632,622 | 1608.148 | 11924.509 |
| native_history | 4,657,152 | - | 102.880 | 106.103 |

The smallest layout patch_hybrid16 is 11.70% smaller than native full-detail historical FTS5, but final median rank latency is 15.63x higher and phrase median 112.39x higher. Both preserve all token positions, but external query syntax is still restricted; native historical has broader functionality. R124 is Python, not R123's optimized native decoder. Per-version hybrid4 is physically smaller than coalesced hybrid4 despite more records; grouping and compressed page utilization matter. Bounded gap splice chooses 23,064 patch records, saving 101,321 raw bytes relative to literals, but only 12,288 physical bytes for hybrid16. Its dependency depth is one within a term/article, not a bound on decoded list bytes or actual query latency. Retain as positional correctness controls; reject as a practical default on this workload. Native FTS5 remains default. No claims of independent-corpus generalization, end-to-end source archive savings, production performance or new compression primitive.

## Stronger prior art and next gate

He and Suel's *Optimizing Positional Index Structures for Versioned Document Collections* (SIGIR 2012, https://research.engineering.nyu.edu/~suel/papers/frag.pdf), sections 2.2–4.2, explicitly addresses offset shifts after insertions/deletions and indexes reusable text fragments with fragment-relative token positions and version/fragment maps. It also separates nonpositional ranking and positional lookups. This is stronger prior art than per-term gap splices. R125 will test a simpler fragment-based control under the exact R124 query contract, not claim reproduction of the paper's full optimizer, codec or reranking. Exact phrase BM25 requires all phrase DF counts; arbitrary top-k TF truncation is not an exact substitute. No novelty claim for fragment reuse.
