# External systems inspected (R176)

Clones live outside the repository (`/tmp/external`, not committed). No external
source code is vendored or copied; the measurements in `report.md` come from
independent implementations of the published layouts, checked by
`tests/test_external_codecs.py`.

| Project | Pinned commit | Licence file at HEAD | What was read | Why it matters here |
|---|---|---|---|---|
| `pisa-engine/pisa` | `775ad8a889b8205df4b82f69283ec2a4f06610dd` | `LICENSE` | `include/pisa/codec/` listing (`simdbp.hpp`, `compact_elias_fano.hpp`, `optpfor.hpp`, `streamvbyte.hpp`, `maskedvbyte.hpp`, `interpolative.hpp`, `block_codec.hpp`), `SimdBpBlockCodec::m_block_size = 128` | Confirms the block size and per-block width policy used for the SIMD-BP128 baseline, and that PISA's codecs are document-list codecs only |
| `lemire/SIMDCompressionAndIntersection` | `b809f38b57fa65384166c7c1d83056395a1ff3e5` | `LICENSE` | repository layout (source clone used only for the licence and block-size corroboration) | Reference implementation lineage for SIMD-BP128 / FastPFor |
| `RoaringBitmap/CRoaring` | `1e4a304aebdd8de78c93f251b9fc002c717505b9` | `LICENSE` | `include/roaring/containers/array.h` (`DEFAULT_MAX_SIZE = 4096`), `roaring.h` | Container switch threshold used by the Roaring baseline |
| `facebook/folly` | `af9c96500b09d6d09a08bd9b44e157b968fa5c16` | `LICENSE` (Apache-2.0) | `folly/compression/elias_fano/EliasFanoCoding.h`: `kSkipQuantum` (0 = disabled), `skipPointers`, `forwardPointers`, `fillSkipPointersUpTo` | Confirms that production Elias-Fano carries skip/forward-pointer metadata; our baseline charges the plain layout only, which is therefore an *optimistic* (smaller) Elias-Fano |

PISA, folly and SIMDCompressionAndIntersection are Apache-2.0; CRoaring is dual
Apache-2.0/MIT. Nothing from them is included in this repository, so no licence
obligations attach to the archive code.

## Literature consulted

* S. Kuruppu, S. J. Puglisi, J. Zobel. *Relative Lempel-Ziv compression of genomes
  for large-scale storage and retrieval.* SPIRE 2010, 201–206.
* C. Hoobin, S. J. Puglisi, J. Zobel. *Relative Lempel-Ziv factorization for
  efficient storage and retrieval of web collections.* PVLDB 5(3):265–273, 2011.
* G. Ottaviano, R. Venturini. *Partitioned Elias-Fano indexes.* SIGIR 2014, 273–282.
* G. E. Pibiri, R. Venturini. *Techniques for inverted index compression.*
  ACM Computing Surveys 53(6), Article 125, 2020.
* D. Lemire, L. Boytsov. *Decoding billions of integers per second through
  vectorization.* Software: Practice and Experience 45(1):1–29, 2015 (cited by
  PISA's `simdbp.hpp`).
* A. Anand, S. Bedathur, K. Berberich, R. Schenkel. *Index maintenance for
  time-travel text search.* SIGIR 2012, 235–244.
* A. Anand, S. Bedathur, K. Berberich, R. Schenkel. *Temporal index sharding for
  space-time efficiency in archive search.* MPI-I-2011-5-001, 2011.

## Feature mismatches that forbid a fair "win"

| System / method | Historical retrieval | Exact source reconstruction | Versioned/phrase semantics | Verdict |
|---|---|---|---|---|
| PISA, FastPFor, SIMD-BP128, Elias-Fano, Roaring | no (static document list) | no | no | **Size-only comparison** on the same posting data; never a runtime or feature win |
| RLZ (Kuruppu/Hoobin) | no | yes (decompress a string) | no (no historical cutoffs, no phrase positions) | Comparable only to our *source* layer; R149/R155 already benchmark against RLE/LZ-style baselines |
| SQLite FTS5 | yes (via time-travel shards, our design) | via our source layer | yes | Feature-matched; the only baseline we claim timing against |
| Lucene postings (FOR/PFor-delta blocks) | no (static index) | no | no | Same size-only treatment as PISA; block/FOR policy is what R173's `bp`/`best` codecs already implement |

Consequence for the paper: the only feature-matched competitor is native FTS5 plus
our own prior rounds. Every compressed-index number is a *component* comparison and
is labelled as such in `BASELINE_COMPARISON.md`.
