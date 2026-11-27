# Novelty audit

Honest accounting of what is prior art, what is our adaptation, and what — if
anything — is original. The short verdict: **no new data structure and no new
algorithm.** The contribution is a measurement-driven selection method and a
set of negative results, and it should be positioned as a systems/measurement
study, not as an algorithmic breakthrough.

## Component by component

| Component | Prior art | Our use | Status |
|---|---|---|---|
| Versioned / time-travel text indexing with historical cutoffs | Anand, Bedathur, Berberich, Schenkel, *Temporal index sharding for space–time efficiency in archive search* (MPI-I-2011-5-001); *Index maintenance for time-travel text search* (SIGIR 2012) | Each revision is a generation; a snapshot at cutoff *c* is the revision chain prefix; DDR/BM25 recomputed over the active set | **Established method**, our implementation |
| Relative Lempel–Ziv / dictionary source compression | Kuruppu, Puglisi, Zobel (SPIRE 2010); Hoobin, Puglisi, Zobel (PVLDB 2011) | R149 marginal recipe: per revision, choose full frame or one-hop delta against the same article, all charged | **Adaptation** of RLZ-style relative compression, not new |
| Frequency postings with value packing + Zstandard | Pibiri & Venturini, *Techniques for inverted index compression* (CSUR 2020); Varint-G8IU, Simple8b, stream-vbyte | R158/R170 frequency index; 27.3% smaller than raw Elias–Fano on our postings | **Engineering**, established components |
| Block-addressable postings, FOR/PFor node blocks, block-max skipping | Lucene postings; PISA `simdbp`; Ottaviano & Venturini (SIGIR 2014) partitioning; Ding & Suel block-max WAND | R173 fixed blocks of 32–512 postings over **positions**, compact per-term directory, candidate-aware activation | **Adaptation**: the block structure is textbook; applying it to *position* postings inside a versioned archive, and charging its directory, is the new arrangement |
| Elias–Fano, SIMD-BP128, Roaring bitmaps | Vigna (WSDM 2013); Lemire & Boytsov (SPE 2015); Chambi et al. (SPE 2016) | Baselines only, reimplemented from specification | **Not ours**, not claimed |
| Selective positional materialization | Long-standing practice in IR engines (positions only for some fields/terms); R172 in this programme | R174/R175: choose the term set by **measured marginal position bytes** and **expected candidate rejection**, under a storage budget, with a Pareto frontier instead of a weighted score | **Adaptation**, but the accounting discipline is the contribution |
| Workload-trained index configuration | Learned/adaptive indexing literature exists broadly; we make no general claim | Train on a hash-split third of the frozen query plan, validate on a second, report held-out separately | **Methodological**, no novelty claim |
| Joint source + index + reconstruction budget | Each piece separately is known; the joint contract (exact bytes back, exact ranks, all metadata charged) is not commonly reported in one measurement | R173–R177 | **Our framing** — the most defensible original element |

## What can honestly be claimed as original

1. **The accounting contract.** Every persistent structure — block directory, term
   rows, lexicon, page slack — is charged against one archive byte count, while
   source reconstruction stays byte-exact and ranking stays oracle-exact. Most
   selective-index papers report index bytes only; the difference here is measured
   and material (the directory alone is 496,808 B, and term rows another 1,075,992 B
   on AP).
2. **Cost-based term selection by measured marginal position bytes with a rejection
   benefit model**, evaluated as a Pareto frontier at six budgets, with the honest
   finding that statistics-only policies lose badly (best statistics-only point
   14,266,368 B / 21,621 µs vs trained 14,503,936 B / 7,054 µs).
3. **Two negative results with numbers**: (a) regional/tiered native mirroring is
   dominated by a global native positional index at every size tested (R175);
   (b) document-frequency-based selection is cost-ineffective — spending 12.6% of the
   archive on the 32 most frequent terms cuts p95 not at all (25,825 µs vs 24,267 µs
   baseline).
4. **A reproducibility artefact**: pinned manifests, deterministic query plans,
   oracle-checked rankings, CI matrices, and raw result JSON per configuration.

## What cannot be claimed

* Any new compression codec, new integer encoding, or better bit-packing.
* Any asymptotic improvement in query time or space.
* A general result about selective indexing beyond these two corpora.
* Superhumanity over PISA/FastPFor/Lucene: not built, not executed, not
  feature-matched.
* Submodularity of the selection objective (measured false: benefit is a threshold).

## Closest prior work and the remaining gap

The nearest framing in the literature is selective/tiered positional indexing over
versioned collections: choose some terms to carry positions, serve the rest from
another source. That idea is not new. What is missing from the literature — and what
this work adds — is (i) the joint byte accounting including directories and rows,
(ii) a rejection-model-based value function rather than document frequency, and
(iii) measured evidence that the natural "hot region gets a native index" alternative
does not pay for itself. That is a modest, defensible contribution for a measurement
paper; it is not a headline result.
