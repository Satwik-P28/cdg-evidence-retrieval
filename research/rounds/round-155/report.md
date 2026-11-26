# R155 compact fragment mapping and split boundary bridge

Status: all three original-code jobs passed. R154 small AP and CLARK were negative on total physical index bytes despite some FTS savings. Full AP pending at design time.

Hypotheses: (1) finalized fragment lookup need not retain insertion-time SHA catalog; use sorted content-ID delta varints with a low-bit flag for multiplicity >1, decode postings exactly. (2) Separate ordinary core phrase matches from phrase matches crossing a boundary. Store unique core token sequences and separate left suffix/right prefix bridge sequences (at most seven tokens on either side). Count only occurrences straddling split in bridge rows. For phrases of length <=8 and nonfinal core lengths >=8, no occurrence crosses two boundaries. Every occurrence is either internal or belongs to exactly one bridge. Repeated core/bridge instances handled by multiplicity. No positional offset storage beyond within-fragment native FTS. No source recovery from this multiset.

Four physical finalized arms: raw quotient (drop insertion content catalog), compact CDC64 halo (drop same catalog and fragment digests, pack mappings), split bridges CDC64, split bridges CDC128. Every arm uses identical prepared active content-to-revision maps; report preparation separately and charge all persisted metadata. Compare identical native rank/df results on R154 query plan, two warm repeats, both AP cohorts and CLARK. Charge pre/post compaction sizes and packed payload, no assertion that dropped catalogs support append. Core and bridge equality verified bytewise at build time; actual native tokenizer roundtrip. Tests include repeated phrase overlaps, exact boundary length eight, duplicate content and malformed varint.

Prior art: He/Suel and earlier two-level fragment indexes https://research.engineering.nyu.edu/~suel/papers/block.pdf ; 2016 versioned data index compression https://sites.cs.ucsb.edu/~tyang/papers/CIKM16final.pdf ; universal repetitive indexes https://arxiv.org/abs/1604.08897. Delta-coded postings, fragment reuse, overlap and boundary-aware matching are established; no novelty claim. If compact representation loses, investigate more distinct joint source/index approach rather than only tuning fragment lengths.

## Verified results

All three R155 jobs passed on 28a12aa6 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45882429528). Full AP compact raw 77,455,360 B vs halo64 73,670,656 B (4.89% smaller), bridge64 85,602,304 B, bridge128 76,771,328 B. Median query raw 378.353 us vs halo64 831.601 us (2.20x slower); common prepared active mapping 12.343 vs 12.588 ms. Small AP halo64 10,993,664 vs raw 10,907,648 B (0.79% larger); CLARK all fragment arms larger. 9,984 native rank comparisons across all 3 corpora/configurations and 4 arms, identical df and scores. Finalized only; insertion catalogs dropped equally. No transactional or source recovery claim, phrases at most eight tokens. R155 supports a storage/latency tradeoff on the full cohort, not general dominance. R151 remains preferred integrated architecture.

| Corpus | Revisions | Arm | Final bytes | Pre-final bytes | Median query us |
|---|---:|---|---:|---:|---:|
| ap | 10009 | raw | 10907648 | 11153408 | 163.909 |
| ap | 10009 | halo64 | 10993664 | 14295040 | 360.733 |
| ap | 10009 | bridge64 | 12832768 | 18681856 | 386.989 |
| ap | 10009 | bridge128 | 11370496 | 14516224 | 305.415 |
| clark | 1161 | raw | 2719744 | 2777088 | 80.364 |
| clark | 1161 | halo64 | 3604480 | 4591616 | 196.072 |
| clark | 1161 | bridge64 | 4292608 | 6131712 | 193.247 |
| clark | 1161 | bridge128 | 3596288 | 4562944 | 160.969 |
| ap | 74364 | raw | 77455360 | 79261696 | 378.352 |
| ap | 74364 | halo64 | 73670656 | 96403456 | 831.601 |
| ap | 74364 | bridge64 | 85602304 | 125140992 | 847.714 |
| ap | 74364 | bridge128 | 76771328 | 98394112 | 801.510 |
