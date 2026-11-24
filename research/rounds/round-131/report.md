# R131: fixed budget sensitivity and codec screen

Status: protocol and implementation only; no results yet. R130 is the parent. Both corpora are reused evaluation sets.

Integrated arms: snapshot, prev8, anchor8, original bounded anchor, candidate counts 1/2/8 (original 4), tighter decoded ratio 1.75, tighter activation 1.10, relaxed activation 2.00, relaxed individual frame ratio 1.00. Each varies one parameter relative to the original. No retrospective replacement of the R129/R130 frozen policy. Every arm retains the complete matched archive, exact source and historical ranking oracle, receipt replay and crash checks. Same five-dimensional dominance criterion.

A separate source-only screen uses xdelta3 VCDIFF against prior revision, with depth 0/1/4/8 and independent Zstd snapshots as fallback. Compare its payload, logical reconstruction and depth to the corresponding Zstd R130 arms; do not compare VCDIFF payload to full SQLite archive sizes. Subprocess startup and temporary files make timing comparisons inappropriate. The screen verifies exact reconstructed bytes and records version information. If competitive, integrate a native decoder and common archive schema before claiming integrated superiority. This is not a full WikECD or Git pack reproduction.

Interpretation: report all tested arms including failures, do not select a new headline policy on these reused corpora without fresh independent validation. Remaining blockers: alternate codec integrated test, fresh held-out histories, independent runner variability, scale, full prior-art audit.
