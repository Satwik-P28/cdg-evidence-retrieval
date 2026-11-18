# CDG Living Research Record: Rounds 33–77

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


## Retroactive archival and metadata write-cost falsification: Rounds 64–65

| Round | Research question | Executed outcome | Promotion decision |
| --- | --- | --- | --- |
| [64](rounds/round-64/report.md) | When a second related source arrives, can retroactively re-encoding an earlier whole-Zlib document into shared gear512 frames overcome R63's early-source gate penalty? | Tested 3 prior histories plus 2 new SHA-pinned source families, vLLM and Pydantic (12 actual revisions each), at 0/128/512 independent docs. At 512, migration archives versus prior R58: Ruff 205,672 vs 209,393 B; Transformers 201,702 vs 205,427; Flask 189,217 vs 192,454 (still worse than whole 188,846); vLLM **214,680 vs 213,624** (counterexample); Pydantic 192,136 vs 195,868. Exact CAS frame readback, reference counts, source IDs retained | Small storage reductions in 4/5 families but not general; extra migration reads, RAM and metadata writes mean no default promotion |
| [65](rounds/round-65/report.md) | Is full metadata rewrite amplification inherent in retroactive source migration, or caused by a weak metadata layout? | Added source append/replace events, SHA-checked length-framed Zlib journal, periodic compact binary checkpoints; corrupt/torn event tests. With 128-event checkpoints, metadata bytes written fell ~97.5% versus *full rewrite per append* on five 500+ source workloads, at ~6–9% extra retained metadata and 1.5–1.9 ms warm cold-replay CPU | Keep journal+checkpoint as a research physical-design baseline. Requires true fsync/atomic recovery and stronger WAL/LSM comparison |

### Updated graph of explanations

**Why the source gate fails:** Source overlapping bytes are not identical to marginal compressed CAS reuse. Early history sources may be profitable to frame only when descendants accumulate. R62 transfer and R63 threshold failure imply a sequential decision problem rather than a universal local ratio.

**Retroactive promotion:** R64 tests moving an earlier source from a whole compressed blob to reusable chunks at the arrival of a related version. This sometimes improves final archive size but violates the no-rewrite simplicity of immutable archival sources and adds publication, read and CAS reference-count complexity. Importantly it fails on the previously unexamined vLLM history, so evidence is mixed.

**Metadata physical design:** R64's full manifest per-arrival rewrite was artificially expensive. R65 demonstrates its cost can be dramatically reduced with standard append-only records and checkpoints, but that shifts cost into a larger retained metadata tail and a slower cold replay path. It does **not** demonstrate actual SSD write savings or guaranteed durability; a conventional transactional database must be compared before a production claim.

**Evidence and truth gap persists:** Earlier R54 data-split retrieval improvement is only closed-world supporting-document selection. R55–59 sentence support shows explicit evidence-loss tradeoffs; byte-verified retrieval is not semantic entailment. CDG has not yet integrated genuine answered questions, independent factual validation, model inference/verifier tokens, and archive/index/update physical costs into one reproducible end-to-end study.

### Next publication-quality experiments

1. Compare archive/CAS transaction semantics with SQLite WAL or a mature log-structured store using real fsync durability, crash-fault injection and concurrent updates.
2. Choose new, truly independent source histories *before* designing a replacement policy. Hold out their identities and timestamps until coefficients and switches are frozen.
3. Establish end-to-end evidence support (answer generation, source alignment, temporal applicability and false acceptance) at fixed query budgets, with full indexing and storage costs and standard strong retrieval baselines.
4. Kill any complexity that does not improve a measured quality/resource Pareto frontier over ordinary BM25 + whole-source Zlib/Git/Zstd + explicit citation verification.

No new codec, general compression theorem, industry-scale state of the art, or hallucination reduction has been established by Rounds 64–65.


## Answer-level test of reversible evidence retrieval: Rounds 66–68

| Round | Test | Reproducible result | Decision |
| --- | --- | --- | --- |
| [66](rounds/round-66/report.md) | Run the frozen title-link bridge and BM25 document retrieval into a SHA-pinned pretrained SQuAD2 extractive answer reader. Separate source-citation byte integrity, answer EM/F1, support coverage, full vs FTS-top2 evidence, model-input tokens, and archive/index bytes | 64 fixed HotpotQA distractor dev questions, 1,272 actual model evaluations. At K5 complete source sets BM25 44 vs bridge 51, **answer EM 11/64 for both**. Input original source sentences reconstructed from whole and gear archive, with index 360,448 B larger than whole archive 231,440 B | Rejected inference that higher retrieval coverage necessarily improves this reader's answers |
| [67](rounds/round-67/report.md) | Compare identical fixed model with one joint 384-token context and an isolated annotated-support oracle diagnostic | 64 same questions, 832 joint model calls. At K5 bridge recovered 51 complete source doc sets but only 38 fully annotated evidence sets within token cap; joint answer EM BM25 7 vs bridge 8. Exact gold-support sentence oracle 23/64 correct | Reader token window and evidence synthesis are both major bottlenecks; oracle is not deployable retrieval |
| [68](rounds/round-68/report.md) | Evaluate frozen per-source and joint readers on the other 64 prespecified HotpotQA questions (SHA-sorted indices 448–511), without tuning model, policies or thresholds | Across combined 128, K5 BM25 vs bridge doc recovery **88 vs 106**, independent per-source answer EM **31 vs 33**, joint reader answer EM **22 vs 24**. Paired exact p=0.50 for +2 answer wins; oracle annotated-support EM **49/128** | No convincing answer-quality improvement, despite reproducible document acquisition advantage. Weak reader + context capacity identified |

### Scientific interpretation graph

1. **Input retention:** R46–65 establish exact bytes in conventional whole-Zlib, CDC and source-migration archives, with compressed CAS receipts and metadata. Across short independent HotpotQA paragraphs, whole-Zlib remains smaller than CDC, and persistent SQLite FTS5 indexes exceed compressed source bytes.
2. **Acquisition of candidate evidence:** R25/R53/R54 verify that a conventional title-link expansion can acquire complete gold supporting documents more often than per-query BM25 in the closed-world HotpotQA distractor candidate pool.
3. **Actual materialization:** R55–59 show sentence pruning and naïve per-document budgets lose annotated supporting facts. R67 confirms a second loss occurs **after** retrieval: strict reader sequence truncation removes some evidence even when retrieval acquired both gold documents.
4. **Answer-use bottleneck:** R66 per-document and R67 joint extractive readers often fail even with supporting evidence. The isolated gold supporting-sentence oracle (R67/R68) improves answer EM but remains far from correct on all questions. R68 heldback transfer makes the positive answer gain for title-bridge only **+2/128**, statistically weak.
5. **Provenance and truth are not equivalent:** A correct SHA receipt means the cited bytes came from a specific archived document version. It does not establish semantic entailment, source authority, factual freshness, or causal reliance. Human-annotated RAGTruth (ACL 2024) and Nov 2026 *Cited but Unused* counterfactual citation work are stronger directions for claim support and causal provenance tests.

### Closest relevant prior work and novelty discipline

- HotpotQA (Yang et al., EMNLP 2018): https://hotpotqa.github.io/ . Its distractor candidate pools contain gold paragraphs; benchmark answer EM/F1 and supporting-fact scores are prior art.
- *Retrieval Granularity as Evidence Design in Small-Model RAG Question Answering* (2026): https://www.mdpi.com/2673-2688/7/8/320 . This study **already** evaluates full HotpotQA distractor dev answer EM/F1, gold-support oracle and context-budget tradeoffs with a stronger Qwen3 8B generator. CDG R66–68 are component integration diagnostics, **not a novel demonstration** that evidence selection affects QA.
- *RAGTruth* (ACL 2024): https://aclanthology.org/2024.acl-long.585/ . Human word-span annotations allow testing actual unsupported claims rather than using answer-span or gold sentence identity as a misleading synonym for hallucination.
- *Cited but Unused: Parametric Provenance in RAG* (Nov 12, 2026): https://arxiv.org/abs/2611.17161 . Even citations that agree with a claim may not have causally influenced the answer. This restricts the interpretation of any exact-storage receipt system.
- LLMLingua-2 (Findings ACL 2024): https://aclanthology.org/2024.findings-acl.57/ . Learned extractive prompt compression for preserving useful tokens is an important strong comparison for future evidence selection; byte-exact lossless archives alone do not compete with prompt compression on model input budget.

### Next graph of falsifiers

**A. Stronger reader:** Fix a genuinely multihop-capable, instruction-following QA model and model-input tokenizer cap. Compare whole, sentence, paragraph, retrieved oracle and proven document retrieval controls. Record actual CPU/GPU time and answer EM/F1. Use a new frozen split or independent domain for confirmation.

**B. Claim-level trust:** Test independent RAGTruth examples with human word-span hallucination labels, including baseless versus contradictory claims, implicit-but-true labels, and correct source version. A lexical citation or exact source digest alone must not be counted as successful semantic verification.

**C. Fully charged system:** Compare standard BM25+Zlib/Git/Zstd, SQLite FTS5+whole-source reader, compression-aware receipts and optional retroactive source migration. Charge indexing bytes/time, compressed archive bytes, source-update and journal writes, actual source-span physical reads, model tokens and reader inference. Multiple caches/indexes must not be treated as free.

**D. Kill rule:** If increasing reader capability or evidence retrieval quality dominates storage scheme choices, redirect optimization to evidence selection and calibrated refusal. Preserve null and negative findings rather than adding new heuristics to force a desired result.

**Status:** R66–68 provide a reproducible negative/limited-positive **downstream answer diagnostic** on the same HotpotQA data family. They are not a peer-reviewed paper, novel lossless code, verified hallucination mitigation or a production research engine.


## Human-labeled claim grounding and why source integrity is not faithfulness: Rounds 69–71

| Round | Falsifiable question | Measured result | Decision |
| --- | --- | --- | --- |
| [69](rounds/round-69/report.md) | On human-annotated RAGTruth QA responses, do lexical source containment and literal name/number warnings reliably identify unsupported output? | Pinned independent RAGTruth corpus, QA test split, 128 source groups and 768 preexisting generated responses. Content-overlap warning identified 121/138 labeled positive responses but incorrectly flagged 367/630 originally clean responses (precision 24.8%, F1 38.7%). Union heuristic identified 136/138 positives yet falsely warned 590/630 clean responses | **Reject** lexical citation/source overlap as adequate response-faithfulness detection; response-level false alarms are excessive |
| [70](rounds/round-70/report.md) | Can training-only threshold calibration reduce false alarms and preserve sensitivity on previously unexamined RAGTruth QA source groups? | 4,892 quality-good QA train responses; 22 disjoint test source groups, 131 good responses with 22 labeled positive. Strict train-FPR 10% max-novelty warning caught 0/22, 0 false alarms; novel-sentence-fraction caught 1/22, five false alarms. Frozen sensitive overlap caught 20/22, 51 false alarms | **Reject** simplistic source-word novelty as a calibrated hallucination verifier; specificity and recall do not jointly succeed |
| [71](rounds/round-71/report.md) | Is a cryptographic source identity alone sufficient to infer whether one of several responses grounded in that source contains unsupported claims? | Full QA test split 900 responses and 150 source groups; **94 groups exhibit both clean and human-labeled unsupported responses sharing identical evidence bytes**. Even a label-informed source-only majority oracle must make 150/900 errors (max 83.3% accuracy), versus always-accept 82.2%. Verified 300 full and 600 partial lossless source receipts. FTS5 163,840 B exceeds whole source archive 96,202 B | Strictly separate byte provenance from response-conditioned source support. This is a conditional counting limit, not a new theoretical theorem |

### Independent data provenance and human-label protocol

RAGTruth was introduced by Niu et al., ACL 2024 (https://aclanthology.org/2024.acl-long.585/). Source git revision **c103204b9ce28d6bbad859304bf30de72b8ed8fe**, response.jsonl Git blob SHA1 **f9ae5913fb9976684f3e13be3cd3465062db54cc**, source_info.jsonl **119277774009f110aa58596b93f9512f62594a89**. Both files are downloaded into transient CI runs and hashed before use; no original passages or responses are committed. The QA source groups remain intact across multiple model outputs, with training and heldout confirmation source groups segregated. The original human label types and implicit_true flags are reported with both inclusive and strict alternate targets. Training-only threshold selection in R70 is not a formal distribution-free calibration guarantee.

### Updated graph of evidence

**Byte layer:** R46–65 demonstrate exact source bytes can be retained in whole-document compression, content-defined frames, CAS version receipts and journal-updated manifests. R71 confirms exact source bytes on a different RAGTruth QA corpus. This solves a *provenance and source integrity* subproblem, not an objective factual truth problem.

**Retrieval layer:** R25/R53/R54 show exact-title bridge can improve HotpotQA distractor supporting-document acquisition. R55–59 show evidence selection and model-window truncation can still discard annotated supporting facts. R66–68 use a real pinned pretrained reader and find that the retrieved-document gain does not reliably propagate into answer EM.

**Human faithfulness layer:** R69's actual human-labeled response sample reveals lexical source verification creates large false-positive rates even as recall increases. R70 freezes train thresholds and confirms that reducing false alarms can remove practically all recall. R71 finds 94/150 identical source groups with conflicting clean/unsupported labels across their different outputs. Thus source integrity and source existence **cannot substitute for response-conditioned semantic assessment**.

**False certainty hazard:** A matching citation digest or literal answer string is necessary for accurate source provenance but not sufficient for entailment, temporal applicability, truth, or causal reliance. Human span annotations are also imperfect or task-specific; their absence is not proof of universally correct output. The R71 best-source-only oracle is an intentionally label-informed upper bound applicable only to methods that never inspect the response.

### Novelty and next falsifiers

1. **Strong semantic verifier:** test a pinned NLI/cross-encoder or grounded claim checker against RAGTruth's human spans, comparing strict versus inclusive labels, cross-task domain shift, calibration and token/latency cost. Keep annotation data out of model/policy tuning except an explicitly designated training split, and reserve a genuinely new corpus for confirmation.
2. **Full system frontier:** integrate answer-capable multihop reader, byte-verified evidence source, FTS index and manifest size, model-token budget, semantic verifier latency and **wrong nonempty accepted answer rate**. Compare at equal source/candidate recall and equal compute budgets rather than celebrating a single component score.
3. **Temporal authority:** differentiate a correct source quotation from a claim still valid at the query date. Evaluate contradictory versions under actual chronological metadata, with explicit abstention.
4. **Conventional comparators:** compare sentence-level attribution/NLI/LLMLingua-2 and trained RAGTruth baselines before claiming novelty. A source-only counting bound and token overlap heuristic are basic controls, not discoveries.
5. **Kill rule:** if a standard retriever+full-source compressor+off-the-shelf checker is better on total cost and human-labeled risk, preserve the negative result and avoid an unnecessarily elaborate integrated system.

**Status:** R69–71 are repeatable, human-label-focused *negative and structural diagnostic results*. CDG has not shown verified hallucination mitigation, novel compression bounds, independent causal citations, or an end-to-end Pareto improvement over strong conventional systems.


## Frozen zero-shot NLI transfer and cost: Round 72

| Round | Hypothesis | Executed evidence | Decision |
| --- | --- | --- | --- |
| [72](rounds/round-72/report.md) | Can a standard pretrained semantic NLI model, not trained on RAGTruth, replace unreliable lexical grounding alarms over fixed source windows? | Pinned cross-encoder/nli-deberta-v3-xsmall (SNLI/MultiNLI) commit a150876415327c80daeff35ca6f68f5ed8cf5c24; 8 QA + **16 previously unexamined Summary** RAGTruth test source groups, 141 good-quality responses (31 human positives), 760 response sentences, 2,273 actual inference pairs, 426,627 model input tokens, 251.993 s CPU forward time. The naive NLI 0.50 entailment threshold caught 31/31 unsupported responses but falsely warned on 108/110 human-negative outputs, F1 0.36471. Original R69 lexical heuristic caught 27/31 with 48/110 false alarms, F1 0.50943. First, top-one and top-three source windows produced nearly identical response-level NLI results | **Reject uncalibrated, off-the-shelf NLI as an adequate RAGTruth verifier under this context/window setting**; more semantic model compute did not improve the tested warning-quality frontier |

### Evidence graph update

- R69–70 demonstrate lexical source-overlap warning signals cannot maintain high recall and low false acceptance/false warning simultaneously when naive strict thresholds are applied.
- R71 proves a narrow counting limitation: source identity/bytes without the response are insufficient to classify that response's faithfulness.
- **R72 conditions on the response**, removing R71's formal obstacle, but reveals a different empirical failure: an ordinary SNLI/MultiNLI NLI cross-encoder on 150-word partial-source premises and sentence-like hypotheses overwhelmingly predicts non-entailment. The high apparent recall is produced by flagging essentially everything. More source windows produce almost no response-level benefit with a 0.50 score cutoff, while adding actual inference expense.
- Thus neither byte integrity nor raw lexical overlap nor generic NLI directly yields a credible calibrated factual verifier. The need is to test claim granularity, evidence matching, semantic support, threshold calibration and total cost *jointly*, with stronger baselines that include task-specific training.
- **Important preexisting art:** LettuceDetect (Kovács and Recski, arXiv:2502.17125) trains a ModernBERT token-level checker on RAGTruth. Evaluating its checkpoint on RAGTruth is an in-domain trained-control result, not independent transfer evidence; the actual original source papers and external benchmark studies must be cited. Cross-encoder NLI SNLI/MultiNLI classification is longstanding established work.
- Source bytes for R72 were retrieved from the pinned RAGTruth files; the NLI model was not run off exact compressed archive receipts and no per-window physical I/O was measured. A future archive-to-verifier integration test must correct this accounting boundary instead of claiming R72 is a full system.
- Next predeclared experiments: fix a train-only confidence/abstention rule, evaluate on untouched RAGTruth Data2txt sources; verify selected premise windows as original exact UTF-8 source byte ranges through versioned CAS; and compare against an actual trained RAGTruth verifier with explicit contamination caveat. Need independent answer-level output acceptance/rejection on a new domain for causal hallucination mitigation.

**Publication gate:** A model with nearly 100% positive recall and nearly 100% false-alarm rate does **not** establish a breakthrough. R72 is a reproducible negative semantic baseline that strengthens the failure diagnosis and identifies the next experimental variables.


## Verifiable NLI evidence windows and the cost of access patterns: Round 73

| Round | Question | Measured source/path outcome | Decision |
| --- | --- | --- | --- |
| [73](rounds/round-73/report.md) | If R72's NLI source windows are retrieved through exact UTF-8 source receipts from compressed CAS, does more selective content-defined framing outperform whole-source Zlib for the *actual response-level source access trace*? | 24 identical R72 RAGTruth QA/Summary source groups, 141 good responses, 760 sentence-like claims; 48 full source receipts and **4,546 selected exact window reads** verified across two source layouts. Whole-source archive 28,398 B vs gear512 35,437 B, with optional separate FTS5 source-line index 73,728 B. Mean compressed source bytes activated per response with source-local warm frame union: first source window whole 1,154 B vs gear 735 B; lexical-best whole 1,154 vs gear 1,241 B; top-three whole 1,154 vs gear 1,343 B. R72 top-three source model prediction F1 equals lexical-best, despite more model compute | Keep exact byte-offset receipts and normalization audit, **reject a universal CDC read-efficiency win**. More semantically selected windows create a cross-layer trade-off and sometimes make whole-source compression cheaper to activate |

### Graph of observations and constraints

**Storage-retrieval-semantic interaction:** R72's trained-general-NLI negative result was obtained from original pinned RAGTruth text. R73 reconstructs the **identical premise window strings** from byte-exact ranges retrieved through whole and content-defined source CAS. A byte receipt authenticates the original source span within this local archive, whereas the model sees a deterministic whitespace normalization; the former does not make the latter a direct verbatim quotation, and neither proves claim entailment.

**More evidence is not free:** For Summary source families, content-defined gear512 reduces compressed frame activation when the reader looks only at initial document regions, but once question-specific lexical windows are distributed through the source it activates more distinct compressed frames than whole-document Zlib. The three-window NLI variant consumed more actual model forward pairs in R72 and activated more frames in R73 yet did not improve the human-labeled F1 versus one lexical-best source window.

**Source index boundary:** R73 builds an optional FTS5 line index (73,728 B), but the actual R72 word-overlap source-window selector works in-memory without consulting it. Its bytes cannot be treated as necessary for this exact policy, just as in-memory source text and lexical scan costs cannot be treated as free. Any future optimized selector must charge its own index and memory.

**Novelty caution:** These are conventional Zlib, content-defined chunks, CAS exact-source receipt and pretrained NLI components. The observation is a workload-specific negative/cost interaction, not a new compressor, factual verifier or proven Pareto optimum. A production benchmark must measure physical SSD reads, decoded model inputs, persistent index/model weight footprints, update durability, wall time per answer, and human-labeled wrong-answer acceptance.

### Next falsification path

1. Fix training-only support-verifier calibration and test against **previously unexamined Data2txt task** source groups, rather than repeatedly inspecting QA/Summary from R72.
2. Compare a RAGTruth-trained span detector as a clearly **in-domain supervised control**, never independent transfer.
3. After semantic claim support is credible, integrate model inference directly from byte-receipt materialized compressed windows, not just offline exact equivalence.
4. Kill any compressed frame layout that increases both persistent footprint and actual compressed data traffic at the relevant evidence query pattern; weigh index/retriever/model costs jointly.

R73 never reruns the NLI model and makes no claim to have improved human-label classification. Its exact-source receipts are local integrity checks, not a guarantee of source authorship or factual truth.


## Transfer, counterfactual evidence sensitivity and strong prior-art detector: Rounds 74–77

| Round | Hypothesis and control | Actual measured results | Decision |
| --- | --- | --- | --- |
| [74](rounds/round-74/report.md) | Can 10/25% QA-training negative NLI false-alarm thresholds transfer to a previously unseen **Data2txt RAGTruth test** task family? Frozen R72 model and source windows, 32 QA train groups and 16 disjoint Data2txt test groups | QA train 190 good responses; Data2txt test 96 good responses, 61 human-positive. Frozen NLI rejects **all 96**, F1 .777 purely from positive prevalence, 35/35 false alarms. QA-train 10% FPR target: top3-max 19 TP / 9 FP / 42 FN / 26 TN, Data2txt FPR **25.71%**, F1 .427; target25% yields **60%** test FPR, F1 .561. 7,550 forward pairs, 1,552,487 actual tokens, 1,228.189 CPU forward seconds | **Reject** reliable cross-task warning calibration and unadjusted F1 as evidence of verifier success. Structured source serialization and task shift are confounds |
| [75](rounds/round-75/report.md) | Keep each Data2txt response identical but replace source with its nearest distinct source by leaf-token Jaccard (same frozen source groups), evaluate paired frozen NLI | 96 actual/swap comparisons; model prefers actual source in 54, substituted in 42. **Weakest-claim** source score delta mean +.00023, source-group 95% bootstrap CI [-.00589,+.00629]; mean-across-claims score delta +.12649. 5,527 forward pairs, 1,495,269 tokens and 1,609.643 CPU forward seconds | Do **not** use lowest-claim NLI score as a calibrated proof of grounding. Actual and swapped contexts are *not* a human-labeled truth pair |
| [76](rounds/round-76/report.md) | Re-evaluate same 141 R72 QA+Summary generated responses with a strong published RAGTruth-trained **LettuceDetect ModernBERT** span detector, rather than weak general NLI | Model 149.6M params, SHA-pinned, 179.992 CPU inference seconds. Combined response TP14 FP16 FN17 TN94, precision .467, recall .452, F1 **.45902**; QA F1 .632, Summary F1 .381; character-level F1 **.40540** | Keep as **published in-domain supervised prior-art control**, not a new CDG model. Not matched with generic R72 384-token NLI or R69 lexical due model/context/training differences |
| [77](rounds/round-77/report.md) | On exactly same trained detector and 141 response strings, does using the original RAGTruth generator prompt instead of locally reconstructed source passages improve human-label performance? | Only **5/141** warnings differ. Original prompt TP15 FP16 FN16 TN94, F1 **.48387**, vs reconstructed TP14 FP16 FN17 TN94, F1 **.45902**; paired source-group bootstrap F1 delta 95% CI **[-.02297,+.08602]**. 142.111 CPU forward seconds for original-prompt route | No statistically reliable effect; prompt framing is a measurable confound but not the fundamental semantic support solution |

### Graph of empirical limits and design constraints

**Source integrity:** R46–65 and R71–73 demonstrate exact source reconstruction from ordinary whole-Zlib and content-defined frames with SHA-bound receipts. R73 charged source archive and optional full-text index bytes, finding material archive/index and source-window traffic tradeoffs. None of those bytes can establish semantic response groundedness by themselves.

**Candidate evidence:** R25/R53/R54 improves HotpotQA closed-world supporting-document acquisition with conventional title-link expansion, but R66–68 real reader QA and RAGTruth R69–77 show that retrieval *availability* and byte-exact materialization do not automatically improve answer correctness or detector faithfulness.

**Detectors:** R69 content-word warning has high recall but catastrophic false alarms. R70 strict train-calibrated source novelty loses recall. R72 generic pretrained NLI at fixed 0.50 has near-universal response rejection under many RAGTruth QA/Summary settings. R74 reveals **QA-to-Data2txt specificity transfer fails**, while a vacuous reject-all rule obtains deceptively high F1 on Data2txt due class prevalence. R75 demonstrates **actual source preference at mean claim score** may coexist with **near-zero difference in worst-claim score**, undermining naive answer-wide lowest-claim gating.

**Strong prior art:** R76's RAGTruth-trained published LettuceDetect delivers a different false-positive/false-negative tradeoff. It is *supervised on the same benchmark family*, has a larger token window and cannot be compared as if it were a matched architecture and training baseline. R77's original prompt route raises F1 by a small paired amount but the clustered uncertainty interval includes zero. None of this is a new hallucination detector.

### Revised research priorities and kill rules

1. **Atomic-claim decomposition and source-value contracts:** test structured Data2txt field-aware entailment, explicit false/unsupported/implicit-true distinctions, multi-passage and temporal contradictions, and verified source offsets, without changing gold-labeled test policies after seeing outputs. The current response-wide minimum NLI score is not a satisfactory claim-support probability.
2. **Train/confirmation separation:** reserve genuinely new domain/source family and independent human annotations for prospective evaluation of a selected verifier. R74 Data2txt groups and R76/R77 RAGTruth QA/Summary groups have been inspected and cannot be treated as fresh confirmation.
3. **Fully costed frontier:** compare BM25/dense/hybrid retrieval + standard compressed source + trained verifier against CDG variants at matched answer-token budgets, charge model weights, candidate processing, source access and index, on-disk update writes and caching. Measure incorrect *accepted* answers and refusals, not merely F1 or source citation bytes.
4. **Causal provenance:** to say a citation caused an answer, test controlled evidence interventions where claim-support labels are explicitly judged, not just byte equality, score shifts or source-token overlap. A swapped source may coincidentally support generic claims and does not automatically constitute a negative truth label.
5. **Stop rule:** do not promote elaborate compression-aware evidence routing if a standard whole-source codec and strong pretrained verifier dominate overall wrong-acceptance cost/latency/space. Preserve all negative and null observations.

**Current scientific status:** CDG has reproducible systems components and rigorous negative tests, but has not demonstrated new lossless compression bounds, generalizable hallucination mitigation, independent semantic faithfulness or end-to-end quality/cost Pareto dominance. All discussed mechanisms have substantial precedent (CAS, source receipts, content-defined chunking, NLI, LettuceDetect).
