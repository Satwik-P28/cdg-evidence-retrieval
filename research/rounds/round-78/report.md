# CDG Round 78: Archive-Fed Trained Verifier and Exact Detector-Input Equivalence

**Research date:** 18 November 2026. **Experiment status:** five unit tests and the full 141-response pretrained-model run **passed** in GitHub Actions 44242421472. Measured results and limitations are recorded below. **Nature:** integration and falsification of source provenance and model inputs, not novel lossless compression, hallucination detection, or end-to-end retrieval.

## Hypothesis and prior work

Rounds 72–73 evaluated general NLI on original text, then independently proved that chosen evidence windows can be recovered from reversible storage. Round 76 evaluated an existing task-specific, RAGTruth-trained LettuceDetect detector on original material. This round tests whether the *actual trained model* receives identical detector inputs after byte-exact storage retrieval, and charges archive storage and read-path costs alongside inference.

This is not first-of-kind semantic grounding research. Relevant prior art includes RAGTruth (ACL 2024), LettuceDetect (2025, arXiv:2502.17125), evidence perturbation and grounding sensitivity research including GASP (2026, arXiv:2607.04223), and traditional content-addressed archive systems. The integration question is narrower and falsifiable.

## Frozen cohort and model

Use the R72/R73/R76 *unchanged* sample: exactly 8 QA and 16 Summary RAGTruth test source groups, 141 quality-good generated responses. Source ID digest must equal the existing lock. No human labels influence input construction. Original source bytes and annotations fetched under immutable RAGTruth Git SHA, original source/answer Git blob hashes checked. The detector is R76's pinned pretrained **KRLabsOrg/lettucedect-base-modernbert-en-v1**, HF snapshot SHA **0ff0f0dd23052cf751dae374f57a539aa092e772**, CPU environment and package **lettucedetect 0.2.3**. Its training includes RAGTruth. Original source texts, responses and weights are never redistributed.

## Controlled intervention

- Establish a benchmark-provided identity map from the 24 source IDs to source byte arrays. This is an **oracle identity from the dataset**. It is not a retrieved result, and source selection/index cost is absent.
- Store all 24 sources with **whole-source zlib6** and **gear512 content-defined CAS**, each with compact binary-zlib manifest using the existing R48 source-reader implementation.
- For QA, byte-recover the full passage source. For Summary, byte-recover the exact prefix encompassing the first 14,400 whitespace-separated words that R76 allows in its detector context. Compute the last word's UTF-8 byte position from the immutable original source. Preserve punctuation and Unicode.
- Recreate R76 passage chunks and question. Assert **exact Python string and question equivalence** between the original route and both archived routes *before* calling the model. Full-source archive readbacks plus every response-source read have manifest/source SHA-bound receipts and exact original byte checks.
- Run R76's exact pretrained detector twice per response: original source route and whole-archive route, alternating their call order across responses; score exact returned hallucination masks for equality. The gear512 route supplies exactly the same verified inputs and is therefore not separately inferred. This is *not* two independently trained models.
- Evaluate frozen human annotation response-level and character-level precision, recall, F1 and confusion, including the strict target excluding implicit_true. Compare against the prior R76 response confusion **TP14, FP16, FN17, TN94** as a cross-run consistency check; do not treat it as an independent test set.
- Record whole and gear512 persistent bytes, separately built *optional* FTS5 bytes (not queried), measured in-memory archive receipt wall time, logical compressed frame activation, uncompressed source prefix lengths, archive build time and paired CPU inference times.

## Primary promotion gates

1. Five regression tests pass, including Unicode prefix, exact QA passage/question, two real archive codec readbacks, cross-generation rejection and separate response/character scoring.
2. RAGTruth and model SHA-pinned identities and 141/24 cohort locks match prior rounds.
3. All 48 full-source readbacks and all 282 response-level compressed source receipts reproduce the original selected bytes; every archived detector context equals its original counterpart.
4. Per-response prediction masks from original and archived source must be exactly equal; any mismatch fails the experiment.
5. Compare measured cost with conventional whole-source archive and optional index overhead included. **No performance superiority is assumed or asserted without numbers.**
6. A new model's hallucination mitigation efficacy is **not** claimed: the experiment scores previously generated responses.

## Limits

Read-path wall time is Python warm-memory timing, not real cold SSD reads, physical I/O, OS cache persistence, journal recovery or transactional durability. Model weights, tokenizer/system RAM, temporary source RAM, model download, source update and durable reader-index maintenance are not counted in source archive bytes. The chosen source is supplied by dataset IDs. R76 context truncation can omit long-document evidence. CPU timing order effects remain, despite alternating evaluation order. Evidence provenance and faithful generation are distinct properties.

**Interpretation rule:** If byte-exact archive text yields identical model masks, that establishes correct composition of storage and *this* verifier, not improved hallucination detection. If one storage layout wins bytes on some source types but loses retained bytes or decompression CPU elsewhere, report the Pareto tradeoff rather than claim a universal architecture win.

## Reproduce

    python -W error::ResourceWarning -m unittest discover -s experiments/round-78 -p 'test_*.py' -v
    python experiments/round-78/archived_detector.py --out experiments/round-78/ci-results.json

Workflow: .github/workflows/cdg-archive-fed-detector.yml. Measured experiment executed successfully in GitHub Actions run 44242421472; see the measured results section.


## Measured results: exact-head run 44242421472

**[FACT] CI outcome:** all five dedicated synthetic regression tests passed; real pretrained CPU evaluation succeeded on the original frozen 141 responses from 24 QA/Summary source groups. Both archives returned 24 full sources, giving **48 full-document SHA-bound readbacks**, plus **282 response-specific exact prefix receipts**. All selected archived contexts matched the original source route exactly and **0/141 paired predicted character masks diverged**.

### Physical and memory read-path accounting

| Measurement | Whole-source Zlib6 + compact manifest | Gear512 CAS + compact manifest |
| --- | ---: | ---: |
| Persistent archive bytes | **28,398** | 35,437 |
| With optional separate FTS5 index | 102,126 | 109,165 |
| Mean logical compressed frame activation per response | **1,154.128 B** | 1,346.887 B |
| Mean warm-memory receipt time per response | 0.0621 ms | **0.0354 ms** |
| Median warm-memory receipt time per response | 0.0595 ms | **0.0292 ms** |

The optional FTS5 index is **73,728 B**, not used for selecting the known benchmark source IDs. Gear512 consumes **24.8% more persistent archive bytes** and **16.7% more logical compressed activation bytes** on the tested full/prefix source reads, but it has lower measured **warm Python receipt** latency. Do not equate receipt latency with cold SSD random I/O or decompression performance at scale.

### Detector and human-label outcomes

The archive-fed condition exactly reproduced the prior Round 76 response-level results, including **TP14, FP16, FN17, TN94**, precision **0.46667**, recall **0.45161**, response F1 **0.45902**, and false-positive rate **0.14545** on 141 responses.

Task separation: QA **TP6/FP3/FN4/TN32**, F1 **0.63158**; Summary **TP8/FP13/FN13/TN62**, F1 **0.38095**. The original and reconstructed source detector masks were identical for every response.

Measured cumulative CPU model inference was **134.895 seconds** for the original-source route and **134.744 seconds** for the archive-fed route. These are repeated in-process runs of the **same inputs** with alternating evaluation order, not independent two-model comparisons. The 0.151-second difference has no demonstrated causal significance and excludes archive read/build/index costs.

### Decision

**[FACT] PASS:** full SHA-byte provenance, task context equivalence and trained-model output identity from compressed sources were reproduced with measured storage and warm-memory costs.

**[INFERENCE]** Whole-source compression is the simpler and more space/traffic-efficient option for this small oracle-source workload; gear512 showed lower receipt CPU wall time. Neither layout is globally superior when considering the measured dimensions together.

**[NOT SHOWN]** Improved hallucination detection, lower actual SSD I/O, successful retrieval of the correct source, better answers, out-of-domain transfer, or end-to-end RAG latency advantage.

**Next falsifier:** test trained detector's evidence sensitivity under source perturbations (Round 79). That evaluates different semantic inputs and cannot reuse Round 78's exact-input invariance as an accuracy improvement.

**Provenance:** https://github.com/Satwik-P28/cdg-evidence-retrieval/actions/runs/44242421472 .
