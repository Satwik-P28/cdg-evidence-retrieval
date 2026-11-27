# R169: one shared alignment for byte reconstruction and signed phrase indexing

Status: implemented; hosted validation pending. Parent R168 0a803c0d0d54a9a48db1a5b17229ecb6f4da7cae. R168 AP 10,009 run 45916500364 confirms zero non-unit private coefficients and identical weighted/adaptive archive bytes (18583552); CLARK also passed. Largest AP pending at observation. No additional real-world coefficient storage gain.

## Mechanism and controls
The existing source codec uses opaque Zstandard dictionary frames, not a directly reusable token edit script. Introduce an alternative one-hop raw byte COPY/LITERAL script compressed with the existing compressor. Obtain native unicode61 byte offsets via the public FTS5 tokenizer callback. A token cell extends from the token start to the next token start (last cell to end of raw bytes); leading non-token bytes are separate. Generate one normalized token Levenshtein alignment, reuse it for signed phrase windows and candidate byte script. On equal token alignments, copy only byte-identical raw cells, including exact punctuation/spacing/case; otherwise emit raw literals. On changed token spans emit raw child cells. Coalesce contiguous copies and literals. Empty and punctuation-only inputs work via leading cell. Strict decoder checks opcode lengths, bounds, and exact output length; digest checked in archive recovery. Source kind 3 uses full parent, not an index-derived raw source. No new persistent token coordinate map; offsets computed at build only.

Only test candidates for existing source kind 1 children whose source parent content equals the chosen aligned index anchor, so existing full source parent is preserved. Admission charges new frame catalog proxy and credits old frame only if last reference; requires existing source frame ratio and activation bounds. Deduplicate by exact frame equality after digest match, remove unreferenced frames. Original source retained if candidate loses. Compare positional, independent weighted adaptive, aligned weighted adaptive and identical aligned joint. Source-only and index-only choices otherwise unchanged; assert matched aligned index statistics and FTS bytes identical. Report candidate counts, original/script candidate bytes, encoding time, selected count, final frame payload and complete file size. All source recoveries and native ranking checks retained.

This tests shared alignment computation and alternative byte representation, not yet shared persistent source/index bytes. No claim of speedup over Zstd unless measured; new script may lose badly. No general joint anchor search yet. Source decoded-byte contract now conservatively counts raw parent+child+intermediate script for kind 3; compressed activated bytes count frames. Candidates that violate this stronger bound are rejected. No transactional integration. Public tokenizer offset handling assumes nonoverlapping default unicode61 tokens; tested with Unicode, case and separators. 


## Local negative-control results

Executed independently with Python 3.13, RapidFuzz 3.14.3, ASCII regex token spans, system libzstd level 3 (not the corpus native tokenizer or necessarily the exact pinned compressor settings). 500 randomized byte-edit pairs reconstructed exactly. Four 200-pair synthetic regimes of 600 random tokens per parent:
| Regime | Dict frame bytes | Script frame bytes | Smaller scripts | Bound-feasible scripts |
|---|---:|---:|---:|---:|
| Single replacement | 7075 | 8000 | 17 | 200 |
| 20 scattered replacements | 42877 | 47285 | 0 | 200 |
| Case and doubled spacing | 383487 | 404944 | 0 | 0 |
| 60-token insertion | 29556 | 33628 | 11 | 200 |

Only 28/800 smaller, all 28 bound-feasible. Aggregate storage loses on every regime. This is a negative control against dictionary compression, not a realistic corpus benchmark. Probe adjacent reproduces the same workload, using the implemented script functions and libzstd via ctypes.

## Strengthened admission

Count materialized script bytes in the decoded-byte bound and reject same-frame no-op replacements. Measure per-revision recovery latency and aggregate activated/decoded bytes in every arm; source times include source verification. The paired aligned modes share the same index representation and must have identical index size. Source/index persistent sharing remains unproven; the next credible direction is to share normalized-token postings as reconstruction predictors with residuals and charge all forward-access structures, or to falsify that approach against the strongest existing R156/R157 controls. 
