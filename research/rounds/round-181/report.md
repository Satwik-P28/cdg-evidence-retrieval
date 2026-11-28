# R181 — Query-independent phrase rejection

## The question

R174 bought positional blocks for terms chosen from a query workload. Held-out queries in
R180's workload are phrases that policy never saw, and R174's selection cannot help them:
the held-out cost of a frequency-only archive is dominated by source reads for phrases whose
terms were not selected.

This round asks whether a structure that knows nothing about the query workload can reject
candidates for *any* phrase, including phrases that did not exist when the index was built.

## Structures and their guarantees

| structure | guarantee | what it may do |
|---|---|---|
| `pairs_all` — exact adjacent-pair postings | complete: every pair that occurs anywhere is stored | reject a candidate that lacks any adjacent pair |
| `pairs_selective-X%` — pairs bought under a vocabulary budget | complete *for the pairs it stores* | same, and says nothing about pairs it did not buy |
| `fingerprints64` — one 64-bit mask per document over hashed pairs | no false negatives | reject only on a clear bit |
| `positions-X%` — R174's cost-based term selection | exact for covered terms | answer or reject with positions |

Two rules hold for everything in the table. A filter may only reject candidates, never
supply a term frequency; and every survivor is verified exactly, against positions when
they cover the phrase and against the source otherwise. A cleared bit, a missing posting,
or a pair that occurs nowhere is evidence of absence only in the direction that is safe.

The distinction between a complete and a selective pair index is not cosmetic. In a
complete index a missing row proves the pair occurs nowhere, so every candidate can be
rejected. In a selective index a missing row means the pair was not worth buying, and
treating it as absence rejects true matches. That is exactly the bug the first version of
this round had; it is now a named field (`pair_index_meta.selective`) with a test that
fails if the two are conflated.

Corruption fails closed: a damaged posting list raises a decode error instead of returning
a short candidate list.

## Results

Frozen workload `b8e157bc9e822e70…` (AP-10,009) and `50d5ccab28dcc206…` (CLARK-1,161), every
query evaluated at the cutoff it was generated for. All six arms on both corpora reported
**zero score error, zero tie-order differences and zero rank mismatches** against the native
FTS5 oracle.

### AP-10,009 (base archive 14,082,048 bytes)

| arm | archive bytes | vs base | median µs | P95 µs | P99 µs | max µs | source reads |
|---|---|---|---|---|---|---|---|
| `freq` | 14,082,048 | — | 6,461 | 388,344 | 588,428 | 819,731 | 168,996 |
| `pairs_all` | 30,851,072 | +119.1% | 3,970 | 20,322 | 81,231 | 332,367 | 9,970 |
| `pairs_selective-5%` | 14,770,176 | +4.9% | 5,532 | 105,639 | 369,527 | 696,854 | 71,887 |
| `fingerprints64` | 14,180,352 | +0.7% | 5,685 | 365,317 | 609,354 | 868,307 | 168,175 |
| `positions-5%` | 14,958,592 | +6.2% | 4,588 | 269,475 | 395,113 | 504,567 | 168,996 |
| `pairs_all+positions-5%` | 31,727,616 | +125.3% | 2,694 | 12,865 | 43,062 | 238,628 | 9,970 |

Candidate checks fall from 122,876,019 to 1,068,866 with the complete pair index (99.1%
rejected) and to 51,252,723 with the 5% vocabulary budget (58.3% rejected).

### CLARK-1,161 (base archive 5,009,408 bytes)

| arm | archive bytes | vs base | median µs | P95 µs | P99 µs | max µs | source reads |
|---|---|---|---|---|---|---|---|
| `freq` | 5,009,408 | — | 2,024 | 168,171 | 348,464 | 619,899 | 63,968 |
| `pairs_all` | 12,431,360 | +148.2% | 861 | 7,400 | 42,235 | 153,169 | 4,379 |
| `pairs_selective-5%` | 5,226,496 | +4.3% | 2,142 | 72,078 | 245,543 | 453,448 | 27,802 |
| `fingerprints64` | 5,033,984 | +0.5% | 1,975 | 182,922 | 320,737 | 617,779 | 63,674 |
| `positions-5%` | 5,296,128 | +5.7% | 1,620 | 159,467 | 335,512 | 637,063 | 63,968 |
| `pairs_all+positions-5%` | 12,718,080 | +153.9% | 1,143 | 9,551 | 51,855 | 209,253 | 4,379 |

## What the numbers say

**Adjacency rejection generalises; term selection does not.** At a matched ~5% physical
budget the pair filter cuts held-out P95 by **3.7× on AP** (388,344 → 105,639 µs) and
**2.3× on CLARK** (168,171 → 72,078 µs). Selective positions at a slightly larger budget cut
P95 by 1.44× on AP and 1.05× on CLARK, and on AP they do not reduce source reads at all:
168,996 before, 168,996 after. The 904 terms R174's document-frequency policy could buy at
that budget almost never cover an unseen phrase's tokens twice, which is exactly why the
positions cannot reject.

**The complete pair index is the wrong purchase.** It is the best performer (19×/23× P95,
P99 81,231/42,235 µs) but costs +119% to +148% of the archive. On either corpus that is a
different storage class, not a 5% budget.

**64-bit document fingerprints do not work at this scale.** They add 0.5% storage and reject
0.5% of candidates (611,907 of 122,876,019 on AP). With thousands of distinct adjacent pairs
per document, a 64-bit mask saturates: nearly every bit is set in nearly every document, so a
clear bit almost never occurs. This is a negative result and it is kept.

**Positions still help on top of rejection, cheaply in latency, expensively in storage.**
`pairs_all+positions-5%` is the fastest arm on both corpora (P95 12,865 / 9,551 µs) but
inherits the full pair index's storage.

## Paired measurement

Every arm ran the same 1,439 AP / 1,320 CLARK queries in a shuffled order against the same
active sets, with per-query latency and per-query counters retained. The comparison is
therefore paired by construction: no arm sees an easier mixture of queries.

## Limitations

* Logical activation only. These are warm-cache measurements of stored bytes touched, not
  physical page I/O, and no claim about cold caches is made.
* Pair identity is a 63-bit content hash. A collision can only merge two posting lists,
  which can only *add* candidates; those are verified exactly, so collisions cannot cause a
  false negative.
* The selective pair budget is spent on vocabulary: tokens enter in document-frequency order
  and every pair whose endpoints are both bought is stored. That rule was chosen after
  measuring two alternatives (document frequency per byte, and rejection per byte), both of
  which bought pairs that queries never used. Only the vocabulary rule is reported as the
  method; the others are not reported as results because they were not run to completion.
* `fingerprints64` is the only approximate structure tested. Larger masks were not measured,
  so the negative result is about 64 bits, not about fingerprinting in general.
* CLARK has 1,157 articles for 1,161 revisions, so `changed_content` queries are absent there
  and temporal evidence for that class is AP-only.