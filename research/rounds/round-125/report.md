# R125: Fragment-relative positional index

**Status: PASS. Three regression tests and original-source [CI 45296860233](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45296860233). Tested implementation commit `422c1e2f67e4a784ed79873e8c8462e48e58732a`.**

[He and Suel, Optimizing Positional Index Structures for Versioned Document Collections (SIGIR 2012)](https://research.engineering.nyu.edu/~suel/papers/frag.pdf), sections 2.2–4.2, establishes fragment-based reuse, relative positions and version/fragment application mapping. Their scheme includes optimized partitioning and separate nonpositional candidate ranking. Our comparison is a deliberately simpler 2MIN-inspired strict local-minimum hash partitioning with maximum-length fallback, compared to fixed 32-token chunks and optional exact application-interval coalescing. It does not reproduce their full optimizer, OPT-PFD codec or reranking system.

Index unique normalized Unicode61 token fragments in native contentless positional FTS5. Reconstruct exact global token positions by joining fragment occurrences to active version applications and adding their offsets. Count phrases across fragment boundaries, including overlaps and repeated terms, using positional intersections. Independent source-derived token-vector reconstruction and exhaustive persisted fragment re-tokenization audit are required. Match R124 query plan, compare native historical and native active-only controls, preserve metadata and all original token positions; no original byte-exact source payload in index. Four cutoffs, same corpus, randomized warm rank timings; exact phrase counts rather than top-k TF candidate truncation. No online maintenance, independent corpus or novel fragment indexing claim.

## Results

445 articles, 2,504 revisions, 43,147 terms, 1,663,050 original Unicode61 normalized token positions. Every fragment re-tokenization and persisted application interval verified; each of five representations reconstructed all original normalized token sequences exactly (8,315,250 positions). Four cutoffs, 159 queries each including 56 phrase-containing queries; 636 rankings per method, 3,204 ranked positions per method, 29,934 positive native phrase/term frequency pairs and 354,106 queried positive token positions checked per fragment method. Zero observed score error, three regression tests passed (including a phrase spanning a fragment boundary).

| Layout | SQLite B | Unique fragments | Unique fragment tokens | Application intervals | Final median us | Final phrase median us |
|---|---:|---:|---:|---:|---:|---:|
| fixed32_version | 6,508,544 | 43,716 | 1,364,344 | 53,172 | 780.586 | 9023.835 |
| fixed32_coalesced | 6,348,800 | 43,716 | 1,364,344 | 44,637 | 756.389 | 8700.829 |
| min32_version | 4,939,776 | 30,456 | 942,219 | 54,358 | 718.452 | 8217.226 |
| min32_coalesced | 4,775,936 | 30,456 | 942,219 | 45,460 | 694.449 | 7958.172 |
| min64_coalesced | 4,255,744 | 18,328 | 1,062,014 | 24,434 | 680.622 | 6966.048 |
| native_history | 4,657,152 | - | - | - | 82.827 | 79.140 |

The min32 partition reduces unique indexed token occurrences 43.34% relative to the original corpus, but remains larger than native with applications and metadata. The min64_coalesced layout is 8.62% smaller than native historical positional FTS5, with 8.22x higher overall median and 88.02x higher phrase median. Native active-only snapshot final median 69.498 us and phrase median 89.834 us, not a historical archive. Fixed-size partitions are poor here despite deduplication; content-defined boundaries improve reuse. Larger content-defined fragments reduce application/index overhead even though min64 contains more unique tokens than min32. App interval coalescing helps physical size but does not eliminate absolute-offset shifts. This is not a comparison to the full He/Suel system, no performance claims across different CI runners. Full positional data retained but limited query grammar, normalized tokens are not original bytes. Source payload excluded.

## Decision

Keep native FTS5 as default; R124 and R125 are exact positional compression controls, not practical latency replacements. R125 shows the fragment-reuse baseline works, but full term-position reconstruction for phrase DF is costly. Next compare exact fragment-local phrase counts plus boundary windows (avoid materializing all common-term positions), and a separate nonpositional TF layer for term-only requests. Do not truncate candidates using nonpositional top-k unless explicitly evaluating approximation; exact historical BM25 requires historical phrase DF and counts. Charge all auxiliary indexes and mappings. Evaluate independent version histories before any novelty/generalization claim. This is established fragment-indexing prior art, not an invention.
