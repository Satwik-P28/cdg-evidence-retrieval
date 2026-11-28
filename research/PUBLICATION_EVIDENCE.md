# Publication evidence register (R173–R183)

Every number in this file is traceable to a committed result JSON, a report in
`research/rounds/`, or a test in `experiments/`. Nothing here is projected,
interpolated or averaged across configurations. Where a number exists only as a
CI-reported figure and could not be re-downloaded, it is labelled as such.

Corpora: **AP NewsEdits** at 10,009 revisions (manifest
`2788f97b57da9dabb24ace843b8f4b9b0993fc1041c9dfcca228ab6e26a79857`) and **CLARK**
at 1,161 revisions (manifest
`1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f`). Machine: 2 vCPU,
3 GB RAM, warm cache, logical byte activation only.

## Central claim, in the strongest form the evidence supports

> In a versioned archive that must answer exact historical keyword queries *and*
> reconstruct any historical source byte, the expensive choice is not "index or no
> index" but *which* positional representation earns its storage. Charging every
> candidate structure its measured marginal bytes and selecting terms by expected
> candidate rejection produces a point that dominates both ends of the frontier:
> against the cheapest exact-frequency archive it spends +3.0% storage to cut p95
> latency 3.4×, and against a native positional index it saves 30% storage at 2.5×
> the latency.

Numbers: frequency-only 14,082,048 B / 24,267 µs p95; trained selective 14,503,936 B /
7,054 µs; native positional FTS5 20,684,800 B / 2,775 µs (R174 `results-ap-10009.json`).

What this claim does **not** say: that the system is faster than FTS5, that it beats
PISA or FastPFor, or that the improvement generalises beyond these two corpora.

## Update after R179–R183: which of these claims survive

R179 re-derived every number in this file from the committed JSON. R180 replaced the
workload. R181 measured the same archive under the new workload. Three claims changed
status, and the change is the most important result in the programme.

| earlier claim | status now | why |
|---|---|---|
| Cost-based selection beats document-frequency selection at equal storage (E5) | **survives, but only in-distribution** | E5 was measured on the query plan the policy was trained on. On R180's held-out splits the trained selective point cuts p95 by 1.44× on AP and 1.05× on CLARK, and on AP it reduces *no* source reads at all. |
| The trained selective point dominates both ends of the frontier | **refuted** | It dominates statistics-only policies; it does not dominate a query-independent adjacency filter at the same storage (R181). It is also not on the R181 frontier at 5% because `pairs_selective-5%` dominates it. |
| "Budget" percentages are storage budgets | **refuted** | Structural overhead is a median 19.2% and up to 71.7% of the estimated budget. R179 reports measured file bytes for every arm. |
| Whole-archive savings of 25% against native positional | **not met** | Best complete archive 20,631,552 B vs native 20,684,800 B on AP: 0.26%. The large savings are index-region only. |

The central claim for the paper is therefore narrower and better supported:

> A query-independent adjacent-pair filter is the representation that earns its bytes for
> held-out phrase queries: at ~5% additional storage it cuts held-out p95 by 3.7× on AP
> and 2.3× on CLARK, while a comparable workload-trained positional selection cuts it by
> 1.44× and 1.05×. Charges are measured archive bytes; rankings and reconstructions stay
> exact against the native oracle.

Numbers: R181 `results-ap-10009.json`, `results-clark-1161.json`; see
`research/rounds/round-181/report.md` and `research/GENERALIZATION_AUDIT.md`.

## Evidence table

| # | Claim | Evidence | Status |
|---|---|---|---|
| E1 | Block-addressable positions decode only candidate blocks and never change a ranking or a reconstructed byte | R173 `probe.py` (PROBE_OK: 40,000 codec round trips, 5,000 block, 2,000 directory, 20,000 shifted-position, 23 native oracle), `tests/test_blocked_positions.py` (27 tests) | **Established** |
| E2 | Block positions cost 2.03 bytes per occurrence at b512/`best`/Zstd (payload + directory), versus 3.21 for the worst codec | R173 `results-ap-10009.json` → `storage_sweep` (8,244,651 B / 4,070,728 occurrences = 2.025; b128-vw-raw 3.21) | **Established**, positions only |
| E3 | Charging every term row on both sides, the best block layout is 5.1% smaller than an uncompressed SIMD-BP128 layout of the same data | R176 `results-ap-10009.json`: 9,320,643 vs 9,817,431 (both include 1,075,992 B of 24 B/term rows); payload+directory only: 8,244,651 vs 8,741,439 | **Established**, size only, modest margin |
| E4 | Our frequency index is 27.3% smaller than the best uncompressed external layout (Elias–Fano) on the same postings and with equal term metadata | R176: 3,048,885 vs 4,193,814 (payload only 3,468,822) | **Established**, size only |
| E5 | Cost-based selection beats document-frequency selection at equal storage | R174: `df_topk` k512 = 18,657,280 B / 12,580 µs; `train_candidates` = 14,503,936 B / 7,054 µs | **Established** |
| E6 | No corpus-statistics-only policy approaches the trained policy | R174: `df-1%` 14,266,368 B / 21,621 µs; `cf-40%` 20,520,960 B / 12,064 µs; `df-40%` 20,787,200 B / 17,380 µs | **Established in-distribution**; see the R179–R183 update above for the held-out caveat |
| E7 | A query-independent adjacent-pair filter beats a workload-trained positional selection on held-out phrase queries at matched storage | R181: AP 388,344 → 105,639 µs p95 at +4.9% bytes vs 269,475 µs at +6.2%; CLARK 168,171 → 72,078 µs at +4.3% vs 159,467 µs at +5.7% | **Established**, two corpora |
| E8 | Every rejection produces zero ranking, tie-order and document-frequency discrepancies | R181: 6 arms × 2 corpora, `score_error` 0.0, `tie_order_differences` 0, `rank_mismatches` empty | **Established** |
| E9 | 64-bit document pair fingerprints are useless at this scale | R181: 0.5% of candidates rejected; dominated on CLARK | **Established**, negative |
| E10 | The estimated payload budget is not a physical storage budget | R179: structural overhead median 19.2%, max 71.7% over 76 arms | **Established** |
| E7 | Term-level selection is the only representation axis with a good byte-for-latency exchange rate | R175: 0.41 MB buys 12,836 µs; regional native mirroring costs 1.15 MB for 517 µs at 256 documents | **Established** for AP |
| E8 | A regional (hot-set) native positional mirror is dominated by the global native index at every size tested | R175: `sel+hot4096` 24,363,008 B / 3,626 µs vs native positional 20,684,800 B / 2,775 µs | **Established**, one corpus shape |
| E9 | Exactness holds on adversarial inputs: empty documents, duplicates, NFC/NFD, 500-fold repeats, huge insert/delete, unrelated revisions, cutoff boundaries | R177 `results-synthetic.json`: 261 rank checks, all exact | **Established** |
| E10 | Non-UTF-8 source bytes are refused rather than silently normalised | R177 `results-synthetic.json` → `malformed_input` | **Established** |
| E11 | Repeated measurement within a process is stable (CV 1.3–4.8%); between processes the same configuration varies up to ~25% | R177 `results-ap-10009.json`, `results-clark-1161.json`; compare R175 `freq` 19,353 µs with R173/R174 `frequency` 24,267 µs | **Established** (it is a methodological finding) |
| E12 | BM25 coefficients are fixed at k1 = 1.2, b = 0.75 and are not exposed | R177 `coefficients`: 9 cases agree with the closed form, `pinned` records the constants | **Established** (a limitation) |
| E13 | A corrupted posting block that still parses would be returned silently: the format has no checksum | R177 `corruption` + note; a per-term digest would cost 358,664 B on AP | **Established** (a defect) |
| E14 | Archive bytes are deterministic across runs; latencies are not | R174 run 1 vs run 2: all 31 overlapping arms byte-identical; median p95 difference 7.7% on AP (max 34.2%), 4.9% on CLARK (max 114%) | **Established** |
| E15 | Building the AP archive takes 22.99 s and adding a selected term set costs 0.12–0.23 s; CLARK takes 5.72 s | R174 run 2, `sweep.build_seconds` and per-arm `materialize_seconds` | **Established**; no incremental append-a-revision path exists, so append latency is unmeasured |

## Not verified, and therefore not claimed

* **AP at 74,364 revisions.** CI ran it (run 45919907942); the artifact could not be
  downloaded in this environment (401, no token). Any figure for that scale here is
  labelled CI-reported and is *not* used as evidence.
* **Cold-cache behaviour.** Dropping the page cache requires root. All latency
  numbers are warm.
* **Physical I/O.** No instrumentation available; "activated bytes" are logical.
* **Feature-matched comparison against PISA/FastPFor.** Not built, not executed. Only
  size comparisons of published layouts are made.
* **CPython documentation and BIP histories.** Not ingested.
* **Generalisation of the trained selection beyond AP/CLARK.** One corpus size each.
* **Submodularity.** Empirically false here (threshold benefit), not assumed.

## Figures that can be drawn from committed data

1. Storage–latency scatter for all R173/R174/R175 arms (Pareto envelope visible:
   frequency-only → trained selective → adaptive → unified b32 → native positional).
2. Bytes per occurrence by codec family and block size (R173 `storage_sweep`).
3. Directory and payload split as a function of block size (R173, R176).
4. p95 by layout for the seven R175 layouts with the hot-region cost isolated.
5. Repetition-to-repetition p95 spread (R177, five points per corpus).
