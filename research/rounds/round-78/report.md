# CDG Round 78: Archive-Fed Trained Verifier and Exact Detector-Input Equivalence

**Research date:** 18 November 2026. **Experiment status:** code and pinned GitHub Actions run submitted; numerical outcomes must be taken from the current exact-head CI artifact. Do not promote this plan to a verified result before success. **Nature:** integration and falsification of source provenance and model inputs, not novel lossless compression, hallucination detection, or end-to-end retrieval.

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

Workflow: .github/workflows/cdg-archive-fed-detector.yml. Numeric results pending exact-head CI.
