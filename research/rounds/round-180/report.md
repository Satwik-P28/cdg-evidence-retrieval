# R180 — A discriminating, frozen query workload

## Why the old workload could not detect the failure

R174's workload was 80 queries produced by one corpus-statistics template, split 60/20/20
by hash into 57/11/12 (AP) and 46/20/14 (CLARK). Held-out phrases were near-duplicates of
training phrases, drawn from the same vocabulary band, so a policy fitted on 22 terms
scored well on them. On the larger corpus the same policy collapsed from 12,973 µs P95 in
training to 1,316,938 µs on held-out queries.

A workload that cannot distinguish a policy that generalises from one that memorises its
own training split is not a benchmark. R180 replaces it.

## What is generated

Twelve classes, 120 queries each, per corpus:

| class | what it stresses |
|---|---|
| `unigram_frequent` | high document frequency, small per-candidate work |
| `unigram_mid` | the middle of the frequency distribution |
| `unigram_rare` | postings that exist but are nearly unique |
| `phrase_2_3` | ordinary adjacent phrases |
| `phrase_4_5` | longer phrases, more offsets to verify |
| `phrase_6_8` | phrases where partial positional coverage is the normal case |
| `rare_middle` | common token, rare token, common token — high candidate count, low exact frequency |
| `absent_phrase` | phrase that does not occur: correct answer is cheap rejection |
| `high_candidate` | ≥ 64 candidate documents before any phrase check |
| `repeated_phrase` | ≥ 5 occurrences in one document: high term frequency |
| `changed_content` | token pair a later revision removed |
| `and_or` | 2-phrase AND and OR combinations |

Every template records the exact candidate count, the exact phrase document frequency and
the expected verification cost (candidates × mean source frame size), plus log-bucket
strata on all three.

Generation is content-derived: n-grams come from corpus text at fixed offsets, terms are
chosen by hashing `class|phrase`, and absent phrases are **verified absent** through the
exact FTS5 oracle rather than assumed. Re-running the generator on the same corpus
reproduces the manifest digest byte for byte (asserted by a test).

## The frozen manifests

| corpus | templates | distinct phrase sets | families | digest |
|---|---|---|---|---|
| AP-10,009 | 1,439 | 1,379 | 1,024 | `b8e157bc9e822e70…` |
| CLARK-1,161 | 1,320 | 1,260 | — | `50d5ccab28dcc206…` |

Class coverage on AP is complete except `unigram_rare` (119 of 120: the corpus has exactly
119 terms with document frequency ≤ 2). On CLARK, `changed_content` is **structurally
unavailable**: CLARK-1,161 has 1,161 revisions over 1,157 articles, so only 4 articles have
a second revision. That shortfall is recorded in the manifest rather than hidden, and
changed-content evidence therefore comes from AP, where it is complete.

Stratification on AP:

| candidate count | `<1` | `<2` | `<5` | `<17` | `<65` | `<257` | `<1025` | `<4097` |
|---|---|---|---|---|---|---|---|---|
| queries | 14 | 296 | 301 | 123 | 215 | 189 | 166 | 135 |

| exact phrase df | 0 | 1–2 | 3–10 | >10 |
|---|---|---|---|---|
| queries | 215 | 806 | 83 | 335 |

The workload is not a sample of easy queries: it contains 215 phrases that do not occur at
all and 135 with more than 4,096 candidate documents.

Queries are spread across all four cutoffs (420 / 332 / 339 / 348 on AP) so that a policy
cannot be tuned to one snapshot.

## Three protocols

**A — independent split.** 60/20/20 over query identity (AP: 834 / 324 / 281). Numbers only.

**B — family holdout.** Phrases are grouped into families by containment or ≥ 60% token
overlap, transitively, so `new york`, `new york city` and `york city` land on one side.
AP has 1,024 families; the split is 713 / 492 / 234 templates. A test asserts that no
family appears in two splits. This is the protocol that prevents the near-duplicate leak
that made R174's held-out slice look easy.

**C — temporal holdout.** Selection uses queries evaluated on the **first** cutoff
(1,744 of 10,009 AP revisions) and evaluation uses the **last** (all 10,009). Templates
whose evidence does not exist yet at the first cutoff are excluded from selection: a
`changed_content` query records `observed_at_cut`, the first cutoff whose revision set
already contains the removal, and a test asserts none of them enter the selection set
early.

## Freezing

The manifests are written and committed **before** any method in rounds 181–183 runs.
Every later result records the `workload_sha256` it was measured against, and loading a
result with a different digest is refused. A template is a dict of phrases, operator,
class, strata and evaluation cutoff; the digest covers all of it.

## Paired measurement

Each query is measured under every arm, in a shuffled order, and results are stored
per query. Comparisons are paired within a query — the same query, the same cutoff, the
same active set — so an arm cannot look better merely because it was run on an easier
mixture. Per-query latency, candidate counts before and after rejection, source reads and
decoded bytes are retained, and median / P95 / P99 / maximum are reported per split.

## Limitations

* One cutoff per query for protocols A and B; the workload is spread across cutoffs rather
  than repeated at all of them, to keep evaluation cost bounded.
* `absent_phrase` queries are evaluated at the cutoff whose vocabulary they were drawn
  against, because absence is a property of a cutoff. A phrase absent early can exist
  later; the manifest records `absent_at_cut` so this cannot be mistaken for a claim about
  the whole corpus.
* CLARK cannot support `changed_content` at this scale (4 multi-version articles), so the
  temporal evidence for that class is AP-only.
* Each template carries one operator; AND/OR interaction is measured only through the
  `and_or` class, not across all classes.
* The workload is generated from English news text in both corpora. Transfer to other
  languages and to code corpora is not evaluated here.
