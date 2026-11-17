# CDG Living Research Record: Rounds 33–43

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
