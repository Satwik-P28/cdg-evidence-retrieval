# CDG Round 102: Out-of-Paper Zstandard Dictionaries Versus Strong Independent Brotli5 Source Store

**Date:** 19 November 2026. **Status:** PASS, ten train-only source provenance, corrupted dictionary, source-ID and FTS invariance regression tests plus original QASPER full train/dev comparison in [GitHub Actions 44470136473](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44470136473).

## Motivation

R101's grouped Brotli blocks saved 15.71% physical bytes versus individually compressed QASPER paragraphs but caused up to 40× UTF-8 decompression-byte amplification for individual top-one evidence reads. Zstandard's existing dictionary compression can share repeated patterns across *independently encoded small sources*. R102 tests that tradeoff against the stronger **per-source Brotli5**, not just plain zstd, and includes the entire dictionary in the SAME physical SQLite source+index database.

Shared dictionary compression is documented existing Zstandard prior art (see https://python-zstandard.readthedocs.io/en/latest/dictionaries.html and RFC 8878 https://www.rfc-editor.org/rfc/rfc8878); the research contribution here is controlled evidence-system measurement, not invented compression mathematics.

## Provenance and leakage guards

- Original QASPER release unchanged, original **888 train papers** SHA256 \`9458bfe76074a8fa8d1685af02bcc73537aa6d338ad20591dfaff1946bc88bf4\` and distinct **281 dev papers** SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`; **zero original article ID overlap**.
- Dictionary samples selected from original train **full text only**, using frozen hash ordering of source IDs. Among **46,882** original training paragraphs, preselected **4,096** samples containing **2,000,232 original UTF-8 source bytes**. Sample IDs frozen by SHA256 \`dcdfe6b2441cf2f65e47eb32a8a29ff26602568ad15ad499f4fb2e4b2798e3dd\`. No QA question text, human evidence labels or dev articles enter dictionary training.
- Four independent Zstandard dictionary target sizes: **8,192; 16,384; 32,768; 65,536 bytes**. Each trained using published \`zstandard.train_dictionary(size, samples)\` once on original training source. Training time and actual resulting dictionary bytes independently measured. Zstd levels 3 and 9 evaluated per size, plus plain zstd3/9 without dictionaries and a strong **Brotli5** full-source baseline.
- All archives share identical SQLite schema including a \`docs.codec\` and \`docs.dict_id\` field and a \`source_dictionaries\` table (empty in no-dictionary controls). Dictionary BLOBs are stored once with their own SHA256 and Zstd dictionary identity. They are **not external uncharged model assets**.
- Every variant has the **same original source paragraph rowids, original source text and FTS5 postings**, every original source SHA256-verified against original QASPER dev text. All **1,005** original article-scoped QASPER question rankings are exactly identical, unchanged FTS global statistics and core/FTS integrity. All original source text remains upstream.
- The source reader prepares the shared Zstd dictionary **once per opened archive** and decodes each individual compressed paragraph independently. It returns and SHA verifies only requested source bytes, with no grouped block decompression amplification. Warm read probes are top1 and top10 original QASPER paper-scoped BM25 results, same query set.

An initial CI run failed because its synthetic fixture assumed the trained dictionary byte output always equals the requested capacity. Zstandard may return a smaller trained dictionary on repetitive input. The corrected regression charges and checks the *actual* trained bytes, and final exact-head CI **44470136473** fully passed.

## Physical source plus FTS5 SQLite file sizes

**All rows include identical extra codec/dict-ID metadata schema.** These figures cannot be compared as-is with R99's slightly smaller schema without its dictionary-ID column/table.

| Codec and dictionary | Whole SQLite archive bytes | Difference versus same-schema Brotli5 |
| --- | ---: | ---: |
| **Brotli5, individual paragraphs** | **9,506,816** | 0 |
| plain zstd3 | 10,113,024 | -606,208 (worse) |
| plain zstd9 | 10,055,680 | -548,864 (worse) |
| zstd3 + trained 8 KiB dictionary | **9,035,776** | +471,040 |
| zstd9 + trained 8 KiB dictionary | **8,839,168** | +667,648 |
| zstd3 + trained 16 KiB dictionary | **8,904,704** | +602,112 |
| zstd9 + trained 16 KiB dictionary | **8,835,072** | +671,744 |
| zstd3 + trained 32 KiB dictionary | **8,826,880** | +679,936 |
| zstd9 + trained 32 KiB dictionary | **8,736,768** | +770,048 |
| zstd3 + trained 64 KiB dictionary | **8,798,208** | +708,608 |
| **zstd9 + trained 64 KiB dictionary** | **8,687,616** | **+819,200** |

**[FACT]** The smallest source+index representation in this experiment is **zstd9 with a 64 KiB independently trained dictionary**: **8.616% fewer total static persisted bytes** than same-schema strong independent Brotli5 baseline. Zstd3 with 64 KiB dictionary saved **7.454%**, making it close in physical storage while using markedly less measured encoding work in this runner.

**[FACT]** Without the dictionary, independent zstd3 and zstd9 were *larger than Brotli5*. Thus the shared trained dictionary, not the same standalone compressor, was the primary mechanism for the observed size improvement.

### Encoding, dictionary construction and warm read

- Train dictionary 8/16/32/64 KiB each required **0.16–0.18 seconds** in this single runner to learn from 4,096 out-of-article source samples; only one dictionary is retained per active archive.
- Source-blob encoding seconds for 13,266 dev sources in this runner: Brotli5 **0.448497 s**; zstd3 with 64 KiB dictionary **0.056492 s**; zstd9 with 64 KiB dictionary **0.308709 s**. This excludes common FTS index creation and SQLite BLOB write/VACUUM.
- Median warm top-one source+SHA receipt time: Brotli5 **0.022232 ms**, zstd3/64KiB **0.017290 ms**, zstd9/64KiB **0.017092 ms**. Warm top-ten receipt median: **0.021139** vs **0.016239** and **0.016110 ms**. These are single-run descriptive timing differences, not a replicated speedup claim.
- Unlike R101's whole-paper block, each paragraph is encoded independently with a reusable archive dictionary. Retrieval of one paragraph inflates its own source content, not the entire paper: no additional paragraph-block read amplification. The ~65 KiB shared dictionary itself must remain resident in a source reader and therefore **RAM and initialization cost** are separate from per-source decoded bytes.

## Controls and limitations

- This is existing standard Zstd dictionary training and whole-source integrity, not new compression mathematics.
- One published scientific QA domain with genuine **article-ID-disjoint train vs dev source corpora**, but source vocabulary/domain still overlaps; results might be weaker on unrelated topics.
- Dictionary is trained on QA train **paragraph text** without train question labels or dev text, mitigating source-adaptation leakage.
- Complete physical on-disk dictionary and metadata cost included; temporary training inputs, training CPU, and memory are **separately measured/not budgeted as persistent archive bytes**.
- No generated responses, answer-level factuality, or improved evidence retrieval ranking. Source-exact verification and unchanged BM25 ranking cannot by themselves imply reduced hallucinations.
- No online source revisions, concurrency, crash recovery, physical cold SSD reads, repeated hardware benchmarking, peak memory measurements or malicious decompression limits for the Brotli baseline.

## Research decision

**KEEP:** a dictionary-backed source store as a serious storage/read alternative to whole-paper grouped Brotli. The zstd3 + 64 KiB dictionary has a particularly favorable **observed storage, encoding and warm read** profile on this corpus. It may be preferable to even smaller zstd9 dictionaries in update-heavy settings.

**NEXT:** compare shared trained Zstd dictionaries with *block grouping*, count both **total archive bytes** and **decompression amplification**, then test under the same binding source+index byte budget for human annotated paragraph evidence. Include strong uniform Brotli5 and entire-paper Brotli5 reference points. For a publication-quality RAG conclusion, downstream generated answers and human support are still required.

## Reproduction

\`\`\`bash
python -m pip install Brotli==1.1.0 zstandard==0.23.0
python -W error::ResourceWarning -m unittest discover -s experiments/round-102 -p 'test_*.py' -v
python experiments/round-102/train_only_zstd_dictionary.py --out experiments/round-102/ci-results.json
\`\`\`

Code \`experiments/round-102/train_only_zstd_dictionary.py\`, ten regression tests \`experiments/round-102/test_train_only_zstd_dictionary.py\`, workflow \`.github/workflows/cdg-r102-zstd-dictionaries.yml\`. Verified exact-head CI and aggregated original source artifact https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44470136473 .
