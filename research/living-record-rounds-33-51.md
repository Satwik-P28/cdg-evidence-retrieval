# CDG Living Research Record: Rounds 33–51

**Updated:** November 17, 2026. This compact continuation index complements research/living-record-rounds-19-32.md and the individually linked reports below. Read the reports and raw experiment artifacts for methods, exact denominators, caveats and provenance. A new round is not proof of novelty or superiority.

## Research question still open

Can a system combine version-accurate, compressed source storage with evidence-complete, temporally valid acquisition so that supported answers improve at matched total latency, memory, update cost and storage against strong conventional systems?

**Current answer:** Unproven. Some components demonstrably reconstruct bytes and maintain identities. Synthetic tests expose retrieval/verifier failures. A fair cost-and-quality win on independent real-world queries has **not** been established.

## Round ledger

| Round | Core experiment or insight | Evidence status | Decision |
| --- | --- | --- | --- |
| [33](rounds/round-33/report.md) | Weighted evidence cover; bounded combinatorial search and prime-size frame negative control | Seeded synthetic optimization, five-report compression control | Avoid number-theoretic performance claims |
| [34](rounds/round-34/report.md) | Stronger local evidence-cover optimization can worsen real coverage under noisy facet predictions | 300 synthetic scenarios | Prioritize validated evidence acquisition |
| [35](rounds/round-35/report.md) | Classical transfer of quantum-inspired concepts; annealing, tensor networks, symmetry residuals and receipts | Bounded classical tests, no quantum execution | Gate all hybrid components against simple baselines |
| [36](rounds/round-36/report.md) | Cheap screening reduces verification cost but loses supported-answer coverage and degrades under shift | Seeded synthetic 3,000-case calibration/test partitions, assumed cost units | Reject uncalibrated cheap-accept shortcuts |
| [37](rounds/round-37/report.md) | Version receipt ensures byte consistency, not fact validity; synthetic stale-document counterexample | 900 synthetic cases | Separate temporal applicability from version identity |
| [38](rounds/round-38/report.md) | Exact as-of lookup retrieves historical source lines in real Git revisions | 12 authentic README versions; 77 self-derived line membership queries | Simple time filtering is a strong baseline for this narrow task |
| [39](rounds/round-39/report.md) | High lexical overlap can hide meaning-altering edits | Authentic diff events + six constructed adversarial pairs | Do not infer proposition identity from similarity |
| [40](rounds/round-40/report.md) | Separate changed citation target from visible claim edits | 54 authentic edit events, limited parser; selective audit | Source-reference review can be a distinct lane, subject to escalation |
| [41](rounds/round-41/report.md) | Temporal queries often describe intervals and set-valued relations, not a single point | 260 within-dataset structural QA variants; 133 strict-window unique matches, 127 abstentions | Treat temporal ambiguity and conflicting validity as explicit states |
| [42](rounds/round-42/report.md) | Four architectures: global snapshots, global+CAS, shards+CAS, hybrid | 32 multi-generation scenarios on 5 internal reports and identity replicas | No dominant architecture; better conventional controls required |
| [43](rounds/round-43/report.md) | Row-ID FTS5 incremental global control, no-op edit correction, 48-scenario planned grid | **Three local standalone unit tests passed; full grid not yet run** | Hold any adaptive architecture claims until fair benchmark |

## The connected hypothesis graph

**Evidence reliability track:** R33 evidence cover → R34 fallible facets → R36 risk/cost gate → R37 temporal staleness → R38 real-source membership → R39 claim-change mismatch → R40 citation-target audit → R41 interval ambiguity.

**Source systems track:** R30 contentless FTS5 → R31 immutable snapshots → R32 source CAS/index reuse → R42 sparse/dense storage Pareto frontier → R43 indexed line-level SQLite control → future independently held-out version history and optimized snapshot control.

**Integration hypothesis:** a source receipt can bind the exact bytes and generation used in verification, while a separate temporal/semantic layer decides what those bytes actually support. Both are necessary for some tasks but **neither implies** the other, and conventional retrieval plus immutable source storage may already be sufficient.

## Highest-priority falsification tests

1. **Fair historical cost:** Run Round 43 full grid, then add a properly durable, page-level or copy-on-write conventional history baseline. Be aware that SQLite session changesets do not directly capture virtual FTS5 edits.
2. **Real evidence:** Use a held-out, independently annotated QA dataset with full source passages and actual retrieval, separating source identity, complete witness recovery, entailment and false acceptance.
3. **Real revisions:** On authentic timestamped source histories, compare temporal SQL and BM25/time filtering with CDG. Treat valid time and observation time distinctly.
4. **Integrated cost:** Charge indexing, version snapshots, compression, decompress/read traffic, reader/model tokens, verification, migration, abstention and update cost.
5. **Stop rule:** If an optimized conventional pipeline matches or Pareto-dominates CDG, simplify the system and document the negative result.

## Evidence hierarchy

- **Verified within a narrow experiment:** local unit tests, executable structural reconstruction checks, explicitly scoped seeded/synthetic outcomes, internally derived line counts.
- **Unverified:** universal compressor improvement, new RAG accuracy state-of-the-art, semantic entailment correctness, robust risk guarantee under shift, production SSD speedups, optimal adaptive routing.
- **Research practice:** retain failures and negative results; never turn seeded toy improvements or model-assisted analyses into unsupported publication claims.

**Current action:** Complete Round 43 correctness and numerical replication, then select one falsifiable end-to-end experiment rather than expanding unrelated architecture components.


## Experimental research rounds 44–51

| Round | Intervention and test | Result and limits |
| --- | --- | --- |
| [44](rounds/round-44/report.md) | Six FTS5 maintenance, diff and history-retention combinations; 48 seeded scenarios | Current-only index minimized update costs (2.885 ms median), but uncached old-generation query p50 rose to 7.717 ms versus 0.299 ms for snapshots; no universal store |
| [45](rounds/round-45/report.md) | Gold-ID-blind retrieval on 91 TimeConflict source records, 260 question variants | BM25 got source row in 260/260 easy templated questions; temporal point-date 227/260 correct, strict full-window 133/260 correct, zero strict mismatches but 127 abstentions; not independent entailment |
| [46](rounds/round-46/report.md) | Eight archive layouts, 12 authentic uv README revisions, 192 sampled byte-span reads | Content-defined frames trade reduced storage and read amplification versus whole Zlib; Git pack remains smaller storage-only; no new compressor |
| [47](rounds/round-47/report.md) | Four frame layouts × six manifest encodings | Gear512 binary-Zlib archive 17,769 bytes vs raw JSON 31,386; cold in-memory manifest parse trade-off remains |
| [48](rounds/round-48/report.md) | FTS5 + exact byte-span compressed reader + generation receipts | 276 source spans retrieved from 120 source-derived keyword queries; index 196,608 bytes dominates compressed source archive; not independent QA |
| [49](rounds/round-49/report.md) | Six historical FTS5 index densities with actual BM25 and phrase parity | Smallest 131,072-byte index preserves keyword row sets but BM25 exact top3 only 24/120 and no phrase support; full detail preserves 120/120 |
| [50](rounds/round-50/report.md) | Slim old FTS + full current index, rebuild old full index on rank/phrase request | 155,648 vs full 196,608 bytes (20.8% reduction), with 120 rank and 36 phrase parity on test corpus but ranked p50 927 us vs 27.4 us; global IDF equivalence not assured |
| [51](rounds/round-51/report.md) | LRU cache capacity 0/1/2/4/12, hot/uniform/recent synthetic historical query streams | See Round 51 report for completed numbers; count rebuild cost and SQLite page memory, not assumed savings |

### Connected hypothesis graph

**Indexing:** R30 contentless plaintext deduplication → R43 row-ID edits → R44 diff/history Pareto → R49 reduced posting detail breaks rankings → R50 two-tier with paid full-search fallback → R51 workload caching.

**Compression:** R32 generation-pinned source CAS → R42 global-shard tradeoffs → R46 framed/delta comparison → R47 compact manifests → R48 exact source-span retrieval. Smaller archive is not necessarily smaller total RAG indexing system. Git pack baseline wins archive-only size.

**Evidence validity:** R34 inaccurate facet predictions → R36 verifier shift failure → R37–41 time/edit/applicability → R45 conventional BM25 already solves a narrow source-selection test. Byte consistency does not establish factual support, temporal validity, source authority, or calibrated risk.

### Promotion and publication gates

- Keep simple conventional baselines for all studies. Retrieval claims require held-out real questions and graded supporting evidence, not exact keyword parity alone.
- Measure a full-system cost function: archive, FTS index, historical cache, updates, decompression, model/verifier tokens, latency, supported-answer rate, false acceptance and abstention.
- Account for peak cache memory and cold starts, with authentic query/update traces and independent source histories.
- Source licensing is documented in LICENSE-NOTE.md and retained third_party notices.
- This repository remains experimental research, not a production release, peer-reviewed paper, state-of-the-art RAG model, or proven new compression algorithm.
