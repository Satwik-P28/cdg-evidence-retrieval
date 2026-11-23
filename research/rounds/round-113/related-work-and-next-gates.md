# R113 related-work audit and controlled next research gates

**Status:** Literature research and experimental proposals, not implemented results. Checked 2026-11-23.

## What the related literature takes away from our originality claim

1. **OReO, ICDE 2024** by Kexin Rong, Paul Liu, Sarah Ashok Sonje and Moses Charikar: online data layout reorganization under workload drift with metrical-task-system competitive guarantees. It already addresses unknown future workloads and tradeoffs with migration costs. CDG's static multiple-choice knapsack cannot be presented as a novel framework or robust online optimizer. https://arxiv.org/abs/2405.04984
2. **RocksDB Blob Direct Write With Partitioned Blob Files, June 2026:** index references and partitionable blobs avoid repeated large-value movement in LSM/WAL machinery. This is directly relevant to R106/R113 write amplification, and suggests separating source receipts/index from larger payloads. A documented v1 limitation is crash recovery of in-flight direct-written blobs. CDG must not claim independent novelty for generic value separation. https://rocksdb.org/blog/2026/06/20/blob-direct-write-partitioned-blob-files.html
3. **Partition, Don't Sort!, PVLDB 2024:** block-partition choice and compression are already a co-design literature. https://www.vldb.org/pvldb/vol17/p3456-hansert.pdf
4. **WikECD, ACM Transactions on the Web, 2026** (Amit Verma, Simran Setia, Gianluca Demartini): original-version compression and random revision reconstruction for Wikipedia. This makes simple 'versioned compressed corpus with fast revision lookup' an existing idea. Any CDG paper must distinguish receipts/FTS correctness and multi-resource actual operations from existing revision-compression algorithms, and use WikECD as a controlled comparison when testing Wikipedia histories. https://doi.org/10.1145/3787449 ; source https://github.com/descentis/WikECD
5. **Wikimedia Analytics API and MediaWiki Revision API:** historical article view-count series and timestamped revision histories are accessible. Treat article pageviews as **article-access proxies**, not individual paragraph retrievals or true user query logs. Daily/weekly train/test chronological splits are possible; revisions furnish genuine edit event times and version data. https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/ and https://www.mediawiki.org/wiki/API:Revisions

## Linked research graph

```text
R106 pseudo-access false positive / static archive frontier
           |                       |
           v                       v
R113 source-only DP negative       OReO (online drift)
           |                       |
           +--> physical byte feasibility <-- RocksDB partitioned blobs
           |                       |
           v                       v
     immutable SHA+version receipts and crash/snapshot safety
           |                       |
           +-----------------------+
                     |
       WikECD / real Wikipedia history + time-binned pageview traces
                     |
       multi-resource objective with independent chronological tests
                     |
       compare simple hash/length/static vs existing real systems
```

## Next implementation gates

### Gate 114-A: actual physical feasibility (necessary, not novel)

Build layouts **before reading query outcomes** and measure their actual SQLite file sizes; choose only those meeting 8 MiB. Compare raw read/write costs at physically matched bytes to `hash_50_25` and `length_budget_35` and `all_paper`. Do not assume monotonicity of physical bytes with proxy fraction or use hidden test query performance to tune the selections. Since R113 has observed 11-policy results, a repeated QASPER DEV search would be exploratory, not fresh evidence.

### Gate 114-B: real time-series external validation

Freeze a reproducible page set and a chronological train/validation/test split **before** collecting performance outcomes. Fetch Wikipedia revision metadata/content and human pageviews at article level with API rate limits and SHA receipts. Reproduce WikECD version retrieval where permitted, train policy on earlier periods, and evaluate later access and edits. Report source/page selection bias, revision content size, redactions/deletions, license terms, retrieval timing, storage and crash recovery semantics. Distinguish real recorded article pageviews from simulated paragraph demands. Do not call pageviews a RAG retrieval trace.

### Gate 114-C: failure-injection provenance

Use immutable block IDs, generation-bound SHA receipts and reader snapshots to test atomic migration while reads continue. Inject cancellation after new block write, after index/receipt staging, before commit, and during garbage collection. Validate that every read returns a single consistent version or explicitly refuses. Compare against RocksDB's documented direct-blob durability boundaries; do not assert stronger guarantees without fsync/crash/restart tests.

### Gate 114-D: evidence-level benefit

Only after storage correctness and independently timed workloads, evaluate claim-level evidence recovery/answer attribution with source consistency across revisions. A storage policy that only changes decompressed bytes cannot improve existing FTS5 rankings by construction. A new retrieval/grounding mechanism, stronger retriever baselines and independently annotated evidence are required to claim hallucination reduction.

**Publication gate:** A short empirical paper can use R101–R106's real source/archive Pareto findings and R112–R113's negative controls. A novel top-tier full paper needs results that beat the strongest published/indexed baselines or a substantive new theorem/guarantee; current R113 is not such a result.