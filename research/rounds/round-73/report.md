# Round 73: Exact Archived NLI Premise Windows and Physical Cost Boundaries

**Date:** 2026-11-17. **Status:** five dedicated source-byte regression tests passed, full SHA-pinned dataset run successful in GitHub Actions **44228871384**. This is a source-access and evidence-provenance audit linked to Round 72. It executes **no new NLI model or generated-answer prediction**.

## Question

Round 72's general NLI model, although trained on SNLI/MultiNLI and tested against RAGTruth human labels, read original source text directly. The source windows were normalized by whitespace, so claiming they came from exact compressed source bytes without testing would overstate the experiment. Do whole-document or content-defined source CAS layouts reduce the logical compressed source traffic for the *actual evidence windows* selected by the NLI reader, after charging persistent storage?

## Frozen reproduction of Round 72 source groups

- RAGTruth Git SHA c103204b9ce28d6bbad859304bf30de72b8ed8fe, SHA-verified upstream source and answer JSONL, no original text redistribution.
- Same SHA-sorted **8 QA and 16 Summary source groups**, sample ID SHA-256 **fd43a5ef07f80a51b05f590f55867eaefa70c9d02374fef7fd54d788d9cb9d84**; 141 quality-good responses and **760** deterministic sentence-like fragments exactly as R72.
- Identical source-window policy: 150 original whitespace-separated words, stride 100, at most 96 windows per source. Return the *exact UTF-8 byte offset range* of each window, read via a source/manifest SHA-bound receipt, and separately verify that whitespace-normalizing the byte-retrieved original source segment produces the *identical NLI premise string* selected in Round 72.
- Query word overlaps used to choose the original first source window, single lexical-best window, or three lexical-best windows. No human annotation controls window selection. This is a full read-path reconstruction, not semantic entailment or claim verification.

## Experimental storage and source activation controls

Two conventional reversible source archives were built for the same 24 source blobs: **whole-source Zlib6 with compact binary-Zlib manifest** and **gear512 content-defined frames with compact binary-Zlib manifest**. A separate SQLite FTS5 source-line index was also built to measure its persistent size, **but the actual word-overlap window selector scans in-memory source windows and does not use this FTS index**. Thus FTS5 storage is an optional conventional-baseline overhead, not an inherent requirement of this precise retrieval implementation.

Source receipt checks: **48 full-document SHA-bound readbacks** (24 unique sources times 2 layouts) and **4,546 selected exact byte-span readbacks** through the layouts. All passed without source byte changes. The normalized content shown to the NLI model is **not** claimed to be itself a byte-exact source quotation, only a verifiably deterministic transformation of an exact byte interval.

### Retained bytes

| Component | Bytes |
| --- | ---: |
| Whole-source Zlib6 CAS plus compact manifest | **28,398** |
| Content-defined gear512 CAS plus compact manifest | **35,437** |
| Optional SQLite FTS5 source-line index | **73,728** |
| Whole archive + optional FTS index | 102,126 |
| Gear512 archive + optional FTS index | 109,165 |

The optional FTS index exceeds either source archive, so the storage boundary cannot ignore indexes in deployments that actually use them.

### Mean compressed frame activation per response

Each metric takes the **union of compressed frames required across all sentences of one response**, simulating a response-local warm frame cache. It is a logical compressed-byte activation count, **not** a measured physical cold SSD read or random-I/O latency.

| Task / evidence policy | Mean whole-Zlib activated bytes | Mean gear512 activated bytes | Mean raw requested window bytes, before frame dedup |
| --- | ---: | ---: | ---: |
| QA, first | 528.933 | 567.933 | 4,503.444 |
| QA, best lexical | 528.933 | 567.933 | 4,346.333 |
| QA, best three | 528.933 | 585.711 | 8,119.911 |
| Summary, first | 1,447.188 | **812.812** | 5,123.604 |
| Summary, best lexical | **1,447.188** | 1,556.354 | 4,938.125 |
| Summary, best three | **1,447.188** | 1,698.271 | 13,894.146 |
| **Combined, first** | 1,154.128 | **734.660** | 4,925.681 |
| **Combined, best lexical** | **1,154.128** | 1,240.901 | 4,749.255 |
| **Combined, best three** | **1,154.128** | 1,343.199 | 12,051.305 |

The whole-source archive activates the full source's compressed blob once per response regardless of source window position. The gear512 archive is cheaper on **first** windows of longer Summary documents, but lexical-best and top-three windows activate enough distinct frames to exceed the compressed whole source on mean response-local traffic. This is a real policy-by-format interaction, not a universal condemnation of content-defined chunking.

The top-three windows increase requested original window bytes substantially. Round 72 had already observed **no response-level human-label F1 gain from top-three versus top-one window NLI** at its fixed threshold. Therefore the additional model pairs and activated frames are **not justified by an observed accuracy improvement** on this sample.

## Accounting limitations and decisions

**Keep:** source/manifest SHA receipts, exact UTF-8 byte offsets, explicit deterministic premise normalization, task-stratified response-local unique frame accounting, separate optional FTS5 footprint.

**Reject:** assuming chunked source compression is inherently faster/cheaper for the evidence accesses of a semantic verifier, or that more retrieved windows automatically increase factual precision. Whole-source compression uses less retained storage on the measured QA/Summary sources and can require fewer compressed activated bytes when the model scans a substantial portion of the source per answer.

**Open costs:** The measured bytes are not actual physical SSD I/O and ignore cache eviction across multiple responses, page alignment, decompression CPU, true source update cost, model weights, citation rendering, and transactional durability. The in-memory lexical window selector is not free: build/scan work and its source text in RAM are separate implementation costs, with simple warm Python timing recorded but not a production throughput benchmark. The R72 model scored *original downloaded text*; R73 proves the windows can be supplied from the reversible archive but **does not rerun the NLI model from those archived bytes**. Separate reproduction of identical window strings strongly implies identical model inputs under the same tokenizer, but is not a measured end-to-end integrated inference run.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-73 -p 'test_*.py' -v
    python experiments/round-73/byte_exact_windows.py --out experiments/round-73/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44228871384 . Exact source text and original generated responses remain at their upstream origin, not distributed in the repository.
