# R153 fair historical receipt timing

Status: both original-code jobs passed. R151's legacy revision scorer scans and validates the length ledger per query; quotient reads native matching rows only. Compare legacy and optimized revision paths on the exact same physical marginal revision archive, and quotient on the matching physical marginal quotient archive. Optimized revision path joins materialized FTS native match rows directly to validity and matching rank_ledger rows, checks native vs stored lengths, and uses the same BM25 scorer. No full ledger scan; does not make a malicious-index completeness claim. Three randomized interleaved warm repetitions on both frozen AP cohorts, identical 256 rank bodies and native results per repeat/method, 64 v2 receipts retained at generation cutoffs and full shared prefix verification per batch. Reproduce physical R151 sizes and compare all receipt bodies exactly. Rank-only receipt times exclude prefix scan; batch timing includes it. Report any reversal, no speed claim until validated.

## Partial verified results

Small AP R153 job passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45881449946). Legacy, optimized revision, quotient median rank receipt 6044.067, 1109.637, 971.505 us; median batch 485.275,184.625,171.543 ms. Most legacy-to-quotient speedup due to removing full ledger scan. Quotient vs fast revision 1.142x median rank speedup; 1.076x batch. All 2,304 rank comparisons exact and 576 v2 receipt replays across methods/repeats. Full job pending. Descriptive warm measurements.


## Full verified results

Both R153 jobs passed on 6fe108d3 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45881449946). Full AP median rank receipt legacy 21.711 ms, optimized revision 1.103 ms, quotient 1.128 ms; p95 25.412, 6.328, 5.841 ms. Median 64-receipt v2 batch 1.732 s, 0.453 s, 0.435 s. Quotient median rank ~2.3% slower than fast revision; batch ~3.8% lower elapsed time. No demonstrated material inherent median latency advantage of quotient at full scale; legacy comparison confounded by ledger scan. 4,608 native rank comparisons and 1,152 batch receipt replays across both cohorts, zero observed score error. Three warm interleaved repetitions, descriptive. Retain fast revision as latency baseline; storage advantage remains independently verified.
