# R154 bounded phrase fragment quotient

Status: all three original-code jobs passed.

Closest prior art: He and Suel, Optimizing Positional Index Structures for Versioned Document Collections (SIGIR 2012), https://research.engineering.nyu.edu/~suel/papers/frag.pdf ; Compact Full-Text Indexing of Versioned Document Collections, https://research.engineering.nyu.edu/~suel/papers/archive.pdf ; Universal Indexes for Highly Repetitive Document Collections https://arxiv.org/abs/1604.08897. They establish fragment sharing/repetitive positional indexing. Do not claim fragment indexing or overlap is novel.

Hypothesis: exact phrase TF up to L=8 can be computed from a multiset of context-qualified fragments without keeping per-fragment global positional offsets in the index. Partition native token sequence into disjoint cores; append at most L-1 right tokens to each. Each phrase occurrence starting at position i belongs to exactly one core. Its remaining tokens lie in that core's extended window. The native FTS xInst offset must be strictly less than core length. Sum these counts times per-content fragment multiplicity; then expand active revision identities, compute native-equivalent df/N/total and BM25. Context and core length are included in fragment identity. This is a bounded phrase-count reduction, not arbitrary positional search. No source reconstruction from unordered fragment uses; byte-exact source storage remains separate. All fragment retokenization is verified using R152 native token stream, no approximate normalization.

Compare physical raw quotient vs fixed 32, content-defined target32 (min16 max64), target64 (min32 max128) with 7-token halos; charge catalog, mapping, validity, index and statistics. Both AP cohorts and independent CLARK. Existing 80 probes plus 24 sampled boundary-crossing phrases (2/4/8 tokens), two warm repeats, independent rebuilt FTS5 at all four cutoffs, exact ordered ranks and df across arms. Adversarial repeated fragment/overlap/tie/replacement/empty documents and a long-phrase rejection. No transaction or complete archive claim; larger phrase bound incurs halo/storage cost. If negative, retain results and consider alternate boundary bridge postings or compact mapping representations; no post-hoc tuning of this experiment.

## Verified results

All three R154 jobs passed on af08061f (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45882031896). 9,984 native rank comparisons across three configurations, four arms, two repeats, 104 probes and four cutoffs; zero observed score error and identical df across arms. Small AP raw quotient 11,153,408 B vs CDC64 14,295,040 B, CLARK 2,777,088 vs 4,591,616 B. Full AP raw 79261696 B vs CDC64 96403456 B. Physical catalog and mapping overhead charged, query timings descriptive. No promotion; R155 tests a finalized compact mapping and boundary bridge separately. Index-only, phrase length <=8, not exact-source reconstruction.

| Corpus | Revisions | Index | Physical B | FTS B | Median query us |
|---|---:|---|---:|---:|---:|
| ap | 74364 | raw | 79261696 | 73351168 | 537.169 |
| ap | 74364 | fixed32 | 187731968 | 101036032 | 1050.151 |
| ap | 74364 | cdc32 | 125558784 | 69537792 | 815.433 |
| ap | 74364 | cdc64 | 96403456 | 63143936 | 772.808 |
| ap | 10009 | raw | 11153408 | 10387456 | 133.704 |
| ap | 10009 | fixed32 | 26726400 | 14606336 | 384.976 |
| ap | 10009 | cdc32 | 18771968 | 10657792 | 310.731 |
| ap | 10009 | cdc64 | 14295040 | 9580544 | 262.159 |
| clark | 1161 | raw | 2777088 | 2527232 | 147.795 |
| clark | 1161 | fixed32 | 7049216 | 3944448 | 298.753 |
| clark | 1161 | cdc32 | 6275072 | 3694592 | 279.010 |
| clark | 1161 | cdc64 | 4591616 | 3145728 | 252.079 |
