# R131: fixed budget sensitivity and codec screen

Status: both final corpus jobs passed. R130 is the parent. Both corpora are reused evaluation sets.

Integrated arms: snapshot, prev8, anchor8, original bounded anchor, candidate counts 1/2/8 (original 4), tighter decoded ratio 1.75, tighter activation 1.10, relaxed activation 2.00, relaxed individual frame ratio 1.00. Each varies one parameter relative to the original. No retrospective replacement of the R129/R130 frozen policy. Every arm retains the complete matched archive, exact source and historical ranking oracle, receipt replay and crash checks. Same five-dimensional dominance criterion.

A separate source-only screen uses xdelta3 VCDIFF against prior revision, with depth 0/1/4/8 and independent Zstd snapshots as fallback. Compare its payload, logical reconstruction and depth to the corresponding Zstd R130 arms; do not compare VCDIFF payload to full SQLite archive sizes. Subprocess startup and temporary files make timing comparisons inappropriate. The screen verifies exact reconstructed bytes and records version information. If competitive, integrate a native decoder and common archive schema before claiming integrated superiority. This is not a full WikECD or Git pack reproduction.

Interpretation: report all tested arms including failures, do not select a new headline policy on these reused corpora without fresh independent validation. Remaining blockers: alternate codec integrated test, fresh held-out histories, independent runner variability, scale, full prior-art audit.

## Verified results

Both jobs passed at 302fb912d41b1baef77d5850954346a3402b8e6b, run https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45494253552. R129 manifests and workloads matched. Across 11 integrated arms: 8250 exact source readbacks, 7040 ranking comparisons, 110 process-death checks; zero observed score error. Candidate counts 1,2,4,8 have identical deterministic metrics on both corpora; this does not prove identical choices or universal equivalence. Tight activation (1.1x) strictly dominates bounded_anchor on CPython under the five declared objectives (5,185,536 vs 5,210,112 B), but the frozen policy remains nondominated on BIPs (4,780,032 vs 4,800,512 B). Tight decode (1.75x) nearly eliminates useful deltas. Relaxed activation does not improve storage. Local choices alter future anchor availability; specific causal mechanisms require anchor tracing. Source-only xdelta3 3.0.11 has larger payloads than matched Zstd predecessor policies at depths 1/4/8 on both corpora. This is not an integrated VCDIFF archive comparison. Do not retrospectively replace the frozen policy.

| Corpus | Policy | Archive B | Payload B | Mean decoded ratio | Max decoded ratio | Max activated ratio | Depth |
|---|---|---:|---:|---:|---:|---:|---:|
| cpython | relaxed_activation | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | tight_decode | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | k2 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | k8 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | snapshot | 9166848 | 4406056 | 1.0000 | 1.0000 | 1.0000 | 0 |
| cpython | anchor8 | 5279744 | 868378 | 1.8148 | 2.0360 | 1.1523 | 1 |
| cpython | k1 | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | prev8 | 5152768 | 804822 | 4.0278 | 8.9986 | 1.2038 | 8 |
| cpython | tight_activation | 5185536 | 740820 | 1.8537 | 2.0360 | 1.0973 | 1 |
| cpython | relaxed_frame | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| cpython | bounded_anchor | 5210112 | 745283 | 1.8557 | 2.0360 | 1.1583 | 1 |
| bips | relaxed_activation | 4792320 | 568561 | 1.8571 | 2.2992 | 1.6530 | 1 |
| bips | tight_decode | 7565312 | 3030643 | 1.0059 | 1.5203 | 1.0862 | 1 |
| bips | k2 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | k8 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | snapshot | 7589888 | 3051292 | 1.0000 | 1.0000 | 1.0000 | 0 |
| bips | anchor8 | 4849664 | 672462 | 1.8119 | 2.2992 | 1.6530 | 1 |
| bips | k1 | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | prev8 | 4710400 | 610268 | 4.0162 | 9.4258 | 1.6898 | 8 |
| bips | tight_activation | 4800512 | 598762 | 1.8380 | 2.0696 | 1.0992 | 1 |
| bips | relaxed_frame | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
| bips | bounded_anchor | 4780032 | 568414 | 1.8559 | 2.0696 | 1.2077 | 1 |
