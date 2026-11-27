# R170: shared token-ID tape and frequency postings

Status: implemented, hosted validation pending. Parent R169 bb80c9c929afcc603da4383cea2abe5b30f394ae.

## Verified evidence and prior negative controls
R169 initial AP 10,009 run 45916937662: 1,120 shared-alignment candidates, 494007 original dictionary frame bytes vs 668667 script frame bytes, zero accepted; identical aligned database 18980864 bytes. Independent adaptive 18583552 bytes; positional 20684800. Exact ranks. Reject shared script default.
R156 committed AP 74,364 results: self_unsharded 109293568 bytes vs marginal 148455424, but uniform read median 1143346us vs 47.25us; self_512 121499648 bytes and 16690us; self_128 138362880 and 4781us. R157 forward_positional 200138752 bytes; forward_presence 143060992 vs marginal_presence 91381760, with much worse query latency than positional. R157 duplicated normalized token data as compressed canonical text. R158 used frequency postings with raw-source verification. Do not rediscover these as novelty.

## Design
A corpus-wide exact lexicon assigns integer IDs; per-content tape stores fixed32 IDs in sequence, independently compressed or raw. Term-frequency lists use R155 delta-varint posting codec and optional Zstd, addressed by same ID. Single-token scoring needs only postings. Phrase scoring intersects candidate postings and verifies overlaps in aligned integer byte search; unaligned matches rejected. Canonical text tape control uses the same frequency posting layout. All vocabulary, tape, metadata, source frame and posting pages charged. Global vocabulary loaded once per opened database and timed; full term lists and candidate tapes decoded. No raw source reads in tape query paths.

Test optional source residual with normalized tape as predictor (kind 4). Preserve all source revisions used as one-hop parents; only replace others if marginal frame storage decreases and existing compression/activation/decoded-byte bounds pass. Charge compressed tape and residual plus unique raw lexical byte lengths for ID source recovery, even with resident lexicon. Charge intermediate integer tape and lexical bytes in decoded bound; source parent depth remains bounded. No relaxed bound claim. Compare positional, adaptive, frequency/no tape, canonical tape+joint, integer tape with unchanged source, integer tape+joint. Same frequency layout and query plan; source-only comparison holds integer index bytes constant. Native BM25 and DF parity, reopen before source audit, all source digests, logical byte bounds, per-class warm query and setup. No independent reproduction or physical IO claim. A tape that fails source admission is a retrieval-only structure, not evidence of persistent source/index savings.

Unit tests: 1,000 randomized integer overlap/alignment cases, empty/unknown/repeated tokens, Unicode, historical cutoffs, exact source bytes after reopening. Hosted results pending.


## Executed local subsystem probe
SQLite 3.46.1 and system libzstd level 3, fixed seed 170. Independent copy of aligned integer phrase counting passed 10,000 random comparisons including overlapping matches and unaligned bytes. Synthetic storage: 1,000 documents of 500 uniformly sampled tokens, vocabulary terms fixed width "tokenNNNNNN". Include vocabulary and tape tables; no postings or source frames. All databases VACUUMed. No corpus or latency claim.

| Vocabulary terms | Text tape file bytes | Integer tape file bytes | Text compressed payload | Integer compressed payload |
|---:|---:|---:|---:|---:|
| 100 | 1036288 | 831488 | 874311 | 746066 |
| 1000 | 1400832 | 1400832 | 1134789 | 1029371 |
| 10000 | 2252800 | 1572864 | 1374259 | 1254734 |

Equal physical size at 1000 terms despite smaller integer payload. Local experiment source adjacent. Initial R170 hosted run 45917277426 started for implementation commit b9a2509d4d487dbe8c488fde4b0cb475ac3925df.
