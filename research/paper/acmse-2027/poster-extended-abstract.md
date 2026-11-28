# Query-Independent Adjacency Filters for Exact Phrase Retrieval in Compressed Archives

ACMSE 2027 poster | anonymous extended-abstract working draft | 2026-11-28

**Draft status:** target two pages including references in conference LaTeX template. Separate research question from full paper; finalized source/index prototype only. Primary evidence independently hosted R179 on branch research/round-179-independent-audit at 67d9f62717ff706079791031e247ac9b2b4f6926, run 46078183333. Secondary R181 numbers are local and on a different query workload; label them accurately. Not a final PDF.

## Abstract

Frequency-only indexes reduce the storage cost of compressed text archives but may require expensive source reconstruction to verify phrases. We investigate query-independent adjacency signatures that reject candidates unable to contain a phrase without storing all term positions or anticipating a particular workload. Each content record stores a checksum-protected Bloom filter over adjacent normalized token pairs; surviving candidates undergo exact source verification and historical BM25 scoring. On two news collections, an adaptive-width filter reduces source verification counts by 94.95% and 93.80% on an expanded content-derived query workload, with corresponding P95 reductions from 472.37 to 67.60 ms and 252.77 to 43.02 ms. Complete archive sizes increase relative to frequency-only retrieval but remain below the matched full positional baseline. All evaluated rankings agree with the native oracle. Full positional retrieval remains substantially faster. The results characterize a storage-versus-verification trade-off using established filtering techniques rather than claiming a novel data structure.

## 1 Motivation and method

A compact term-frequency index can answer a unigram query directly. For a phrase, however, intersecting term postings provides only a candidate set: the terms may occur in the wrong order or at unrelated offsets. Decompressing all such candidates inflates tail latency. Auxiliary nextword indexes and positional indexing are established approaches [1,2]; we examine small query-independent filters in a versioned compressed archive.

For a document d with normalized token sequence t_1,...,t_n, insert every adjacent pair (t_i,t_{i+1}) into a fixed-width or adaptive-width bitset using three hash-derived bit locations. For phrase p, form the union of the bits for all its adjacent pairs. If any required bit is absent from d's filter, d cannot contain p. Otherwise the phrase may or may not occur. The filter never supplies a phrase count or score. Exact verification reconstructs the source and counts overlapping occurrences with the fixed native tokenizer. Historical ranking uses the active revision population. The filter tag binds content identity, width, source digest and bitset; missing or checksum-invalid filters cause source verification rather than rejection. This addresses accidental corruption, not malicious replacement of trusted metadata.

## 2 Evaluation

Compare frequency-only retrieval, 512-bit and 1,024-bit filters, an adaptive filter of 256–4,096 bits based on distinct pair count, full positional FTS5 and signed correction windows. All complete database sizes include source frames and metadata. AP has 10,009 derived revisions; CLARK has 1,161 revisions, mostly distinct articles. Each corpus uses 80 legacy queries and 160 extended queries including later-document phrases and frequent-token combinations, four cutoffs and two shuffled warm passes. The table reports the extended workload only (1,280 rank checks per arm per corpus). Filter masks are resident after separately timed setup. No claim of cold-device I/O or end-to-end LLM performance.

| Corpus | Representation | Archive MB | P95 ms | Source verifications |
|---|---|---:|---:|---:|
| AP | Frequency | 14.082 | 472.369 | 616,010 |
| AP | 512-bit | 14.627 | 412.646 | 472,184 |
| AP | 1,024-bit | 15.012 | 302.601 | 227,256 |
| AP | Adaptive | 17.023 | 67.601 | 31,118 |
| AP | Positional | 20.685 | 2.431 | not required for phrase counts |
| CLARK | Frequency | 5.009 | 252.772 | 210,376 |
| CLARK | 512-bit | 5.124 | 214.852 | 157,494 |
| CLARK | 1,024-bit | 5.206 | 151.304 | 86,974 |
| CLARK | Adaptive | 5.616 | 43.022 | 13,050 |
| CLARK | Positional | 5.992 | 0.529 | not required for phrase counts |

The adaptive filter requires 20.88% and 12.10% more complete storage than frequency-only retrieval while reducing P95 by 6.99x and 5.88x, respectively. It uses about 17.70% and 6.29% less archive storage than the full positional controls, but is far slower. All evaluated score/rank/DF signatures agree. On the legacy workload the latency reductions are smaller; performance is workload-dependent.

A separate experiment (R181, locally committed results) evaluates selective exact pair postings on a broader generated workload of 1,439 AP and 1,320 CLARK templates. The selective pair arms use 14.770 MB and 5.226 MB, with P95 105.639 ms and 72.078 ms, compared with respective frequency-only P95 388.344 ms and 168.171 ms. These are whole-manifest aggregates, not held-out-only values; its positional comparator is document-frequency selected. Do not compare these absolute latencies directly with R179's different workload or claim trained-policy superiority from this comparison.

## 3 Conclusion and future work

Query-independent adjacency filters trade a small-to-moderate archive increment for reduced exact verification work, while maintaining historical ranking correctness on the evaluated workloads. Very small masks saturate; larger filters cost space and memory. The matched full positional index remains the latency winner. Future work will compare fixed and adaptive filters, selective exact pair postings and blocked positions on one frozen workload, evaluate actual memory/page I/O and integrate successful representations transactionally. The current poster concerns preliminary query-path optimization, not the full paper's source encoding, atomic receipt or integrated storage results.

## References

1. Bahle, Williams and Zobel. Efficient phrase querying with an auxiliary index. SIGIR 2002. https://doi.org/10.1145/564376.564415
2. Manning, Raghavan and Schütze. Introduction to Information Retrieval, section 2.4. Cambridge University Press, 2008. https://nlp.stanford.edu/IR-book/html/htmledition/positional-postings-and-phrase-queries-1.html

## Author review (not submission text)

Verify raw hosted result JSON and percentages; add Bloom filter original citation, dataset references, actual tokenizer and filter bit packing. Fit one table or trade-off chart in two pages. Add accurate AI-research-use methods disclosure, anonymize. Check simultaneous related submissions with chairs. No claims about novel Bloom filters, true natural search logs, held-out R181 performance, transaction integration or production speed.
