# Licensing note

This compilation is a research record rather than a blanket relicensing of historical third-party inputs. External datasets, embedded third-party scripts and borrowed code retain their original applicable licenses. Until individual source packages are audited for provenance and licensing, do not treat every nested archived file as permission to redistribute or sublicense it. Consider making a private repository until the audit is complete.


## Audited bundled research inputs (2026-11-17)

- **Astral uv README historical revisions** in research/rounds/round-38/uv_readme_revisions.json and downstream experiments: sourced from https://github.com/astral-sh/uv at pinned upstream Git blob IDs, with corresponding dual MIT/Apache-2.0 project licensing. A copy of the source MIT notice is retained as third_party/uv-LICENSE-MIT.txt. No affiliation or endorsement.
- **PRISM-Edit TimeConflict subset** in experiments/round-41/timeconflict and downstream rounds: sourced from https://github.com/CheerCHuang/PRISM-Edit, which declares its own TimeConflict dataset contribution and MIT project licensing, subject to bundled third-party component notices. The verbatim upstream MIT notice is retained as third_party/PRISM-Edit-LICENSE.txt. Structured facts and QA records remain attributed to the upstream creators, not original CDG data.

The notices are separate from any license that may apply to original CDG code. Some older research archive contents may contain other third-party materials that still require independent audits. Documentation of a license is not proof of independent truth/accuracy of dataset assertions and does not authorize use of unrelated model weights.


## HotpotQA development evaluation inputs (Rounds 54–59)

HotpotQA is credited to Yang et al. (EMNLP 2018), with the original dataset distributed under **CC BY-SA 4.0** (https://hotpotqa.github.io/). These experiments use a fixed, SHA-256-checked mirror of the official distractor development dataset at Hugging Face namlh2004/hotpotqa revision 7e54db4656209750ff487f6fdf8e39a66dba136b, object digest e3da074df24e8369009918aa5cdbdd254dadcde4c63f7569d36afd6f2268caa8. Data bytes are downloaded into ephemeral GitHub Actions runners and are **not committed or redistributed** here. Derived retrieval statistics and benchmark code do not imply proprietary rights over the upstream paragraphs.

This source is distinct from the 100-question pinned OpenSPG/KAG training sample reproduced in Round 53. Respect the upstream dataset attribution and share-alike obligations if redistributing adapted source content. Existing licensing notes for other bundled historical materials remain in force.


## Independent README revision histories (Rounds 62–63)

The experiment retrieves upstream README.md revisions at immutable Git commit cutoffs: astral-sh/ruff (MIT license), huggingface/transformers (Apache License 2.0), and pallets/flask (BSD 3-Clause). Each historical source blob is SHA-256- and Git-blob-SHA-1-identified in experiment metadata. Historical README bytes are downloaded transiently by CI and **not committed or redistributed** in this repository. The originating projects retain authorship and license rights in their documentation. Where reproduced or adapted, users must comply with each upstream project's applicable license and attribution terms.

The experiments additionally use separate SHA-pinned HotpotQA development paragraphs under CC BY-SA 4.0, already documented above. Derived measurements do not create ownership of original text. See research/rounds/round-62/report.md and research/rounds/round-63/report.md for exact source provenance and limitations.


## Additional pinned revision histories (Rounds 64–65)

The retroactive source-migration experiments additionally fetch immutable README.md revision histories from **vllm-project/vllm** under the Apache License 2.0 license (Git cutoff 935f87de846980dc16c54ac1996595fc12eb3f9e) and **pydantic/pydantic** under the MIT license (cutoff e56f60fd32273d1d7c397a3ac46bba05e6a73454). The exact original files remain under upstream authorship and licenses, are SHA/Git-blob identified, and are never bundled in this repository. The experimental scripts download them into transient CI environments and store only checksums, experiment records and derived aggregate numerical results.


## Pinned external pretrained QA reader (Rounds 66–68)

Real answer-quality experiments use **deepset/tinyroberta-squad2** under **CC BY 4.0**, pinned to Hugging Face model commit **12b287c9df677e28b07f0a023850dba68c997dbf** with model-identity metadata recorded in experiments/round-66/model_lock.json. The original model weights, tokenizer vocabulary and training artifacts remain upstream, and are downloaded transiently for CI inference, not redistributed by this repository. Credit and follow the model card's attribution terms: https://huggingface.co/deepset/tinyroberta-squad2 .

The evaluations also download SHA-verified HotpotQA distractor development inputs under CC BY-SA 4.0, as documented above. Derived aggregate answer/citation statistics do not transfer ownership of source paragraphs or pretrained model data. The test suite's source receipts establish exact extracted bytes, not that those bytes truthfully entail an answer.


## RAGTruth human-annotated QA benchmark (Rounds 69–71)

RAGTruth source and response annotation data originate from ParticleMedia/RAGTruth and Niu et al., ACL 2024, https://aclanthology.org/2024.acl-long.585/ . The experiment pins immutable upstream Git revision c103204b9ce28d6bbad859304bf30de72b8ed8fe and verifies the Git object hash for response.jsonl (f9ae5913fb9976684f3e13be3cd3465062db54cc) and source_info.jsonl (119277774009f110aa58596b93f9512f62594a89).

RAGTruth annotations and the underlying source passages have potentially different licenses and provenance: source material may include MS MARCO, summarization news corpora and Yelp-derived fields. **No original paragraphs, model-generated answers, word-level annotations, or model weights are committed or redistributed in this repository.** These experimental scripts download the original files transiently and publish only derived aggregate counts, checksums and code. Consult each original dataset's applicable license/terms before reuse or redistribution. Attribution of the RAGTruth paper and upstream repository is required for scholarly use.
