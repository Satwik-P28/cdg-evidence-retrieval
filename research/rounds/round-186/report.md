# R186–R187: repeated global signed suffix and cancellation-aware prefix experiments

Parent R185 b7e42b72. Scope: synthetic patch database, not integrated historical BM25 or source recovery. Python 3.13, SQLite 3.46.1, zlib level 6; compiled FTS5 auxiliary xInstCount. Reopen SQLite files after VACUUM; query twice in shuffled order. Every result equals independent direct overlapping phrase-count difference for every pair, including missing/zero corrections. Counts below are pair-query comparisons, not independent observations or full BM25 checks. Persistent database pages charged, shared external token IDs, anchors, original sources and historical mappings excluded equally.

R186: signed suffix residual R from R185, global lexicographic inverted lists keyed by big-endian uint16 token sequence (tokens <65535), cid-delta varints and signed coefficients, raw or zlib postings. Query prefix range [q,q+0xffff). Exact prefix delta comparator stores every nonzero prefix. Front-coded compressed block layouts store first key as SQLite directory, decode predecessor block plus blocks whose first keys lie inside the range. Page-aware variant targets 900 compressed bytes (SQLite WITHOUT ROWID local payload limit near 1KiB at 4KiB pages); singleton overflow allowed. Binary search for block size is heuristic, no monotonicity proof. Mixed hybrid chooses suffix residuals when distinct residual keys <=40% of old+new token count, otherwise native FTS rows. Native FTS control uses actual MATCH and C xInstCount, not resident Python postings used in R185.

54 workload configurations, 3 seeds (186–188), 3 vocabulary sizes (32,256,2048), 6 edit regimes, 400 correction pairs per case, balanced length 1–8 and random absent probes. 30,945,600 comparisons. Layouts evolved progressively: seed186 6 arms, seed187 9 arms (32/128 key blocks with fixed-length block header), seed188 12 arms (varint body length and page-aware blocks). Median ratios are computed against each case's own FTS control; not all arms have identical replication counts. Reproduction script defaults to final format, not the earlier fixed-header version. 

| arm | n cases | median size ratio | median p95 ratio | smaller | p95 faster | both |
|---|---:|---:|---:|---:|---:|---:|
| suffix |54|2.048|0.500|2|41|0|
| prefix |54|7.208|0.112|0|54|0|
| suffix_short1 |54|2.115|0.296|0|54|0|
| suffix_short2 |54|2.364|0.129|0|53|0|
| hybrid |54|1.960|0.664|0|39|0|
| block32 |36|1.048|0.977|11|19|3|
| block128 |36|2.748|1.477|6|6|0|
| block128_short2 |36|3.087|0.805|6|23|1|
| blockpage |18|0.954|1.120|12|6|4|
| blockpage_short2 |18|1.249|0.621|4|15|1|
| blockpage_hybrid |18|1.048|1.239|4|5|0|

R187: choose exact net-prefix postings for lengths 1–3 using estimated avoided residual entries / estimated persistent row cost. For prefix q let W(q) be count of residual (suffix,cid) entries in its range, Z(q) nonzero aggregated cid corrections. Gain proxy W-Z; materialize exact sums when ratio (W-Z)/(key bytes+encoded posting bytes+12) is high. Corpus only, no query-plan features. A selected prefix with zero net postings stores an explicit empty marker (missing cache row must fall back). Budgets 2%,5%,10% of measured base block archive use encoded cost estimates, not enforced file-size constraints. Page overhead can make actual increment larger.

18 workloads, 2 new seeds 189–190, 3 vocab sizes, sub/mixed/repeat, 400 pairs each, 5 arms, 5,664,000 comparisons.

| arm | median storage / FTS | median P95 / FTS | median storage / block | median P95 / block | both vs FTS |
|---|---:|---:|---:|---:|---:|
| blockpage |0.818|1.275|1.000|1.000|3/18|
| cache2 |0.864|0.962|1.056|0.767|6/18|
| cache5 |0.864|0.806|1.100|0.672|8/18|
| cache10 |0.955|0.694|1.155|0.530|12/18|

Cache10 faster than uncached 17/18. No universal dominance. Highly repetitive synthetic text particularly favors the approach.

Scale check: 6 cases, seeds191/192, vocabulary256, 2000 pairs each, sub/mixed/repeat, 4 arms, 7,680,000 comparisons. Total R186/R187 78 workload configurations, 7 seeds, 44,289,600 comparisons with no observed discrepancy. Ratios median across six cases: blockpage size0.994/p95 0.618, cache5 size1.055/p95 0.328, cache10 size1.091/p95 0.244. Both cached modes smaller and faster only 2/6 (repetitive). Mixed cases are larger than FTS. Native timings are noisy and sequential; no cold IO, no RSS, no complete archive or ranking claim.

| seed/regime | FTS bytes | block bytes | cache5 bytes | cache10 bytes | FTS p95 us | cache10 p95 us (rounded) |
|---|---:|---:|---:|---:|---:|---:|
|191/sub|335872|335872|356352|368640|1044|183|
|191/mixed|339968|577536|610304|634880|580|180|
|191/repeat|208896|102400|114688|114688|3387|639|
|192/sub|335872|331776|352256|364544|938|281|
|192/mixed|339968|577536|610304|634880|747|129|
|192/repeat|208896|102400|114688|114688|1729|815|

Raw local per-arm files SHA256 (full raw results and historical scripts supplied in separate CDG-R186-R187-repeated-experiments.zip, not all copied into GitHub in this commit):
seed186.json 0c4824b2be6e36a71766c4a0ac3b133c6ba5b493ec3a12aafe4f2dc63ab3eec2
seed187.json d22442440e80814ad1dbcaa0249525971cec537cc63f0207b7b09845b7c6434b
seed188.json 92ef929c41e608e6e81ca817fb251a13f42bee364baa0a3ae6651ae6229a45d6
cache-results.json 22c0c871306648f8495ce3b5d350608ab6ecc17424556fcb695a6b6ca3dd7576
scale-results.json 109d537b8c5494eb03e78bd9d92e5193d562eb59667abe0472b17ea7f37587d7

Reproduce final format: compile count.c with cc -O3 -Wall -Wextra -Werror -shared -fPIC count.c -o count.so; run python probe.py --suite cache or --suite scale. Repo script is transcription of local final implementation with consolidated CLI, not byte-identical historical local scripts. Hosted smoke validates separately, pending at commit.

Prior art: compressed dynamic q-gram self-indexes https://doi.org/10.1016/j.ic.2020.104518 ; repetitive document retrieval with precomputed document lists https://pmc.ncbi.nlm.nih.gov/articles/PMC5445192/ ; prefix trie inverted files https://www.sciencedirect.com/science/article/pii/S030645739700037X . Suffix keys, prefix materialization, signed frequency differences, front coding and compressed postings are not new. Candidate contribution: select exact aggregated signed deltas based on cancellation opportunity, coupled with bounded-length historical phrase reconstruction. Requires real revision corpus matched controls and transactional integration. No RH theorem used.

Next: test identical selected anchors and source archive on AP/CLARK and real Git histories; use real tokenizer, lexicon charge, all active revision rank/DF/source parity, compare R167 native signed and R155 fragment baselines. Measure actual page/cold-read and peak memory if feasible. Do not claim aggregate synthetic result as paper-ready improvement. Keep ACMSE full paper R159/R160 and signed-correction poster R165–168 as previously scoped; this work is exploratory.
