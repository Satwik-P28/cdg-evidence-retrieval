# Formal contract and proof obligations (R148)

Status: implementation-linked proof sketch; not a mechanized proof. Scope: valid archives created by cooperating local writers, strict UTF-8 extracted source texts, deterministic codec configuration, SQLite transaction semantics, successful fsync and immutable committed sidecar prefix. No power-loss experiment, malicious publisher authentication, whole-commit atomicity, deletion, garbage collection or arbitrary vector queries.

## 1. Source reconstruction and cost bounds

Let X_i be the exact retained source bytes, n_i their length, F_i the independent Zstandard frame and f_i its size. A literal stores F_i. A delta stores D_i encoded against an earlier literal revision j of the same article, with encoded size d_i. The fixed policy admits only candidates with:

- n_i + n_j <= 2.5 n_i
- d_i + f_j <= 1.5 f_i
- d_i <= 0.8 f_i

Candidates are the four newest earlier literals, and the smallest eligible encoded delta wins (newest tie). Otherwise store a literal. Empty sources use the literal fallback; decoded ratio defined only for nonempty requested sources.

Proposition: every valid nonempty revision has depth <=1, logical decoded work <=2.5 n_i and logical activated frame bytes <=1.5 f_i. Proof: literal recovery decodes only X_i and activates F_i, with ratios 1. Delta recovery first reconstructs literal j, then decodes D_i with X_j as dictionary. By admission, the two byte sums satisfy the inequalities; there is no recursive delta parent. Exactness follows from correct lossless codec operation, checked source length and SHA-256 digest. The bound is per requested revision, not actual decompressor allocations, CPU cycles, physical page reads, cache misses or batch wall time. Summing per-request inequalities bounds aggregate no-cache logical work relative to summed request bytes. A depth limit alone does not bound n_j/n_i or f_j/f_i.

Proposition: exact encoded-frame reuse preserves those logical costs and source outputs. For a selected frame D_i or F_i, the catalog pointer is reused only after checking committed-prefix bounds, exact length and byte equality. Every revision retains its own parent, depth, length and source digest. Replacing a frame pointer with an equal-byte pointer leaves codec input and dictionary unchanged. The physical frame extent can be shared even if distinct revisions use different dictionaries. No cross-revision identity is inferred from compressed equality.

## 2. Transactional visibility

Define committed high-water E, sidecar identity, frame catalog, revision rows, origin rows, positional index, heads, rank ledger and origin ledger as SQLite-committed state. Invariant: catalog extents partition [header,E); each revision pointer names an extent; all visible revisions have corresponding index and ledger entries; old extents are immutable.

Inductive step: BEGIN IMMEDIATE serializes cooperating writers. Reconciliation truncates only bytes beyond the committed E; pinned readers reference an earlier prefix E' <= E. A new frame is written at E and synchronized before metadata commit. A reused frame already lies within committed E and is byte-verified. Catalog insertion (if new), revision, source, origin, index and rank/triggered origin ledger, heads and high-water are committed atomically by SQLite. Before commit, new bytes may exist but no visible row points to them; after commit the newly visible metadata references an already synchronized frame or immutable prior frame. On exception, the writer rolls back; it must not truncate based only on an ambiguous commit outcome. A fresh write transaction observes resolved SQLite visibility, then reconciles safely. The induction assumes a successfully initialized archive, cooperating writers, correct SQLite and filesystem behavior and a durable synchronized frame; it is not a proof against arbitrary hardware faults. Process-death cases R137/R143/R145/R147 empirically exercise specific stages.

## 3. Historical ranking

For cutoff c, active revision per article is the maximum generation <=c. FTS postings contain retained generations; filter positional matches to the active set. Compute active document count N_c, total token count and phrase document frequencies on that set, then use the declared FTS5 BM25 formula and deterministic tie-breaking. Under identical tokenization, positional phrase counts, statistics and ordering, this reproduces rebuilding an FTS5 index over the active documents. Native comparisons test the declared grammar; zero observed numerical error is empirical, not an unrestricted theorem of floating-point equality or arbitrary FTS5 syntax.

## 4. Provenance commitment

Let H be SHA-256 with unambiguous canonical encoding and domain separation. Seed P_0=H(domain_manifest || manifest_bytes). For g>=1, P_g=H(domain_entry || P_(g-1) || canonical(g,article,ordinal,source_digest,origin_id,time,blob_id,rank_prefix)). A v2 receipt includes manifest hash, P_c, ranking body and per-hit origin metadata; its digest must be retained outside the archive. Recompute actual metadata entries through c, verify stored prefix rows, reissue ranking and check exact hit source length/digests and blob hash, then compare the complete receipt to the trusted digest.

If a committed prefix field or manifest changes, the first altered hash input differs. Equal final P_c requires a collision (or second-preimage) in the chain under the hash assumption; recomputing all stored roots does not help against an unchanged external commitment. This does not authenticate the origin publisher. Receipt verification scans metadata and checks returned source frames, not every nonhit frame; full audit is separate. The origin chain commits to the stored rank prefix, not an independent rederivation of every token/index row. Do not claim exhaustive detection of nonhit index corruption or an untrusted index proof. An attacker replacing the external trust root is outside the model.

## 5. Batch equivalence

For a fixed SQLite snapshot and immutable frame prefix, independently verifying receipt cutoffs c_1...c_m recomputes sum(c_i) origin entries. One ordered scan through max(c_i) yields exactly the same prefix states by the recurrence. Retain roots only at requested cutoffs, reissue each original ranking and check each individual trusted digest before returning any results. Therefore successful batch output equals successful individual replay in the same snapshot; metadata scan work becomes max(c_i), while ranking and source verification remain per receipt. No persistent trusted cache, sublinear single receipt guarantee or new cryptographic primitive is claimed.

## 6. Claims and falsification

- Bounds are deterministic admission invariants; observed maxima depend on corpus.
- Git controls may use offline, future and cross-document deltas; no comparable update protocol.
- Strong storage claim must use R148 matched baseline after success; do not extrapolate pending results.
- Source preservation is not relevance or hallucination reduction. CLARK-News latest-only top-10 coverage exceeds historical coverage in the observed sample.
- Commitments are not publisher signatures. Hardware power-loss and independent third-party replication remain untested.
