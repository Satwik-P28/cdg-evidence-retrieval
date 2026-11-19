# CDG Round 97: Original QASPER Long-Paper Paragraph Evidence Retrieval

**Date:** 18 November 2026, late evening local. **Verified:** nine independent schema and ranking regression tests and full source-locked QASPER dev data retrieval experiment PASSED [GitHub Actions 44458177474](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44458177474). This is a new domain and text granularity, not a resampled SciFact set, and not an answer-generation evaluation.

## Task contract

QASPER 0.3 (Dasigi et al., NAACL 2021, https://aclanthology.org/2021.naacl-main.365/) supplies a known **paper ID** with each natural question, along with original section/paragraph text and human paragraph/figure/table annotations. We compare two source+retrieval representations on the complete **281 QASPER dev papers** and **13,266 nonempty text paragraphs**:

1. Conventional source-readable SQLite FTS5(title=original section name, abstract=exact original paragraph string).
2. Round 90 ordinary contentless FTS5 with independently stored **zlib6-compressed SHA-256-verified original source bytes** from the identical section/paragraph fields.

Both indexes use the same SQLite unicode61, BM25 section-title weight 5.0 and paragraph body weight 1.0, the first 28 distinct source-independent content terms combined by OR. The original paper is given with the question: query only rowids belonging to that paper. This is **not open-domain global document retrieval**. Every returned top-10 source original byte string is checked against the source-locked QASPER original paragraph, not merely a hash stored by the archive itself.

Human annotation is matched using whitespace-normalized exact strings against the original full-text paragraphs, with figure/table references explicitly excluded and unmatched textual evidence not guessed. Multiple annotated answer evidence lists for a question are unioned to represent *any* identified supporting paragraph in the same paper. Cases without at least one confident exact text paragraph are **excluded** from evidence recall denominator, not treated as known no-answer.

## Frozen source and cohort

- Original official train/dev QASPER release SHA256 \`a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a\`, official dev member SHA256 \`2ae7ee62a65b1c4225791c70de80c2aad4e8998cf1fd4f09a53103db4f21af93\`, inherited R96 verification.
- Original QASPER dev: **281** papers, **1,005** questions, **13,266** nonempty text paragraphs.
- Human annotation instances **1,764**, of which **1,452** contain at least one exactly matched text paragraph. Those correspond to **888 distinct questions** eligible for exact paragraph retrieval evaluation. **117** questions have no exact matched text-evidence paragraph, including table/figure/unanswerable/mismatched cases. Those are excluded from recall denominator and reported separately.
- **129** nonfloating original evidence strings unmatched in exact paragraph mapping and **253** table/figure evidence references in the dev audit. We do not convert them into fictitious gold paragraphs.

## Verified full-corpus results

| Metric | Conventional full text FTS5 | SHA-verified compressed source + contentless FTS5 |
| --- | ---: | ---: |
| Total static persistent source+index bytes | **12,099,584 B** | **9,822,208 B** |
| Source+index storage saved | baseline | **18.8219%** |
| Questions with identical top-10 paper-scoped ranked rowids | \multicolumn{2}{c}{**1,005 / 1,005**} |
| Human exact paragraph Recall@1 | **229/888 = 25.7883%** | **229/888 = 25.7883%** |
| Human exact paragraph Recall@3 | **434/888 = 48.8739%** | **434/888 = 48.8739%** |
| Human exact paragraph Recall@5 | **537/888 = 60.4730%** | **537/888 = 60.4730%** |
| Human exact paragraph Recall@10 | **664/888 = 74.7748%** | **664/888 = 74.7748%** |
| All top-10 source paragraphs verified byte-exact against original upstream | **8,856** | **8,856** |
| Warm cumulative query and original source check wall time | **0.39573 s** | **0.48115 s** |

\`PRAGMA integrity_check\` was **ok** for both. The two sources return exactly the same document ranks, so same-source compression does **not** improve retrieval or generated answers by itself. Warm measured compressed retrieval was *slower* in this one runner, with no cold-SSD control or repeated timing study.

## Mechanistic interpretation and negative result

SciFact's complete source+index architecture saved **36.58%**, whereas QASPER's paragraph-level source+index saved **18.82%**. The archive wins less with many relatively short paragraphs because each row incurs compression metadata, SQLite pages and FTS postings. This result is **not** evidence against compression mathematics or proof of a universal relationship with paragraph length; a controlled cross-granularity size ablation is still required.

QASPER baseline gold paragraph Recall@1 **25.79%** is low despite perfect source integrity and known paper ID. Longer articles and question paraphrases make ordinary lexical BM25 weaker at finding precise human text evidence than short, claim-overlap SciFact abstracts. This is one corpus and one fixed lexical policy, so no universal lexical retrieval ranking claim.

The result separates three distinct resources/quality concepts: original source byte integrity, stored source+postings capacity, and actual human evidence acquisition. Lossless source compression preserves the first but cannot repair the third without changing selection/ranking.

## Prior art and scientific status

QASPER original evidence QA: https://aclanthology.org/2021.naacl-main.365/ . SQLite contentless prior art: https://www.sqlite.org/fts5.html . Evidence fragmentation and content selection are established topics, and this round does not claim first discovery. Stronger full-document and dense retrieval controls, plus real response generation and annotations, are necessary for a publication-level result.

## Next falsification

Run BOTH source representations with **binding 6 MiB and 8 MiB** byte caps on original QASPER paragraphs. Predeclare at least uniform hash and paper-balanced paragraph retention policies without looking at dev gold evidence. Preserve QASPER's known-paper retrieval scope; measure eligible evidence Recall@1/5/10 and the number of papers retaining source content. A compression advantage that disappears under smarter paper-aware retention or under another corpus should be reported as a negative result.

## Reproduction

\`\`\`bash
python -W error::ResourceWarning -m unittest discover -s experiments/round-97 -p 'test_*.py' -v
python experiments/round-97/qasper_paragraph_retrieval.py --out experiments/round-97/ci-results.json
\`\`\`

Code \`experiments/round-97/qasper_paragraph_retrieval.py\`, regression tests \`experiments/round-97/test_qasper_paragraph_retrieval.py\`, CI \`.github/workflows/cdg-r97-qasper-paragraphs.yml\`. Verified run and aggregate artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44458177474 .
