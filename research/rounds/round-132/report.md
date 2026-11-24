# R132 fresh histories and scaling protocol

Status: all six original-code jobs passed.

Fixed pins before examining source compression outcomes: git/git v2.47.0 (777489f9e09c8d0dd6b12f9d90de6376330577a2), kubernetes/website main commit cd5dc586db87bc80666a54ce7ba113e19b062b91. Git top-level Documentation .txt/.adoc files and English Kubernetes docs Markdown excluding _index.md. Hash selection from each baseline snapshot with new R132 salt. Two sizes per corpus: 400 path-touch commits / 80 requested files and 800 / 160. Report excluded paths; no replacement. Two separately scheduled large jobs, seeds 132 and 133, change build and read order but not source or query plan. Small versus large cohorts differ in baseline time, composition and history length; descriptive scale test, not pure controlled size extrapolation. No latency confidence intervals from two runners.

Seven fixed integrated policies: snapshot, prev1, prev8, anchor8, frozen four-candidate policy, latest-only literal anchor, and tighter 1.1x activation. All use R131/R129 retrieval contract and exact source, ranking, receipt and process-death checks. Record machine/software environment and SHA256 of ordered source encoding decisions including payload digests. This distinguishes matching aggregate metrics from identical encodings. Cross-run manifests, query plans, deterministic costs and encoding hashes must agree before pooling. Timing variation is reported separately.

The primary policy remains the original frozen bounded_anchor. Latest-only and tight activation are exploratory candidates preselected after R131, now checked on new repositories. Do not change thresholds based on R132 then describe R132 as held out. VCDIFF remains source-only; no universal codec superiority.

## Results

All six jobs passed on d7be66b25d0c7084b8d5cfe163b817238f453a70, https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45496514345. Four unique corpus/window configurations; repeated large jobs must not be counted as new datasets. Frozen bounded policy is nondominated in all four measured configurations. Latest-only and original four-candidate encodings match exactly in all four configurations by ordered dependency and payload digest. Large replicates agree on manifests, workload, deterministic metrics and encoding digests for every policy. Conventional anchor8 is smaller on both Kubernetes configurations; CDG has lower worst-case activation and decode ratios, not universal storage superiority. Exclusions of missing paths and different baseline windows limit pure scaling interpretation. Two runner repetitions are descriptive, not a confidence interval.

| Corpus | Window | Retained docs | Revisions | Snapshot B | Bounded B | Saving | Depth-8 premium | Decode reduction vs prev8 | Anchor8 B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gitdocs | 400 | 80 | 221 | 3526656 | 2187264 | 37.98% | 0.00% | 44.20% | 2203648 |
| gitdocs | 800 | 160 | 667 | 9461760 | 5582848 | 41.00% | 5.09% | 53.97% | 5615616 |
| k8sdocs | 400 | 69 | 144 | 1269760 | 929792 | 26.77% | 1.79% | 40.37% | 925696 |
| k8sdocs | 800 | 141 | 378 | 3334144 | 2215936 | 33.54% | 3.84% | 50.86% | 2207744 |

| Corpus | Runner CPU | Seed | Append median us | Source read median us |
|---|---|---:|---:|---:|
| gitdocs | Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz | 133 | 1286.16 | 78.01 |
| gitdocs | AMD EPYC 7763 64-Core Processor | 132 | 1506.54 | 81.51 |
| k8sdocs | AMD EPYC 9V74 80-Core Processor | 133 | 860.81 | 39.20 |
| k8sdocs | Intel(R) Xeon(R) 6975P-C | 132 | 783.80 | 36.48 |
