# R115: Direct snapshot-reference revision frames

**Status: PASS. Original-source CI [45284933893](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45284933893).**

R114 found a source-only storage vs. reconstruction tradeoff for previous-revision
dictionary chains. Direct references to snapshots and reference-selection are
established prior art, including PRESIDIO and WikECD. This round tests a
concrete restricted reference policy against ordinary bounded previous-version
chains in the same physical SQLite schema. It is not an originality claim.

Frozen cohorts: R114's 100 SHA-selected articles are the development set;
the next 100 in the same predeclared rank are an article-disjoint evaluation
set. Both derive from the same pinned Versions repository (not an independent
dataset or real access history).

Compare snapshots, prev2/4/8, latest-anchor4/8, and bounded_anchor.
The latter considers the last four independently encoded snapshots, stores
a direct reference only if the new dictionary frame is no more than 80%
of the independent frame, parent+child compressed payload <= 1.5x the
independent compressed frame, and parent+child raw bytes <= 2.5x the
requested revision. Otherwise it stores a new snapshot. No future revisions
or held-out query outcomes are consulted. For the accepted reference these
logical payload/decode bounds hold by construction; they are not disk I/O or
latency bounds. Every revision verifies exact source bytes, SHA receipt,
parent ordering, dependency depth and foreign keys. Count physical size,
append WAL, activated compressed bytes and decoded bytes, with warm timings
exploratory. No search index, FTS, real user logs, RAG outcome, or WikECD
reproduction.

References: [WikECD](https://doi.org/10.1145/3787449);
[PRESIDIO](https://www.crss.us/media/pubs/33ef15dd54e7d4175fe554cff674cb6e386038c6.pdf);
[Versions](https://github.com/natwar-modani/versions).

## Verified two-cohort results

Both cohorts match the same pinned full-corpus SHA-256 as R114. Development: 100 articles, 567 revisions. Article-disjoint evaluation: 100 articles, 550 revisions. Seven policy arms each, 7,819 exact reconstruction checks; all passed. The bounded logical-read contract was checked for every selected revision in both cohorts.

### article_disjoint

| Policy | SQLite B | Append WAL B | Mean weighted decode amplification | Worst activated compressed / standalone | Max depth |
|---|---:|---:|---:|---:|---:|
| anchor4 | 1,425,408 | 8,549,032 | 1.490 | 13.562 | 1 |
| anchor8 | 1,482,752 | 8,998,112 | 1.464 | 13.562 | 1 |
| bounded_anchor | 1,286,144 | 8,565,512 | 1.499 | 1.484 | 1 |
| prev2 | 1,212,416 | 7,807,432 | 1.714 | 21.013 | 2 |
| prev4 | 1,011,712 | 7,514,912 | 2.293 | 19.892 | 4 |
| prev8 | 860,160 | 6,814,512 | 2.977 | 21.681 | 7 |
| snapshot | 1,982,464 | 10,164,072 | 1.000 | 1.000 | 0 |

### development

| Policy | SQLite B | Append WAL B | Mean weighted decode amplification | Worst activated compressed / standalone | Max depth |
|---|---:|---:|---:|---:|---:|
| anchor4 | 1,449,984 | 8,796,232 | 1.458 | 9.406 | 1 |
| anchor8 | 1,515,520 | 9,150,552 | 1.437 | 9.406 | 1 |
| bounded_anchor | 1,306,624 | 8,334,792 | 1.513 | 1.500 | 1 |
| prev2 | 1,146,880 | 7,840,392 | 1.722 | 20.177 | 2 |
| prev4 | 987,136 | 7,605,552 | 2.296 | 20.177 | 4 |
| prev8 | 835,584 | 7,045,232 | 3.088 | 20.177 | 7 |
| snapshot | 1,925,120 | 10,048,712 | 1.000 | 1.000 | 0 |

## Decision and limitations

On article-disjoint evaluation, bounded_anchor uses 1,286,144 B versus snapshot 1,982,464 B (35.12% lower), with 15.73% less WAL. It uses 6.08% more physical storage and 9.71% more WAL than prev2, but reduces average source decode amplification from 1.714x to 1.499x and worst activated payload ratio from 21.013x to 1.484x. Worst nonempty-revision decoded ratio is 2.229x (bounded by 2.5x). Both fixed-anchor variants also have depth at most one, yet have worst payload ratio 13.562x, so depth alone does not control read amplification. Bounded_anchor uses 9.77% less physical storage than anchor4, but marginally more WAL and mean decoded bytes. It does not dominate all controls. The bound is a simple consequence of accepting only admissible parent/child frames, not a new delta coding theorem. There is no claimed universal gain, exact device read bound, or latency improvement.

Future: compare against actual WikECD and other established bounded-reference algorithms on their native full revision data, add actual access distributions and byte-identical generation-bound evidence retrieval. A complete archive index and atomic read/write correctness remain required for a CDG-specific systems contribution.
