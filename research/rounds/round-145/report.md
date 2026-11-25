# R145: transactional exact-frame deduplication

Status: implemented, unverified.

Branch from verified R143 rather than the unverified R144 provenance correction. R142 coalesced layouts achieved near-Git storage but only supported finalized readback. Add a SQLite frame_catalog keyed by SHA256 of encoded frame bytes and storing offset/length. Reuse an existing committed pointer only after exact byte equality and committed-prefix bounds checks. New unique frames use the R137 write/fsync/commit protocol; reused frames do not write or sync the sidecar. Catalog and revision metadata commit together. Keep per-revision anchor ordinal/depth, so sharing encoded bytes does not conflate dictionary context. A corrupt catalog entry fails audit; collision with different bytes fails closed. No frame deletion or garbage collection.

Compare matched transactional snapshot/CDG with and without reuse, on both frozen R142 cohorts. Charge catalog and pointer overhead; assert exact R142 coalesced payload bytes and unique frame counts, unchanged logical work, exact source bytes, historical ranks/receipts and pinned-reader stability. Distinct new/reuse crash points, catalog corruption, cross-article duplicates. 17 unit tests per job. Scope v1 receipt only; independent R144 correction is pending. No power-loss, concurrent-writer stress specific to dedup, or provenance authentication claim.

## Initial failure

Both jobs on 3486a9df failed before data acquisition because hashlib was not imported. Corrected import, added static undefined-name check before existing tests. Original run https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45568600037. No dedup measurements yet.


## Partial verified results

Corrected R145 commit 0028b46a: 10,009-revision job passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45691626610); full job still pending at archival. Snapshot 42,846,800 B, snapshot reuse 33,673,706 B, bounded anchor 30,691,764 B, bounded anchor reuse 30,111,765 B. Reuses 3,566 encoded frames, identical logical reconstruction metrics, 40,036 exact reads and 1,024 historical rank comparisons with zero observed score error. Catalog overhead charged. No full cohort claim.
