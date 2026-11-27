# R172: selective positional materialization

Parent R171 315a4d23861661a47172fd1238c7a7440b45e044. R171 run 45918100320 passed all jobs. Large AP 74,364: positional 148459520 bytes, adaptive 132964352, frequency 95735808, text 186740736, text joint 171364352, text delta 154562560, text delta joint 141307904, IDs 171769856, IDs delta 145862656. All ranks exact. Text delta payload 46139587 vs 69093915 (17452 admissions); ID delta 40335523 vs 59798287 (16949 admissions). Text delta joint selected 11989 source residuals. Still larger and slower than adaptive; no CLARK tape deltas. Reject standalone tape as general default.

## Hypothesis and methods
Frequency-only R170/R171 is small but raw source phrase verification inflates tail latency. Add positions for terms with highest unique-content document frequency, independent of query labels. Fixed top32,128,512, all positions, frequency only, native full positional and signed adaptive controls. Store exact position lists in one compressed delta-varint blob per term, using lexicon IDs assigned in same sorted order. All pages charged; all-position control intentionally duplicates frequency and position metadata and is not a claim of optimal positional compression. When all phrase offsets covered, intersect shifted position lists, respecting bounds and overlapping matches, and use exact count. With at least two covered offsets but incomplete coverage, the intersection is an upper bound; zero safely rejects a candidate, otherwise source verification remains mandatory. One covered offset skips position loads. Cache within each query only. Use frozen R170 query plan and native oracle, all source recovery checks and exact DF/signature parity. Track query class latency, position bytes/decoded bytes, covered and partially covered phrases, candidate rejection, source reads, activated/decoded bytes, complete DB pages. Full corpus positions use a finalized archive; selection may include future revisions relative to a cutoff, no rank leakage but not an online evaluation. No physical IO or peak RSS claim. Corpus outcomes pending.

## Prior art
Selective or augmented phrase indexes, positional postings and direct-index fallback are established. Relevant references: Phrase Query Optimization on Inverted Indexes (https://paperzz.com/doc/7812782/phrase-query-optimization-on-inverted-indexes); To index or not to index: Time–space trade-offs for positional ranking functions in search engines (https://www.sciencedirect.com/science/article/pii/S0306437919305186); Manning et al., Introduction to Information Retrieval, section 2.4 (https://nlp.stanford.edu/IR-book/html/htmledition/positional-postings-and-phrase-queries-1.html). R172 evaluates versioned archive-specific tradeoffs, not a novel indexing primitive.


## Executed local independent probe
SQLite 3.46.1, Python stdlib only. Independent copy of the exact delta-varint codec and shifted position kernel (adjacent probe); 10,000 randomized codec round trips, 10,000 full coverage exact count comparisons, 10,000 partial coverage upper-bound comparisons passed. Separate native FTS5 synthetic corpus: 400 documents, 250 tokens each, seed 172, 60% draws from 16 common terms and 40% from 1,000 rare terms. 24 fixed phrases (8 common, 8 mixed with common offsets around rare middle term, 8 rare). Each of five selection policies matched brute-force TF and native FTS5 membership for all 24 queries, 120 query checks. Counts below are candidate source verification calls, not timings or measured disk reads; no compressed storage measurement in this probe.

| Selected terms | Common candidate verifications | Mixed candidate verifications | Rare candidate verifications | Total |
|---:|---:|---:|---:|---:|
| 0 | 3200 | 308 | 24 | 3532 |
| 8 | 2800 | 308 | 24 | 3132 |
| 16 | 0 | 88 | 24 | 112 |
| 32 | 0 | 72 | 24 | 96 |
| 1016 (all) | 0 | 0 | 0 | 0 |

Top16 rejected 2214 common candidates and resolved 986 common candidates exactly; for mixed phrases rejected 220 of 308 candidates with incomplete coverage. Top16 reduced fallback calls 96.83% on this deliberately favorable synthetic vocabulary. Not a real-corpus speedup: decoding common position lists could cost more than source fallback. R172 hosted run 45919907942 initiated for implementation commit 537f3a30d9d8b8069686bb2958d8ec7493e1536b; AP10k unit-test step passed at observation; remaining corpus results pending.
