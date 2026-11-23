# R114: Independent processed Wikipedia revision histories

**Status: PASS. Original-source CI run [45284548700](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45284548700).**

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

## Verified results

The pinned checkout contained 445 eligible articles and 2504 revisions, rather than relying on the upstream README counts. The deterministic sample comprised 100 articles and 567 revisions; all eight policies reconstructed every source exactly (4,536 policy/revision checks). Full input manifest SHA-256: `fd24e20eff865dd34567f7b94b1323cb86c3cd4046b09a7d47118547dc14f7a7`. Raw source bytes: 2,285,394 per arm.

| Policy | Physical SQLite B | Decode amplification | WAL B | Mean activated payload B |
|---|---:|---:|---:|---:|
| adaptive4 | 1,134,592 | 1.668 | 8,099,952 | 1894.7 |
| cdc1024 | 1,777,664 | 1.000 | 25,469,872 | 2346.0 |
| delta2 | 1,150,976 | 1.722 | 7,848,632 | 2038.9 |
| delta4 | 991,232 | 2.296 | 7,605,552 | 2243.5 |
| delta8 | 839,680 | 3.088 | 7,135,872 | 2483.1 |
| fixed2048 | 3,477,504 | 1.000 | 22,524,072 | 2102.8 |
| fixed512 | 1,667,072 | 1.000 | 41,991,072 | 2746.7 |
| snapshot | 1,929,216 | 1.000 | 10,048,712 | 1789.8 |

The depth-8 control uses 56.48% fewer physical bytes and 28.99% less appended WAL than snapshots, but decodes 3.09x original requested bytes. The snapshot control has lower mean activated compressed bytes than every delta arm. Chunk deduplication saves some payload bytes but introduces expensive manifests, B-tree pages and append WAL. Fixed2048 exceeds even independent snapshot physical size. These are actual physical source-only stores, not full search indexes or actual device write traffic. The SQLite layouts differ by their row populations. No per-edit times or actual query arrivals are available. Chunk decoder counts unique decompressed chunks within a request, whereas chain decoding includes all reconstructed ancestors. The current adaptive rule is a heuristic and does not dominate all controls. No new compressor, theorem or general advantage over WikECD is established.

Next: compare direct-to-checkpoint dictionary frames with previous-revision chains on disjoint hash-selected articles; bound ancestor reconstruction cost and test exact parent and SHA integrity. For a publication, add WikECD reproduction, real timestamps/access evidence and independently repeated hardware measurements. Do not treat this filtered corpus as a full revision stream.
