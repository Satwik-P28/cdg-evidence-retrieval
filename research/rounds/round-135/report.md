# R135: published WikECD and physical layout control

Status: all four original-code jobs passed.

R134 compares packed external files to source BLOBs inline in SQLite; SQLite allocation can confound storage comparison. Export exactly the existing snapshot and CDG encoded frames, unchanged, to a contiguous sidecar and replace each BLOB with a fixed 16-byte offset/length. Retain original dependency metadata and all index, ledger and provenance fields. Charge the entire sidecar and compacted SQLite database. Verify source bytes, identical rank receipts and equal logical decode/activation costs to original inline arms. This measures finalized layout effects, not an atomic append implementation.

Published wikecd==0.1.1, native compress_article, gzip JSON serializer and retrieve_range. Two settings: upstream default heuristic budget and explicit larger budget equal to twice total source character count per document. Input real UTF-8 revisions and original commit timestamps, per-document ordinal order. Store complete native artifacts contiguously with a per-revision offset/length pointer in the same SQLite retrieval archive. Charge every serialized byte. No adaptation of WikECD's compression algorithm. Exact byte checks are mandatory and any incompatible revision/API fails the arm. Distinguish cold per-article gzip JSON inflation and partition-prefix logical source volume (proxy, not decoder traffic) from actual CDG frame activation. Full native WikECD and TimIR system-level transaction equivalence is not claimed.

All arms reuse four largest frozen cohorts, verify manifest/query hashes, and preserve same full historical BM25 and evidence receipts. R134 Git results are the established comparison. No post-result parameter tuning.

## Results

All four jobs passed on 79bd29fd747d95134e578179e71a46787a209b5e, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45499545120. 10,770 exact readbacks and 7,680 historical ranking comparisons, zero observed score error. Packed CDG is within -0.39% to +1.17% of finalized Git depth-1 total size from R134; the logical reconstruction metrics are unchanged from inline CDG. Relative to matched packed independent snapshots it reduces total bytes by 30.9–42.6%. Published WikECD 0.1.1 default artifacts occupy 24.9–57.9% more-reducible total archive bytes (CDG reduction relative to WikECD). Both tested WikECD settings produce almost entirely literal anchors; neither establishes a strong tuned WikECD frontier, and no Wikipedia-native corpus has been tested here. WikECD partition-prefix source volume is a proxy, not actual decoder byte traffic; separately measured full JSON inflation/activation must not be conflated with it. Sidecar layout does not have atomic append/crash parity.

| Corpus | Policy | Total archive B | SQLite B | Sidecar B | Mean logical decode ratio | Max activation ratio |
|---|---|---:|---:|---:|---:|---:|
| bips | snapshot | 7589888 | 7589888 | 0 | 1.0000 | 1.0000 |
| bips | bounded_anchor | 4780032 | 4780032 | 0 | 1.8559 | 1.2077 |
| bips | snapshot_sidecar | 6983452 | 3932160 | 3051292 | 1.0000 | 1.0000 |
| bips | bounded_anchor_sidecar | 4500574 | 3932160 | 568414 | 1.8559 | 1.2077 |
| bips | wiki_default | 7843814 | 3932160 | 3911654 | 1.0000 | 47.5466 |
| bips | wiki_large_budget | 7848411 | 3932160 | 3916251 | 1.0010 | 47.5468 |
| cpython | snapshot | 9166848 | 9166848 | 0 | 1.0000 | 1.0000 |
| cpython | bounded_anchor | 5210112 | 5210112 | 0 | 1.8557 | 1.1583 |
| cpython | snapshot_sidecar | 8600360 | 4194304 | 4406056 | 1.0000 | 1.0000 |
| cpython | bounded_anchor_sidecar | 4939587 | 4194304 | 745283 | 1.8557 | 1.1583 |
| cpython | wiki_default | 11719088 | 4194304 | 7524784 | 1.0000 | 53.5656 |
| cpython | wiki_large_budget | 11719636 | 4194304 | 7525332 | 1.0000 | 53.5658 |
| k8sdocs | snapshot | 3334144 | 3334144 | 0 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor | 2215936 | 2215936 | 0 | 1.7797 | 1.4090 |
| k8sdocs | snapshot_sidecar | 2864806 | 1630208 | 1234598 | 1.0000 | 1.0000 |
| k8sdocs | bounded_anchor_sidecar | 1979384 | 1630208 | 349176 | 1.7797 | 1.4090 |
| k8sdocs | wiki_default | 2637350 | 1630208 | 1007142 | 1.0000 | 34.9299 |
| k8sdocs | wiki_large_budget | 2638392 | 1630208 | 1008184 | 1.0008 | 34.9305 |
| gitdocs | snapshot | 9461760 | 9461760 | 0 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor | 5582848 | 5582848 | 0 | 1.8203 | 1.2603 |
| gitdocs | snapshot_sidecar | 8358433 | 4182016 | 4176417 | 1.0000 | 1.0000 |
| gitdocs | bounded_anchor_sidecar | 5066811 | 4182016 | 884795 | 1.8203 | 1.2603 |
| gitdocs | wiki_default | 8355922 | 4182016 | 4173906 | 1.0000 | 36.6238 |
| gitdocs | wiki_large_budget | 8361662 | 4182016 | 4179646 | 1.0024 | 36.6243 |
