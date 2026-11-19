# CDG Round 96: Immutable Independent QASPER Evidence Corpus Audit

**Date:** 18 November 2026 local late evening. **Status:** PASS, nine schema/provenance adversarial tests and official source audit in [GitHub Actions 44457765633](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44457765633). This round establishes an independently authored external benchmark and exact evidence matching scope; no source retrieval or answer generation metrics are claimed yet.

## Motivation and prior work

Rounds 83–95 have used SciFact scientific abstracts and claim evidence labels. That corpus is short, fixed, public, biomedical, and its claim vocabulary often overlaps its evidence abstracts. QASPER (Dasigi et al., NAACL 2021, https://aclanthology.org/2021.naacl-main.365/) instead contains questions about **long NLP paper full texts** with annotated expert evidence paragraphs, figures and tables. This is a distinct task, not a random split of SciFact. QASPER originally targets question answering and evidence retrieval, not the SUPPORT/CONTRADICT claim-verification classification from SciFact.

Before comparing compressed source archives, source provenance and evidence mapping must be strictly bounded. Official dataset metadata is at https://huggingface.co/datasets/allenai/qasper/blob/main/dataset_infos.json and documentation https://huggingface.co/datasets/allenai/qasper/blob/main/README.md .

## Frozen official dataset release

- Official upstream release: \`https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz\`.
- Tar size exactly **10,835,856 bytes**; SHA256 **\`a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a\`**. The SHA and byte count were independently present in official QASPER dataset metadata and enforced before any JSON parsing.
- Training member \`qasper-train-v0.3.json\` (31,969,387 bytes), SHA256 **\`9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4\`**.
- Development member \`qasper-dev-v0.3.json\` (11,398,686 bytes), SHA256 **\`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`**.
- **Zero** overlapping paper IDs between training and development.
- All original text is parsed in memory; the submitted source audit contains only schema counts, identifiers of original upstream files, hashes and annotation coverage. Do not commit original copyrighted scientific paper text.

## Original source and evidence mapping audit

| Original source statistic | Training | Development |
| --- | ---: | ---: |
| Papers | 888 | 281 |
| Questions | 2,593 | 1,005 |
| Text paragraphs | 46,882 | 13,266 |
| Text paragraph UTF-8 bytes | 21,368,420 | 6,328,953 |
| Human answer annotation instances | 2,675 | 1,764 |
| Annotation instances with any evidence | 2,308 | 1,552 |
| Annotation instances with >=1 exact matched text paragraph | 2,161 | 1,452 |
| Exact original nonfloating evidence paragraph strings matched | 3,676 | 2,426 |
| Original nonfloating evidence strings unmatched to normalized paragraph | 147 | 129 |
| Table/figure evidence references | 386 | 253 |

Evidence string alignment uses **whitespace normalization only** and exact match to original full-text paragraph content, not a semantic proxy or matching by question label. References beginning \`FLOAT SELECTED\` are counted as table/figure references, not falsely attached to unrelated text. Duplicate paragraph text can validly map to multiple positions. Nullable section titles are accepted as empty section names; an initial test revealed official QASPER has optional null section titles, which was corrected, with an exact-head source-audit rerun.

**Important denominator:** 1,452/1,764 is not the model answer accuracy. Some annotations are unanswerable or refer to figures/tables; some text evidence may be reflowed or otherwise not exactly matched. The external evidence-retrieval evaluation must restrict gold recall denominator to QA cases with >=1 confidently matched human text-evidence paragraph and report excluded cases explicitly. Multiple annotated answers per question must have correctly combined or separately evaluated evidence sets without turning missing annotation into known negative labels.

## Engineering and scientific decision

**KEEP:** Original QASPER 0.3 source SHA-lock, distinct paper-ID splits, rigid source size and schema audit, and explicit no-match/table evidence accounting. These are prerequisites for independent evidence performance measurement.

**NOT SHOWN:** Generalization of R90 compression or R95 budget advantages, long-passage retrieval quality, generated-answer factuality, attribution performance or a novel algorithm.

**NEXT:** Benchmark source-readable full-content FTS5 versus the SHA-verified compressed contentless source store on the exact 13,266 QASPER development paragraphs. Treat the question's paper ID as an externally known scope and compare passage Recall@1/5/10 for only eligible annotated text evidence, ensuring that both architectures return the same top-k source identity and bytes. Then evaluate tight equal-archive byte budgets and make the paper-scope assumption explicit, not a full open-domain search claim.

## Reproduce

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-96 -p 'test_*.py' -v
python experiments/round-96/qasper_source_probe.py --out experiments/round-96/ci-results.json
\`\`\`

Code \`experiments/round-96/qasper_source_probe.py\`, tests \`experiments/round-96/test_qasper_source_probe.py\`, workflow \`.github/workflows/cdg-r96-qasper-lock.yml\`. Verified full CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44457765633 .
