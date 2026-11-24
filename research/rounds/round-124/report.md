# R124: Exact temporal position vectors and bounded gap-splice patches

Status: pending original-source CI.

R123 term-frequency-only layouts are not positional substitutes for FTS5.
Extract all Unicode61 positions from original sources. Compare per-version
position vectors, coalesced identical local-ordinal vectors, direct versus
hybrid blocks, and bounded patches against the latest literal gap vector
within the same term/article. Patches encode common prefix/suffix lengths
and literal middle gaps; only use when shorter than a full vector. Depth
at most one, no cross-article anchors. Persisted vectors are expanded against
every original revision; coverage counts and complete interval equality
checked. Exact phrase counts including overlaps and repeated terms come
from positional intersections and are independently checked with native
FTS5 phrase counts on rebuilt active indexes. Compare native historical
full-detail FTS5, same version/article metadata, source payload excluded.
The query plan adds two-/three-token phrases and mixed AND/OR probes.
Three randomized warm timing passes; Python decoder, prepared active maps.
No NEAR, prefix, NOT, arbitrary grammar, online updates, WAL, independent
corpus, real access trace, or novelty claim. Gap coding, delta coding and
temporal coalescing are established.
