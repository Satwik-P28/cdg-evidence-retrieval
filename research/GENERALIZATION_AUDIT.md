# Generalization audit

This document records where the earlier rounds' claims came from, why one of them failed
under an honest held-out split, and what evidence now supports generalisation instead.

## The failure that triggered the audit

R174's hosted matrix on the larger AP corpus (run `45926879483`, large-AP job `140270152160`)
reported, for one budgeted arm:

| split | queries | P95 |
|---|---|---|
| training | 59 | 12,973 µs |
| validation | 14 | 178,982 µs |
| held-out | 7 | 1,316,938 µs |

Held-out source reads: 36,816. Training P95 was two orders of magnitude better than held-out
P95 for the same policy on the same archive.

## Why it happened

Three defects compounded:

1. **The workload was not discriminating.** R174's 80 queries came from one corpus-statistics
   template: sixteen terms per frequency band, eight AND/OR pairs, sixteen phrase probes. The
   held-out slice was 12 queries on AP (57/11/12), drawn from the same vocabulary and the same
   generation rule as training.
2. **The split was over queries, not over query families.** Near-identical phrase variants sat
   on both sides, so a policy that memorised a term could look like a policy that generalised.
3. **Selection was additive per term.** A term earned a share of every candidate opportunity it
   participated in. On the small corpus the 20–22 selected terms happened to cover the held-out
   phrases; on the larger corpus they did not, and the policy had no mechanism to cover a phrase
   it had not seen.

The third point is a property of the objective, not bad luck: an additive share model cannot
express "this phrase needs two of its three tokens", which is R183's subject.

## What changed in the evaluation

| before | now |
|---|---|
| 80 queries per corpus | 1,439 (AP) and 1,320 (CLARK) templates, 12 classes |
| 12 held-out queries on AP | 281 held-out (protocol A), 234 (protocol B) |
| one split rule | independent, family holdout, temporal holdout |
| aggregate latency | median, P95, P99 and maximum per split |
| workload described in prose | frozen manifest with a SHA-256 digest and committed strata |
| absent phrases assumed | verified absent through the exact FTS5 oracle at the evaluation cutoff |

The workload is frozen before any method in R181–R183 is run, and every result records the
digest it was measured against. A result whose digest does not match is refused at load time.

## Family holdout (protocol B)

Phrases are grouped into families by containment or ≥ 60% token overlap, transitively, so
`new york`, `new york city` and `york city` cannot straddle a split. AP has 1,024 families;
the split is 713 / 492 / 234 templates. A test asserts that no family appears in two splits.

This is the protocol that would have caught the original failure. Under it, a policy that only
works on the phrases it was fitted to cannot score well, because its held-out families share no
tokens with the phrases that selected it.

## Temporal holdout (protocol C)

Selection uses queries evaluated at the first cutoff — 1,744 of 10,009 AP revisions — and
evaluation uses the last. Templates whose evidence does not exist at the first cutoff are
excluded from selection: a `changed_content` query records `observed_at_cut`, the first cutoff
whose revision set contains the removal, and a test asserts that no such query enters the
selection set early.

## What the new evidence shows

Measured on the frozen workload with the exact FTS5 oracle as the reference, at a matched
~5% physical storage budget:

| corpus | frequency-only P95 | selective positions P95 | selective pairs P95 | improvement |
|---|---|---|---|---|
| AP-10,009 | 388,344 µs | 269,475 µs (1.44×) | 105,639 µs (3.7×) | pairs 2.6× better than positions |
| CLARK-1,161 | 168,171 µs | 159,467 µs (1.05×) | 72,078 µs (2.3×) | pairs 2.2× better than positions |

The pattern is the one the failure predicted. A workload-trained positional selection buys
terms that covered *its own* phrases; on unseen phrases at the same budget it barely moves, and
on AP it does not reduce source reads at all (168,996 before and after). A query-independent
adjacency structure works at the level of token pairs, so an unseen phrase built from familiar
words is filtered without ever having been anticipated.

Two corpus types now carry the claim: AP (news revisions, 10,009 documents, multi-revision
articles) and CLARK (dated news, 1,161 revisions over 1,157 articles). Generalisation across
corpora is demonstrated in the sense that the same structure and the same budget rule produce
the same direction and comparable magnitude of improvement on both.

## What is still not proven

* **No transfer experiment was run.** The selection policies in R183 are fitted per corpus.
  Evaluating an AP-fitted policy on CLARK was specified as "where feasible"; the corpora share
  a language but not a vocabulary, and a term-level policy cannot transfer across disjoint
  vocabularies by construction. This is a negative design finding rather than a missing number:
  term selection is corpus-specific, which is precisely why the query-independent structures
  matter.
* **The larger AP corpus was not re-measured.** AP-100,000 exceeds the available memory in this
  environment (74,364 revisions, 406 MB database). All numbers here are AP-10,009 and CLARK-1,161.
  No claim is made about the 74k-revision scale, and the original failure at that scale is
  reported, not repaired.
* **Only two corpora and one language.** English news in both cases. Code and non-English
  corpora are not evaluated.
* **Timing is warm-cache logical activation**, not physical I/O. A cold-cache comparison could
  change the constant factors, though not the direction: pair rejection removes source reads,
  and a source read costs more when it misses cache.
* **P99 remains heavy-tailed** even for the best arm (AP 369,527 µs at 5%, 81,231 µs for the
  complete index). The 2× P95 target is met by the complete index and by nothing else on AP;
  the 5% budget meets P95 on CLARK and comes within 3.7× on AP.

## Files

* `experiments/round-179/repair.py` — mechanical recomputation of the earlier claims.
* `experiments/round-180/workload.py` — workload generation, strata and the three protocols.
* `experiments/round-180/manifest-ap-10009.json`, `manifest-clark-1161.json` — frozen manifests.
* `experiments/round-181/rejection.py` — rejection structures and their measurements.
* `experiments/round-182/planner.py` — cost-aware execution.
* `experiments/round-183/joint.py` — phrase-level joint selection.