# CDG Living Research Record: Rounds 33–63

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

1. **Fair historical cost:** Round 43's full CI grid was completed; now add a properly durable, page-level or copy-on-write conventional history baseline. Be aware that SQLite session changesets do not directly capture virtual FTS5 edits.
2. **Real evidence:** Use a held-out, independently annotated QA dataset with full source passages and actual retrieval, separating source identity, complete witness recovery, entailment and false acceptance.
3. **Real revisions:** On authentic timestamped source histories, compare temporal SQL and BM25/time filtering with CDG. Treat valid time and observation time distinctly.
4. **Integrated cost:** Charge indexing, version snapshots, compression, decompress/read traffic, reader/model tokens, verification, migration, abstention and update cost.
5. **Stop rule:** If an optimized conventional pipeline matches or Pareto-dominates CDG, simplify the system and document the negative result.

## Evidence hierarchy

- **Verified within a narrow experiment:** local unit tests, executable structural reconstruction checks, explicitly scoped seeded/synthetic outcomes, internally derived line counts.
- **Unverified:** universal compressor improvement, new RAG accuracy state-of-the-art, semantic entailment correctness, robust risk guarantee under shift, production SSD speedups, optimal adaptive routing.
- **Research practice:** retain failures and negative results; never turn seeded toy improvements or model-assisted analyses into unsupported publication claims.

**Current action (superseding the initial R43 instruction):** Finish independent corpus/factual-support evaluation and a cost-accounted end-to-end RAG control. R43–59 component experiments are executable, but do not prove an end-to-end advantage.


## Experimental research rounds 44–53

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

| [52](rounds/round-52/report.md) | Indexed point/batch row-to-span lookup instead of scanning all rows after cached FTS hit | Hot trace cache4 median 178.125 us scan vs 30.831 us batch, same SQLite cache pages and exact tested ranking/phrase output; promoted batch as experimental default |

| [53](rounds/round-53/report.md) | Independently run the original 100-question HotpotQA-derived R25 Python study and compare the independent JS analysis | Exact agreement in BM25, bridge, MMR complete-document counts @2/@3/@5, paired success counts and top2 supporting-sentence totals; same curated training sample, NOT held-out replication |

### Connected hypothesis graph

**Indexing:** R30 contentless plaintext deduplication → R43 row-ID edits → R44 diff/history Pareto → R49 reduced posting detail breaks rankings → R50 two-tier with paid full-search fallback → R51 workload caching → R52 batched row-ID span resolution.

**Compression:** R32 generation-pinned source CAS → R42 global-shard tradeoffs → R46 framed/delta comparison → R47 compact manifests → R48 exact source-span retrieval. Smaller archive is not necessarily smaller total RAG indexing system. Git pack baseline wins archive-only size.

**Evidence validity:** R34 inaccurate facet predictions → R36 verifier shift failure → R37–41 time/edit/applicability → R45 conventional BM25 already solves a narrow source-selection test. R53 independently reproduces R25's stronger title-bridge result on its previously unreplicated pinned authentic 100-question sample, while leaving the held-out generalization question open. Byte consistency does not establish factual support, temporal validity, source authority, or calibrated risk.

### Promotion and publication gates

- Keep simple conventional baselines for all studies. Retrieval claims require held-out real questions and graded supporting evidence, not exact keyword parity alone.
- Measure a full-system cost function: archive, FTS index, historical cache, updates, decompression, model/verifier tokens, latency, supported-answer rate, false acceptance and abstention.
- Account for peak cache memory and cold starts, with authentic query/update traces and independent source histories.
- Source licensing is documented in LICENSE-NOTE.md and retained third_party notices.
- This repository remains experimental research, not a production release, peer-reviewed paper, state-of-the-art RAG model, or proven new compression algorithm.


## Continuation: Rounds 54–61

| Round | Experimental question | Verified result | Research decision |
| --- | --- | --- | --- |
| [54](rounds/round-54/report.md) | Do frozen R25 BM25 and exact-title bridge results survive a separately split official HotpotQA distractor dev sample? | Source SHA256 verified, locked 512 IDs; complete gold docs @2 168 BM25 vs 212 bridge; @5 345 vs 439; no missing annotations in sample; one bad annotation in 7,405 total dev records | Retain bridge as a non-novel, high-value benchmark only; no generated answers |
| [55](rounds/round-55/report.md) | Does exact FTS5 sentence selection and compressed frame materialization beat whole-source read on authentic multihop context? | First 128 questions; 107/128 full docs, only 79/128 complete gold sentences with FTS top2; whole-source compressed archive (482,158 B) smaller than gear512 (504,264 B), common sentence index 708,608 B | Reject naive per-source gear compression and top2 sentence pruning as general solution |
| [56](rounds/round-56/report.md) | Do simple sentence ranker combinations recover support at matched per-document budgets? | Bridge K5 on 128: top2 FTS 79, local BM25 78, title priority 77, random 43; top4 FTS 101 and title priority 103; selective frame read benefits small | No decisive universal sentence reranker |
| [57](rounds/round-57/report.md) | Does allocating at most 10 evidence sentences globally beat assigning 2 to each of five documents? | Two 128 partitions: front allocation 86 and 88 complete sets vs uniform2 79 and 80; balanced 80 and 91; front modestly reduced idealized compressed frame bytes | Exploratory positive signal; must compare to recycled-uniform and confirm on remaining questions |
| [58](rounds/round-58/report.md) | Can online storage+read-cost selection mix whole-source Zlib with content-defined frames as source regimes change? | 1,288 authentic source blobs, 3 input orders. Online read-weighted 487,779 B and 324.169 mean compressed bytes/span vs all-whole 511,165 B and 360.953; storage-only heuristic made no switch | Keep as candidate heterogeneous archive strategy, not a codec or proof of generality |
| [59](rounds/round-59/report.md) | Does front allocation beat **uniform with recycling** on the remaining previously untested 256 sentence-allocation questions? | Front 187/256 vs recycled uniform 183/256, exact paired p=0.618, 95% bootstrap interval of percentage-point gain [-3.125, +6.25]; balanced 191 but also nonsignificant | **Reject promotion of rank-frontloading**; mechanically recycling unused budget is safe but costs extra sentences |

### Updated graph of connected hypotheses

**Question acquisition:** R25 title-link expansion → R53 independent cross-language replication → R54 new official dev split. The title-link advantage is credible *for closed-world HotpotQA distractor document acquisition*, not proof of novel graph reasoning, open-corpus RAG, factual support or answer generation.

**Evidence selection:** R36 cheap verifier misses → R45 temporal/source selection → R55 FTS top2 loses support → R56 sentence reranker variants → R57 global budget exploration → R59 frozen remainder check. The exploratory frontloading gain weakened under a correct recycled-uniform comparator. Keep complete annotated evidence recovery and abstention separate from source confidence and actual answer truth.

**Compression under source heterogeneity:** R46–47 related revisions favor content-defined frames and small manifests → R55 independent short paragraphs favor whole Zlib → R58 mixed-source archive uses online compressed CAS plus estimated read activation. The strongest observed mixed-source candidate improves a small two-dimensional storage/read cost, but remains behind known-cohort routing on stored bytes and behind all-gear on read traffic. Git pack and Zstandard remain mandatory independent controls.

**System-scale cost boundary:** R48 source-span receipts require an FTS5 index much bigger than the compact source archive → R49 reduced index postings can break BM25 order/phrase matching → R50/51 cached historical FTS rebuilds trade memory for latency → R52 batch row-ID fixes hot cache lookup overhead. These must be integrated with R54–59 acquisition quality to support a total cost claim.

### Latest falsification priorities

1. **Independent source families:** held-out multihop QA beyond HotpotQA, plus authentic versioned documents with query-time constraints and evaluator-confirmed supporting passages.
2. **Full cost:** compare vanilla BM25+Git/Zstd/whole source versus conditional content-defined frames, charging index creation, archival manifest, read/CPU/physical I/O, citations, verifier/model tokens, and abstention.
3. **Counterfactual support:** presence of an annotated gold sentence is not a proof that it logically supports a generated claim. Test semantic contradictions, quotation/negation, multi-claim completeness and authority.
4. **Novelty gate:** the title-link heuristic, frame CAS, greedy cost routing and budget recycling are conventional techniques. An original contribution requires a new falsifiable mechanism or a defensible and generalizable empirical characterization that is not already covered by prior art.
5. **Kill/simplify rule:** if the conventional simple pipeline matches quality and Pareto-dominates at realistic resources, retain the negative result rather than add adaptive components without value.

**Present status:** Rounds 54–61 are executable experimental research. No peer-reviewed acceptance, new compression bound, universal RAG speedup, or hallucination guarantee has been established.


## Strong compression baseline and source-mixture falsification: Rounds 60–61

| Round | Hypothesis tested | Evidence | Outcome |
| --- | --- | --- | --- |
| [60](rounds/round-60/report.md) | Does R58 mixed-source Zlib remain competitive after Zstandard 3/9 and an actual Git pack baseline? | 1,288 authentic sources; Zstd3/9; real Git repo with 13 commits and git gc --aggressive; exact SHA/source span tests | Zlib6 mixed read-weighted archive 487,779 B vs Zstd3 mixed 508,271 B and Git pack+idx 494,194 B, but Git stores commit/tree semantics absent in custom CAS. No strict equivalence or novelty |
| [61](rounds/round-61/report.md) | Does the R58 policy, frozen before testing, improve both archive size and read traffic on 12 new source mixtures? | Last 128 HotpotQA dev question IDs supply 1,280 short source paragraphs; 0/3/6/12 history prefixes × 96/384/1,024 documents; full exact readback | Compressed span traffic improves in all 12, archive bytes improve in only 6/12. Unrelated-source regimes can become 0.7–1.6% larger. Reject a universal adaptive default |

### Revised scientific focus

The evidence graph now has three distinct constraints:
1. **What gets retrieved?** R54 shows frozen title-link expansion improves complete supporting-document recall on a separate HotpotQA split, but gold-containing local candidate pools and no answer generator limit claims.
2. **What must be preserved?** R55–59 show exact byte reconstruction is feasible yet naive snippet pruning loses annotated witnesses, and rank-frontloaded sentence allocation failed strict confirmation against recycled uniform.
3. **How should bytes be stored?** R46–48 related revisions favor framing; R55 isolated short docs favor whole Zlib; R58 observed small mixed-source gains; **R60 and R61 restrict the claim** to a specific source mixture and archive contract. Zstd and Git are serious conventional controls, not straw men.

Next pre-registered work should test source-family relatedness estimates against a **separate timestamped revision corpus**, then couple it to a full end-to-end source-index-and-verification cost. Negative results must remain in the master record. CDG still does not demonstrate novel compression, a calibrated hallucination reduction guarantee, or Pareto dominance over standard complete systems.


## Transfer to independently maintained revision histories: Rounds 62–63

| Round | Study | Executed outcome | Decision |
| --- | --- | --- | --- |
| [62](rounds/round-62/report.md) | Frozen R58 archive policy on genuine pinned source histories from Ruff (12 README revisions), Transformers (12) and Flask (7), each with 0/128/512 previously unused short paragraphs | Ruff+512: 209,393 B vs whole 262,918 (-20.36%); Transformers+512: 205,427 B vs whole 261,985 (-21.59%); Flask+512: 192,454 B vs whole 188,846 (+1.91%); logical compressed read bytes fell in all three | Genuine cross-history transfer for two large highly related histories but one important shallow-history storage counterexample |
| [63](rounds/round-63/report.md) | Frozen 96-byte source shingle overlap gate, three thresholds 0.2/0.5/0.8, 18 combinations with 128/512 independent documents and exact readback | With 512 independent docs and threshold 0.2, gated Ruff = 217,780 B vs ungated 209,393; gated Transformers = 220,405 vs ungated 205,427; gated Flask = 188,990 vs ungated 192,454 (whole 188,846). Gate suppresses valuable history framing in earlier sources | **Reject fixed-threshold gating as universal optimizer**; relatedness must not be conflated with marginal compressed cost or future source reuse |

### Source provenance for R62–63

These version histories are immutable only under their pinned upstream commit cutoffs, and the exact Git blob and SHA-256 digests of every sampled README are recorded in the workflow's JSON artifact. The loader keeps actual distinct historical file states and skips no-op/absent file versions. It never manufactures extra revisions to reach an arbitrary count. Ruff is MIT licensed, Transformers Apache-2.0, Flask BSD-3-Clause. Upstream source text is not distributed as a repo artifact; only digests and metrics are committed.

### Graph-of-hypotheses revision

**Source-family transfer:** R46–47 uv-specific revision compression → R55 unrelated short-paragraph counterexample → R58 heterogeneous routing → R61 different mixture ratios → R62 frozen algorithm replication on three independent upstream codebase histories. The strongest empirical support now concerns structurally related, versioned documents, not arbitrary text.

**Feature test:** R63 simple online local source similarity explains some of the regime distinction but does not consistently predict the correct storage decision; it is sensitive to history depth, arrival order, chunking crossover, manifest overhead and unseen future reuse. More thresholds on the same inspected source histories would be overfitting, not stronger evidence.

**Alternative research directions, without promotion:** (a) bounded retroactive source-family recoding when a second genuinely related revision arrives; (b) a source-version aware archive reference baseline with Git pack or common Zstd frames; (c) query-weighted decoding under actual historical retrieval traces rather than random byte slices; (d) temporal and factual support verification over truly independently scored QA claims.

**Hard publication gate:** Any proposed improvement must outperform standard reference mechanisms at the same *logical data and version semantics*, with all source index, archive, update/recompression, model-token and verifier costs charged. Neither byte-exact source reads nor gold sentence identity implies factual entailment or absence of hallucinations. CDC/FastCDC, Rabin-style chunking, MinHash/shingling, CAS and source similarity are established techniques.
