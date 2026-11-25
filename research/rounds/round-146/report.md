# R146: batched provenance prefix replay

Status: both original-code jobs passed.

R144 v2 median full-AP replay latency 393.885 ms vs 45.217 ms for v1. Eliminate redundant metadata scans without weakening the trusted digest contract. Each batch owns a fresh SQLite read transaction, verifies all supplied receipt digests, scans actual provenance rows through maximum requested cutoff, checks every stored prefix and retains recomputed roots only for requested cutoffs. Reissue each ranking and verify exact source bytes and hit origin metadata, compare full individual bodies/digests. No persistent trust cache and no return of partial successes. Cost of prefix metadata rows falls from sum(c_i) to max(c_i), independent of request order. Single receipt remains linear; ranking cost unchanged. External trusted digest and local immutable source prefix assumptions remain. This is ordinary amortization, not new cryptography.

Frozen R144 nested AP cohorts, identical archive sizes, same 16 queries and four cutoffs, compare one receipt, 16 same-cutoff receipts, and 64 mixed-cutoff receipts. Individual arm owns one snapshot too, so not inflated by connection-per-receipt overhead. Three randomized method-order repetitions; compare total batch latency and actual prefix row counts. Test duplicate/mixed order and five mutations, plus cross-transaction revalidation and suffix-scoped behavior. No timing or correctness claim before CI.

## Verified results

Both R146 jobs passed on 911f44f3 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45691769935). Small cohort 16/64 receipt median total speedups 6.47x/5.76x; full cohort 7.50x/7.08x (6.652s to 0.887s; 16.488s to 2.329s). Full mixed metadata rows 2,790,544 to 74,364 (37.53x reduction). Single receipt unchanged/slightly slower; no asymptotic gain for single queries. All verified receipt bodies identical. Three warm randomized method-order repeats, no cross-transaction trust cache, no extra archive storage.
