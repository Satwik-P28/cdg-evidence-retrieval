# Round 56: Sentence Ranking versus Source-Frame Read Amplification

**Date:** 2026-11-17. **Status:** successfully executed in GitHub Actions run 44163953028. Five regression tests passed and 5,582 exact source-span/representation checks completed. Uses the same first 128 immutable SHA-ranked HotpotQA distractor-dev questions examined in R55. Because this subset was already inspected, policy comparisons are exploratory ablations, NOT fresh independent held-out validation.

## Question and design

Can ordinary lexical scores, explicit title-link evidence signals, or diversity ranking preserve *all annotated supporting sentences* with fewer materialized bytes than naive top-two FTS5 retrieval from the previously selected five documents?

Hold document acquisition fixed to either R25 BM25 or the frozen R25 title-bridge selection. Score each original source's sentences under five label-blind retrieval policies:
- FTS5 BM25 (global source-sentence index);
- paragraph-local lexical BM25 (R25);
- paragraph-local BM25 with sentences containing another selected document title moved first;
- fixed 0.75 relevance/0.25 Jaccard redundancy MMR;
- deterministic random-hash ordering as a negative control.

Compare 1, 2, 3, 4, and *all* sentences per selected document at K=2 and K=5 documents. Choose sentences solely from question, source text and selected document names, not the gold support annotation. Verify every retrieved UTF-8 original byte span under version-pinned source digests. Count mean unique compressed frames touched **once per question** (idealized local cache) using both whole Zlib and 512-byte content-defined frames; count archive + shared FTS index size.

## Executed bridge @5 results

Upper bound when all sentences retained: **107 / 128 complete annotated support sets**, identical to full supporting-document recovery. A source selector cannot exceed this without retrieving additional documents.

| Sentence rank policy | Complete support @2 sentences per doc | @3 | @4 | All |
| --- | ---: | ---: | ---: | ---: |
| FTS5 BM25 | **79** | 92 | 101 | 107 |
| Local BM25 | 78 | 94 | 102 | 107 |
| Title-mention first | 77 | **95** | **103** | 107 |
| Sentence MMR | 77 | **95** | 102 | 107 |
| Deterministic random | 43 | 75 | 93 | 107 |

The negative control confirms query-relevant ranking substantially helps at short budgets. Nevertheless a title-link priority is **worse** than plain FTS5 at two sentences per document and only slightly better at three/four; there is no defensible universal improvement. These small differences are not independent significance claims.

Mean compressed frame traffic per question under the frozen bridge K5:

| Policy and budget | Gear512 compressed bytes, ideal per-query dedup | Whole-Zlib compressed bytes |
| --- | ---: | ---: |
| FTS5 2 | 1,601.33 | 1,628.79 |
| FTS5 3 | 1,660.71 | 1,628.79 |
| FTS5 4 | 1,680.77 | 1,628.79 |
| FTS5 all | 1,705.07 | 1,628.79 |
| Title priority 2 | 1,619.14 | 1,628.79 |
| Title priority 3 | 1,670.72 | 1,628.79 |
| Title priority 4 | 1,689.29 | 1,628.79 |

At three or four sentences per document, frame-based decoding can access **more** compressed bytes than whole-Zlib's one-full-source-per-document strategy. In the strict physical read-traffic comparison, a slightly higher gold-sentence recall does not offset the additional cost because all original short documents can be read with minimal extra compressed bytes. All candidates were already used for BM25 document scoring.

The shared FTS5 sentence index occupies 708,608 B; archive bytes: gear512 = 504,264 B and whole-Zlib = 482,158 B. Index memory and model-token costs beyond these numbers are not included.

## Negative results and decision

1. No compressed-frame format or selective sentence ranking **Pareto-dominates** a simple full-source Zlib reader in both complete support and activated compressed bytes on this corpus.
2. Title-link priority does not beat all alternatives at the strict two-sentence budget; improvements at three/four are marginal and may be selection noise.
3. Increasing per-document sentence budget is more reliable for recovering gold supporting facts than adding speculative reranking rules. But with short source paragraphs, that increase often eliminates meaningful compressed-read savings.
4. The next targeted hypothesis is **cross-document sentence budget allocation**. Fixed 2 sentences each of five docs may waste capacity on distractors and underallocate to the truly informative sources. Test a fixed *global* budget and label-blind allocation rules, including reversed-position and random controls.

## Reproduction

    python -W error::ResourceWarning -m unittest discover -s experiments/round-56 -p 'test_*.py' -v
    python experiments/round-56/sentence_policy.py --sample-size 128 --out experiments/round-56/results.json

CI execution: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44163953028 . All source data downloaded transiently from the official dev mirror, no redistributed text. Exact source bytes do not imply factual truth, sentence entailment or generated-answer correctness.
