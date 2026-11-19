# CDG Round 94: Actual Retrieved-Source Scientific Verdict Yield, Not Oracle Accuracy

**Date:** 18 November 2026, local evening. **Status:** nine source-provenance/label-scope regression tests and complete original SciFact pretrained NLI model evaluation PASSED in [GitHub Actions run 44446054309](https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44446054309). This is the first pipeline in this continuation that produces a pretrained model verdict from a *retrieved* compressed or full-content source instead of merely measuring evidence-doc recall. It is still **not free-form generative RAG or human-scored hallucination reduction**.

## Controlled task

On expert-annotated SciFact development claims, run real FTS5/BM25 top-one source retrieval, retrieve the source text from the actual stored implementation, and apply a **frozen published three-way NLI cross encoder**. Count as a validated outcome only when that exact retrieved claim-document pair carries a SciFact expert SUPPORT or CONTRADICT annotation. Wrong retrieval may select an unannotated document; do not transfer the label of the gold source to the wrong document and never call such a case correct or incorrect without a human label.

Original SciFact archive SHA256: \`11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be\`. Full corpus 5,183 abstracts and 300 dev queries; **188** dev claims have at least one annotated evidence source. Original dataset remains upstream. Official benchmark: https://aclanthology.org/2020.emnlp-main.609/ .

## Retrieval and scoring design

- Complete compressed source/index: Round 90 ordinary contentless FTS5 + SQLite SHA-256-verified zlib6 BLOB sources. **9,224,192 bytes** static persisted source+index, below both predeclared budgets.
- Conventional FTS5 source reader: SHA-hash ordered source subsets exactly as Round 92, using seeds **11, 37, 71** under **10 MiB / 12 MiB**. Full content source is read out of FTS5; no gold label enters ranking.
- All 188 annotated development claims are queried under all seven routes (full compressed and six conventional budget/seed cases). Actual top-one source bytes are separately reconstructed from each store and compared against SHA-locked upstream original source text.
- Deduplicate repeated (claim ID, actual retrieved document ID) inputs across routes. **346 distinct claim-document pairs** were scored using a single model instance, with exact text equality asserted for duplicate routes.
- Model: published \`cross-encoder/nli-deberta-v3-xsmall\`, immutable Hugging Face revision **\`a150876415327c80daeff35ca6f68f5ed8cf5c24\`**, **70,831,107 parameters**. No training or threshold search in this round.
- Three-class fixed decision: predict **SUPPORT** if entailment probability >= .50 and not lower than contradiction; predict **CONTRADICT** if contradiction probability >= .50 and greater than entailment; otherwise **ABSTAIN**. A neutral classification is **not** incorrectly called a contradiction.
- Tokenizer limit 384, \`truncation=only_first\` on source side. **103/346** originally untruncated claim-source pairs exceeded cap. Actual padded model input tokens **106,080**, measured CPU model scoring wall time **120.714 seconds** on a single GitHub Actions runner. This is not a matched end-to-end latency comparison across all baselines because repeated model pairs are deliberately deduplicated.
- For each scenario, partition outcomes into: selected source human-annotated for that claim; selected source unannotated; empty retrieval. On annotated selected sources only, count correct label, wrong label and abstention separately.
- Define **certified annotated-pair verdict yield** as number of cases where the retrieved source is explicitly annotated and the model's nonabstaining verdict matches that exact annotation, divided by the same 188 eligible claims. This is an *observed human-label-backed coverage yield*, **not overall answer accuracy**, since unannotated documents have unknown truth.

## Original SciFact results

| Route | Annotated source retrieved at rank 1 | Correct annotated verdict | Wrong annotated verdict | Annotated abstention | Human-annotation-backed verdict yield |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Full compressed, 5,183 docs** | **136** | **30** | **13** | **93** | **30/188 = 15.9574%** |
| 10 MiB conventional, seed 11 (3,720 docs) | 86 | 16 | 9 | 61 | 8.5106% |
| 10 MiB conventional, seed 37 (3,742 docs) | 98 | 23 | 12 | 63 | 12.2340% |
| 10 MiB conventional, seed 71 (3,687 docs) | 100 | 21 | 8 | 71 | 11.1702% |
| 12 MiB conventional, seed 11 (4,497 docs) | 106 | 21 | 13 | 72 | 11.1702% |
| 12 MiB conventional, seed 37 (4,503 docs) | 114 | 26 | 12 | 76 | 13.8298% |
| 12 MiB conventional, seed 71 (4,457 docs) | 124 | 25 | 12 | 87 | 13.2979% |

**Across three seeds:** conventional under 10 MiB averaged **20/188 = 10.6383%** certified yield, under 12 MiB **24/188 = 12.7660%**. The full compressed corpus yielded **15.9574%**, 5.3191 and 3.1914 percentage points higher respectively. These are descriptive means over overlapping dev claims and are **not** independent confidence intervals.

**Crucial: source-annotation versus verifier error.** Full compressed retrieved human-annotated rank-one sources **136/188**. Among those 136, the model made only **30 correct support/refute decisions**, **13 wrong** and **93 abstentions**, a **22.0588% conditional correct rate** on annotated selected sources. Among the remaining **52** unannotated selected sources, it predicted support for 1, contradiction for 8 and abstained for 43; none of these 52 can be scored correct or wrong using labels belonging to different gold source documents. They are **not a known-negative class**.

This model-level bottleneck is consistent with Round 83's previous poor fixed-threshold generic NLI gold-oracle SUPPORT sensitivity. It does not mean compression harmed semantics: no comparison changes the model input when a claim and source identity are the same. The compressed layout simply retains more potential annotated sources under the fixed budget.

## Regressions and caveats

- Nine tests enforce exact original compressed/full source readback, claim-ID alignment, three-class threshold semantics, **neutral abstain instead of automatically contradiction**, missing-source treatment, wrong retrieved source label scoping, and unexpected cohort rejection.
- An initial CI run successfully completed inference but failed post-inference because the evaluation assembler incorrectly expected \`claim_id\` instead of the original SciFact \`id\`. This reporting-code bug was corrected and a dedicated regression added; only final exact-head green run **44446054309** supports numerical claims.
- Independent sources with no SciFact annotation can also contain real valid evidence. The yield is an annotated-certification lower bound, not full population accuracy or estimated hallucination probability.
- The frozen xsmall general NLI checkpoint may be poorly matched to biomedical scientific claims, and model or related benchmark contamination cannot be ruled out.
- The model has a short 384-token cap; a large fraction of source contexts truncate. This may explain some abstentions or errors. Source exactness does not establish that model context contains all relevant rationale sentences.
- The source budget excludes pretrained model weights, RAM, network transfer, logs, active SQLite journals, and cold SSD I/O. The study cannot claim the full compute stack fits a 10/12 MiB machine.
- The conventional baseline uses hash-uniform document retention. Round 93 already established that train-selected retention performs substantially better on retrieval; these model-level conventional outcomes are not the strongest conventional selection baseline.
- No new model was trained, no generated natural-language answer was evaluated, and no original compression mathematics was introduced.

## Research decision

**KEEP:** a separately auditable pipeline metric for original-text retrieval, annotated-source coverage and fixed-checker verdict yield. This is more meaningful than source Recall alone, while preserving uncertainty on unannotated docs.

**REJECT:** interpreting the NLI model's low yield as a general RAG ceiling, calling the missing-doc cases wrong, or promoting relative yield improvement as hallucination suppression.

**NEXT:** combine this evaluation with the **Round 93 train-validated smart document selection** and a stronger published scientific-grounding verifier such as FactCG or MiniCheck under the same frozen cohort, storing/source-reading identical evidence. Also evaluate a true human-annotated generated-answer task (e.g., RAGTruth QA) before any free-form hallucination claim. Use model pairs and prompt tokens in total cost.

## Reproduce

\`\`\`bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
python -m pip install transformers==4.52.4 huggingface_hub==0.32.4 tokenizers==0.21.4 numpy==2.2.6 sentencepiece==0.2.0 protobuf==5.29.5
python -W error::ResourceWarning -m unittest discover -s experiments/round-94 -p 'test_*.py' -v
python experiments/round-94/retrieved_verdicts.py --out experiments/round-94/ci-results.json
\`\`\`

Code: \`experiments/round-94/retrieved_verdicts.py\`, tests \`experiments/round-94/test_retrieved_verdicts.py\`, CI \`.github/workflows/cdg-r94-retrieved-verdicts.yml\`. Verified job and aggregate artifact: https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44446054309 .
