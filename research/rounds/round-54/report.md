# Round 54: Previously Unseen HotpotQA Distractor Development Retrieval

**Date:** 2026-11-17. **Status:** SHA-verified official distractor development mirror, prespecified sample of 512, executed successfully in GitHub Actions run 44162926421. Seven new regression tests passed. Policies were frozen at their R25 definitions before reading dev outcomes.

## Dataset and integrity

Source: namlh2004/hotpotqa, revision 7e54db4656209750ff487f6fdf8e39a66dba136b, file hotpot_dev_distractor_v1.json. Bytes = **61,065,698**; verified SHA-256 = **e3da074df24e8369009918aa5cdbdd254dadcde4c63f7569d36afd6f2268caa8**. This is a revision-locked mirror of the official HotpotQA distractor development data. Dataset license: CC BY-SA 4.0. Data bytes are downloaded transiently, not redistributed in this repo.

Of 7,405 records, **7,404 have structurally valid gold sentence annotations**, and **one has an out-of-range annotated sentence ID**. There were zero missing gold-document titles by this audit. The bad item was not in the selected sample.

Select the first **512** rows after sorting the SHA256 of (fixed salt CDG-R54-DEV-SHA256-LOCKED-v1 + pipe + original question ID); selected ID list SHA256 = **7f868b57a4219fa7f1e4d926cc1283a101abc48ede498cb255e7419edea72e50**. The fixed selection comprises 403 bridge and 109 comparison questions. Invalid gold annotations remain in denominators and count as zero recoveries if sampled; none occurred in this subset.

## Frozen policies

- Original Round 25 lexical BM25 per question-local full candidate texts.
- Iterative exact-title mention bridge with prior bonus 2.0, examining previously selected source text only.
- Original MMR (0.75 normalized BM25 minus 0.25 redundancy).
- Precomputed title-mention adjacency, required to match the exact bridge document rankings and evidence counts.
- Question-text-only comparison gate using prespecified surface cues; this is exploratory and may be brittle. No selection policy sees gold supporting titles, question type annotations, or answers.

These are ordinary established lexical and graph heuristics, not new theory. The evaluation setting supplies gold-bearing candidate paragraphs, so it is not open-corpus retrieval.

## Results, complete supporting documents recovered

| Method | Top 2 | Top 3 | Top 5 |
| --- | ---: | ---: | ---: |
| BM25 | 168/512 | 249/512 | 345/512 |
| Frozen exact title bridge | **212/512** | **327/512** | **439/512** |
| MMR | 161/512 | 245/512 | 346/512 |
| Precomputed title-link graph | 212/512 | 327/512 | 439/512 |
| Question-text gate | 213/512 | 313/512 | 417/512 |

**Paired K=2 results:** 163 both succeed, 49 bridge only, 5 BM25 only, 295 neither. **K=5:** 343 both succeed, 96 bridge only, 2 BM25 only, 71 neither. These paired comparisons avoid conflating unequal document budgets.

**K=2 type breakdown:** On 403 bridge questions BM25 succeeds on 139 and title bridge on 185. On 109 comparison questions BM25 succeeds on 29 and title bridge on 27. The text gate succeeds on 185 bridge and 28 comparison cases. It improves one top-2 result over unconditional bridge but does not dominate at K=3 or K=5, and is not promoted.

The frozen policy exhibits +44/512 additional complete-document recoveries at K=2 and +94/512 at K=5 on independent dev questions versus BM25. Document retrieval is not the same as complete supporting-sentence recovery, semantic entailment, factual credibility or correct generated answers.

## Limitations and next falsifier

The dev split is held out relative to the earlier 100 train questions, but not untouched by the broader research literature. The sample is 512 rather than all 7,405. The per-question candidate pool includes gold paragraphs, all candidate full text is scored for BM25, and title-graph preprocessing has a cost. No full RAG generation, model token use, cold SSD, persistent embedding index, or statistically independent corpus family was evaluated.

Round 55 measures exact compressed evidence bytes, frame traffic and sentence loss on the first 128 of these SHA-ranked question IDs. Later rounds should compare stronger sentence extraction policies and precomputed title-link indexing at matched full-cost budgets.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-54 -p 'test_*.py' -v
    python experiments/round-54/heldout_dev.py --sample-size 512 --out experiments/round-54/results.json

CI: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44162926421 .
Official dataset: https://hotpotqa.github.io/ . Original work: Yang et al., HotpotQA (EMNLP 2018).
