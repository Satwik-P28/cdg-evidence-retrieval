# R115: Direct snapshot-reference revision frames

**Status: code and CI pushed; corpus results pending.**

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
