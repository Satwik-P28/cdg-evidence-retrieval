# R114: Independent processed Wikipedia revision histories

**Status: implementation pushed; original-corpus results pending.**

R113 rejected the source-only static layout proxy. R114 changes the source
workload, not the name of the optimizer. The public WISE 2021 Versions dataset
contains real processed article revisions in within-article chronological
order, selected and filtered by the upstream authors. Pin repository commit
`06b32f753c4ac6fd154ffa8b5a9af2cd11b777c0` and hash original input file bytes.
Select up to 100 articles by a predetermined SHA-256 rank.

Compare independent Zstandard snapshots, previous-version raw dictionary
frames with bounded chains 2/4/8, a causal adaptive depth-4 threshold, fixed
512/2048-byte chunk deduplication, and gear content-defined chunking
(256..4096 bytes, approximately 1024-byte boundary mask). All arms use the
same SQLite revision and chunk tables, per-version SHA-256, sequential
within-article append transactions, and exact random revision reconstruction.
Count physical database bytes after VACUUM, journal file growth with automatic
checkpoint disabled, actual compressed bytes fetched including manifests,
and decompressed source bytes. All revisions receive equal request weight;
this is NOT an observed access distribution. Timings are exploratory.

Prior art: [Versions](https://github.com/natwar-modani/versions) (CC BY-SA 3.0);
[WikECD](https://doi.org/10.1145/3787449) (directly relevant existing revision
storage); [BloArk](https://arxiv.org/abs/2410.04410); [FastCDC](https://www.usenix.org/conference/atc16/technical-sessions/presentation/xia).
This experiment does not reproduce WikECD or prove a new algorithm. No corpus
content is redistributed. No timestamps, full edit histories, observed query
logs, FTS retrieval, RAG accuracy, or physical SSD write counters are present.
