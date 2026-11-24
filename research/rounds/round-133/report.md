# R133 novelty and claim audit

Status: targeted literature audit and formal contract; offline oracle completed and verified.

## Closest prior work

| Work | Prior art | What we can still evaluate |
|---|---|---|
| Berberich et al., SIGIR 2007, https://doi.org/10.1145/1277741.1277831 | Temporal inverted indexing and time-travel text search | Exact source-byte reconstruction and jointly accounted receipt archive in this implementation |
| Staudinger et al., SIGIR-AP 2024, https://arxiv.org/abs/2411.04051 ; TimIR https://repositum.tuwien.at/handle/20.500.12708/224602 ; https://github.com/MoritzStaudinger/TimIR | Historical sparse ranked-list reconstruction, historical term statistics and stored result-list hashes | Exact-byte source binding and bounded compression integrated with transactional ranking ledger; not a claim that ranking hashes are new |
| He and Suel, SIGIR 2012, https://doi.org/10.1145/2348283.2348319 | Compression of positional inverted indexes across versioned collections | We keep native FTS5 fixed and charge full index costs; do not claim best index compression |
| Bhattacherjee et al., PVLDB 2015, https://pmc.ncbi.nlm.nih.gov/articles/PMC5526644/ | Formal storage/recreation cost tradeoffs and bounded reconstruction graph optimization | A concrete causal, one-hop, byte-budget contract measured with a full retrieval archive |
| Guo et al., IPDPS 2024, https://arxiv.org/abs/2402.11741 | Graph-theoretic dataset versioning and optimization algorithms | Restricted latest-anchor offline control below, not new general graph optimization |
| WikECD, ACM TWEB 20(3), 2026, https://doi.org/10.1145/3787449 | Dynamic anchor selection, compressed revision histories and indexed/time-based recovery | Matched historical BM25 and source/receipt transaction contract; direct full implementation comparison not performed |
| Git pack-objects, https://git-scm.com/docs/git-pack-objects | Delta candidate windows and bounded delta depth | Explicit per-request logical ratios, not novelty of bounded depth or candidate windows |

The literature audit uses abstracts, public descriptions and repository documentation; it is not a systematic full-text review. ACM WikECD full text was not accessible in this pass. No priority or uniqueness claim is justified. Source-only xdelta comparisons do not substitute for a full external archival system. The working title should stay systems-oriented.

## Contract proof

For a nonempty requested revision x, independent F(x) activates |F(x)| compressed bytes and decodes |x| source bytes. A delta D(x|b) is admitted only if b is an independent earlier literal, |F(b)|+|D(x|b)| <= 1.5|F(x)| and |b|+|x| <= 2.5|x|. Both inequalities hold by admission, and the decoder visits only b and x by depth-one construction. The individual-frame condition additionally guarantees |D| <= 0.8|F(x)|, not any aggregate optimality. Strict earlier ordinals ensure acyclicity. Empty revisions fall back to literals when an eligible nonempty anchor would violate the decoded bound. Digest/length checks reject detected inconsistency; correctness of valid codec frames follows from lossless roundtrip, not collision impossibility. These bounds exclude page I/O, cache, CPU, memory, metadata and repeated requests.

Historical ranking correctness is conditional on exact active validity intervals, token lengths, phrase frequencies, tokenizer and native-compatible BM25 arithmetic for the declared grammar. The independent rebuilt native oracle supplies empirical confirmation, not proof of all arbitrary FTS5 queries. Receipt replay relies on a trusted commitment. Atomicity is revision-level SQLite transaction scope, not whole Git commit or power-loss validation.

## Offline oracle

For latest-literal-only one-hop encoding, let f_t be independent frame cost and d(j,t) the feasible dictionary-frame cost from anchor j (infinity if admission fails). State DP_t(j) is minimum payload cost through t with latest literal j. Start DP_0(0)=f_0. Transition at t: open new literal DP_t(t)=f_t+min_j DP_(t-1)(j); retain existing literal DP_t(j)=DP_(t-1)(j)+d(j,t). By induction these are the only two allowed actions; the minimum is optimal within this restricted offline class. Runtime O(n^2) candidate encodings and O(n) working states, ignoring encoder cost. It is not a lower bound on unrestricted multi-anchor or alternative-codec methods. Compare greedy latest-only to this oracle using exactly the same 1.5x/2.5x/80% bounds. No training, no deployment of future-aware choices, no integrated size claims. Two previously measured large cohorts, Git/Kubernetes. Frozen manifest checks. Brute-force state enumeration on short random cost matrices validates recurrence.

## Verified results

Both R133 jobs passed (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45497029658). On Git (667 revisions), greedy payload 884,795 B versus restricted offline optimum 871,706 B (1.48% less); six of 160 documents improved. On Kubernetes (378 revisions), greedy 349,176 B versus 344,556 B (1.32% less); four of 141 documents improved. These are source-only comparisons, not archive size or general optimality. The oracle verifies the frozen R132 manifest and reproduces the k1 payload totals. Further tuning of this restricted policy has little measured headroom on these two cohorts.
