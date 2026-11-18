# Round 71: Source-Only Faithfulness Bound and Verifiable Archive Receipts

**Date:** 2026-11-17. **Status:** full RAGTruth QA test split analyzed, five new tests passed in GitHub Actions run **44215418502**. This round makes a narrow conditional impossibility statement about **source-only** warning algorithms, not about response-conditioned semantic verifiers or all factual RAG systems.

## Structural experiment

RAGTruth supplies multiple generated responses conditioned on exactly the same human-provided source. The response text and hallucination-span labels vary while the source document and its cryptographic content digest remain fixed. Any deterministic classifier whose only input is source bytes and source identity must assign the **same** prediction to every response in that group. In a group containing both human-positive and human-negative responses, at least the smaller class must be misclassified regardless of the classifier's implementation.

For each QA test source, compute:
- Number of human-labeled unsupported responses and number without positive annotation.
- Whether the same source has both kinds of generated outputs.
- Nondeployable label-oracle majority-vote upper bound on source-only accuracy: sum of max(positives, negatives) across groups divided by all responses.
- The minimal unavoidable number of source-only classification errors: sum of min(positives, negatives) across groups.
- Always-accept and always-reject baselines and a strict target that excludes labels with implicit_true.

This best-source-only oracle deliberately **uses the human labels** for a mathematical ceiling, and cannot be deployed to detect real outputs. A proper verifier that conditions on **both source and response** is not subject to this bound.

## Full QA test split results

There are **900 responses from 150 distinct QA source groups**, six generated outputs per group.

| Metric | Human unsupported labels | Strict target excluding implicit_true |
| --- | ---: | ---: |
| Responses with a positive label | 160/900 | 133/900 |
| Source groups with both positive and negative responses | **94/150** | 82/150 |
| Minimum unavoidable source-only classification errors | **150/900** | 125/900 |
| Best possible oracle source-only accuracy | **750/900 = 83.333%** | 775/900 = 86.111% |
| Always accept (predict no unsupported response) | 740/900 = 82.222% | 767/900 = 85.222% |

The oracle's apparent 83.3% accuracy is only **1.1 percentage points** greater than the vacuous always-accept baseline, because the dataset is imbalanced. Source hashing, exact citation IDs, successful lossless decoding and mere source existence therefore cannot be interpreted as a sufficient statement about response groundedness. They can be valuable as evidence storage provenance but do not identify an unsupported claim in an answer.

Previously inspected R69 source group partition: 128 groups, 768 responses, 80 mixed-label source groups, 128 minimum unavoidable errors; source-only oracle accuracy 640/768 = 83.333%. The 22-group R70 confirmation partition: 132 responses, 14 mixed-label groups, 22 minimum unavoidable errors and oracle 110/132 = 83.333%. Note that R70 excluded one quality-flagged response and used 131 response records, whereas these structural counts include every test response by default. The quality-good-only results are recorded separately in the JSON.

## Exact archive and source-index costs

Every original QA source passage was UTF-8 encoded, archived under two reversible codecs, and returned through source- and manifest-bound SHA source receipts. Exact full-source and 128-byte probe comparisons were executed against the original content, with a common SQLite FTS5 line index built separately and its bytes counted.

| Storage component | Bytes |
| --- | ---: |
| Original 150 QA source passages, uncompressed | 205,135 |
| Whole-source Zlib archive plus manifests | **96,202** |
| Gear512 content-defined frame archive plus manifests | 117,721 |
| Shared FTS5 SQLite source-line index | **163,840** |
| Whole archive plus FTS5 index | 260,042 |
| Gear512 archive plus FTS5 index | 281,561 |

There were **300 exact full-source readback checks**, **600 exact compressed source-span readback checks**, and **293 FTS5-returned source byte-span checks**. For sampled 128-byte ranges, content-defined framing activated an average of **476.39 compressed bytes**, versus **604.273** for whole-source Zlib, but required an additional 21,519 archive bytes at rest. This is logical compressed frame activation, **not** measured physical SSD I/O.

None of these cryptographic receipts has information about the varying response unless the response is actually inspected. A source may be perfectly archived and still be used to generate a human-labeled unsupported response.

## Limits and publication discipline

This conditional source-only error lower bound is a direct counting argument, **not a new information-theoretic theorem**. It does not constrain a model with access to the generated response, its token probabilities, citations, metadata or a semantic entailment model. The human annotations represent source-faithfulness judgments rather than a complete exhaustive determination of objective truth. Source passage authorship, time applicability, authority and claims made during inference are outside the archive verification check.

The QA subset is one of RAGTruth's task families, and all responses were originally generated by other models. Source bytes are SHA-pinned and reproduced exactly, but neither answer generation nor hallucination reduction was performed by CDG in this round.

**Decision:** Keep lossless receipts for provenance and append response-conditioned claim verification as a separate subsystem. Do not promote a purely source-byte-grounded hallucination detector, or measure success solely by whether a citation matches source text. Future work requires a strong pretrained NLI or grounded claim checker evaluated on independent human annotations, with a full cost frontier.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-71 -p 'test_*.py' -v
    python experiments/round-71/source_only_bound.py --out experiments/round-71/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44215418502 . Original RAGTruth data and underlying source contents remain at their upstream repositories; only aggregate statistics and byte hashes are published.
