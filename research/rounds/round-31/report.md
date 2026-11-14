# Round 31: Immutable Evidence Snapshots, Stale Receipts, and Update Amplification

**Research date:** 13 November 2026  
**Executed:** local Python 3, actual SQLite contentless FTS5 and independent Zstandard frames; ten unit tests and one five-report update benchmark.  
**Status:** snapshot-integrity integration result, not authenticated origin freshness, not official HotpotQA QA, not distributed transaction safety and not a novel compression algorithm.

## Why this branch won

Rounds 26–30 sought smaller compressed reads and better joint retrieval efficiency. The actual file-backed tests repeatedly showed that compressed-byte reduction and total latency differ, while Round 30 identified duplicated plaintext in the FTS5 schema. The more fundamental remaining problem is **whether a byte-perfect citation can be stale because its search index, link graph or source version changed**. This round makes source-version identity a requirement of the physical acquisition interface. The next claim about evidence correctness cannot rest on a hash alone without specifying which generation the hash belongs to.

We could have added a neural controller, but there is no held-out complete-evidence benefit supporting that complexity. Instead, this experiment treats `(FTS postings, line-offset receipts, title-link sidecar, compressed frames, source manifests)` as a *single publication unit*. A reader pins the unit and is not allowed to mix identities across generations.

## Implementation and contracts

`experiments/round-31/snapshot_store.py` and its dependent snapshot-local FTS5/zstd modules implement:

1. **Staged generation:** build a private directory containing a contentless SQLite FTS5 source index, exact byte offsets, Zstd frames, source SHA-256 metadata, and a title-link table made solely from the source collection. Verify each source's current hash again before publishing.
2. **Sealed manifest:** record the generation UUID, schema, source identities/hashes, compressed-file hash, database hash and link count. Synchronize the files and directory before a rename to a published immutable generation directory.
3. **Atomic local pointer:** replace a small `CURRENT` pointer by `os.replace()` only after the new directory has been built. This is a single-writer local POSIX protocol, not a proven crash-recovery implementation under every filesystem or hardware failure.
4. **Pinned reader:** resolve `CURRENT` once, verify the two data-file hashes at open, and open read-only immutable SQLite plus a compressed payload file descriptor belonging to that same generation. Old readers can continue using old generations after updates.
5. **Generation-bound receipt:** return `(generation, source_id, source_sha256, raw_start, raw_end)` and reject an old-generation or wrong-source-digest receipt when used on the new reader. Selected bytes come from the physically pinned Zstd frames.

The link sidecar built by this toy snapshot store recognizes canonicalized **filenames**, not encyclopedia titles. On the five report inputs its link count is zero. That is not an evaluated negative result for actual title-link indexes. The separate Round 30 HotpotQA analysis produced 403 edges, but has not been run through this snapshot code.

The implementation has no users or permissions. An attacker with write access to the archive can modify source/manifest/hashes together; a SHA-256 digest stored beside the data is **not authentication**. This system also does not fetch a trusted origin's latest version, so a *consistent but old* generation is possible and deliberately allowed. A source modified after a reader opens is not rechecked on each read. There is no rollback log, cross-process writer lock, garbage collector, ACL, signed manifest or validated recovery from a hard power loss. In-flight input mutations may still need a filesystem-consistent input snapshot rather than hash rechecks. These limitations define the current system boundary.

## Executed tests

Ten local `unittest` cases passed:

- Exact Unicode line readback, frame reconstruction and observed title-edge lookup.
- Old reader pinned across a source update; new reader sees new source and new link table.
- Stale receipt refused against a new generation, including unchanged-content republish with different generation identity.
- Simulated publication failure before pointer replacement leaves the prior generation current.
- Corrupt SQLite and compressed-frame payload rejected at reader opening.
- Tampered source digest, out-of-bounds intervals, duplicate input names and empty input set rejected.
- Deleted original inputs do not invalidate the pinned historical archive. Consistent old snapshots are not misrepresented as current-origin freshness.

The tests use authored small fixtures and ordinary process-level faults. They do not emulate concurrent writers, disk-sector faults, unexpected machine shutdown or cross-host cache invalidation.

## Physical update trial

The benchmark builds the same storage schema for **five local CDG technical reports from Rounds 24–28**, with no HotpotQA data. Filenames are disambiguated in a temporary directory and the original reports are not changed. It publishes a first 512-byte-frame snapshot; runs 15 source-derived lexical queries; appends one line to one source; publishes a second entire generation; then checks stale receipt refusal, old-reader continuity and new-source visibility.

| Observed quantity | One local execution |
|---|---:|
| Input source bytes | 63,869 |
| Initial SQLite + compressed payload | 181,633 B |
| Of which SQLite | 139,264 B |
| Of which compressed payload | 42,369 B |
| First full build | 31.36 ms |
| Changed-source full rebuild | 29.01 ms |
| Two retained generations, manifests, pointer | 365,879 B |
| Mean compressed frame bytes per top-five request | 2,185.7 B |
| Warm median search + decode, 15 queries | 240.4 µs |
| Warm p95 search + decode, 15 queries | 503.6 µs |
| New reader rejects old receipt | Yes |
| Old reader preserves pinned result after switch | Yes |
| New reader finds added source line | Yes |

These timings describe one machine, one run, warm caches, small manually chosen topic terms, and Python overhead. **They are not statistically stable performance findings**. Input reports have different length and query distributions from ordinary RAG retrieval. Because a full generation is rebuilt even when a single line changes, the update amplification and retained-history storage are significant. The one changed source represents a tiny fraction of the corpus, but a full **181 KB** new-generation payload+index is written and the archive stays approximately **366 KB** while both generations are retained.

Both the old and new snapshots are required to support existing pinned readers and citations. Eagerly deleting the old snapshot invalidates them; retaining every generation makes space consumption grow linearly with update count. A reader-reference or lease-aware garbage collector and a source-segment deduplication scheme are necessary before claiming acceptable recurring update cost.

## Graph-of-thoughts: interactions and decisions

### H31-A: Immutable provenance is an interface contract, not a performance feature

All source-acquisition actions should return a receipt bound to a *generation*, with exact original byte offsets and a source digest. An evidence planner cannot silently combine documents from generations if its evaluation assumes a single coherent source state. The generation receipt is operationally meaningful even when a source's text is unchanged. However, generation consistency alone does not establish external truth, authority, freshness or entailment.

### H31-B: Copy-on-write metadata creates a new compression bottleneck

A source mutation should ideally rewrite only impacted source frames and affected postings/edges. Building a whole new SQLite DB duplicates almost all FTS postings and stored metadata. Immutable fragments or LSM-style segments could lower update amplification, but may increase query fan-out, tombstone complexity and index-storage overhead. This is standard database/storage design, not a new compression theorem.

### H31-C: Deduplicating frames requires source/version discipline

Identical compressed plaintext frames can be content-addressed across generations, and references to these frames can be immutable. But sharing a frame does not make a source authority-independent. The signed or trusted source manifest still needs a `(source, version, span)` mapping; authorization is enforced at the source edge, not inferred from the presence of shared bytes. Future compression savings must include content-hash index and reference-count metadata.

### H31-D: Title links must be first-class versioned data

A link `A → B` depends on source A's content and B's title normalization. Updates to either can invalidate an edge or its destination. A live link graph should record source-version and destination-identity, or be rebuilt as part of a new immutable generation. This round tests this only with filenames on authored fixtures. True multihop source title-link update effects on the authentic HotpotQA corpus remain unmeasured.

### H31-E: A snapshot consistency check is distinct from an evidence truth check

A passage can be byte-perfect but semantically irrelevant. A link can be exact yet only appear in a negated or quoted sentence. A source can be old but internally self-consistent. Therefore use independent evidence labels: `byte_identity`, `generation_consistency`, `origin_authority`, `relation_supported`, `witness_complete`, and `answer_supported`. Only the first two receive direct implementation support in this round.

### H31-F: The potential efficient frontier is multi-objective

For a versioned retrieval engine, evaluate:

\[
J = \alpha E[C_{\mathrm{query}}] + \beta E[C_{\mathrm{update}}] + \gamma D_{\mathrm{current}} + \delta D_{\mathrm{retained}} + \rho P(\mathrm{invalid\ receipt}).
\]

Current evidence does not determine these weights. Hard safety requirements should instead reject invalid receipts before trading off remaining costs. If a simpler segmented contentless index with immutable source frames dominates a custom hypergraph planner in quality, cost and update safety, discard the more elaborate controller.

## Prior art and novelty boundary

- SQLite FTS5 **contentless**, **contentless-delete** (available from SQLite 3.43.0), and external-content update semantics: https://www.sqlite.org/fts5.html . SQLite's contentless-delete functionality may improve incremental updates but does not itself solve atomic multi-file snapshot publication.
- Zstandard seekable compression and independently decodable frames: https://github.com/facebook/zstd/blob/dev/contrib/seekable_format/README.md .
- Copy-on-write snapshotting, immutable generations, reader pinning and atomic pointer swaps are established storage practices. This implementation does **not** claim invention of those techniques.

The defensible contribution of Round 31 is a **tested correctness boundary and a measured update-cost warning** for the CDG prototype. It does not establish a novel information-retrieval architecture or compression advantage. The failure criterion is whether a simpler versioned FTS5+seekable-Zstd baseline recovers the same evidence at lower total costs.

## Reproduce

Python 3.10+, SQLite with FTS5, host `libzstd` shared library. No PyPI `zstandard` package or online access required for the local tests.

```bash
cd experiments/round-31
python -m unittest -v test_snapshot_store.py
python benchmark.py \
  --files /path/to/round24-report.md /path/to/round25-report.md \
          /path/to/round26-report.md /path/to/round27-report.md \
          /path/to/round28-report.md \
  --output results_reproduced.json
```

The checked-in `results.json` contains one local run with hashes of the original five reports. Host timing values will vary. This round does not bundle the full upstream HotpotQA corpus, and the earlier 100-question physical evaluation remains unexecuted.

## Round 32: specific falsification gates

1. **Input provenance:** obtain the pinned full-context HotpotQA subset and run Round 30's physical FTS5/bridge reader locally. Compare document and sentence recall against Round 25's independent BM25 implementation; never equate the different scoring functions.
2. **Versioned incremental baseline:** compare immutable *per-source* compressed frame files + contentless-delete FTS5 update against the current full-copy rebuild. Include a controlled crashed-write/restart test and old reader pinning.
3. **Retention frontier:** quantify storage of ten generations under no sharing, frame deduplication and metadata-segment reuse, plus reader-aware GC. Report update amplification, query p50/p95, stored footprint and stale receipt rejection.
4. **Authority:** add a trusted external manifest and scope/ACL checks before any claim of source freshness or authorization.

**Decision:** KEEP the simplest immutable-snapshot interface. NO-GO on any assertion of source authority or complete crash safety. Prioritize input access and incremental mutation costs before adding more graph-control mechanisms.