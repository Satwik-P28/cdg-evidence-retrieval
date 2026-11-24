# R136: real large-scale derived news revision storage

Status: public source acquired; full AP eligible subset evaluated successfully.

NewsEdits (Spangher et al., NAACL 2022; https://aclanthology.org/2022.naacl-main.10/ ; https://github.com/isi-nlp/NewsEdits) publishes preprocessed sentence-level revision tables. The upstream demo uses data/ap-matched-sentences.db and the split_sentences table with entry_id, version, sent_idx, sentence. Select AP only, deterministic SHA256 ranking of IDs with >=2 versions, add complete histories until 100,000 retained revisions or corpus exhaustion. Record actual count, source SHA256, selection and exact derived revision manifest. No size-based selection, no substitution of synthetic data. Duplicate or malformed sentence rows fail closed. Join sentence strings in sentence-index order with newline, preserve original upstream version IDs. Exactness means derived UTF-8 bytes only, not original article HTML or original source bytes. No corpus-global timestamps or historical RAG claim.

Compare six source-only SQLite policies with identical source/ordinal/digest metadata and upstream version mapping. Charge compacted SQLite bytes, payload bytes, exact source reads, per-request logical bounds and decoded work. Do not compare these source-only sizes to full FTS archives. Preserve every tested policy including losses. Source acquisition via public Google Drive folder is not yet verified; workflow can take explicit public artifact ID if listing fails. No raw news text uploaded to artifacts. This is a large-scale source-storage gate, not the final integrated scale experiment.

## Results

R136 completed on commit 9b06f135 (https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/45500923265). Exhausted all 12,841 eligible AP documents, yielding 74,364 derived text revisions (target 100,000 not reached), 327,838,512 raw bytes and 446,184 exact readbacks across six policies. Source-only SQLite bytes fall from 300,437,504 to 132,505,600 (55.90% reduction) for bounded_anchor. Relative to prev8 the archive premium is 17.68% and mean logical decoded work falls 54.84%. Worst-case decoded ratios: prev8 489.02x, anchor8 128.89x, CDG 2.4877x; worst activation CDG 1.5x. Four candidates improve source SQLite size by 4.15% and payload by 4.41% against k1, reversing the small-corpus equivalence finding. This is evidence of workload sensitivity, not universal multi-anchor superiority. NewsEdits is derived sentence text; no original news byte identity, FTS index, chronological global replay, or RAG accuracy is tested. The source database and selection hashes are recorded in results.

| Policy | Source SQLite B | Payload B | Mean decode | Max decode | Max activation |
|---|---:|---:|---:|---:|---:|
| snapshot | 300437504 | 149369811 | 1.0000 | 1.0000 | 1.0000 |
| prev8 | 112594944 | 51566108 | 3.6380 | 489.0189 | 86.8889 |
| anchor8 | 148963328 | 67227462 | 1.7436 | 128.8889 | 50.5926 |
| k1 | 138244096 | 62752187 | 1.6220 | 2.4877 | 1.5000 |
| bounded_anchor | 132505600 | 59982761 | 1.6428 | 2.4877 | 1.5000 |
| tight_activation | 134160384 | 62421909 | 1.5921 | 2.3164 | 1.1000 |
