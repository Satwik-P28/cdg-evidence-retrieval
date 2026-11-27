# R168: sparse coefficient exceptions

Status: implemented; validation pending. Parent R167 c36507120d45a3814c06e8d321a14ce5506334c4.

## Verified prior results
R166 run 45915506537 completed all three jobs. AP 74,364: positional 148459520 bytes, sparse 136331264, dense 134033408, quotient 133197824; FTS 57241600 vs 73351168. 58494 raw vs 49266 unique windows, 58490 uses. R167 run 45915803144 completed AP 10,009 and CLARK at observation; largest AP pending. AP 10k: eager quotient 18616320 bytes, 5379.5535us median prep, 135.0255us median query; global quotient identical size, prep 1802.388us, one-time map load 4444.19us; direct runs 18673664, prep 1948.4825us, map load 474.918us; adaptive 18583552, prep 1877.2595us, map load 1590.641us, median query 141.3975us, p95 1269.427us vs eager 1144.234us. All checked ranks exact. CLARK no deltas, empty-table overhead remains.

## R168 mechanism
Private signed term (cid,w,k) formerly materialized abs(k) identical indexed rows, parity encoding sign. Now one row, plus magnitude exception only for abs(k)>1. Create patch_coeff lazily so unit-only data pays no additional page. At lookup, sign is parity and magnitude is the exception or default 1. Shared windows keep signed coefficients in patch_use. Exact by distributivity of integer multiplication over TF. Fix fallback prepare_delta without caller-supplied global mapping for all run modes, so direct corrections are not skipped.

For fixed sharing choices, count avoided rows and tokens and assert old direct rows = new rows + avoided rows, old direct tokens = new tokens + avoided tokens, shared counts and total coefficient L1 unchanged. Compare weighted adaptive with unchanged R167 sharing decision, then adjust proxy to number of distinct child uses rather than replicated coefficient magnitudes. Both are heuristic, not claimed byte-optimal. R168 reduces matched arms to positional, independent sparse, quotient global, original direct/adaptive, weighted direct/adaptive, adjusted weighted adaptive. Same source archive, anchors and query plan, exact native score/df parity, all source recoveries.

Unit tests include positive and negative coefficients, shared/private mixtures, reopened databases, nonconsecutive content IDs, inactive/future content, lazy map fallback and repeated edit-window native scoring. No claim of new corpus result until CI. Full corpus may have almost no non-unit private coefficients; synthetic counterexample should not be confused with typical data.

## Next step
R169 should stop optimizing correction mapping in isolation. The actual source codec is one-hop byte delta against a recent full source revision with compressed-frame and decoded-byte bounds; the retrieval codec currently independently selects a full index content by a token-window proxy. To share dependencies, expose the source candidate list and measure the intersection with feasible index base content IDs. Compare independent and joint policies with identical source recovery bounds, exact ranking, complete archive storage, and charge new token coordinate metadata. An aligned ID alone does not mean shared physical bytes. Do not report novelty until that comparison and stronger prior-art baselines are done.


## Executed local synthetic probe

Independent local SQLite copy of the private-row codec, 1,000 children, 2,000 distinct signed correction terms, no shared windows. Actual optimized/VACUUM SQLite bytes, including patch_run and lazy patch_coeff pages (no empty patch_use table in this simplified probe). Native FTS match membership, complete coefficient recovery after reopening, and Python TF aggregation for six queries at four cutoffs; 192 comparisons across eight databases, zero failures. No BM25 latency or complete archive claim.

| Absolute coefficient | Replicated bytes | Weighted bytes | Replicated rows | Weighted rows |
|---:|---:|---:|---:|---:|
| 1 | 155648 | 155648 | 2000 | 2000 |
| 2 | 266240 | 180224 | 4000 | 2000 |
| 4 | 487424 | 180224 | 8000 | 2000 |
| 16 | 1830912 | 180224 | 32000 | 2000 |

Probe source is adjacent. R168 hosted implementation run 45916500364 started; no hosted R168 benchmark result at observation.
